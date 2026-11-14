"""`IgniApp`: its checks, its token, its calls to igni, and what it closes."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
import pytest

import igni_service.app as app_module
from igni_service import ConfigurationError, IgniApp, IgniUnavailable, MemoryKeyStore
from igni_service.app import AppId
from igni_service.testing import FakeIgni
from igni_service.urls import IgniPaths

from .answers import answer
from .conftest import ORG

PATH = IgniPaths.app_vm_profile("app-bot")


@pytest.fixture
async def app(fake: FakeIgni) -> IgniApp:
    return fake.app("app-bot", org_id=ORG, name="Bot")


class TestMakingOne:
    @pytest.mark.parametrize("app_id", ["", "   ", "\n\t"])
    def test_a_blank_app_id_is_refused(self, app_id: str) -> None:
        with pytest.raises(ConfigurationError, match="app id"):
            IgniApp(app_id, igni_server_url="https://igni.test", key_store=MemoryKeyStore())

    @pytest.mark.parametrize("url", ["", "  "])
    def test_a_blank_igni_server_url_is_refused(self, url: str) -> None:
        with pytest.raises(ConfigurationError, match="IGNI_SERVER_URL"):
            IgniApp("app-bot", igni_server_url=url, key_store=MemoryKeyStore())

    async def test_an_app_id_is_the_client_id(self) -> None:
        assert await AppId("app-bot").client_id() == "app-bot"

    def test_it_says_which_app_it_is(self, app: IgniApp) -> None:
        assert app.app_id == "app-bot"


class TestItsKey:
    async def test_the_key_is_made_on_first_use_and_kept_in_the_store(self) -> None:
        store = MemoryKeyStore()
        assert await store.get() is None
        app = IgniApp("app-bot", igni_server_url="https://igni.test", key_store=store)

        first = await app.public_jwks()
        kept = await store.get()
        second = await app.public_jwks()

        assert kept is not None and first.keys[0].kid == kept.kid
        assert second == first
        assert await app.thumbprint() == kept.kid
        await app.aclose()

    async def test_a_second_app_on_the_same_store_has_the_same_key(self) -> None:
        store = MemoryKeyStore()
        one = IgniApp("app-bot", igni_server_url="https://igni.test", key_store=store)
        two = IgniApp("app-bot", igni_server_url="https://igni.test", key_store=store)

        assert await one.thumbprint() == await two.thumbprint()
        await one.aclose()
        await two.aclose()


class TestItsToken:
    async def test_it_is_kept_until_sixty_seconds_before_it_expires(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        first = await app.token()

        fake.clock.advance(539)  # type: ignore[attr-defined]
        assert await app.token() == first
        assert fake.oauth.grants == ["client_credentials"]

        fake.clock.advance(1)  # type: ignore[attr-defined]
        renewed = await app.token()
        assert renewed != first
        assert fake.oauth.grants == ["client_credentials"] * 2

    async def test_callers_at_once_share_one_grant(
        self, fake: FakeIgni, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = fake.transport()

        class Slow(httpx.AsyncBaseTransport):
            """igni answering after a moment, so callers really are at once."""

            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                await asyncio.sleep(0.01)
                return await real.handle_async_request(request)

        monkeypatch.setattr(fake, "transport", Slow)
        busy = fake.app("app-busy", org_id=ORG)

        tokens = await asyncio.gather(*(busy.token() for _ in range(8)))

        assert len(set(tokens)) == 1
        assert fake.oauth.grants == ["client_credentials"]

    async def test_a_refused_grant_is_unavailable_and_the_next_call_asks_again(
        self, fake: FakeIgni
    ) -> None:
        stranger = fake.app("app-gone", org_id=ORG)
        registered = fake.clients.clients.pop("app-gone")

        for _ in range(2):
            with pytest.raises(IgniUnavailable, match="refused this app a token"):
                await stranger.token()

        fake.clients.clients["app-gone"] = registered
        assert await stranger.token()


class TestACall:
    async def test_it_goes_with_the_apps_token_and_its_json_body(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        response = await app.request("PUT", IgniPaths.app_vm_profile_request("app-bot"), json={})

        [seen] = fake.traffic.requests_to(IgniPaths.app_vm_profile_request("app-bot"))
        assert seen.method == "PUT" and seen.json_body() == {}
        assert seen.headers["authorization"] == f"Bearer {await app.token()}"
        assert response.status_code in (200, 201)

    async def test_without_json_no_body_is_sent(self, app: IgniApp, fake: FakeIgni) -> None:
        await app.request("GET", PATH)

        [seen] = fake.traffic.requests_to(PATH)
        assert seen.body == b"" and "content-type" not in seen.headers

    async def test_a_401_is_retried_once_with_a_new_token(
        self, app: IgniApp, fake: FakeIgni, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        refusals = [httpx.Response(401, json={"detail": "expired"})]
        answer(monkeypatch, PATH, lambda: refusals.pop() if refusals else None)

        response = await app.request("GET", PATH)

        assert response.status_code == 200
        assert fake.oauth.grants == ["client_credentials"] * 2, "the refused token was dropped"
        first, second = fake.traffic.requests_to(PATH)
        assert first.headers["authorization"] != second.headers["authorization"]

    async def test_a_second_401_is_unavailable_and_asks_no_third_time(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        fake.traffic.fail(PATH, 401)

        with pytest.raises(IgniUnavailable, match="refused this app's token"):
            await app.request("GET", PATH)

        assert len(fake.traffic.requests_to(PATH)) == 2

    @pytest.mark.parametrize("status", [403, 404, 500])
    async def test_any_other_status_is_given_back_as_it_is(
        self, app: IgniApp, fake: FakeIgni, status: int
    ) -> None:
        fake.traffic.fail(PATH, status)

        response = await app.request("GET", PATH)

        assert response.status_code == status
        assert len(fake.traffic.requests_to(PATH)) == 1

    async def test_a_network_error_is_unavailable_and_names_only_its_type(
        self, app: IgniApp, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def down() -> httpx.Response:
            raise httpx.ConnectError("secret-host.internal refused")

        answer(monkeypatch, PATH, down)

        with pytest.raises(IgniUnavailable) as raised:
            await app.request("GET", PATH)

        assert str(raised.value) == "could not reach igni server: ConnectError"

    async def test_a_timeout_is_unavailable_too(
        self, app: IgniApp, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def slow() -> httpx.Response:
            raise httpx.ReadTimeout("slow")

        answer(monkeypatch, PATH, slow)

        with pytest.raises(IgniUnavailable, match="ReadTimeout"):
            await app.request("GET", PATH)


class TestClosing:
    async def test_a_client_it_was_given_stays_open(self, fake: FakeIgni) -> None:
        client = fake.http_client()
        app = IgniApp(
            "app-bot",
            igni_server_url=fake.addresses.base_url,
            key_store=MemoryKeyStore(),
            http=client,
        )

        await app.aclose()

        assert not client.is_closed
        await client.aclose()

    async def test_a_client_it_made_itself_is_closed(self) -> None:
        app = IgniApp("app-bot", igni_server_url="https://igni.test", key_store=MemoryKeyStore())
        client = app.server.http

        await app.aclose()

        assert client.is_closed

    async def test_the_context_manager_closes_on_the_way_out_and_on_an_error(self) -> None:
        with pytest.raises(RuntimeError):
            async with IgniApp(
                "app-bot", igni_server_url="https://igni.test", key_store=MemoryKeyStore()
            ) as app:
                client = app.server.http
                raise RuntimeError("boom")

        assert client.is_closed


def test_every_method_the_docs_of_app_tell_a_reader_to_call_exists() -> None:
    """The module's own text names `app.something`: each must be a member of an `IgniApp`."""
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    app = IgniApp("app-bot", igni_server_url="https://igni.test", key_store=MemoryKeyStore())

    named = set(re.findall(r"\bapp\.(\w+)", source)) - {"py"}

    assert {"public_jwks", "vm_profile"} <= named
    assert sorted(name for name in named if not hasattr(app, name)) == []

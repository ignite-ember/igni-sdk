"""`app.vm_profile` when igni does not simply say yes: refusals, trouble, and answers that are not records."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from igni_service import IgniApp, IgniUnavailable, VmPackages, VmProfileRefused, VmProfileRequest
from igni_service.testing import FakeIgni
from igni_service.urls import IgniPaths

from .answers import answer
from .conftest import ORG

WANTED = VmProfileRequest(packages=VmPackages(apt=["chromium"]))
REQUEST_PATH = IgniPaths.app_vm_profile_request("app-bot")
PROFILE_PATH = IgniPaths.app_vm_profile("app-bot")

CALLS: dict[str, Callable[[IgniApp], object]] = {
    "request": lambda app: app.vm_profile.request(WANTED),
    "status": lambda app: app.vm_profile.status(),
    "effective": lambda app: app.vm_profile.effective(),
}
PATHS = {"request": REQUEST_PATH, "status": REQUEST_PATH, "effective": PROFILE_PATH}


@pytest.fixture
async def app(fake: FakeIgni) -> IgniApp:
    return fake.app("app-bot", org_id=ORG, name="Bot")


async def call(app: IgniApp, which: str) -> object:
    return await CALLS[which](app)  # type: ignore[misc]


@pytest.mark.parametrize("which", CALLS)
class TestWhateverIsAsked:
    @pytest.mark.parametrize("status", [400, 403, 422])
    async def test_a_4xx_is_a_refusal_in_igni_s_words(
        self, app: IgniApp, fake: FakeIgni, which: str, status: int
    ) -> None:
        fake.traffic.fail(PATHS[which], status)

        with pytest.raises(VmProfileRefused) as refused:
            await call(app, which)

        assert refused.value.status == status
        assert "failing on purpose" in str(refused.value)

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    async def test_busy_or_broken_igni_is_unavailable_and_not_a_refusal(
        self, app: IgniApp, fake: FakeIgni, which: str, status: int
    ) -> None:
        fake.traffic.fail(PATHS[which], status)

        with pytest.raises(IgniUnavailable, match=f"igni answered {status}") as raised:
            await call(app, which)

        assert not isinstance(raised.value, VmProfileRefused)

    @pytest.mark.parametrize(
        "reply",
        [
            lambda: httpx.Response(200, text="<html>nginx</html>"),
            lambda: httpx.Response(200, json=["a list"]),
            lambda: httpx.Response(200, json={"unexpected": True}),
        ],
        ids=["not-json", "wrong-shape", "missing-fields"],
    )
    async def test_a_200_that_is_not_the_record_is_unavailable(
        self,
        app: IgniApp,
        monkeypatch: pytest.MonkeyPatch,
        which: str,
        reply: Callable[[], httpx.Response],
    ) -> None:
        answer(monkeypatch, PATHS[which], reply)

        with pytest.raises(IgniUnavailable, match="something else"):
            await call(app, which)


class TestWhereTheStatusesDiffer:
    async def test_a_request_answered_201_is_taken_as_a_200_is(
        self, app: IgniApp, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record = await app.vm_profile.request(WANTED)
        answer(
            monkeypatch,
            REQUEST_PATH,
            lambda: httpx.Response(201, json=record.model_dump(mode="json")),
        )

        assert await app.vm_profile.request(WANTED) == record

    async def test_a_status_answered_201_is_not_a_record(
        self, app: IgniApp, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record = await app.vm_profile.request(WANTED)
        answer(
            monkeypatch,
            REQUEST_PATH,
            lambda: httpx.Response(201, json=record.model_dump(mode="json")),
        )

        with pytest.raises(IgniUnavailable, match="igni answered 201"):
            await app.vm_profile.status()

    async def test_a_404_on_status_is_never_asked_and_on_the_others_a_refusal(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        fake.traffic.fail(REQUEST_PATH, 404)
        fake.traffic.fail(PROFILE_PATH, 404)

        assert await app.vm_profile.status() is None
        for which in ("request", "effective"):
            with pytest.raises(VmProfileRefused) as refused:
                await call(app, which)
            assert refused.value.status == 404

    async def test_a_429_on_status_is_unavailable_and_not_never_asked(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        fake.traffic.fail(REQUEST_PATH, 429)

        with pytest.raises(IgniUnavailable, match="igni answered 429"):
            await app.vm_profile.status()

    async def test_a_refusal_carries_the_detail_igni_sent(
        self, app: IgniApp, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answer(
            monkeypatch,
            REQUEST_PATH,
            lambda: httpx.Response(400, json={"detail": "memory_mib is over the cap"}),
        )

        with pytest.raises(VmProfileRefused, match="memory_mib is over the cap"):
            await app.vm_profile.request(WANTED)

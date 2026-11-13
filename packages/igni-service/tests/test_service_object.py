"""`IgniService` itself: how it is built, what it puts on an app, how it shuts down."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from igni_service import (
    CallerKind,
    ConfigurationError,
    IgniService,
    IgniSettings,
    KeyCipher,
    MemoryKeyStore,
    Person,
)
from igni_service.cors import BearerCors
from igni_service.testing import FakeIgni, SettingsOverrides
from igni_service.tokens import IgniCall, TokenRefused
from igni_service.urls import IgniPaths
from igni_service.web_sessions import MemoryWebSessionStore

from .conftest import ORG, bearer

SERVICE = FakeIgni.SERVICE_URL


async def test_every_blank_setting_is_named_in_one_refusal() -> None:
    fake = FakeIgni()
    settings = fake.settings(
        SettingsOverrides(igni_server_url="  ", public_base_url="\t", service_name="")
    )

    with pytest.raises(ConfigurationError) as refused:
        fake.service(settings)

    for name in ("IGNI_SERVER_URL", "PUBLIC_BASE_URL", "SERVICE_NAME"):
        assert name in str(refused.value)


async def test_a_service_takes_people_only_unless_it_says_more(fake: FakeIgni) -> None:
    plain = IgniService(fake.settings(), key_store=MemoryKeyStore(), http=fake.http_client())
    assert plain.accepted_callers == frozenset({CallerKind.PERSON})
    with pytest.raises(TokenRefused):
        await plain.caller_of(fake.signer.app_token("reporter", org_id=ORG))
    assert fake.service().accepted_callers == frozenset({CallerKind.PERSON})
    both = fake.service(accepted_callers=[CallerKind.PERSON, CallerKind.APP])
    assert both.accepted_callers == frozenset({CallerKind.PERSON, CallerKind.APP})


async def test_the_web_sign_in_callback_comes_first_and_every_address_once(
    fake: FakeIgni,
) -> None:
    callback = f"{SERVICE}/auth/callback"
    settings = fake.settings(
        SettingsOverrides(redirect_uris=["https://b.test/cb", callback, "https://b.test/cb"])
    )

    await fake.service(settings).registration.register()

    [body] = [seen.json_body() for seen in fake.traffic.requests_to(IgniPaths.CLIENTS)]
    assert body["redirect_uris"] == [callback, "https://b.test/cb"]


async def test_the_sessions_of_a_service_given_no_store_are_kept_in_memory(
    fake: FakeIgni,
) -> None:
    assert isinstance(fake.service().web.store, MemoryWebSessionStore)


async def test_a_given_key_store_is_used_and_no_database_is_opened(fake: FakeIgni) -> None:
    store = MemoryKeyStore()

    igni = IgniService.from_settings(fake.settings(), key_store=store, http=fake.http_client())

    assert igni.key.store is store
    assert isinstance(igni.web.store, MemoryWebSessionStore)
    await igni.aclose()


async def test_closing_disposes_the_engine_the_service_made_and_may_be_repeated(
    tmp_path: Path,
) -> None:
    fake = FakeIgni()
    settings = fake.settings(
        SettingsOverrides(
            key_encryption_key=KeyCipher.generate(),
            key_database_url=f"sqlite+aiosqlite:///{tmp_path / 'k.db'}",
        )
    )
    igni = IgniService.from_settings(settings)
    engine: AsyncEngine = igni.key.store.engine  # type: ignore[attr-defined]
    await igni.thumbprint()
    pool = engine.pool

    await igni.aclose()

    assert engine.pool is not pool, "the engine's connections were disposed of"
    pool = engine.pool
    await igni.aclose()
    assert engine.pool is pool, "a second close disposes nothing again"


async def test_closing_closes_the_http_client_it_made_but_not_one_it_was_given(
    fake: FakeIgni,
) -> None:
    mine = IgniService(fake.settings(), key_store=MemoryKeyStore())
    first = mine.server.http
    await mine.aclose()
    assert first.is_closed

    given = fake.http_client()
    theirs = IgniService(fake.settings(), key_store=MemoryKeyStore(), http=given)
    await theirs.aclose()
    assert not given.is_closed
    await given.aclose()


async def test_leaving_the_lifespan_stops_the_background_tasks_even_mid_retry(
    fake: FakeIgni,
) -> None:
    igni = fake.service()
    fake.traffic.fail(IgniPaths.CLIENTS, 500)
    fake.traffic.fail(IgniPaths.TOKEN, 500)

    def ours() -> list[asyncio.Task[object]]:
        names = {"keep_trying", "run"}
        return [
            task
            for task in asyncio.all_tasks()
            if getattr(task.get_coro(), "__name__", "") in names and not task.done()
        ]

    async with igni.lifespan(None):
        await asyncio.sleep(0.05)
        assert len(ours()) == 2, "registration and revocations are both running"

    assert ours() == []


async def test_install_puts_igni_s_routes_sign_in_and_cors_on_the_app(igni: IgniService) -> None:
    app = FastAPI()

    igni.install(app)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://service.test"
    ) as http:
        subjects = await http.delete("/v1/igni/subjects/u-max")
        organisations = await http.delete(f"/v1/igni/organisations/{ORG}")
        sign_in = await http.get("/auth/callback")
    assert subjects.status_code == 401, "igni's route is there, and asks for igni's token"
    assert organisations.status_code == 401
    assert sign_in.status_code != 404, "the sign-in routes are there"
    assert [str(m.cls) for m in app.user_middleware] == [str(BearerCors)]


async def test_the_handlers_come_back_unchanged() -> None:
    igni = FakeIgni().service()

    async def erase(subject: object) -> None: ...
    async def export(subject: object) -> list[object]:
        return []

    async def deleted(org_id: str) -> None: ...

    assert igni.on_erase(erase) is erase
    assert igni.on_export(export) is export  # type: ignore[arg-type]
    assert igni.on_organisation_deleted(deleted) is deleted


async def test_the_router_is_built_once(igni: IgniService) -> None:
    assert igni.router is igni.router


async def test_a_host_is_for_the_one_organisation_it_was_made_for(igni: IgniService) -> None:
    assert igni.host(ORG).org_id == ORG
    assert igni.host("org-other").org_id == "org-other"


async def test_a_sent_token_that_is_refused_is_not_anonymous(fake: FakeIgni) -> None:
    igni = fake.service()
    app = FastAPI()

    @app.get("/maybe")
    async def maybe(person: Person | None = Depends(igni.optional_person)) -> dict[str, str]:
        return {"who": person.user_id if person else "nobody"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://service.test"
    ) as http:
        none = await http.get("/maybe")
        good = await http.get(
            "/maybe", headers=bearer(fake.signer.person_token("u-ada", org_id=ORG))
        )
        bad = await http.get("/maybe", headers=bearer("not-a-token"))

    assert none.json() == {"who": "nobody"}
    assert good.json() == {"who": "u-ada"}
    assert bad.status_code == 401
    assert bad.headers["www-authenticate"].startswith('Bearer error="invalid_token"')


@pytest.mark.parametrize("header", ["Basic dTpw", "Bearer", "Token abc", ""])
async def test_only_a_bearer_credential_is_a_token(http: httpx.AsyncClient, header: str) -> None:
    response = await http.get("/me", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not authenticated"}


async def test_the_scheme_is_read_without_regard_to_case(
    http: httpx.AsyncClient, fake: FakeIgni
) -> None:
    token = fake.signer.person_token("u-ada", org_id=ORG)

    response = await http.get("/me", headers={"Authorization": f"bEaReR {token}"})

    assert response.status_code == 200


async def test_a_caller_the_service_does_not_accept_is_a_401_over_http(fake: FakeIgni) -> None:
    igni = fake.service()
    app = FastAPI()

    @app.get("/who")
    async def who(caller: object = Depends(igni.caller)) -> dict[str, str]:
        return {"ok": "yes"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://service.test"
    ) as http:
        app_token = await http.get(
            "/who", headers=bearer(fake.signer.app_token("reporter", org_id=ORG))
        )
        person = await http.get(
            "/who", headers=bearer(fake.signer.person_token("u-ada", org_id=ORG))
        )

    assert app_token.status_code == 401
    assert person.status_code == 200


async def test_a_bare_token_outside_http_may_carry_its_scheme_or_not(
    igni: IgniService, fake: FakeIgni
) -> None:
    token = fake.signer.person_token("u-ada", org_id=ORG)

    assert (await igni.person_of(token)).user_id == "u-ada"
    assert (await igni.person_of(f"Bearer {token}")).user_id == "u-ada"
    assert (await igni.caller_of(f"Bearer {token}")).kind is CallerKind.PERSON
    with pytest.raises(TokenRefused):
        await igni.person_of("")


async def test_igni_calling_is_a_dependency_that_says_401_or_503(
    igni: IgniService, fake: FakeIgni
) -> None:
    app = FastAPI()

    @app.get("/from-igni")
    async def from_igni(call: IgniCall = Depends(igni.igni_call)) -> dict[str, str]:
        return {"org": call.org_id}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://service.test"
    ) as http:
        none = await http.get("/from-igni")
        person = await http.get(
            "/from-igni", headers=bearer(fake.signer.person_token("u-ada", org_id=ORG))
        )
        good = await http.get("/from-igni", headers=bearer(fake.signer.igni_token(ORG)))

    unreachable = FakeIgni()
    unreachable.traffic.fail(IgniPaths.JWKS, 500)
    away_service = unreachable.service()
    away_app = FastAPI()

    @away_app.get("/from-igni")
    async def from_away(call: IgniCall = Depends(away_service.igni_call)) -> dict[str, str]:
        return {"org": call.org_id}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=away_app), base_url="http://service.test"
    ) as http:
        away = await http.get("/from-igni", headers=bearer(unreachable.signer.igni_token(ORG)))

    assert none.status_code == 401
    assert person.status_code == 401
    assert good.json() == {"org": ORG}
    assert away.status_code == 503


def test_the_settings_are_the_ones_the_service_was_made_with() -> None:
    fake = FakeIgni()
    settings: IgniSettings = fake.settings()

    assert fake.service(settings).settings is settings

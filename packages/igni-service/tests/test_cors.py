"""Cross-origin calls from an extension's page: bearer routes only, never credentials."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.utils import get_dependant
from fastapi.security import HTTPBearer

from igni_service import Caller, CallerKind, IgniService, Person
from igni_service.cors import BearerRoutes
from igni_service.testing import FakeIgni, SpaceClaims

from .conftest import ORG, bearer

PAGE_ORIGIN = "http://127.0.0.1:4242"


class Members:
    """A service's own dependency, built on `igni.person`."""

    def __init__(self, igni: IgniService) -> None:
        self.igni = igni

    def member(self) -> Callable[..., Awaitable[Person]]:
        igni = self.igni

        async def member(person: Person = Depends(igni.person)) -> Person:
            return person

        return member


@pytest.fixture
def cors_app(igni: IgniService) -> FastAPI:
    app = FastAPI()
    igni.install(app)
    members = Members(igni).member()

    @app.get("/v1/notes")
    async def notes(person: Person = Depends(igni.person)) -> dict[str, str]:
        return {"user": person.user_id}

    @app.post("/v1/notes")
    async def add(person: Person = Depends(igni.org_admin)) -> dict[str, str]:
        return {"user": person.user_id}

    gated = APIRouter(dependencies=[Depends(members)])

    @gated.get("/v1/gated")
    async def gated_route() -> dict[str, str]:
        return {"ok": "yes"}

    app.include_router(gated)

    @app.get("/v1/public")
    async def public(person: Person | None = Depends(igni.optional_person)) -> dict[str, str]:
        return {"reader": person.user_id if person else ""}

    @app.get("/v1/bare")
    async def bare(token: str = Depends(igni.token)) -> dict[str, str]:
        person = await igni.person_of(token)
        return {"user": person.user_id}

    @app.get("/v1/maybe")
    async def maybe(token: str | None = Depends(igni.optional_token)) -> dict[str, bool]:
        return {"token": token is not None}

    @app.get("/settings")
    async def settings(person: Person = Depends(igni.web.person)) -> dict[str, str]:
        return {"user": person.user_id}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"ok": "yes"}

    return app


@pytest.fixture
async def page(cors_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=cors_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://service.test", headers={"Origin": PAGE_ORIGIN}
    ) as client:
        yield client


def preflight(method: str, headers: str = "authorization") -> dict[str, str]:
    return {"Access-Control-Request-Method": method, "Access-Control-Request-Headers": headers}


async def test_a_bearer_route_answers_a_preflight_for_any_origin(page: httpx.AsyncClient) -> None:
    response = await page.options(
        "/v1/notes", headers=preflight("POST", "authorization,content-type")
    )
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["access-control-allow-methods"] == "DELETE, GET, HEAD, PATCH, POST, PUT"
    assert response.headers["access-control-allow-headers"] == "Authorization, Content-Type"
    assert "access-control-allow-credentials" not in response.headers


async def test_a_call_with_a_token_is_readable_cross_origin(
    page: httpx.AsyncClient, fake: FakeIgni
) -> None:
    token = fake.signer.person_token("u-max", org_id=ORG)
    response = await page.get("/v1/notes", headers=bearer(token))
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers


async def test_a_refused_token_is_readable_so_the_page_can_fetch_a_new_one(
    page: httpx.AsyncClient,
) -> None:
    response = await page.get("/v1/notes", headers=bearer("not-a-token"))
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "*"


async def test_the_services_own_dependency_on_igni_person_counts(
    page: httpx.AsyncClient, fake: FakeIgni
) -> None:
    assert (await page.options("/v1/gated", headers=preflight("GET"))).status_code == 204
    token = fake.signer.person_token("u-max", org_id=ORG)
    response = await page.get("/v1/gated", headers=bearer(token))
    assert response.headers["access-control-allow-origin"] == "*"


async def test_optional_person_routes_are_bearer_routes(page: httpx.AsyncClient) -> None:
    assert (await page.options("/v1/public", headers=preflight("GET"))).status_code == 204


async def test_a_call_without_a_token_gets_no_yes(page: httpx.AsyncClient) -> None:
    response = await page.get("/v1/public")
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_a_preflight_without_authorization_is_refused(page: httpx.AsyncClient) -> None:
    response = await page.options("/v1/notes", headers=preflight("GET", "content-type"))
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


async def test_a_preflight_for_another_header_is_refused(page: httpx.AsyncClient) -> None:
    response = await page.options("/v1/notes", headers=preflight("GET", "authorization,x-other"))
    assert response.status_code == 403


async def test_a_preflight_for_another_method_is_refused(page: httpx.AsyncClient) -> None:
    response = await page.options("/v1/notes", headers=preflight("TRACE"))
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/settings", "/health", "/nowhere"])
async def test_the_answer_from_a_cookie_or_open_route_stays_unreadable(
    page: httpx.AsyncClient, fake: FakeIgni, path: str
) -> None:
    token = fake.signer.person_token("u-max", org_id=ORG)
    called = await page.get(path, headers=bearer(token))
    assert "access-control-allow-origin" not in called.headers


@pytest.mark.parametrize(
    "path", ["/auth/logout", "/v1/igni/subjects/erase", "/v1/igni/organisations/x"]
)
async def test_sign_in_and_igni_calls_get_no_preflight_yes(
    page: httpx.AsyncClient, path: str
) -> None:
    response = await page.options(path, headers=preflight("POST"))
    assert "access-control-allow-origin" not in response.headers


async def test_igni_calls_answer_are_unreadable(page: httpx.AsyncClient, fake: FakeIgni) -> None:
    response = await page.post("/v1/igni/subjects/erase", headers=bearer("anything"), json={})
    assert "access-control-allow-origin" not in response.headers


async def test_a_same_origin_call_is_untouched(fake: FakeIgni, cors_app: FastAPI) -> None:
    token = fake.signer.person_token("u-max", org_id=ORG)
    transport = httpx.ASGITransport(app=cors_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://service.test") as client:
        response = await client.get("/v1/notes", headers=bearer(token))
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("path", ["/v1/bare", "/v1/maybe"])
async def test_a_route_holding_the_bare_token_is_a_bearer_route(
    page: httpx.AsyncClient, fake: FakeIgni, path: str
) -> None:
    token = fake.signer.person_token("u-max", org_id=ORG)
    response = await page.get(path, headers=bearer(token))
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


async def test_the_bare_token_is_required_by_igni_token(page: httpx.AsyncClient) -> None:
    assert (await page.get("/v1/bare")).status_code == 401
    assert (await page.get("/v1/maybe")).json() == {"token": False}


# ── Routes on `igni.caller`: a person's, an app's or a space's token ──


class Owners:
    """A service's own dependency built on `igni.caller`, and one built on that."""

    def __init__(self, igni: IgniService) -> None:
        self.igni = igni

    def caller_org(self) -> Callable[..., Awaitable[str]]:
        igni = self.igni

        async def caller_org(caller: Caller = Depends(igni.caller)) -> str:
            return caller.org_id

        return caller_org

    def owner(self) -> Callable[..., Awaitable[str]]:
        caller_org = self.caller_org()

        async def owner(org_id: str = Depends(caller_org)) -> str:
            return f"owner in {org_id}"

        return owner


@pytest.fixture
async def callers_page(fake: FakeIgni) -> AsyncIterator[httpx.AsyncClient]:
    igni = fake.service(accepted_callers=frozenset(CallerKind))
    app = FastAPI()
    igni.install(app)
    owners = Owners(igni)

    @app.get("/v1/who")
    async def who(caller: Caller = Depends(igni.caller)) -> dict[str, str]:
        return {"kind": caller.kind.value}

    by_router = APIRouter(dependencies=[Depends(igni.caller)])

    @by_router.get("/v1/by-router")
    async def by_router_route() -> dict[str, str]:
        return {"ok": "yes"}

    app.include_router(by_router)

    @app.get("/v1/nested")
    async def nested(owner: str = Depends(owners.owner())) -> dict[str, str]:
        return {"owner": owner}

    @app.get("/v1/caller-and-cookie")
    async def caller_and_cookie(
        caller: Caller = Depends(igni.caller), person: Person = Depends(igni.web.person)
    ) -> dict[str, str]:
        return {"kind": caller.kind.value}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://service.test", headers={"Origin": PAGE_ORIGIN}
    ) as client:
        yield client


CALLER_TOKENS: dict[str, Callable[[FakeIgni], str]] = {
    "person": lambda f: f.signer.person_token("u-max", org_id=ORG),
    "app": lambda f: f.signer.app_token("reporter", org_id=ORG),
    "space": lambda f: f.signer.space_token(
        "sp-1", SpaceClaims(org=ORG, app="reporter", external_id="cust-9")
    ),
}


@pytest.mark.parametrize("kind", list(CALLER_TOKENS))
async def test_a_caller_route_is_readable_cross_origin_for_each_kind(
    callers_page: httpx.AsyncClient, fake: FakeIgni, kind: str
) -> None:
    response = await callers_page.get("/v1/who", headers=bearer(CALLER_TOKENS[kind](fake)))
    assert response.status_code == 200
    assert response.json() == {"kind": kind}
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize("path", ["/v1/who", "/v1/by-router", "/v1/nested"])
async def test_a_caller_route_answers_a_preflight_that_carries_authorization(
    callers_page: httpx.AsyncClient, path: str
) -> None:
    allowed = await callers_page.options(path, headers=preflight("GET"))
    assert allowed.status_code == 204
    assert allowed.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in allowed.headers
    refused = await callers_page.options(path, headers=preflight("GET", "content-type"))
    assert refused.status_code == 403
    assert "access-control-allow-origin" not in refused.headers


@pytest.mark.parametrize("path", ["/v1/by-router", "/v1/nested"])
async def test_igni_caller_counts_through_a_router_and_a_nested_dependency(
    callers_page: httpx.AsyncClient, fake: FakeIgni, path: str
) -> None:
    response = await callers_page.get(path, headers=bearer(CALLER_TOKENS["app"](fake)))
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


async def test_a_refused_caller_token_is_readable(callers_page: httpx.AsyncClient) -> None:
    response = await callers_page.get("/v1/nested", headers=bearer("not-a-token"))
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "*"


async def test_a_caller_route_called_without_a_token_gets_no_yes(
    callers_page: httpx.AsyncClient,
) -> None:
    response = await callers_page.get("/v1/who")
    assert response.status_code == 401
    assert "access-control-allow-origin" not in response.headers


async def test_a_caller_route_that_also_reads_the_cookie_gets_no_yes(
    callers_page: httpx.AsyncClient, fake: FakeIgni
) -> None:
    response = await callers_page.get(
        "/v1/caller-and-cookie", headers=bearer(CALLER_TOKENS["person"](fake))
    )
    assert "access-control-allow-origin" not in response.headers


def test_every_igni_dependency_that_reads_a_bearer_token_is_classified(
    igni: IgniService,
) -> None:
    """A new bearer dependency on `IgniService` must be judged, not forgotten:
    left out of both lists, the extension's page could not call its routes."""
    reading_bearer = set()
    for name in dir(type(igni)):
        member = getattr(igni, name)
        if name.startswith("_") or not callable(member) or isinstance(member, type):
            continue
        try:
            dependant = get_dependant(path="/", call=member)
        except Exception:  # noqa: BLE001, S112 — not a FastAPI dependency
            continue
        if any(isinstance(sub.call, HTTPBearer) for sub in dependant.dependencies):
            reading_bearer.add(name)
    assert reading_bearer == {*BearerRoutes.DEPENDENCIES, *BearerRoutes.NOT_THE_PAGES}

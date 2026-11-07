"""What the fake answers on each route family before any handler runs.

Pinned so the fake's router answers as it did when it was an if-chain:
authentication before the method, and an authenticated path no handler
takes answered by the directory.
"""

from __future__ import annotations

import pytest

from igni_service import IgniService
from igni_service.crypto import RsaKeyPair
from igni_service.testing import FakeIgni
from igni_service.testing_bearers import BearerTokens, TokenHolder
from igni_service.testing_clients import FakeClientRegistry
from igni_service.testing_router import RouteGuard
from igni_service.testing_routes import RouteAuth
from igni_service.testing_wire import DetailError, SeenRequest
from igni_service.urls import IgniPaths

from .conftest import ORG, bearer

NOT_FOUND = {"detail": "Not Found"}
NOT_AUTHENTICATED = {"detail": "Not authenticated"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"{IgniPaths.DIRECTORY}/members"),
        ("POST", IgniPaths.NOTIFICATIONS),
        ("POST", IgniPaths.SERVICE_EVENTS),
        ("GET", IgniPaths.service_event("ev-1")),
        ("POST", IgniPaths.SERVICE_ITEMS),
        ("POST", IgniPaths.SERVICE_ATTACHMENTS),
        ("GET", IgniPaths.REVOCATIONS),
        ("GET", IgniPaths.SERVED),
        ("GET", IgniPaths.SERVICE_VM_PROFILE),
        ("GET", IgniPaths.app_vm_profile("app-1")),
    ],
)
async def test_every_authenticated_family_refuses_no_token(
    fake: FakeIgni, method: str, path: str
) -> None:
    async with fake.http_client() as http:
        response = await http.request(method, f"{FakeIgni.BASE}{path}")

    assert (response.status_code, response.json()) == (401, NOT_AUTHENTICATED)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/nothing-here"),
        ("GET", IgniPaths.CLIENTS),
        ("GET", f"{IgniPaths.CLIENTS}/c-1/other"),
    ],
)
async def test_a_path_nobody_serves_is_not_found(fake: FakeIgni, method: str, path: str) -> None:
    async with fake.http_client() as http:
        response = await http.request(method, f"{FakeIgni.BASE}{path}")

    assert (response.status_code, response.json()) == (404, NOT_FOUND)


@pytest.mark.parametrize(
    ("method", "path", "status", "body"),
    [
        ("GET", IgniPaths.SERVICE_EVENTS, 404, NOT_FOUND),
        ("GET", f"{IgniPaths.DIRECTORY}/nothing", 404, NOT_FOUND),
        (
            "GET",
            f"{IgniPaths.DIRECTORY}/people/u-nobody",
            404,
            {"detail": "Not a member of this organisation"},
        ),
    ],
)
async def test_an_authenticated_path_no_handler_takes_is_the_directorys(
    igni: IgniService,
    fake: FakeIgni,
    method: str,
    path: str,
    status: int,
    body: dict[str, str],
) -> None:
    token = await igni.tokens.token(ORG)
    async with fake.http_client() as http:
        response = await http.request(method, f"{FakeIgni.BASE}{path}", headers=bearer(token))

    assert (response.status_code, response.json()) == (status, body)


async def test_an_organisation_the_directory_lacks_is_said(
    igni: IgniService, fake: FakeIgni
) -> None:
    token = await igni.tokens.token("org-nowhere")
    async with fake.http_client() as http:
        response = await http.get(
            f"{FakeIgni.BASE}{IgniPaths.SERVICE_EVENTS}", headers=bearer(token)
        )

    assert (response.status_code, response.json()) == (404, {"detail": "no such organisation"})


async def test_the_token_endpoints_refuse_a_request_with_no_assertion(fake: FakeIgni) -> None:
    async with fake.http_client() as http:
        token = await http.post(f"{FakeIgni.BASE}{IgniPaths.TOKEN}", data={"grant_type": "x"})
        revoke = await http.post(f"{FakeIgni.BASE}{IgniPaths.REVOKE}", data={"token": "x"})

    assert (token.status_code, token.json()) == (400, {"error": "invalid_request"})
    assert (revoke.status_code, revoke.json()) == (401, {"error": "invalid_client"})


async def test_an_app_route_needs_the_apps_own_token(fake: FakeIgni) -> None:
    async with fake.http_client() as http:
        response = await http.get(f"{FakeIgni.BASE}{IgniPaths.APPS}/app-1")

    assert (response.status_code, response.json()) == (401, NOT_AUTHENTICATED)


async def test_nothing_uploaded_is_said(fake: FakeIgni) -> None:
    async with fake.http_client() as http:
        response = await http.get(f"{FakeIgni.BASE}{IgniPaths.extension('c-1')}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Nothing uploaded for this client"}


def test_an_apps_token_is_not_a_services() -> None:
    clients = FakeClientRegistry()
    clients.add_app("app-1", ORG, "Bot", RsaKeyPair.generate())
    bearers = BearerTokens()
    token = bearers.issue_app(TokenHolder(client_id="app-1", org_id=ORG))
    headers = {"authorization": f"Bearer {token}"}
    seen = SeenRequest(method="GET", path="/", headers=headers, body=b"")
    guard = RouteGuard(bearers, clients)

    assert guard.holder_for(seen, RouteAuth.SERVICE) == DetailError.not_authenticated()
    assert guard.holder_for(seen, RouteAuth.APP) == TokenHolder(client_id="app-1", org_id=ORG)

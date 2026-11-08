"""What the fake answers on each route family before any handler runs.

Pinned so the fake's router answers as it did when it was an if-chain:
authentication before the method, and an authenticated path no handler
takes answered by the directory.
"""

from __future__ import annotations

import httpx
import pytest

from igni_service import IgniService
from igni_service.crypto import RsaKeyPair
from igni_service.testing import FakeIgni, SettingsOverrides
from igni_service.testing_bearers import BearerTokens, TokenHolder
from igni_service.testing_bundles import UploadedManifest
from igni_service.testing_clients import FakeClientRegistry
from igni_service.testing_router import RouteGuard, RouteTable
from igni_service.testing_routes import Handler, Route, RouteAuth
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


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"{IgniPaths.DIRECTORY}/members"),
        ("GET", IgniPaths.app_vm_profile("app-1")),
        ("GET", "/v1/nothing-here"),
    ],
)
async def test_a_failure_a_test_asked_for_answers_before_the_token_or_the_path_is_looked_at(
    fake: FakeIgni, method: str, path: str
) -> None:
    fake.traffic.fail(path, 503)

    async with fake.http_client() as http:
        response = await http.request(method, f"{FakeIgni.BASE}{path}")

    assert (response.status_code, response.json()) == (503, {"detail": "failing on purpose"})
    assert [seen.path for seen in fake.traffic.seen] == [path]


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


async def test_an_address_that_is_not_the_fakes_is_never_reached(fake: FakeIgni) -> None:
    async with fake.http_client() as http:
        with pytest.raises(httpx.ConnectError, match=r"^igni\.test:8080 is not igni$"):
            await http.get(f"http://igni.test:8080{IgniPaths.JWKS}")

    assert fake.traffic.seen == []


def test_a_bundle_without_a_manifest_is_refused_in_igni_s_words() -> None:
    refused = UploadedManifest.from_archive(b"not a tarball")

    assert refused == DetailError(detail="no manifest.json at the bundle's root")


@pytest.mark.parametrize(
    ("path", "query", "said"),
    [
        (IgniPaths.REVOCATIONS, {"since": "yesterday"}, "since must be a cursor, not 'yesterday'"),
        (
            f"{IgniPaths.DIRECTORY}/members",
            {"limit": "many"},
            "limit must be a whole number, not 'many'",
        ),
    ],
)
async def test_a_query_igni_cannot_read_is_a_422_not_a_crash(
    igni: IgniService, fake: FakeIgni, path: str, query: dict[str, str], said: str
) -> None:
    token = await igni.tokens.token(ORG)
    async with fake.http_client() as http:
        response = await http.get(f"{FakeIgni.BASE}{path}", params=query, headers=bearer(token))

    assert (response.status_code, response.json()) == (422, {"detail": said})


def test_a_setting_igni_settings_lacks_is_refused_not_ignored() -> None:
    with pytest.raises(ValueError, match="no_such_setting"):
        SettingsOverrides.model_validate({"no_such_setting": "x"})


def test_the_fakes_router_answers_its_requests_and_the_fake_has_no_handle_of_its_own(
    fake: FakeIgni,
) -> None:
    request = httpx.Request("GET", f"{FakeIgni.BASE}{IgniPaths.JWKS}")

    response = fake.router.handle(request)

    assert response.status_code == 200 and response.json()["keys"]
    assert [seen.path for seen in fake.traffic.seen] == [IgniPaths.JWKS]
    # The pipeline is `fake.router`; `FakeIgni.handle` is gone, deliberately.
    assert not hasattr(fake, "handle")


async def test_after_a_reset_the_router_still_records_into_the_fakes_traffic(
    fake: FakeIgni,
) -> None:
    fake.traffic.fail(IgniPaths.JWKS, 503)
    fake.reset()

    async with fake.http_client() as http:
        response = await http.get(f"{FakeIgni.BASE}{IgniPaths.JWKS}")

    assert response.status_code == 200
    assert [seen.path for seen in fake.traffic.seen] == [IgniPaths.JWKS]


async def test_a_revoked_services_token_is_not_authenticated(
    igni: IgniService, fake: FakeIgni
) -> None:
    token = await igni.tokens.token(ORG)
    fake.clients.revoke()

    async with fake.http_client() as http:
        response = await http.get(
            f"{FakeIgni.BASE}{IgniPaths.DIRECTORY}/members", headers=bearer(token)
        )

    assert (response.status_code, response.json()) == (401, NOT_AUTHENTICATED)


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", IgniPaths.REVOCATIONS, 200),
        ("GET", IgniPaths.SERVED, 200),
        ("POST", IgniPaths.NOTIFICATIONS, 401),
        ("GET", f"{IgniPaths.DIRECTORY}/members", 401),
        ("GET", IgniPaths.SERVICE_VM_PROFILE, 401),
    ],
)
async def test_a_token_for_no_organisation_reaches_only_revocations_and_served(
    igni: IgniService, fake: FakeIgni, method: str, path: str, status: int
) -> None:
    await igni.tokens.token(ORG)
    client_id = await igni.registration.client_id()
    token = fake.oauth.bearers.issue_service(TokenHolder(client_id=client_id), "service")

    async with fake.http_client() as http:
        response = await http.request(method, f"{FakeIgni.BASE}{path}", headers=bearer(token))

    assert response.status_code == status
    if status == 401:
        assert response.json() == NOT_AUTHENTICATED


def _app_token(fake: FakeIgni, app_id: str) -> dict[str, str]:
    fake.clients.add_app(app_id, ORG, "Bot", RsaKeyPair.generate())
    return bearer(fake.oauth.bearers.issue_app(TokenHolder(client_id=app_id, org_id=ORG)))


@pytest.mark.parametrize(
    ("method", "path", "status", "body"),
    [
        ("GET", f"{IgniPaths.APPS}/app-1", 404, NOT_FOUND),
        ("GET", f"{IgniPaths.APPS}/app-1/vm-profile/extra", 404, NOT_FOUND),
        ("DELETE", IgniPaths.app_vm_profile("app-1"), 404, NOT_FOUND),
        ("GET", f"{IgniPaths.APPS}/app-1/nothing", 404, NOT_FOUND),
        (
            "GET",
            IgniPaths.app_vm_profile("app-other"),
            403,
            {"detail": "Only the app itself asks for its VM"},
        ),
    ],
)
async def test_an_app_path_igni_does_not_serve_the_app_is_refused(
    fake: FakeIgni, method: str, path: str, status: int, body: dict[str, str]
) -> None:
    headers = _app_token(fake, "app-1")

    async with fake.http_client() as http:
        response = await http.request(method, f"{FakeIgni.BASE}{path}", headers=headers)

    assert (response.status_code, response.json()) == (status, body)


def test_the_first_route_serving_a_path_says_its_token_the_first_taking_it_answers() -> None:
    def answer(status: int) -> Handler:
        return lambda call: httpx.Response(status)

    guarded = Route(path="/v1/x", method="GET", auth=RouteAuth.SERVICE, handler=answer(200))
    open_post = Route(path="/v1/x", method="POST", handler=answer(201))
    shadowed = Route(path="/v1/x", method="POST", handler=answer(202))
    table = RouteTable(routes=(guarded, open_post, shadowed), fallback=answer(404))
    post = SeenRequest(method="POST", path="/v1/x", headers={}, body=b"")

    assert table.family("/v1/x") is guarded
    assert table.route(post) is open_post
    assert table.family("/v1/y") is None


@pytest.mark.parametrize(
    ("error", "status", "body"),
    [
        (DetailError.not_found(), 404, NOT_FOUND),
        (DetailError.not_authenticated(), 401, NOT_AUTHENTICATED),
        (DetailError(detail="no"), 400, {"detail": "no"}),
    ],
)
def test_igni_s_error_body_carries_its_detail_and_not_its_status(
    error: DetailError, status: int, body: dict[str, str]
) -> None:
    response = error.to_response()

    assert (response.status_code, response.json()) == (status, body)

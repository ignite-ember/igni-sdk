"""The route table's pieces at their edges: what a route serves and takes, an app's path, and whose VM is asked about."""

from __future__ import annotations

import httpx
import pytest

from igni_service.crypto import RsaKeyPair
from igni_service.testing import FakeIgni
from igni_service.testing_bearers import TokenHolder
from igni_service.testing_clients import FakeClientRegistry
from igni_service.testing_router import RouteTable
from igni_service.testing_routes import AppPath, Route, RouteAuth, VmProfileRoutes
from igni_service.testing_wire import RoutedCall, SeenRequest
from igni_service.urls import IgniPaths

from .conftest import ORG


def seen(method: str, path: str) -> SeenRequest:
    return SeenRequest(method=method, path=path, headers={}, body=b"{}")


def answer(call: RoutedCall) -> httpx.Response:
    return httpx.Response(204)


def test_only_the_two_service_kinds_are_service_tokens() -> None:
    assert {auth: auth.is_service for auth in RouteAuth} == {
        RouteAuth.NONE: False,
        RouteAuth.SERVICE: True,
        RouteAuth.SERVICE_ANY_ORG: True,
        RouteAuth.APP: False,
    }
    assert [auth.value for auth in RouteAuth] == ["none", "service", "service_any_org", "app"]


def test_a_route_serves_its_exact_path_or_what_starts_with_it_as_a_prefix() -> None:
    exact = Route(path="/v1/x", handler=answer)
    prefix = Route(path="/v1/x", prefix=True, handler=answer)

    assert exact.serves("/v1/x") and not exact.serves("/v1/x/y") and not exact.serves("/v1/")
    assert prefix.serves("/v1/x") and prefix.serves("/v1/x/y") and prefix.serves("/v1/xy")
    assert not prefix.serves("/v1/")


def test_a_route_takes_its_method_or_any_when_it_names_none() -> None:
    anything = Route(path="/v1/x", handler=answer)
    only_get = Route(path="/v1/x", method="GET", handler=answer)

    assert anything.takes(seen("DELETE", "/v1/x")) and anything.takes(seen("GET", "/v1/x"))
    assert only_get.takes(seen("GET", "/v1/x"))
    assert not only_get.takes(seen("POST", "/v1/x"))
    assert not only_get.takes(seen("get", "/v1/x")), "methods are as sent"
    assert not only_get.takes(seen("GET", "/v1/y"))


def test_a_route_table_is_frozen() -> None:
    table = RouteTable(routes=(), fallback=answer)

    with pytest.raises(ValueError, match="frozen"):
        table.routes = (Route(path="/", handler=answer),)


@pytest.mark.parametrize(
    ("path", "parsed"),
    [
        (f"{IgniPaths.APPS}/app-1/vm-profile", ("app-1", "vm-profile")),
        (f"{IgniPaths.APPS}/app-1/", ("app-1", "")),
        (f"{IgniPaths.APPS}/app-1", None),
        (f"{IgniPaths.APPS}/app-1/vm-profile/extra", None),
        (f"{IgniPaths.APPS}/app-1/vm-profile/", None),
        (f"{IgniPaths.APPS}/", None),
        (IgniPaths.APPS, None),
    ],
)
def test_an_app_path_is_an_id_and_one_thing_asked_of_it(
    path: str, parsed: tuple[str, str] | None
) -> None:
    result = AppPath.parse(path)

    assert (result and (result.app_id, result.what)) == parsed


def app_call(app_id: str, method: str, path: str, body: bytes = b"{}") -> RoutedCall:
    return RoutedCall(
        seen=SeenRequest(method=method, path=path, headers={}, body=body),
        holder=TokenHolder(client_id=app_id, org_id=ORG),
    )


def test_an_app_asks_for_its_own_vm_and_no_other_apps(fake: FakeIgni) -> None:
    routes = VmProfileRoutes(fake.vm_profiles, fake.clients, fake.extensions)

    other = routes.app(app_call("app-1", "GET", IgniPaths.app_vm_profile("app-2")))
    own = routes.app(app_call("app-1", "GET", IgniPaths.app_vm_profile("app-1")))

    assert (other.status_code, other.json()) == (
        403,
        {"detail": "Only the app itself asks for its VM"},
    )
    assert own.status_code == 200


def test_an_app_request_is_filed_under_its_registered_name_or_else_its_id(
    fake: FakeIgni,
) -> None:
    fake.clients.add_app("app-known", ORG, "Known Bot", RsaKeyPair.generate())
    routes = VmProfileRoutes(fake.vm_profiles, fake.clients, fake.extensions)
    unregistered = VmProfileRoutes(fake.vm_profiles, FakeClientRegistry(), fake.extensions)
    put = f"{IgniPaths.APPS}/{{}}/vm-profile-request"

    assert routes.app(app_call("app-known", "PUT", put.format("app-known"))).status_code == 201
    assert unregistered.app(app_call("app-lost", "PUT", put.format("app-lost"))).status_code == 201

    names = {key[2]: record.subject.name for key, record in fake.vm_profiles.requests.items()}
    assert names == {"app-known": "Known Bot", "app-lost": "app-lost"}


def test_an_app_route_answers_only_the_methods_it_has_for_each_thing(fake: FakeIgni) -> None:
    routes = VmProfileRoutes(fake.vm_profiles, fake.clients, fake.extensions)
    base = f"{IgniPaths.APPS}/app-1"

    def status(method: str, what: str) -> int:
        return routes.app(app_call("app-1", method, f"{base}/{what}")).status_code

    assert status("GET", "vm-profile") == 200
    assert status("PUT", "vm-profile") == 404
    assert status("DELETE", "vm-profile-request") == 404
    assert status("GET", "vm-profile-request") == 404, "asked for none yet"
    assert routes.app(app_call("app-1", "GET", base)).status_code == 404


async def test_a_path_served_for_another_method_only_is_not_found_without_a_token(
    fake: FakeIgni,
) -> None:
    async with fake.http_client() as http:
        response = await http.put(f"{FakeIgni.BASE}{IgniPaths.CLIENTS}")

    assert (response.status_code, response.json()) == (404, {"detail": "Not Found"})

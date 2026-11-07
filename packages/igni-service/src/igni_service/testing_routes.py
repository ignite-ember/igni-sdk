"""How the fake routes a request: one `Route` per path, and the glue to two collaborators.

A `Route` names a path (exact, or a prefix), the method it takes (any,
when `None`), the token it needs (`RouteAuth`) and the bound method that
answers it. `AgentRoutes` and `VmProfileRoutes` adapt `FakeAgents` and
`FakeVmProfiles`, which answer from plain arguments, to a `RoutedCall`.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

import httpx
from pydantic import BaseModel, ConfigDict

from igni_service.testing_clients import FakeClientRegistry
from igni_service.testing_extensions import FakeExtensionStore
from igni_service.testing_items import FakeAgents
from igni_service.testing_vm_profiles import FakeVmProfiles
from igni_service.testing_wire import DetailError, RoutedCall, SeenRequest
from igni_service.urls import IgniPaths

Handler = Callable[[RoutedCall], httpx.Response]


class RouteAuth(StrEnum):
    """The token a route needs."""

    NONE = "none"
    #: A service token for one organisation.
    SERVICE = "service"
    #: A service token, for one organisation or for none (revocations, served).
    SERVICE_ANY_ORG = "service_any_org"
    #: An app's own token.
    APP = "app"

    @property
    def is_service(self) -> bool:
        return self in (RouteAuth.SERVICE, RouteAuth.SERVICE_ANY_ORG)


class Route(BaseModel):
    """One path the fake serves, and what answers it."""

    model_config = ConfigDict(frozen=True)

    path: str
    #: Whether `path` is a prefix rather than the whole path.
    prefix: bool = False
    #: The method it takes; `None` for any.
    method: str | None = None
    auth: RouteAuth = RouteAuth.NONE
    handler: Handler

    def serves(self, path: str) -> bool:
        return path.startswith(self.path) if self.prefix else path == self.path

    def takes(self, seen: SeenRequest) -> bool:
        return self.serves(seen.path) and self.method in (None, seen.method)


class AppPath(BaseModel):
    """`/v1/apps/{app_id}/{what}`."""

    app_id: str
    what: str

    @classmethod
    def parse(cls, path: str) -> AppPath | None:
        parts = path.removeprefix(f"{IgniPaths.APPS}/").split("/")
        if len(parts) != 2:
            return None
        return cls(app_id=parts[0], what=parts[1])


class AgentRoutes:
    """The agent channel's routes (service-identity §15), for `FakeAgents`."""

    def __init__(self, agents: FakeAgents) -> None:
        self.agents = agents

    def event(self, call: RoutedCall) -> httpx.Response:
        return self.agents.event(call.seen.body, call.holder.client_id, call.holder.org_id)

    def item(self, call: RoutedCall) -> httpx.Response:
        return self.agents.item(call.seen.body, call.holder.client_id, call.holder.org_id)

    def upload(self, call: RoutedCall) -> httpx.Response:
        return self.agents.upload(
            client_id=call.holder.client_id,
            filename=call.seen.first("filename"),
            content_type=call.seen.headers.get("content-type", ""),
            data=call.seen.body,
        )

    def status(self, call: RoutedCall) -> httpx.Response:
        return self.agents.status(call.seen.path.rsplit("/", 1)[1], call.holder.client_id)


class VmProfileRoutes:
    """VM profile routes (service-identity §12): a service's, and an app's own."""

    def __init__(
        self,
        vm_profiles: FakeVmProfiles,
        clients: FakeClientRegistry,
        extensions: FakeExtensionStore,
    ) -> None:
        self.vm_profiles = vm_profiles
        self.clients = clients
        self.extensions = extensions
        self._app_routes: dict[tuple[str, str], Handler] = {
            ("vm-profile-request", "PUT"): self._app_put,
            ("vm-profile-request", "GET"): self._app_get,
            ("vm-profile", "GET"): self._app_profile,
        }

    def service(self, call: RoutedCall) -> httpx.Response:
        """`GET /v1/service-vm-profile`: the request the service's extension makes."""
        holder = call.holder
        return self.vm_profiles.service(
            holder.org_id, holder.client_id, self.extensions.shipped(holder.client_id)
        )

    def app(self, call: RoutedCall) -> httpx.Response:
        """`/v1/apps/{app_id}/...`: only the app itself asks for its VM."""
        path = AppPath.parse(call.seen.path)
        if path is None:
            return DetailError(detail="Not Found", status=404).to_response()
        if path.app_id != call.holder.client_id:
            return DetailError(
                detail="Only the app itself asks for its VM", status=403
            ).to_response()
        handler = self._app_routes.get((path.what, call.seen.method))
        if handler is None:
            return DetailError(detail="Not Found", status=404).to_response()
        return handler(call)

    def _app_put(self, call: RoutedCall) -> httpx.Response:
        holder = call.holder
        client = self.clients.get(holder.client_id)
        name = client.client_name if client else holder.client_id
        return self.vm_profiles.app_put(holder.org_id, holder.client_id, name, call.seen.body)

    def _app_get(self, call: RoutedCall) -> httpx.Response:
        return self.vm_profiles.app_get(call.holder.org_id, call.holder.client_id)

    def _app_profile(self, call: RoutedCall) -> httpx.Response:
        return self.vm_profiles.app_profile(call.holder.org_id, call.holder.client_id)


__all__ = ["AgentRoutes", "AppPath", "Route", "RouteAuth", "VmProfileRoutes"]

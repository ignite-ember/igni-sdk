"""How `FakeIgni` answers a request: its routes, whose token it is, and the pipeline.

`RouteTable` is every path the fake serves, in the order they are
matched, and the handler an authenticated service path no route takes
falls back to (the directory, as igni's router has it). `RouteGuard`
says whom a request's bearer token stands for, for the token a route
needs. `FakeRouter` is the pipeline: the address, the record, any
failure a test asked for, the route, its token, then the handler.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict

from igni_service.testing_bearers import BearerTokens, TokenHolder
from igni_service.testing_clients import FakeClientRegistry
from igni_service.testing_routes import Handler, Route, RouteAuth
from igni_service.testing_wire import (
    DetailError,
    IgniAddresses,
    RecordedTraffic,
    RoutedCall,
    SeenRequest,
)


class RouteTable(BaseModel):
    """Every path igni serves a service, in the order they are matched."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    routes: tuple[Route, ...]
    fallback: Handler
    """What answers an authenticated service path no route takes."""

    def family(self, path: str) -> Route | None:
        """The first route serving `path`: it says which token the path needs."""
        return next((route for route in self.routes if route.serves(path)), None)

    def route(self, seen: SeenRequest) -> Route | None:
        """The first route taking `seen`'s path and method."""
        return next((route for route in self.routes if route.takes(seen)), None)


class RouteGuard:
    """Whom a request's bearer token stands for, for the token a route needs."""

    def __init__(self, bearers: BearerTokens, clients: FakeClientRegistry) -> None:
        self.bearers = bearers
        self.clients = clients

    def holder_for(self, seen: SeenRequest, auth: RouteAuth) -> TokenHolder | DetailError:
        """Whom the request's bearer token stands for, when `auth` needs one."""
        if auth is RouteAuth.NONE:
            return TokenHolder()
        if auth is RouteAuth.APP:
            holder = self.bearers.app_holder(seen.bearer())
        else:
            holder = self.bearers.service_holder(seen.bearer())
        client = self.clients.get(holder.client_id) if holder else None
        if holder is None or client is None or client.is_revoked:
            return DetailError.not_authenticated()
        if auth is RouteAuth.SERVICE and not holder.org_id:
            return DetailError.not_authenticated()
        return holder


class FakeRouter:
    """Answers a request as igni would, on the fake's address only."""

    def __init__(
        self,
        *,
        addresses: IgniAddresses,
        traffic: RecordedTraffic,
        guard: RouteGuard,
        table: RouteTable,
    ) -> None:
        self.addresses = addresses
        """The fake's addresses: a request to any other host is answered 404."""
        self.traffic = traffic
        """Where every request is recorded, and the failures a test asked for are read."""
        self.guard = guard
        """Checks the bearer token each route needs."""
        self.table = table
        """The routes, by method and path."""

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Answer `request` as igni would: failures a test asked for first, then the route.

        The first route serving the path says which token it needs; that
        token is checked before the method is. An authenticated service
        path no route takes is the table's fallback, as igni's router has it.
        """
        if not self.addresses.reaches(str(request.url)):
            where = urlsplit(str(request.url)).netloc
            raise httpx.ConnectError(f"{where} is not igni", request=request)
        seen = self.traffic.record(request)
        failure = self.traffic.failure_for(seen.path)
        if failure is not None:
            return failure
        family = self.table.family(seen.path)
        if family is None:
            return DetailError.not_found().to_response()
        holder = self.guard.holder_for(seen, family.auth)
        if isinstance(holder, DetailError):
            return holder.to_response()
        call = RoutedCall(seen=seen, holder=holder)
        route = self.table.route(seen)
        if route is not None:
            return route.handler(call)
        if family.auth.is_service:
            return self.table.fallback(call)
        return DetailError.not_found().to_response()


__all__ = ["FakeRouter", "RouteGuard", "RouteTable"]

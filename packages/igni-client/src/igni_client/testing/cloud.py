"""igni server's discovery, played: `/.well-known/openid-configuration` and `/v1/me/cloud`.

What `discover()` and `Fleet.from_server()` ask igni server, answered as
`contracts/cloud-discovery.schema.json` says: entitlement by the group's
mode, the gateway's address, and who pulls the person's events (one owner
per person, the person's choice only in `local_and_cloud`).
"""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus
from typing import Any

import httpx
from pydantic import ValidationError

from igni_client.cloud import (
    CLOUD_PATH,
    EVENTS_OWNER_PATH,
    CloudGroup,
    CloudIgni,
    EventsOwner,
    EventsOwnerRequest,
    Mode,
)

DISCOVERY_PATH = "/.well-known/openid-configuration"


class FakeServer:
    """igni server as discovery sees it. `tokens` maps each accepted bearer token to its producer.

    Only a person's token is answered (`403` for an app's or a space's,
    `401` for one it does not know). `mode` is the group's, for everyone;
    `inactive` and `not_licensed` hold the people igni server says no for.
    """

    def __init__(
        self,
        tokens: dict[str, str],
        *,
        url: str = "http://igni.test",
        gateway_url: Callable[[], str | None] = lambda: None,
    ) -> None:
        self.tokens = tokens
        self.url = url
        self._gateway_url = gateway_url
        #: Whether igni server has Fleet: without it, no `igni_gateway` and `fleet_not_configured`.
        self.fleet_configured = True
        #: Whether igni server has `/v1/me/cloud`; an older one answers `404`.
        self.serves_cloud = True
        #: The group's mode.
        self.mode: Mode = "local_and_cloud"
        self.group: CloudGroup | None = CloudGroup(id="g-engineering", name="Engineering")
        #: People (`person:<id>`) who are not active producers, or whose licence does not cover them.
        self.inactive: set[str] = set()
        self.not_licensed: set[str] = set()
        #: Who each person chose to pull their events, in `local_and_cloud`.
        self.events_owners: dict[str, EventsOwner] = {}
        #: Every request igni server was asked.
        self.calls: list[httpx.Request] = []

    @property
    def gateway_url(self) -> str | None:
        return self._gateway_url() if self.fleet_configured else None

    def answer(self, producer: str) -> CloudIgni:
        """What `/v1/me/cloud` answers `producer`."""
        reason = self._reason(producer)
        return CloudIgni(
            cloud="unavailable" if reason else "available",
            reason=reason,
            gateway_url=self.gateway_url,
            mode=self.mode,
            events_owner=self.owner(producer),
            group=self.group,
            producer=producer,
        )

    def owner(self, producer: str) -> EventsOwner:
        """Who pulls `producer`'s events: fixed by `local` and `cloud`, chosen in `local_and_cloud`."""
        if self.mode == "local":
            return "local"
        if self.mode == "cloud":
            return "cloud"
        return self.events_owners.get(producer, "local")

    def _reason(self, producer: str) -> str | None:
        if not self.fleet_configured:
            return "fleet_not_configured"
        if self.mode == "local":
            return "group_local_only"
        if producer in self.inactive:
            return "inactive"
        if producer in self.not_licensed:
            return "not_licensed"
        return None

    def transport(self) -> httpx.MockTransport:
        """igni server's discovery, for an `httpx.AsyncClient`."""
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if path == DISCOVERY_PATH and request.method == "GET":
            return self._discovery()
        if not self.serves_cloud or path not in (CLOUD_PATH, EVENTS_OWNER_PATH):
            return httpx.Response(HTTPStatus.NOT_FOUND, json={"detail": "Not Found"})
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        producer = self.tokens.get(token)
        if producer is None:
            return httpx.Response(HTTPStatus.UNAUTHORIZED, json={"detail": "Not authenticated"})
        if not producer.startswith("person:"):
            return httpx.Response(
                HTTPStatus.FORBIDDEN, json={"detail": "This describes a person's desktop"}
            )
        if path == CLOUD_PATH and request.method == "GET":
            return self._json(self.answer(producer).model_dump(mode="json"))
        if path == EVENTS_OWNER_PATH and request.method == "PUT":
            return self._set_owner(request, producer)
        return httpx.Response(HTTPStatus.METHOD_NOT_ALLOWED, json={"detail": "Method Not Allowed"})

    def _discovery(self) -> httpx.Response:
        document: dict[str, Any] = {"issuer": self.url}
        if self.gateway_url is not None:
            document["igni_gateway"] = self.gateway_url
        return self._json(document)

    def _set_owner(self, request: httpx.Request, producer: str) -> httpx.Response:
        try:
            asked = EventsOwnerRequest.model_validate_json(request.content or b"{}")
        except ValidationError as refused:
            return httpx.Response(HTTPStatus.UNPROCESSABLE_ENTITY, json={"detail": str(refused)})
        forbidden = (self.mode == "local" and asked.owner == "cloud") or (
            self.mode == "cloud" and asked.owner == "local"
        )
        if forbidden:
            return httpx.Response(HTTPStatus.CONFLICT, json={"error": "mode_forbids"})
        self.events_owners[producer] = asked.owner
        return self._json(self.answer(producer).model_dump(mode="json"))

    @staticmethod
    def _json(body: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            HTTPStatus.OK, json=body, headers={"Cache-Control": "private, max-age=60"}
        )


__all__ = ["DISCOVERY_PATH", "FakeServer"]

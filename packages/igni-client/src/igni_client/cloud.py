"""Finding a person's cloud igni from igni server: `discover()` and `set_events_owner()`.

igni server's `GET /v1/me/cloud` answers, for a person's session, whether
they have a cloud igni they may use, the gateway's address, their group's
mode and who pulls their service events. The shape is
`contracts/cloud-discovery.schema.json`, igni-sdk's own contract, which
igni server and the desktop are tested against too. An igni server older
than the endpoint answers `404`; its `igni_gateway` (in
`/.well-known/openid-configuration`) is then all there is to go on.

What the answer says is entitlement, not the VM's live state: the
gateway's `GET /v1/me` says that (`Me.vm`), and never wakes the VM.
"""

from __future__ import annotations

import os
from typing import Any, Literal, get_args
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from igni_client.auth.server import IgniServer
from igni_client.auth.tokens import TokenSource
from igni_client.errors import (
    GROUP_LOCAL_ONLY,
    AuthError,
    GroupIsLocalOnly,
    IgniClientError,
    NotAllowed,
    NotSupported,
    Unavailable,
)

#: Whether the person has a cloud igni they may use from the desktop.
CloudState = Literal["available", "unavailable"]
#: Where the person's group runs igni: only on the desktop, only in the cloud, or either.
Mode = Literal["local", "cloud", "local_and_cloud"]
#: Which side pulls the person's service events: the desktop, or the gateway for the VM.
EventsOwner = Literal["local", "cloud"]

#: Why a cloud igni is unavailable, as igni server says it today; the set is open.
REASONS = ("fleet_not_configured", "group_local_only", "inactive", "not_licensed")

#: igni server's route, and the one that chooses who pulls events.
CLOUD_PATH = "/v1/me/cloud"
EVENTS_OWNER_PATH = "/v1/me/cloud/events-owner"
#: Set to `1` to take a plain-HTTP gateway, as the desktop's development build does.
INSECURE_GATEWAY_ENV = "IGNI_DEV_GATEWAY_INSECURE"


def _known(value: Any, known: tuple[str, ...], safe: str) -> Any:
    """`value` when it is one of `known`, else `safe`: a newer server's word reads the safe way."""
    return value if value in known else safe


class CloudGroup(BaseModel):
    """The person's group, for display."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str = ""


class CloudIgni(BaseModel):
    """What igni server says of a person's cloud igni (`GET /v1/me/cloud`).

    Read leniently, as the contract asks: a `cloud` value this version does
    not know reads as `unavailable`, a `mode` or `events_owner` as `local`,
    and a `reason` is kept as sent (`REASONS` are the ones known today).
    Fields igni server adds later are kept in `model_extra`.
    """

    model_config = ConfigDict(extra="allow")

    cloud: CloudState = "unavailable"
    #: Why it is unavailable — `fleet_not_configured`, `group_local_only`,
    #: `inactive`, `not_licensed` or a newer reason; `None` when available.
    reason: str | None = None
    #: The gateway's public address; `None` when igni server has no Fleet.
    gateway_url: str | None = None
    mode: Mode = "local"
    events_owner: EventsOwner = "local"
    group: CloudGroup | None = None
    #: The gateway's producer id for the person (`person:<id>`); empty from an older server.
    producer: str = ""

    @field_validator("cloud", mode="before")
    @classmethod
    def _cloud(cls, value: Any) -> Any:
        return _known(value, get_args(CloudState), "unavailable")

    @field_validator("mode", mode="before")
    @classmethod
    def _mode(cls, value: Any) -> Any:
        return _known(value, get_args(Mode), "local")

    @field_validator("events_owner", mode="before")
    @classmethod
    def _owner(cls, value: Any) -> Any:
        return _known(value, get_args(EventsOwner), "local")

    @property
    def available(self) -> bool:
        """Whether there is a cloud igni to connect to: available, a gateway, and a group that allows it."""
        return self.cloud == "available" and self.mode != "local" and bool(self.gateway_url)

    @property
    def allows_local(self) -> bool:
        """Whether the group lets the person run igni on their own computer."""
        return self.mode != "cloud"

    def refusal(self) -> IgniClientError | None:
        """What connecting to the cloud igni would raise, or `None` when it is available."""
        if self.available:
            return None
        if self.reason == GROUP_LOCAL_ONLY or self.mode == "local":
            return GroupIsLocalOnly(
                "igni server says the person's group runs igni only on their own computer "
                "(group_local_only); use the local igni"
            )
        if self.reason == "fleet_not_configured" or not self.gateway_url:
            return NotSupported("igni server has no Fleet: there is no cloud igni to connect to")
        return NotAllowed(
            f"igni server says the person has no cloud igni to use ({self.reason or 'unavailable'})"
        )


class EventsOwnerRequest(BaseModel):
    """The body of `PUT /v1/me/cloud/events-owner`."""

    owner: EventsOwner


class _Refusal(BaseModel):
    """igni server's refusal: FastAPI's `detail`, or an OAuth-style `error`."""

    model_config = ConfigDict(extra="ignore")

    detail: Any = None
    error: Any = None
    error_description: Any = None

    @classmethod
    def of(cls, response: httpx.Response) -> _Refusal:
        try:
            return cls.model_validate_json(response.content)
        except ValidationError:
            return cls(detail=response.text.strip())

    def reason(self) -> str:
        return str(self.detail or self.error_description or self.error or "")


def _answer(response: httpx.Response, what: str) -> CloudIgni:
    """igni server's answer to `what` as a `CloudIgni`, or the error its status means."""
    if response.status_code == 200:
        try:
            return CloudIgni.model_validate_json(response.content)
        except ValidationError as exc:
            raise Unavailable(f"igni server answered {what} with something else") from exc
    refusal = _Refusal.of(response)
    if response.status_code == 401:
        raise AuthError(f"igni server refused the session for {what}: {refusal.reason()}")
    if response.status_code == 403:
        raise NotAllowed(
            f"igni server refused {what}: it answers only a person's session, never an app's, "
            f"a space's or a VM's ({refusal.reason() or 'forbidden'})"
        )
    if response.status_code == 409 and refusal.error == "mode_forbids":
        raise NotAllowed(
            f"igni server refused {what}: the group's mode does not allow that owner (mode_forbids)"
        )
    raise Unavailable(f"igni server answered {what} with {response.status_code}")


async def discover(
    server: str, auth: TokenSource, *, http: httpx.AsyncClient | None = None
) -> CloudIgni:
    """Ask igni server at `server` about the person's cloud igni.

    `auth` is the person (`Person`, or their `ApiKey`): igni server answers
    only a person's session, and refuses an app's or a space's with
    `NotAllowed`. A refused session raises `AuthError`; an igni server out of
    reach `Unavailable`. An igni server older than `/v1/me/cloud` is read
    from its `igni_gateway` alone: available in `local_and_cloud` when it
    names a gateway, `fleet_not_configured` when it names none.
    """
    igni_server = IgniServer(server, http=http)
    try:
        token = await auth.token()
        response = await igni_server.call("GET", CLOUD_PATH, what="cloud discovery", bearer=token)
        if response.status_code != 404:
            return _answer(response, "cloud discovery")
        gateway = await igni_server.gateway()
        if gateway is None:
            return CloudIgni(
                cloud="unavailable", reason="fleet_not_configured", mode="local_and_cloud"
            )
        return CloudIgni(cloud="available", gateway_url=gateway, mode="local_and_cloud")
    finally:
        await igni_server.aclose()


async def set_events_owner(
    server: str,
    auth: TokenSource,
    owner: EventsOwner,
    *,
    http: httpx.AsyncClient | None = None,
) -> CloudIgni:
    """Choose who pulls the person's service events from now on: `"cloud"` or `"local"`.

    In a `local_and_cloud` group the desktop pulls them until the person
    first switches; a program that uses Fleet only through igni-client sets
    `"cloud"` here, once. igni server answers what it now says of the
    person's cloud igni. A group whose mode does not allow `owner` (`cloud`
    in `local` mode, `local` in `cloud` mode) raises `NotAllowed`.
    """
    if owner not in get_args(EventsOwner):
        raise ValueError("the events owner is 'cloud' or 'local'")
    igni_server = IgniServer(server, http=http)
    try:
        token = await auth.token()
        response = await igni_server.call(
            "PUT",
            EVENTS_OWNER_PATH,
            what="the events owner",
            bearer=token,
            json=EventsOwnerRequest(owner=owner),
        )
        return _answer(response, "the events owner")
    finally:
        await igni_server.aclose()


def insecure_gateway_allowed() -> bool:
    """Whether `IGNI_DEV_GATEWAY_INSECURE=1` lets a plain-HTTP gateway through."""
    return os.environ.get(INSECURE_GATEWAY_ENV, "") == "1"


def checked_gateway(cloud: CloudIgni, *, allow_http: bool) -> str:
    """The gateway to connect to, or what connecting would raise.

    igni server's token goes only to igni server and to the gateway igni
    server itself names; that gateway must speak TLS, unless `allow_http`
    (a lab, a test) says a plain-HTTP one will do.
    """
    refusal = cloud.refusal()
    if refusal is not None:
        raise refusal
    assert cloud.gateway_url is not None  # `available` says there is one
    scheme = urlsplit(cloud.gateway_url).scheme
    if scheme == "https" or (scheme == "http" and allow_http):
        return cloud.gateway_url
    raise NotAllowed(
        f"igni server named a gateway that is not https ({cloud.gateway_url}); the person's "
        f"session goes only over TLS (set {INSECURE_GATEWAY_ENV}=1 for a lab gateway)"
    )


__all__ = [
    "CLOUD_PATH",
    "EVENTS_OWNER_PATH",
    "INSECURE_GATEWAY_ENV",
    "REASONS",
    "CloudGroup",
    "CloudIgni",
    "CloudState",
    "EventsOwner",
    "EventsOwnerRequest",
    "Mode",
    "checked_gateway",
    "discover",
    "insecure_gateway_allowed",
    "set_events_owner",
]

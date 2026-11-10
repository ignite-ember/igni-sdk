"""This service's own tokens for igni, one per organisation.

`client_credentials` with `private_key_jwt` and `organisation=<org>`:
every token names one organisation, and the directory and notifications
answer for that one only. So a token is kept per organisation and
renewed `RENEW_BEFORE` ahead of its expiry rather than at it — a call
made with a token about to expire can reach igni after it has.

A 401 from igni with a token that should still be good means igni has
stopped honouring it (the service was revoked, or igni's keys moved):
`request` drops it and tries once more with a fresh one.

A token refused because of the service's registration is raised as what
it means: `ServiceNotApproved` while no super admin has approved it,
`ServiceRevoked` after one revoked it. Which of the two is read from a
field, never from igni's sentence: the `client_state` igni sends with
`invalid_client`, or — from an igni server that does not send it yet —
the `state` igni answers a registration with, asked for again the way
every start asks it (the same key gets the same registration back, and
changes nothing: re-registering cannot un-revoke).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from igni_service.clock import Clock
from igni_service.errors import IgniUnavailable, ServiceNotApproved, ServiceRevoked
from igni_service.grants import ClientCredentialsGrant
from igni_service.registration import ServiceRegistration
from igni_service.server import IgniServer
from igni_service.signing import SigningKey
from igni_service.token_endpoint import GrantRefused, IssuedTokens, TokenEndpoint


class HeldToken(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)
    token: str
    expires_at: float


class ServiceTokens:
    """Service tokens for igni, kept per organisation."""

    RENEW_BEFORE = 60.0
    """How long before expiry a kept token is replaced, in seconds."""

    def __init__(
        self,
        igni: IgniServer,
        registration: ServiceRegistration,
        key: SigningKey,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._igni = igni
        self._registration = registration
        self._endpoint = TokenEndpoint(igni, registration, key)
        self._clock = clock or Clock()
        self._held: dict[str, HeldToken] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def forget(self, org_id: str | None = None) -> None:
        if org_id is None:
            self._held.clear()
        else:
            self._held.pop(org_id, None)

    async def token(self, org_id: str) -> str:
        """A service token for `org_id`. Raises `IgniUnavailable`."""
        if not org_id:
            raise IgniUnavailable("a service token is for one organisation, and none was named")
        held = self._fresh(org_id)
        if held is not None:
            return held
        lock = self._locks.setdefault(org_id, asyncio.Lock())
        async with lock:
            held = self._fresh(org_id)
            if held is not None:
                return held
            issued = await self._issue(org_id)
            self._held[org_id] = HeldToken(
                token=issued.access_token,
                expires_at=self._clock.monotonic() + issued.expires_in,
            )
            return issued.access_token

    def _fresh(self, org_id: str) -> str | None:
        held = self._held.get(org_id)
        if held is not None and self._clock.monotonic() < held.expires_at - self.RENEW_BEFORE:
            return held.token
        return None

    NOT_APPROVED = "pending"
    """igni's registration states that refuse a service token, by what they mean."""
    REVOKED = "revoked"

    async def _issue(self, org_id: str) -> IssuedTokens:
        try:
            return await self._endpoint.grant(ClientCredentialsGrant(organisation=org_id))
        except GrantRefused as exc:
            # `invalid_client` while a super admin has not approved this
            # service yet, or after they revoked it: raised as its own
            # kind, because "try again later" is the wrong advice.
            raise self.refusal(exc, await self.client_state(exc)) from exc

    async def client_state(self, exc: GrantRefused) -> str | None:
        """The state igni holds this service's registration in, when `exc` is about it.

        `None` for any refusal but `invalid_client`. Otherwise igni's
        `client_state`; from an igni server that does not send one, the
        `state` of this key's registration, registering it again to ask —
        `None` if that cannot be had either.
        """
        if exc.refusal.error != "invalid_client":
            return None
        if exc.refusal.client_state is not None:
            return exc.refusal.client_state
        try:
            return (await self._registration.register()).state
        except IgniUnavailable:
            return None

    @classmethod
    def refusal(cls, exc: GrantRefused, client_state: str | None = None) -> IgniUnavailable:
        """What igni's refusal of a service token means, as the error to raise.

        `client_state` is the registration's state (`client_state`); the
        error's message carries igni's own words, which are for people.
        """
        message = f"igni server refused a service token: {exc}"
        if client_state == cls.NOT_APPROVED:
            return ServiceNotApproved(
                f"{message}. A super admin approves this service in igni's portal under "
                "Services, after checking the thumbprint this service logged at start-up."
            )
        if client_state == cls.REVOKED:
            return ServiceRevoked(message)
        return IgniUnavailable(message)

    async def request(
        self, method: str, path: str, *, org_id: str, **kwargs: Any
    ) -> httpx.Response:
        """One call to igni as this service, for `org_id`. Raises `IgniUnavailable`.

        Answers whatever igni answered, error statuses included, except a
        401 — which is retried once with a new token, and raised if it
        happens again.
        """
        extra_headers: dict[str, str] = dict(kwargs.pop("headers", None) or {})
        for attempt in (1, 2):
            token = await self.token(org_id)
            try:
                response = await self._igni.http.request(
                    method,
                    self._igni.url(path),
                    headers={**extra_headers, "Authorization": f"Bearer {token}"},
                    **kwargs,
                )
            except httpx.HTTPError as exc:
                raise IgniUnavailable(f"could not reach igni server: {type(exc).__name__}") from exc
            if response.status_code != 401:
                return response
            self.forget(org_id)
            if attempt == 2:
                break
        raise IgniUnavailable(f"igni server refused this service for organisation {org_id}")

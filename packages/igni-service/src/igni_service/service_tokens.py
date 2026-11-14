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
`invalid_client` (every igni server since 0.7.0 sends it).
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx
from pydantic import BaseModel, ConfigDict

from igni_service.clock import Clock
from igni_service.errors import IgniUnavailable, ServiceNotApproved, ServiceRevoked
from igni_service.grants import ClientCredentialsGrant
from igni_service.keyed_locks import KeyedLocks
from igni_service.registration import ServiceRegistration
from igni_service.server import IgniServer
from igni_service.signing import SigningKey
from igni_service.token_endpoint import GrantRefused, IssuedTokens, TokenEndpoint


class HeldToken(BaseModel):
    """A token kept for one organisation, and when it stops being good."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    token: str
    """The bearer token."""
    expires_at: float
    """When it expires, on the clock's `monotonic` reading."""


class ServiceTokens:
    """Service tokens for igni, kept per organisation."""

    RENEW_BEFORE = 60.0
    """How long before expiry a kept token is replaced, in seconds."""

    NOT_APPROVED = "pending"
    """The registration state igni refuses a token in until a super admin approves it."""
    REVOKED = "revoked"
    """The registration state igni refuses a token in after a super admin revoked it."""

    def __init__(
        self,
        igni: IgniServer,
        registration: ServiceRegistration,
        key: SigningKey,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._igni = igni
        self._endpoint = TokenEndpoint(igni, registration, key)
        self._clock = clock or Clock()
        self._held: dict[str, HeldToken] = {}
        self._locks = KeyedLocks()

    def forget(self, org_id: str | None = None) -> None:
        """Drop the token kept for `org_id`, or every kept token when none is named."""
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
        async with self._locks.held(org_id):
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

    async def _issue(self, org_id: str) -> IssuedTokens:
        try:
            return await self._endpoint.grant(ClientCredentialsGrant(organisation=org_id))
        except GrantRefused as exc:
            # `invalid_client` while a super admin has not approved this
            # service yet, or after they revoked it: raised as its own
            # kind, because "try again later" is the wrong advice.
            raise self.refusal(exc) from exc

    @classmethod
    def refusal(cls, exc: GrantRefused) -> IgniUnavailable:
        """What igni's refusal of a service token means, as the error to raise.

        Which error is read from the `client_state` igni sends beside
        `invalid_client`; the error's message carries igni's own words,
        which are for people.

        Args:
            exc: igni's refusal of the grant.
        """
        message = f"igni server refused a service token: {exc}"
        client_state = exc.refusal.client_state if exc.refusal.error == "invalid_client" else None
        if client_state == cls.NOT_APPROVED:
            return ServiceNotApproved(
                f"{message}. A super admin approves this service in igni's portal under "
                "Services, after checking the thumbprint this service logged at start-up."
            )
        if client_state == cls.REVOKED:
            return ServiceRevoked(message)
        return IgniUnavailable(message)

    async def request(
        self,
        method: str,
        path: str,
        *,
        org_id: str,
        params: Mapping[str, str | int] | None = None,
        json: Mapping[str, object] | None = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """One call to igni as this service, for `org_id`. Raises `IgniUnavailable`.

        Answers whatever igni answered, error statuses included, except a
        401 — which is retried once with a new token, and raised if it
        happens again.

        Args:
            method: The HTTP method.
            path: The path on igni server, such as `IgniPaths.DIRECTORY`.
            org_id: The organisation the call is for: it is made with
                this service's token for that organisation.
            params: The query string.
            json: A JSON body.
            content: A raw body, such as an uploaded file's bytes.
            headers: Headers to send beside the service's token; an
                `Authorization` header among them is dropped.
        """
        # The service's token is the only credential: a caller's own
        # Authorization header, in any case, is dropped rather than sent beside it.
        extra_headers = {
            name: value
            for name, value in (headers or {}).items()
            if name.lower() != "authorization"
        }
        for attempt in (1, 2):
            token = await self.token(org_id)
            try:
                response = await self._igni.http.request(
                    method,
                    self._igni.url(path),
                    params=params,
                    json=json,
                    content=content,
                    headers={**extra_headers, "Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as exc:
                raise IgniUnavailable(f"could not reach igni server: {type(exc).__name__}") from exc
            if response.status_code != 401:
                return response
            self.forget(org_id)
            if attempt == 2:
                break
        raise IgniUnavailable(f"igni server refused this service for organisation {org_id}")

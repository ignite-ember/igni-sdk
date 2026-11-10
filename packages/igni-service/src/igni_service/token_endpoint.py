"""igni's token and revocation endpoints, as this service calls them with its own key.

Every grant this service asks for — `client_credentials` for itself,
`authorization_code` and `refresh_token` for a person signed in to its
pages — and every revocation (a person signing out) authenticates the
same way: a `private_key_jwt` client assertion, single use, addressed to
igni's issuer.
"""

from __future__ import annotations

import json
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from igni_service.errors import IgniError, IgniUnavailable
from igni_service.grants import Grant
from igni_service.server import IgniServer
from igni_service.signing import SigningKey
from igni_service.urls import IgniPaths

ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


class IssuedTokens(BaseModel):
    """What the token endpoint answers."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    access_token: str
    expires_in: int = 600
    refresh_token: str = ""
    token_type: str = "Bearer"  # noqa: S105 — the OAuth token type, not a token


class OAuthRefusal(BaseModel):
    """The body of a refusal: RFC 6749 §5.2's error, and the client's state.

    `client_state` is igni's own field beside `invalid_client`: the state
    it holds the client's registration in when that is why it refused —
    `pending` (no super admin has approved it yet) or `revoked` — in the
    words `POST /v1/clients` answers a registration's `state` with. It is
    absent from any other refusal, and from every refusal of an igni
    server that predates it.
    """

    model_config = ConfigDict(extra="ignore", use_attribute_docstrings=True)

    error: str = ""
    error_description: str = ""
    client_state: str | None = None

    @classmethod
    def read(cls, body: str) -> OAuthRefusal:
        """The refusal in `body`; an empty one when `body` is not RFC 6749's JSON."""
        try:
            return cls.model_validate(json.loads(body))
        except (ValueError, ValidationError):
            return cls()


class GrantRefused(IgniError):
    """igni answered and refused: `invalid_client`, `invalid_grant`, `unsupported_token_type`.

    `detail` is the body as igni sent it; `refusal` is the same body read
    (`error`, `error_description`, `client_state`).
    """

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status} {detail}")
        self.status = status
        self.detail = detail
        self.refusal = OAuthRefusal.read(detail)


class ClientIdentity(Protocol):
    """Whatever knows the client id to authenticate as: a service's
    registration, or an app's id as its org admin registered it."""

    async def client_id(self) -> str: ...


class TokenEndpoint:
    """`POST /v1/oauth/token` and `POST /v1/oauth/revoke`, authenticated as this client."""

    def __init__(self, igni: IgniServer, registration: ClientIdentity, key: SigningKey) -> None:
        self._igni = igni
        self._registration = registration
        self._key = key

    async def grant(self, grant: Grant) -> IssuedTokens:
        """Ask for tokens. Raises `GrantRefused` or `IgniUnavailable`."""
        response = await self._post(IgniPaths.TOKEN, grant.form(), what="a token request")
        try:
            return IssuedTokens.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise IgniUnavailable(
                "igni server answered a token request with something else"
            ) from exc

    async def revoke(self, refresh_token: str) -> None:
        """End the sign-in a refresh token belongs to (RFC 7009).

        Every refresh token of that sign-in stops renewing at igni. A token
        igni no longer considers valid is not an error. Raises
        `GrantRefused` or `IgniUnavailable`.
        """
        await self._post(
            IgniPaths.REVOKE,
            {"token": refresh_token, "token_type_hint": "refresh_token"},
            what="a revocation",
        )

    async def _post(self, path: str, form: dict[str, str], *, what: str) -> httpx.Response:
        client_id = await self._registration.client_id()
        authenticated = {
            **form,
            "client_assertion_type": ASSERTION_TYPE,
            "client_assertion": await self._key.assertion(
                client_id=client_id, audience=await self._igni.issuer()
            ),
        }
        try:
            response = await self._igni.http.post(self._igni.url(path), data=authenticated)
        except httpx.HTTPError as exc:
            raise IgniUnavailable(
                f"could not reach igni server for {what}: {type(exc).__name__}"
            ) from exc
        if response.status_code in (400, 401, 403):
            raise GrantRefused(response.status_code, response.text)
        if response.status_code != 200:
            raise IgniUnavailable(f"igni server answered {what} {response.status_code}")
        return response

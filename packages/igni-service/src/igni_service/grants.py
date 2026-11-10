"""The OAuth grants this SDK sends to igni's token endpoint, as typed requests.

Each one is a form (`application/x-www-form-urlencoded`); the client
assertion that authenticates it is added by `TokenEndpoint`, not here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Grant(BaseModel):
    """A token request, sent as a form. Fields left `None` are not sent."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    def form(self) -> dict[str, str]:
        return self.model_dump(exclude_none=True)


class ClientCredentialsGrant(Grant):
    """A client's own token: a service's for one `organisation` (or for none,
    with a `scope`), or an app's, which names neither."""

    grant_type: Literal["client_credentials"] = "client_credentials"
    organisation: str | None = None
    scope: str | None = None


class AuthorizationCodeGrant(Grant):
    """A person's sign-in code redeemed, with the PKCE verifier that started it."""

    grant_type: Literal["authorization_code"] = "authorization_code"
    code: str
    code_verifier: str
    redirect_uri: str


class RefreshTokenGrant(Grant):
    """A person's sign-in renewed."""

    grant_type: Literal["refresh_token"] = "refresh_token"
    refresh_token: str

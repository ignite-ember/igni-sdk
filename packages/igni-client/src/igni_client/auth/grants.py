"""The OAuth grants the client sends to igni server's token endpoint."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel

ASSERTION_TYPE: Final = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
TOKEN_EXCHANGE: Final = "urn:ietf:params:oauth:grant-type:token-exchange"  # noqa: S105 — an RFC 8693 grant type, not a token
ACCESS_TOKEN_TYPE: Final = "urn:ietf:params:oauth:token-type:access_token"  # noqa: S105 — an RFC 8693 URN, not a token
API_KEY_GRANT: Final = "urn:igni:params:oauth:grant-type:api-key"


class Grant(BaseModel):
    """A token request, sent as a form."""

    def form(self) -> dict[str, str]:
        return self.model_dump()


class ApiKeyGrant(Grant):
    """A person's API key, for a short session as them."""

    grant_type: Literal["urn:igni:params:oauth:grant-type:api-key"] = API_KEY_GRANT
    api_key: str


class ClientCredentialsGrant(Grant):
    """An app's own token, proved with a `private_key_jwt` assertion."""

    grant_type: Literal["client_credentials"] = "client_credentials"
    client_assertion_type: Literal["urn:ietf:params:oauth:client-assertion-type:jwt-bearer"] = (
        ASSERTION_TYPE
    )
    client_assertion: str


class SpaceExchangeGrant(Grant):
    """An app's token exchanged (RFC 8693) for one of its space's."""

    grant_type: Literal["urn:ietf:params:oauth:grant-type:token-exchange"] = TOKEN_EXCHANGE
    subject_token: str
    subject_token_type: Literal["urn:ietf:params:oauth:token-type:access_token"] = ACCESS_TOKEN_TYPE
    space: str

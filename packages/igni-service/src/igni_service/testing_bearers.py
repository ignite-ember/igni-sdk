"""The bearer tokens the fake's token endpoint issued, and whom each one stands for.

A service token is for one organisation, or for none (revocations and
the served organisations only, service-identity §3, §21); an app's own
token is for its organisation (§11.1). Each is an opaque string the fake
remembers until a test expires it.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class TokenHolder(BaseModel):
    """Who a bearer token was issued to: a client, and the organisation it is for."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    client_id: str = ""
    org_id: str = ""
    """Empty for a service token for no organisation, and on unauthenticated routes."""


class BearerTokens:
    """Every service and app token issued so far, by token."""

    def __init__(self) -> None:
        self.service: dict[str, TokenHolder] = {}
        self.apps: dict[str, TokenHolder] = {}

    def issue_service(self, holder: TokenHolder, prefix: str) -> str:
        token = f"{prefix}-{uuid.uuid4().hex}"
        self.service[token] = holder
        return token

    def issue_app(self, holder: TokenHolder) -> str:
        token = f"app-{uuid.uuid4().hex}"
        self.apps[token] = holder
        return token

    def service_holder(self, bearer: str) -> TokenHolder | None:
        return self.service.get(bearer)

    def app_holder(self, bearer: str) -> TokenHolder | None:
        return self.apps.get(bearer)

    def expire_service(self) -> None:
        """Stop honouring every service token issued so far, as a key move would."""
        self.service.clear()


__all__ = ["BearerTokens", "TokenHolder"]

"""The claims of the tokens igni signs, and what a test may change about one.

Every token is a `JwtEnvelope` (issuer, subject, audience, kind, times)
plus the claims of its kind: a person's (`PersonClaims`), an app's
(`AppClaims`), a space's (`SpaceClaims`) or igni's own call to a service
(`IgniClaims`). `TokenOverrides` is what a test bends to make a token a
service must refuse: another audience, issuer, kind, organisation,
subject, key or lifetime.
"""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from igni_service.crypto import RsaKeyPair


class JwtEnvelope(BaseModel):
    """What every token igni signs carries, whatever it is for."""

    iss: str
    sub: str
    aud: str
    token_use: str
    iat: int
    iat_ms: int
    exp: int


class OrgClaims(BaseModel):
    """Claims for one organisation; `USE` is the `token_use` of their kind."""

    USE: ClassVar[str]

    org: str


class PersonClaims(OrgClaims):
    """A person's claims, for one organisation, as igni's directory knows them."""

    USE: ClassVar[str] = "user"

    org_name: str = ""
    org_role: str = "member"
    email: str = ""
    name: str = ""
    super_admin: bool = False
    #: The client a person signed in to, on a token issued at the token endpoint.
    azp: str | None = None


class AppClaims(OrgClaims):
    """An app's token exchanged for a service (service-identity §9.2)."""

    USE: ClassVar[str] = "app"

    kind: Literal["app"] = "app"
    name: str


class SpaceClaims(OrgClaims):
    """A space's token exchanged for a service (§9.2, §17)."""

    USE: ClassVar[str] = "space"

    kind: Literal["space"] = "space"
    app: str
    external_id: str


class IgniClaims(OrgClaims):
    """What igni signs to call a service about one organisation."""

    USE: ClassVar[str] = "igni"


class TokenOverrides(BaseModel):
    """What a test changes about a token; `None` is "as igni would sign it".

    `org=""` is a change (a token for no organisation), which is why every
    field is optional rather than defaulted.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    aud: str | None = None
    iss: str | None = None
    use: str | None = None
    sub: str | None = None
    org: str | None = None
    kid: str | None = None
    key: RsaKeyPair | None = None
    lifetime: float | timedelta | None = None

    def seconds(self, default: float) -> float:
        """The lifetime in seconds, or `default` when not changed."""
        if self.lifetime is None:
            return default
        if isinstance(self.lifetime, timedelta):
            return self.lifetime.total_seconds()
        return self.lifetime


__all__ = [
    "AppClaims",
    "IgniClaims",
    "JwtEnvelope",
    "OrgClaims",
    "PersonClaims",
    "SpaceClaims",
    "TokenOverrides",
]

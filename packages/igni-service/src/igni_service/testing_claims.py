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

    model_config = ConfigDict(use_attribute_docstrings=True)

    iss: str
    """The issuer: igni's issuer URL."""
    sub: str
    """Whom the token is for: a user id, an app id, a space id, or igni."""
    aud: str
    """The audience: the service's own URL."""
    token_use: str
    """The kind of token: `user`, `app`, `space` or `igni`."""
    iat: int
    """When it was issued, in seconds since the epoch."""
    iat_ms: int
    """The same, in milliseconds."""
    exp: int
    """When it expires, in seconds since the epoch."""


class OrgClaims(BaseModel):
    """Claims for one organisation; `USE` is the `token_use` of their kind."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    USE: ClassVar[str]

    org: str
    """The organisation the token is for."""


class PersonClaims(OrgClaims):
    """A person's claims, for one organisation, as igni's directory knows them."""

    USE: ClassVar[str] = "user"

    org_name: str = ""
    """The organisation's display name."""
    org_role: str = "member"
    """`admin` or `member` in the organisation."""
    email: str = ""
    """The person's email address."""
    name: str = ""
    """The person's display name."""
    super_admin: bool = False
    """Whether the person is a super admin of the deployment."""
    azp: str | None = None
    """The client a person signed in to, on a token issued at the token endpoint."""


class AppClaims(OrgClaims):
    """An app's token exchanged for a service (service-identity §9.2)."""

    USE: ClassVar[str] = "app"

    kind: Literal["app"] = "app"
    """Always `app`."""
    name: str
    """The app's display name."""


class SpaceClaims(OrgClaims):
    """A space's token exchanged for a service (§9.2, §17)."""

    USE: ClassVar[str] = "space"

    kind: Literal["space"] = "space"
    """Always `space`."""
    app: str
    """The app the space belongs to."""
    external_id: str
    """The app's own name for its end user."""


class IgniClaims(OrgClaims):
    """What igni signs to call a service about one organisation."""

    USE: ClassVar[str] = "igni"


class TokenOverrides(BaseModel):
    """What a test changes about a token; `None` is "as igni would sign it".

    `org=""` is a change (a token for no organisation), which is why every
    field is optional rather than defaulted.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, use_attribute_docstrings=True)

    aud: str | None = None
    """Another audience: a token for another service."""
    iss: str | None = None
    """Another issuer: a token somebody other than igni signed."""
    use: str | None = None
    """Another `token_use`: the wrong kind of token."""
    sub: str | None = None
    """Another subject."""
    org: str | None = None
    """Another organisation; an empty string is a token for none."""
    kid: str | None = None
    """Another key id in the header: a key igni does not publish."""
    key: RsaKeyPair | None = None
    """Another key to sign with: a signature igni's keys do not verify."""
    lifetime: float | timedelta | None = None
    """How long it lives, in seconds or as a `timedelta`; negative is already expired."""

    def seconds(self, default: float) -> float:
        """The lifetime in seconds, or `default` when not changed.

        Args:
            default: The lifetime to answer with when the test changed none:
                how long the token lives otherwise.
        """
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

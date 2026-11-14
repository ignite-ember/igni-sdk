"""The claims of a token this service accepts, and the refusal of one it does not.

`TokenVerifier` checks a token's signature, issuer and audience; what it
then reads from the token is a `VerifiedClaims`: one typed model of every
claim a caller model or the revocation list reads, so nothing downstream
goes back to a dictionary of claims.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from types import MappingProxyType
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from igni_service.errors import IgniError


class TokenUse:
    """`token_use` values a service accepts."""

    USER = "user"
    IGNI = "igni"
    APP = "app"
    """An app acting as itself, exchanged for this service (igni's service-identity §9.2)."""
    SPACE = "space"
    """One end user of an app, a producer of its own (§17), exchanged for this service."""


class TokenRefused(IgniError):
    """The token is not one this service accepts, and why.

    The reason is said only in terms anybody holding the token could read
    from it themselves — expired, for another audience, the wrong kind —
    or as "not signed by igni" for everything about its signature. It goes
    in the 401's RFC 6750 challenge and the service's log, never in the
    body, which stays "Not authenticated".
    """

    def __init__(self, reason: str = "the token is not one this service accepts") -> None:
        super().__init__(reason)
        self.reason = reason
        """Why, in words safe to show whoever holds the token."""


class VerifiedClaims(BaseModel):
    """The claims of a token whose signature, issuer and audience have been checked.

    Every claim a caller model or the revocation list reads, typed. A claim
    that is text is written as text whatever the token held (a missing or
    null one is empty); `exp` and `iat` are finite numbers or the token is
    refused.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    iss: str
    """The issuer: igni server's issuer URL."""
    aud: str | list[str]
    """The audience: this service's own URL."""
    token_use: str
    """The kind of token: `user`, `igni`, `app` or `space` (`TokenUse`)."""
    exp: float
    """When the token stops working, in seconds since the epoch."""
    iat: float
    """When the token was issued, in seconds since the epoch."""
    iat_ms: int | None = None
    """When the token was issued, in milliseconds, when the token carries it."""
    sub: str = ""
    """Whom the token is for: a user id, an app id, a space id, or igni's issuer."""
    org: str = ""
    """The organisation the token is for."""
    org_name: str = ""
    """The organisation's display name, on a person's token."""
    org_role: str = ""
    """`admin` or `member` in `org`, on a person's token."""
    email: str = ""
    """The person's email address, on a person's token."""
    name: str = ""
    """The person's or the app's display name."""
    super_admin: bool = False
    """Whether the person is a super admin of the igni deployment."""
    app: str = ""
    """The app a space belongs to, on a space's token."""
    external_id: str = ""
    """The app's own name for its end user, on a space's token."""
    azp: str | None = None
    """The client the token was issued to, when the token names one."""

    UNREADABLE: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "exp": "the token's exp or iat is not a number",
            "iat": "the token's exp or iat is not a number",
            "iat_ms": "the token's iat is not a number",
        }
    )
    """What a token is refused with when a claim of it cannot be read, by claim."""

    @field_validator(
        "iss",
        "sub",
        "org",
        "org_name",
        "org_role",
        "email",
        "name",
        "app",
        "external_id",
        mode="before",
    )
    @classmethod
    def _text(cls, value: object) -> str:
        """A claim as text: a missing or null claim is empty, a number is written out."""
        return str(value or "")

    @field_validator("azp", mode="before")
    @classmethod
    def _optional_text(cls, value: object) -> str | None:
        """A claim as text, kept apart from one the token does not carry."""
        return None if value is None else str(value)

    @field_validator("super_admin", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        """Only the JSON `true` is true: `"true"`, `1` or `[true]` are not."""
        return value is True

    @field_validator("exp", "iat", mode="before")
    @classmethod
    def _instant(cls, value: object) -> float:
        """Seconds since the epoch, read as `float` reads them (text included).

        NaN and infinity compare false with everything: a token with an `exp`
        of either would never expire, so neither is a point in time.
        """
        try:
            seconds = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError("not a number") from None
        if not math.isfinite(seconds):
            raise ValueError("not a finite number")
        return seconds

    @field_validator("iat_ms", mode="before")
    @classmethod
    def _milliseconds(cls, value: object) -> int | None:
        """Milliseconds since the epoch, read as `int` reads them; absent is `None`."""
        if value is None:
            return None
        try:
            return int(value)  # type: ignore[call-overload, no-any-return]
        except (TypeError, ValueError, OverflowError):
            raise ValueError("not a number") from None

    @classmethod
    def read(cls, raw: dict[str, Any], *, use: Collection[str]) -> VerifiedClaims:
        """The claims of a decoded token, if it is a kind in `use`. `TokenRefused` otherwise.

        Args:
            raw: The claims as the token's signature check decoded them.
            use: The ``token_use`` values this route takes.
        """
        token_use = raw.get("token_use")
        if not isinstance(token_use, str) or token_use not in use:
            raise TokenRefused(
                f"the wrong kind of token: token_use {token_use!r}, "
                f"and this takes {' or '.join(sorted(use))}"
            )
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            claim = str(exc.errors()[0]["loc"][0])
            raise TokenRefused(cls.UNREADABLE.get(claim, TokenRefused().reason)) from None

    @property
    def issued_ms(self) -> int:
        """`iat_ms`; a token without it counts from the start of its `iat` second."""
        return self.iat_ms if self.iat_ms is not None else int(self.iat * 1000)

    @property
    def is_igni(self) -> bool:
        """Whether this is igni's own call to the service, not anybody's session."""
        return self.token_use == TokenUse.IGNI

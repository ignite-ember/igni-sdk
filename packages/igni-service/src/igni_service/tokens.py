"""Tokens igni signed for this service, checked against igni's keys.

A token is accepted only when all of these hold — each closes a
different door:

* the header names RS256 (chosen here, never by the token) and a `kid`
  igni publishes, and the signature verifies under that key;
* `iss` is igni's issuer;
* `aud` is **this service's own URL** — a token igni minted for another
  service, or for igni itself, is not a token for this one;
* `token_use` is the kind the route takes: `user` for a person, `igni`
  for igni calling this service, and — only where the service accepts them
  (`accepted_callers`) — `app` and `space` for an app or an app's end user
  (igni's service-identity §9.2, §17); a refresh token is not an access
  token, a person is not igni, and an app is not a person;
* `exp` is in the future, and `iat` and `sub` are present.

Everything a service needs about a person is in their token. Nothing is
asked of igni per request; somebody removed from the organisation stops
getting in when their ten-minute token expires and igni will not renew it.
"""

from __future__ import annotations

from collections.abc import Collection
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import jwt
from pydantic import BaseModel, ConfigDict

from igni_service.clock import Clock
from igni_service.crypto import ALGORITHM
from igni_service.errors import IgniError
from igni_service.jwks import IgniKeys
from igni_service.server import IgniServer

if TYPE_CHECKING:
    from igni_service.revocations import RevocationFeed


class TokenUse:
    """`token_use` values a service accepts."""

    USER = "user"
    IGNI = "igni"
    APP = "app"
    """An app acting as itself, exchanged for this service (igni's service-identity §9.2)."""
    SPACE = "space"
    """One end user of an app, a producer of its own (§17), exchanged for this service."""


class CallerKind(StrEnum):
    """Who a request may come from: a person, an app, or an app's space."""

    PERSON = "person"
    """A person, with the token igni issued them for this service (`Person`)."""
    APP = "app"
    """An app acting as itself (`App`)."""
    SPACE = "space"
    """One end user of an app, a producer of its own (`Space`)."""

    @property
    def token_use(self) -> str:
        """The `token_use` claim a token of this kind carries: `user`, `app` or `space`."""
        return TokenUse.USER if self is CallerKind.PERSON else self.value


#: Everything about a token's signature, said as one thing: which check
#: failed (algorithm, key id, signature) is not for whoever holds it.
_NOT_SIGNED = "the token is not signed by igni server's keys"
_NO_ORGANISATION = "the token names no person, or no organisation"


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


class Person(BaseModel):
    """A person, as their token describes them, in the one organisation it names."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    user_id: str
    """The person's igni user id (the token's `sub`)."""
    org_id: str
    """The organisation the token is for; every call it makes is in this one."""
    org_name: str = ""
    """The organisation's display name, when the token carries it."""
    org_role: str = "member"
    """`admin` or `member` in `org_id`."""
    email: str = ""
    """The person's email address, when the token carries it."""
    name: str = ""
    """The person's display name, when the token carries it."""
    super_admin: bool = False
    """Whether the person is a super admin of the igni deployment. It does not
    make them an admin of `org_id`."""

    @property
    def kind(self) -> CallerKind:
        """Always `CallerKind.PERSON`: what a `match` on a `Caller` reads."""
        return CallerKind.PERSON

    @property
    def is_org_admin(self) -> bool:
        """Whether the person is an admin of `org_id` (`org_role == "admin"`)."""
        return self.org_role == "admin"

    @property
    def display_name(self) -> str:
        """Their name, or their email address when the token has no name."""
        return self.name or self.email

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> Person:
        """The person a verified token's claims describe (`sub`, `org`, `org_role`, ...).

        Args:
            claims: The verified claims of a token, as ``TokenVerifier.claims``
                read them: the person's ``sub``, ``org``, ``org_name``,
                ``org_role``, ``email``, ``name`` and ``super_admin``.
        """
        return cls(
            user_id=str(claims.get("sub") or ""),
            org_id=str(claims.get("org") or ""),
            org_name=str(claims.get("org_name") or ""),
            org_role=str(claims.get("org_role") or "member"),
            email=str(claims.get("email") or ""),
            name=str(claims.get("name") or ""),
            super_admin=claims.get("super_admin") is True,
        )


class App(BaseModel):
    """An app acting as itself: igni's `app` token for this service."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    app_id: str
    """The app's id, as an org admin registered it (the token's `sub`)."""
    org_id: str
    """The organisation the app belongs to."""
    name: str = ""
    """The app's display name, when the token carries it."""

    @property
    def kind(self) -> CallerKind:
        """Always `CallerKind.APP`."""
        return CallerKind.APP

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> App:
        """The app a verified `app` token's claims describe.

        Args:
            claims: The verified claims of an ``app`` token, as
                ``TokenVerifier.claims`` read them: the app's ``sub``, its
                ``org`` and its ``name``.
        """
        return cls(
            app_id=str(claims.get("sub") or ""),
            org_id=str(claims.get("org") or ""),
            name=str(claims.get("name") or ""),
        )


class Space(BaseModel):
    """One end user of an app, a producer of its own: igni's `space` token for this service."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    space_id: str
    """The space's id at igni (the token's `sub`)."""
    org_id: str
    """The organisation the space's app belongs to."""
    app_id: str
    """The app the space belongs to."""
    external_id: str = ""
    """The app's own name for its end user."""

    @property
    def kind(self) -> CallerKind:
        """Always `CallerKind.SPACE`."""
        return CallerKind.SPACE

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> Space:
        """The space a verified `space` token's claims describe.

        Args:
            claims: The verified claims of a ``space`` token, as
                ``TokenVerifier.claims`` read them: the space's ``sub``, its
                ``org``, the app's ``app`` and the app's own name for it,
                ``external_id``.
        """
        return cls(
            space_id=str(claims.get("sub") or ""),
            org_id=str(claims.get("org") or ""),
            app_id=str(claims.get("app") or ""),
            external_id=str(claims.get("external_id") or ""),
        )


Caller = Person | App | Space
"""Whoever a request comes from, typed: a person, an app or an app's space."""

PEOPLE_ONLY: frozenset[CallerKind] = frozenset({CallerKind.PERSON})
"""What a service accepts unless it says otherwise: people only."""


class IgniCall(BaseModel):
    """igni itself calling this service, for one organisation."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    org_id: str
    """The organisation igni is calling about."""


class TokenVerifier:
    """Checks tokens igni signed for this service.

    Args:
        igni: igni server itself: its address, its issuer and this service's
            own URL.
        keys: igni's public keys, which a token's signature is checked
            against.
        clock: The clock a token's ``exp`` and ``iat`` are compared with; the
            system's own by default.
        revocations: What igni has revoked, which every token but igni's own
            is checked against; nothing is checked when it is not given.
    """

    LEEWAY = 60.0
    """How far in the future an `iat` may be, for clocks that disagree."""

    def __init__(
        self,
        igni: IgniServer,
        keys: IgniKeys,
        *,
        clock: Clock | None = None,
        revocations: RevocationFeed | None = None,
    ) -> None:
        self._igni = igni
        self._keys = keys
        self._clock = clock or Clock()
        self.revocations = revocations
        """What igni has revoked since a token was issued (`igni_service.revocations`)."""

    async def claims(self, token: str, *, use: str | Collection[str]) -> dict[str, Any]:
        """The verified claims of a `use` token (or one of several) for this service.

        `TokenRefused` for a token that is not one; `IgniUnavailable` when
        it cannot be checked at all because igni's keys or issuer cannot
        be had.

        Args:
            token: The token to check, with or without the ``Bearer`` prefix.
            use: The ``token_use`` the token must carry, or the kinds of it
                this service takes.
        """
        bare = (token or "").removeprefix("Bearer ").strip()
        try:
            header = jwt.get_unverified_header(bare)
        except jwt.PyJWTError:
            raise TokenRefused("the token is not a JWT") from None
        if header.get("alg") != ALGORITHM:
            raise TokenRefused(_NOT_SIGNED)
        key = await self._keys.key(str(header.get("kid") or ""))
        if key is None:
            raise TokenRefused(_NOT_SIGNED)
        issuer = await self._igni.issuer()
        try:
            claims: dict[str, Any] = jwt.decode(
                bare,
                key.public_key(),
                algorithms=[ALGORITHM],
                audience=self._igni.own_url,
                issuer=issuer,
                # `exp` and `iat` are compared below against this object's
                # clock, so the moment a token stops working is testable
                # without waiting for it.
                options={
                    "require": ["exp", "iat", "sub", "iss", "aud"],
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
        except jwt.InvalidAudienceError:
            raise TokenRefused(
                f"the token is for another audience; this service's is {self._igni.own_url}"
            ) from None
        except jwt.InvalidIssuerError:
            raise TokenRefused("the token was issued by somebody other than igni server") from None
        except jwt.MissingRequiredClaimError as exc:
            raise TokenRefused(f"the token has no {exc.claim!r} claim") from None
        except (jwt.PyJWTError, ValueError):
            raise TokenRefused(_NOT_SIGNED) from None
        allowed = {use} if isinstance(use, str) else set(use)
        if claims.get("token_use") not in allowed:
            raise TokenRefused(
                f"the wrong kind of token: token_use {claims.get('token_use')!r}, "
                f"and this takes {' or '.join(sorted(allowed))}"
            )
        try:
            expires, issued = float(claims["exp"]), float(claims["iat"])
        except (TypeError, ValueError):
            raise TokenRefused("the token's exp or iat is not a number") from None
        now = self._clock.wall()
        if now >= expires:
            raise TokenRefused("the token has expired")
        if issued > now + self.LEEWAY:
            raise TokenRefused("the token was issued in the future; check this machine's clock")
        if self.revocations is not None and claims.get("token_use") != TokenUse.IGNI:
            # A removed person is refused at once, not when their token
            # expires; igni's own calls are not anybody's session.
            await self.revocations.check(claims)
        return claims

    async def person(self, token: str) -> Person:
        """The person a `user` token names. `TokenRefused` for anything else.

        Args:
            token: The token to read, as the person's own.
        """
        person = Person.from_claims(await self.claims(token, use=TokenUse.USER))
        if not person.user_id or not person.org_id:
            # Every user token names one organisation. One that does not
            # is not one igni minted for a person.
            raise TokenRefused(_NO_ORGANISATION)
        return person

    async def caller(self, token: str, *, accept: Collection[CallerKind] = PEOPLE_ONLY) -> Caller:
        """Whoever a token names, if it is a kind in `accept`. `TokenRefused` otherwise.

        People only unless the service says more: an app's or a space's
        token is a token for this URL all the same, and a service that
        serves people must not take an app for one.

        Args:
            token: The token to read.
            accept: The kinds of caller this service takes; people only
                unless it says more.
        """
        kinds = {CallerKind(kind) for kind in accept}
        claims = await self.claims(token, use={kind.token_use for kind in kinds})
        use = claims.get("token_use")
        caller: Caller
        if use == TokenUse.USER:
            caller = Person.from_claims(claims)
            if not caller.user_id or not caller.org_id:
                raise TokenRefused(_NO_ORGANISATION)
        elif use == TokenUse.APP:
            caller = App.from_claims(claims)
            if not caller.app_id or not caller.org_id:
                raise TokenRefused("the token names no app, or no organisation")
        else:
            caller = Space.from_claims(claims)
            if not caller.space_id or not caller.org_id or not caller.app_id:
                raise TokenRefused("the token names no space, app or organisation")
        return caller

    async def igni_call(self, token: str) -> IgniCall:
        """igni itself, for the organisation an `igni` token names.

        Args:
            token: The token igni itself signed for this service.
        """
        claims = await self.claims(token, use=TokenUse.IGNI)
        org_id = str(claims.get("org") or "")
        if not org_id or claims.get("sub") != await self._igni.issuer():
            raise TokenRefused("the token is not igni's own call for an organisation")
        return IgniCall(org_id=org_id)

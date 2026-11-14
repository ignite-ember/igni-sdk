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

What a verified token says is a `VerifiedClaims` (`igni_service.verified_claims`);
who it names is a caller model (`igni_service.callers`). Both are importable
from here too.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING, Any

import jwt

from igni_service.callers import (
    PEOPLE_ONLY,
    App,
    Caller,
    CallerKind,
    IgniCall,
    Person,
    Space,
)
from igni_service.clock import Clock
from igni_service.crypto import ALGORITHM
from igni_service.jwks import IgniKeys
from igni_service.server import IgniServer
from igni_service.verified_claims import TokenRefused, TokenUse, VerifiedClaims

if TYPE_CHECKING:
    from igni_service.revocations import RevocationFeed

#: Everything about a token's signature, said as one thing: which check
#: failed (algorithm, key id, signature) is not for whoever holds it.
_NOT_SIGNED = "the token is not signed by igni server's keys"


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

    async def claims(self, token: str, *, use: str | Collection[str]) -> VerifiedClaims:
        """The verified claims of a `use` token (or one of several) for this service.

        `TokenRefused` for a token that is not one; `IgniUnavailable` when
        it cannot be checked at all because igni's keys or issuer cannot
        be had.

        Args:
            token: The token to check, with or without the ``Bearer`` prefix.
            use: The ``token_use`` the token must carry, or the kinds of it
                this service takes.
        """
        claims = VerifiedClaims.read(
            await self._decoded(token), use={use} if isinstance(use, str) else set(use)
        )
        now = self._clock.wall()
        if now >= claims.exp:
            raise TokenRefused("the token has expired")
        if claims.iat > now + self.LEEWAY:
            raise TokenRefused("the token was issued in the future; check this machine's clock")
        if self.revocations is not None and not claims.is_igni:
            # A removed person is refused at once, not when their token
            # expires; igni's own calls are not anybody's session.
            await self.revocations.check(claims)
        return claims

    async def _decoded(self, token: str) -> dict[str, Any]:
        """The claims of a token signed by igni's keys, for this service, from igni."""
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
            decoded: dict[str, Any] = jwt.decode(
                bare,
                key.public_key(),
                algorithms=[ALGORITHM],
                audience=self._igni.own_url,
                issuer=issuer,
                # `exp` and `iat` are compared in `claims` against this
                # object's clock, so the moment a token stops working is
                # testable without waiting for it.
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
        return decoded

    async def person(self, token: str) -> Person:
        """The person a `user` token names. `TokenRefused` for anything else.

        Args:
            token: The token to read, as the person's own.
        """
        return self._person(await self.claims(token, use=TokenUse.USER))

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
        if claims.token_use == TokenUse.USER:
            return self._person(claims)
        if claims.token_use == TokenUse.APP:
            app = App.from_claims(claims)
            if not app.is_named:
                raise TokenRefused("the token names no app, or no organisation")
            return app
        space = Space.from_claims(claims)
        if not space.is_named:
            raise TokenRefused("the token names no space, app or organisation")
        return space

    @staticmethod
    def _person(claims: VerifiedClaims) -> Person:
        """The person a `user` token's claims name; every user token names one organisation."""
        person = Person.from_claims(claims)
        if not person.is_named:
            # One that does not is not one igni minted for a person.
            raise TokenRefused("the token names no person, or no organisation")
        return person

    async def igni_call(self, token: str) -> IgniCall:
        """igni itself, for the organisation an `igni` token names.

        Args:
            token: The token igni itself signed for this service.
        """
        claims = await self.claims(token, use=TokenUse.IGNI)
        if not claims.org or claims.sub != await self._igni.issuer():
            raise TokenRefused("the token is not igni's own call for an organisation")
        return IgniCall(org_id=claims.org)


__all__ = [
    "PEOPLE_ONLY",
    "App",
    "Caller",
    "CallerKind",
    "IgniCall",
    "Person",
    "Space",
    "TokenRefused",
    "TokenUse",
    "TokenVerifier",
    "VerifiedClaims",
]

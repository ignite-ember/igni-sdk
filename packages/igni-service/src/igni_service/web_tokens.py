"""The web sign-in's tokens at igni: redeemed, checked, renewed and revoked.

A sign-in's code and a session's refresh token are both exchanged at
igni's token endpoint with the service's own client assertion; the
access token that comes back is checked as any other (`token_use` =
`user`, `aud` = this service) and must be for this client (`azp`) and
name an organisation.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict

from igni_service.callers import Person
from igni_service.errors import IgniError
from igni_service.grants import AuthorizationCodeGrant, RefreshTokenGrant
from igni_service.registration import ServiceRegistration
from igni_service.server import IgniServer
from igni_service.signing import SigningKey
from igni_service.token_endpoint import IssuedTokens, TokenEndpoint
from igni_service.tokens import TokenVerifier
from igni_service.verified_claims import TokenRefused, TokenUse

logger = logging.getLogger(__name__)


class SignedIn(BaseModel):
    """What igni issued for a person, and who the access token says they are."""

    model_config = ConfigDict(frozen=True)

    person: Person
    issued: IssuedTokens


class WebTokenExchange:
    """A person's tokens asked of igni, and the access token checked for this client.

    Args:
        igni: igni server as this service reaches it.
        registration: This service's registration with igni: its client id
            is what the access token's `azp` must name.
        key: This deployment's signing key, for the client assertion.
        verifier: Checks the access token igni issued.
    """

    def __init__(
        self,
        igni: IgniServer,
        registration: ServiceRegistration,
        key: SigningKey,
        verifier: TokenVerifier,
    ) -> None:
        self._registration = registration
        self._verifier = verifier
        self._endpoint = TokenEndpoint(igni, registration, key)

    async def client_id(self) -> str:
        """This service's client id at igni, registering first when there is none."""
        return await self._registration.client_id()

    async def sign_in(self, grant: AuthorizationCodeGrant | RefreshTokenGrant) -> SignedIn:
        """Exchange `grant` at igni and check the access token it answers with.

        Raises:
            GrantRefused: igni refused the code or the refresh token.
            TokenRefused: the token is not a user token for this service and
                this client, or names no organisation.
            IgniUnavailable: igni could not be reached.
        """
        issued = await self._endpoint.grant(grant)
        claims = await self._verifier.claims(issued.access_token, use=TokenUse.USER)
        client_id = await self.client_id()
        person = Person.from_claims(claims)
        if claims.azp not in (None, client_id) or not person.is_named:
            raise TokenRefused(
                "the sign-in answered with a token for another client, or for no organisation"
            )
        return SignedIn(person=person, issued=issued)

    async def revoke(self, refresh_token: str) -> None:
        """Revoke at igni, best effort: signing out here has already happened."""
        try:
            await self._endpoint.revoke(refresh_token)
        except IgniError as exc:
            # The refresh token was only ever in the session just deleted,
            # so it is not lost to anybody; it simply stays valid at igni
            # until it expires.
            logger.warning("igni: could not revoke a sign-in on sign-out: %s", exc)

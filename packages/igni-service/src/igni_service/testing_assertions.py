"""Client authentication at the token and revocation endpoints, as igni checks it.

A `private_key_jwt` assertion (RFC 7523) proves a client when it is
signed by the client's registered key, issued and subjected by the
client, addressed to igni, alive for at most five minutes, and its
`jti` has not been seen before. A revoked client, or one still waiting
for approval when igni requires approval, is refused in igni's own
words, which the SDK reads to tell the two apart.
"""

from __future__ import annotations

import httpx
import jwt
from pydantic import BaseModel

from igni_service.clock import Clock
from igni_service.crypto import ALGORITHM
from igni_service.testing_clients import FakeClient, FakeClientRegistry
from igni_service.testing_wire import IgniAddresses, OAuthError, TokenForm

#: The longest a client assertion may live, in seconds.
MAX_ASSERTION_LIFETIME = 300

#: igni server's own words (its `assertions.py`).
REVOKED = "this client has been revoked"
WAITING = "this client is waiting for a super admin to approve it"


class AssertionResult(BaseModel):
    """The client an assertion proved, or why it proved none."""

    client: FakeClient | None = None
    #: igni's reason, when it gives one; most refusals give none.
    refusal: str | None = None

    def to_error(self) -> httpx.Response:
        return OAuthError(
            error="invalid_client", error_description=self.refusal, status=401
        ).to_response()


class ClientAssertionVerifier:
    """Checks client assertions against the registered keys, each `jti` once."""

    def __init__(
        self,
        *,
        addresses: IgniAddresses,
        clock: Clock,
        clients: FakeClientRegistry,
        require_approval: bool = False,
    ) -> None:
        self.addresses = addresses
        self.clock = clock
        self.clients = clients
        #: When set, a pending registration gets no service token.
        self.require_approval = require_approval
        #: Every `jti` already used: replay memory, which no reset forgets.
        self.jtis: set[str] = set()

    def verify(self, form: TokenForm) -> AssertionResult:
        """The client `form`'s assertion proves, or the refusal."""
        try:
            claimed = jwt.decode(form.client_assertion, options={"verify_signature": False})
        except jwt.PyJWTError:
            return AssertionResult()
        client_id = str(claimed.get("iss", ""))
        client = self.clients.get(client_id)
        if client is None:
            return AssertionResult()
        if client.is_revoked:
            return AssertionResult(refusal=REVOKED)
        if self.require_approval and not client.is_approved:
            return AssertionResult(refusal=WAITING)
        try:
            claims = jwt.decode(
                form.client_assertion,
                client.jwk.public_key(),
                algorithms=[ALGORITHM],
                audience=self.addresses.assertion_audiences(),
                issuer=client_id,
                options={
                    "require": ["exp", "jti", "sub"],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
        except jwt.PyJWTError:
            return AssertionResult()
        lifetime = float(claims["exp"]) - self.clock.wall()
        if claims.get("sub") != client_id or not 0 < lifetime <= MAX_ASSERTION_LIFETIME:
            return AssertionResult()
        if claims["jti"] in self.jtis:
            return AssertionResult()
        self.jtis.add(claims["jti"])
        return AssertionResult(client=client)


__all__ = ["MAX_ASSERTION_LIFETIME", "AssertionResult", "ClientAssertionVerifier"]

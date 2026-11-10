"""igni's signing keys, the tokens it signs with them, and where it publishes them.

`FakeSigner` signs RS256 with a `kid`, as igni does: a person's token
with their claims from the directory (`person_token`), an app's and a
space's exchanged for the service (`app_token`, `space_token`), and
igni's own call to the service (`igni_token`). `TokenOverrides` bends one
into a token a service must refuse. `keys.rotate()` publishes a new key
and signs with it, keeping the old one published.
"""

from __future__ import annotations

import httpx

from igni_service.clock import Clock
from igni_service.crypto import JwkSet, RsaKeyPair
from igni_service.testing_claims import (
    AppClaims,
    IgniClaims,
    JwtEnvelope,
    OrgClaims,
    SpaceClaims,
    TokenOverrides,
)
from igni_service.testing_directory import FakeDirectory
from igni_service.testing_wire import IgniAddresses, RoutedCall

LIFETIME = 600.0
"""How long a token igni signs lives, in seconds."""


class KeyRing:
    """igni's signing key, and every key it still publishes, by kid."""

    def __init__(self) -> None:
        self.pair = RsaKeyPair.generate()
        self.kid = "igni-key-1"
        self.published: dict[str, RsaKeyPair] = {self.kid: self.pair}

    def rotate(self) -> str:
        """Publish and sign with a new key, keeping the old one published."""
        self.pair = RsaKeyPair.generate()
        self.kid = f"igni-key-{len(self.published) + 1}"
        self.published[self.kid] = self.pair
        return self.kid

    def sign(self, payload: dict[str, object], overrides: TokenOverrides) -> str:
        """`payload` signed with the current key, or the one a test substitutes."""
        return (overrides.key or self.pair).sign_jwt(payload, kid=overrides.kid or self.kid)

    def jwks(self) -> JwkSet:
        return JwkSet(keys=[pair.public_jwk(kid) for kid, pair in self.published.items()])


class FakeSigner:
    """Signs every token igni would, and serves its metadata and keys."""

    def __init__(self, *, addresses: IgniAddresses, clock: Clock, directory: FakeDirectory) -> None:
        self.addresses = addresses
        self.clock = clock
        self.directory = directory
        self.keys = KeyRing()
        self.max_age = 300
        """How long a service may keep igni's keys, in seconds."""

    def sign(self, sub: str, claims: OrgClaims, overrides: TokenOverrides | None = None) -> str:
        """A token for `sub` carrying `claims`, as igni signs one, bent by `overrides`."""
        changes = overrides or TokenOverrides()
        now = self.clock.wall()
        envelope = JwtEnvelope(
            iss=changes.iss if changes.iss is not None else self.addresses.issuer,
            sub=changes.sub if changes.sub is not None else sub,
            aud=changes.aud if changes.aud is not None else self.addresses.service_url,
            token_use=changes.use if changes.use is not None else claims.USE,
            iat=int(now),
            iat_ms=int(now * 1000),
            exp=int(int(now) + changes.seconds(LIFETIME)),
        )
        if changes.org is not None:
            claims = claims.model_copy(update={"org": changes.org})
        payload = envelope.model_dump() | claims.model_dump(exclude_none=True)
        return self.keys.sign(payload, changes)

    def person_token(
        self, user_id: str, *, org_id: str, overrides: TokenOverrides | None = None
    ) -> str:
        """A user token as igni issues one: the person's claims, for one organisation."""
        return self.sign(user_id, self.directory.claims_for(org_id, user_id), overrides)

    def app_token(
        self, app_id: str, *, org_id: str, name: str = "", overrides: TokenOverrides | None = None
    ) -> str:
        """An app's token exchanged for this service (igni's service-identity §9.2)."""
        return self.sign(app_id, AppClaims(org=org_id, name=name or app_id), overrides)

    def space_token(
        self, space_id: str, space: SpaceClaims, overrides: TokenOverrides | None = None
    ) -> str:
        """A space's token exchanged for this service (§9.2, §17)."""
        return self.sign(space_id, space, overrides)

    def igni_token(self, org_id: str, overrides: TokenOverrides | None = None) -> str:
        """What igni signs to call the service about one organisation; its subject is igni."""
        return self.sign(self.addresses.issuer, IgniClaims(org=org_id), overrides)

    # ── Routes ──────────────────────────────────────────────────────

    def discovery(self, call: RoutedCall) -> httpx.Response:
        """`/.well-known/openid-configuration`."""
        return httpx.Response(200, json=self.addresses.discovery().model_dump())

    def jwks(self, call: RoutedCall) -> httpx.Response:
        """`/.well-known/jwks.json`, cacheable for `max_age`."""
        return httpx.Response(
            200,
            json=self.keys.jwks().model_dump(exclude_none=True),
            headers={"Cache-Control": f"public, max-age={self.max_age}"},
        )


__all__ = ["FakeSigner", "KeyRing"]

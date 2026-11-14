"""igni's signing keys as the fake keeps them, and the metadata and keys it publishes."""

from __future__ import annotations

from typing import Any

import jwt

from igni_service.crypto import RsaKeyPair
from igni_service.testing import FakeIgni, ManualClock
from igni_service.testing_claims import TokenOverrides
from igni_service.testing_signer import LIFETIME, KeyRing
from igni_service.testing_wire import RoutedCall, SeenRequest

from .conftest import ORG


def claims_of(token: str, pair: RsaKeyPair) -> dict[str, Any]:
    key = pair.public_jwk().model_dump(exclude_none=True)
    claims: dict[str, Any] = jwt.decode(
        token,
        jwt.PyJWK(key).key,
        algorithms=["RS256"],
        options={"verify_aud": False, "verify_exp": False, "verify_iat": False},
    )
    return claims


def call() -> RoutedCall:
    return RoutedCall(seen=SeenRequest(method="GET", path="/", headers={}, body=b""))


def test_the_ring_starts_with_one_key_and_each_rotation_adds_the_next_kid() -> None:
    ring = KeyRing()
    first = ring.pair

    assert ring.kid == "igni-key-1" and list(ring.published) == ["igni-key-1"]
    assert [ring.rotate(), ring.rotate()] == ["igni-key-2", "igni-key-3"]

    assert ring.kid == "igni-key-3" and ring.pair is ring.published["igni-key-3"]
    assert ring.published["igni-key-1"] is first
    assert [jwk.kid for jwk in ring.jwks().keys] == ["igni-key-1", "igni-key-2", "igni-key-3"]


def test_the_ring_signs_with_the_current_key_under_its_kid_unless_a_test_substitutes() -> None:
    ring = KeyRing()
    ring.rotate()
    other = RsaKeyPair.generate()

    own = ring.sign({"a": 1}, TokenOverrides())
    kid_only = ring.sign({"a": 1}, TokenOverrides(kid="x"))
    key_only = ring.sign({"a": 1}, TokenOverrides(key=other))

    assert jwt.get_unverified_header(own)["kid"] == "igni-key-2"
    assert claims_of(own, ring.pair) == {"a": 1}
    assert jwt.get_unverified_header(kid_only)["kid"] == "x"
    assert claims_of(kid_only, ring.pair) == {"a": 1}
    assert jwt.get_unverified_header(key_only)["kid"] == "igni-key-2"
    assert claims_of(key_only, other) == {"a": 1}


def test_a_token_lives_ten_minutes_from_now_to_the_second(
    fake: FakeIgni, clock: ManualClock
) -> None:
    clock.advance(0.75)
    token = fake.signer.person_token("u-ada", org_id=ORG)

    claims = claims_of(token, fake.signer.keys.pair)

    now = fake.clock.wall()
    assert LIFETIME == 600.0
    assert claims["iat"] == int(now) and claims["iat_ms"] == int(now * 1000)
    assert claims["exp"] == int(now) + 600


def test_a_lifetime_of_zero_and_a_fraction_move_the_expiry_by_whole_seconds(
    fake: FakeIgni,
) -> None:
    zero = fake.signer.person_token("u-ada", org_id=ORG, overrides=TokenOverrides(lifetime=0))
    half = fake.signer.person_token("u-ada", org_id=ORG, overrides=TokenOverrides(lifetime=0.5))
    pair = fake.signer.keys.pair

    assert claims_of(zero, pair)["exp"] == claims_of(zero, pair)["iat"]
    assert claims_of(half, pair)["exp"] == claims_of(half, pair)["iat"]


def test_igni_signs_the_call_to_a_service_with_itself_as_the_subject(fake: FakeIgni) -> None:
    claims = claims_of(fake.signer.igni_token(ORG), fake.signer.keys.pair)

    assert claims["sub"] == claims["iss"] == fake.addresses.issuer
    assert (claims["token_use"], claims["org"]) == ("igni", ORG)
    assert claims["aud"] == fake.addresses.service_url


def test_an_app_token_names_the_app_and_falls_back_to_its_id_for_a_name(fake: FakeIgni) -> None:
    named = claims_of(
        fake.signer.app_token("app-bot", org_id=ORG, name="Bot"), fake.signer.keys.pair
    )
    unnamed = claims_of(fake.signer.app_token("app-bot", org_id=ORG), fake.signer.keys.pair)

    assert (named["sub"], named["name"], named["token_use"]) == ("app-bot", "Bot", "app")
    assert unnamed["name"] == "app-bot"


def test_the_token_after_a_rotation_is_signed_by_the_new_key_and_the_old_one_still_verifies(
    fake: FakeIgni,
) -> None:
    keys = fake.signer.keys
    old_pair = keys.pair
    before = fake.signer.person_token("u-ada", org_id=ORG)

    keys.rotate()
    after = fake.signer.person_token("u-ada", org_id=ORG)

    assert jwt.get_unverified_header(before)["kid"] == "igni-key-1"
    assert jwt.get_unverified_header(after)["kid"] == "igni-key-2"
    assert claims_of(before, old_pair)["sub"] == "u-ada"
    assert claims_of(after, keys.pair)["sub"] == "u-ada"


def test_the_discovery_document_is_the_addresses_metadata(fake: FakeIgni) -> None:
    response = fake.signer.discovery(call())

    assert response.status_code == 200
    assert response.json() == fake.addresses.discovery().model_dump()
    assert response.json()["jwks_uri"] == f"{fake.addresses.issuer}/.well-known/jwks.json"


def test_the_keys_are_published_cacheable_for_the_max_age_the_test_sets(fake: FakeIgni) -> None:
    fake.signer.keys.rotate()

    default = fake.signer.jwks(call())
    fake.signer.max_age = 7
    short = fake.signer.jwks(call())

    assert default.headers["cache-control"] == "public, max-age=300"
    assert short.headers["cache-control"] == "public, max-age=7"
    assert [key["kid"] for key in default.json()["keys"]] == ["igni-key-1", "igni-key-2"]
    assert all("d" not in key for key in default.json()["keys"]), "the public halves only"

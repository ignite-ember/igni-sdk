"""The claims igni signs and what a test may bend about a token."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt
import pytest
from pydantic import BaseModel, ValidationError

from igni_service.crypto import RsaKeyPair
from igni_service.testing import FakeIgni, ManualClock, PersonClaims, SpaceClaims, TokenOverrides
from igni_service.testing_claims import AppClaims, IgniClaims, JwtEnvelope

from .conftest import ORG


def payload(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


def verified_by(token: str, pair: RsaKeyPair) -> dict[str, Any]:
    """The token's claims, if `pair`'s public key signed it (its clock aside)."""
    return jwt.decode(
        token,
        pair.public_jwk().public_key(),
        algorithms=["RS256"],
        audience=FakeIgni.SERVICE_URL,
        options={"verify_exp": False, "verify_iat": False},
    )


class TestTheLifetime:
    def test_no_change_is_the_default(self) -> None:
        assert TokenOverrides().seconds(600) == 600
        assert TokenOverrides().seconds(0.5) == 0.5

    @pytest.mark.parametrize("lifetime", [30, 30.5, 0, -1, -3600.25])
    def test_a_number_is_its_own_seconds(self, lifetime: float) -> None:
        assert TokenOverrides(lifetime=lifetime).seconds(600) == lifetime

    def test_a_duration_is_its_total_seconds(self) -> None:
        assert TokenOverrides(lifetime=timedelta(minutes=5)).seconds(600) == 300
        assert TokenOverrides(lifetime=timedelta(days=1, seconds=1.5)).seconds(600) == 86401.5
        assert TokenOverrides(lifetime=timedelta(seconds=-10)).seconds(600) == -10
        assert TokenOverrides(lifetime=timedelta(0)).seconds(600) == 0

    def test_nothing_changed_by_default(self) -> None:
        assert TokenOverrides().model_dump() == dict.fromkeys(
            ("aud", "iss", "use", "sub", "org", "kid", "key", "lifetime")
        )


class TestWhatTokensCarry:
    def test_a_person_s_token_carries_the_envelope_and_the_directory_s_claims(
        self, fake: FakeIgni, clock: ManualClock
    ) -> None:
        claims = payload(fake.signer.person_token("u-ada", org_id=ORG))

        assert claims["iss"] == FakeIgni.ISSUER
        assert claims["aud"] == FakeIgni.SERVICE_URL
        assert (claims["sub"], claims["token_use"], claims["org"]) == ("u-ada", "user", ORG)
        assert (claims["org_role"], claims["super_admin"]) == ("admin", False)
        assert claims["iat"] == int(clock.wall())
        assert claims["iat_ms"] // 1000 == claims["iat"]
        assert claims["exp"] - claims["iat"] == 600
        assert "azp" not in claims

    def test_an_igni_token_is_about_one_organisation_and_its_subject_is_igni(
        self, fake: FakeIgni
    ) -> None:
        claims = payload(fake.signer.igni_token(ORG))

        assert (claims["sub"], claims["token_use"], claims["org"]) == (
            FakeIgni.ISSUER,
            "igni",
            ORG,
        )

    def test_the_uses_of_each_kind_of_claim(self) -> None:
        assert [c.USE for c in (PersonClaims, AppClaims, SpaceClaims, IgniClaims)] == [
            "user",
            "app",
            "space",
            "igni",
        ]

    def test_defaults_of_a_person_s_claims(self) -> None:
        claims = PersonClaims(org="o")

        assert (claims.org_role, claims.super_admin, claims.azp) == ("member", False, None)
        assert (claims.org_name, claims.email, claims.name) == ("", "", "")

    def test_an_app_and_a_space_are_their_own_kind_and_no_other(self) -> None:
        assert AppClaims(org="o", name="Bot").kind == "app"
        assert SpaceClaims(org="o", app="a", external_id="e").kind == "space"
        with pytest.raises(ValidationError):
            AppClaims.model_validate({"org": "o", "name": "Bot", "kind": "space"})
        with pytest.raises(ValidationError):
            SpaceClaims.model_validate({"org": "o", "app": "a", "external_id": "e", "kind": "app"})

    @pytest.mark.parametrize(
        ("model", "given"),
        [
            (AppClaims, {"org": "o"}),
            (AppClaims, {"name": "Bot"}),
            (SpaceClaims, {"org": "o", "app": "a"}),
            (SpaceClaims, {"org": "o", "external_id": "e"}),
            (SpaceClaims, {"app": "a", "external_id": "e"}),
            (IgniClaims, {}),
            (PersonClaims, {}),
        ],
    )
    def test_a_claim_set_without_what_it_requires_is_refused(
        self, model: type[BaseModel], given: dict[str, Any]
    ) -> None:
        with pytest.raises(ValidationError):
            model.model_validate(given)

    def test_the_envelope_requires_every_claim(self) -> None:
        with pytest.raises(ValidationError):
            JwtEnvelope.model_validate({"iss": "i", "sub": "s", "aud": "a"})


class TestWhatATestBends:
    def test_an_empty_organisation_is_a_token_for_none_not_an_unchanged_one(
        self, fake: FakeIgni
    ) -> None:
        bent = fake.signer.person_token("u-ada", org_id=ORG, overrides=TokenOverrides(org=""))
        plain = fake.signer.person_token("u-ada", org_id=ORG, overrides=TokenOverrides(org=None))

        assert payload(bent)["org"] == ""
        assert payload(plain)["org"] == ORG

    def test_the_issuer_and_the_kind_are_what_the_test_says(self, fake: FakeIgni) -> None:
        for token in (
            fake.signer.person_token(
                "u-ada", org_id=ORG, overrides=TokenOverrides(iss="x", use="y")
            ),
            fake.signer.igni_token(ORG, TokenOverrides(iss="x", use="y")),
            fake.signer.app_token("a", org_id=ORG, overrides=TokenOverrides(iss="x", use="y")),
            fake.signer.space_token(
                "s",
                SpaceClaims(org=ORG, app="a", external_id="e"),
                TokenOverrides(iss="x", use="y"),
            ),
        ):
            claims = payload(token)
            assert (claims["iss"], claims["token_use"]) == ("x", "y")

    def test_the_audience_and_the_subject_are_what_the_test_says(self, fake: FakeIgni) -> None:
        claims = payload(
            fake.signer.person_token(
                "u-ada", org_id=ORG, overrides=TokenOverrides(aud="http://other", sub="u-max")
            )
        )

        assert (claims["aud"], claims["sub"]) == ("http://other", "u-max")

    def test_the_lifetime_moves_the_expiry(self, fake: FakeIgni) -> None:
        claims = payload(
            fake.signer.person_token(
                "u-ada", org_id=ORG, overrides=TokenOverrides(lifetime=timedelta(seconds=-5))
            )
        )

        assert claims["exp"] == claims["iat"] - 5

    def test_the_key_id_is_what_the_test_says(self, fake: FakeIgni) -> None:
        token = fake.signer.person_token("u-ada", org_id=ORG, overrides=TokenOverrides(kid="nope"))

        assert jwt.get_unverified_header(token)["kid"] == "nope"

    def test_another_key_signs_a_token_igni_s_keys_do_not_verify(self, fake: FakeIgni) -> None:
        other = RsaKeyPair.generate()
        token = fake.signer.person_token("u-ada", org_id=ORG, overrides=TokenOverrides(key=other))

        assert verified_by(token, other)["sub"] == "u-ada"
        with pytest.raises(jwt.InvalidSignatureError):
            verified_by(token, fake.signer.keys.pair)

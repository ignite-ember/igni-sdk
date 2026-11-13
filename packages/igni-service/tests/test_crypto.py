"""RSA keys, JWKs and what is signed with them: the shapes igni verifies, with real keys."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from jwt.algorithms import RSAAlgorithm

from igni_service.crypto import (
    ALGORITHM,
    AssetClaim,
    Base64Url,
    BundleClaim,
    Jwk,
    JwkSet,
    RsaKeyPair,
)


@pytest.fixture(scope="module")
def pair() -> RsaKeyPair:
    return RsaKeyPair.generate()


@pytest.fixture(scope="module")
def other() -> RsaKeyPair:
    return RsaKeyPair.generate()


def unpadded(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def jws_parts(token: str) -> tuple[dict[str, Any], bytes]:
    header, payload, _ = token.split(".")
    return json.loads(unpadded(header)), unpadded(payload)


class TestBase64Url:
    def test_it_is_urlsafe_and_unpadded(self) -> None:
        assert Base64Url.encode(b"\xfb\xff\xfe") == "-__-"
        assert Base64Url.encode(b"a") == "YQ"
        assert Base64Url.encode(b"") == ""

    @pytest.mark.parametrize(
        ("value", "encoded"),
        [
            (0, "AA"),  # one zero byte, not nothing
            (1, "AQ"),
            (255, "_w"),  # top bit set: no sign byte in front
            (256, "AQA"),  # two bytes, minimal
            (65537, "AQAB"),  # the usual RSA exponent
        ],
    )
    def test_an_integer_is_its_minimal_big_endian_bytes(self, value: int, encoded: str) -> None:
        assert Base64Url.uint(value) == encoded


class TestTheJwk:
    def test_unset_members_are_left_out_of_its_json(self) -> None:
        assert Jwk(kty="RSA", kid="k", n="AQAB").as_dict() == {
            "kty": "RSA",
            "kid": "k",
            "n": "AQAB",
        }

    def test_a_member_it_does_not_know_is_kept(self) -> None:
        jwk = Jwk.model_validate({"kty": "RSA", "kid": "k", "x5t": "abc"})

        assert jwk.as_dict()["x5t"] == "abc"

    def test_it_is_frozen(self) -> None:
        with pytest.raises(Exception, match="frozen"):
            Jwk(kty="RSA").kid = "other"

    def test_its_public_key_verifies_what_the_pair_signed(
        self, pair: RsaKeyPair, other: RsaKeyPair
    ) -> None:
        token = pair.sign_jwt({"sub": "u"})

        claims = jwt.decode(token, pair.public_jwk().public_key(), algorithms=[ALGORITHM])
        assert claims == {"sub": "u"}
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, other.public_jwk().public_key(), algorithms=[ALGORITHM])


class TestTheJwkSet:
    def test_find_returns_the_rsa_key_with_that_id(
        self, pair: RsaKeyPair, other: RsaKeyPair
    ) -> None:
        keys = JwkSet(keys=[pair.public_jwk(), other.public_jwk()])

        assert keys.find(other.thumbprint()) == other.public_jwk()
        assert keys.find(pair.thumbprint()) == pair.public_jwk()

    def test_an_unknown_id_is_none(self, pair: RsaKeyPair) -> None:
        assert JwkSet(keys=[pair.public_jwk()]).find("nobody") is None
        assert JwkSet().find("nobody") is None

    def test_a_key_of_another_type_is_not_found_by_its_id(self) -> None:
        keys = JwkSet.model_validate({"keys": [{"kty": "EC", "kid": "ec-1"}]})

        assert keys.find("ec-1") is None


class TestTheKeyPair:
    def test_a_new_key_is_2048_bits_and_never_the_same(
        self, pair: RsaKeyPair, other: RsaKeyPair
    ) -> None:
        assert pair.private_key.key_size == 2048
        assert pair.thumbprint() != other.thumbprint()

    def test_the_pem_round_trips_to_the_same_key(self, pair: RsaKeyPair) -> None:
        pem = pair.private_pem()

        assert pem.startswith("-----BEGIN PRIVATE KEY-----")
        assert RsaKeyPair.from_pem(pem).thumbprint() == pair.thumbprint()
        assert RsaKeyPair.from_pem(pem).private_pem() == pem

    def test_a_key_that_is_not_rsa_is_refused(self) -> None:
        for key in (ec.generate_private_key(ec.SECP256R1()), ed25519.Ed25519PrivateKey.generate()):
            pem = key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode()
            with pytest.raises(ValueError, match="not an RSA private key"):
                RsaKeyPair.from_pem(pem)

    def test_garbage_and_an_encrypted_key_are_refused(self, pair: RsaKeyPair) -> None:
        encrypted = pair.private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b"secret"),
        ).decode()

        with pytest.raises(ValueError):
            RsaKeyPair.from_pem("not a pem")
        with pytest.raises(TypeError):
            RsaKeyPair.from_pem(encrypted)

    def test_the_thumbprint_is_rfc_7638_over_e_kty_n(self, pair: RsaKeyPair) -> None:
        # Computed here from the key's JWK as PyJWT writes it, not with the SDK's encoder.
        members = RSAAlgorithm.to_jwk(pair.private_key.public_key(), as_dict=True)
        canonical = f'{{"e":"{members["e"]}","kty":"RSA","n":"{members["n"]}"}}'
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest())
            .rstrip(b"=")
            .decode()
        )

        assert pair.thumbprint() == expected
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", expected)

    def test_the_public_jwk_is_an_rs256_signing_key_named_by_its_thumbprint(
        self, pair: RsaKeyPair
    ) -> None:
        jwk = pair.public_jwk()
        members = RSAAlgorithm.to_jwk(pair.private_key.public_key(), as_dict=True)

        assert (jwk.kty, jwk.use, jwk.alg) == ("RSA", "sig", "RS256")
        assert jwk.kid == pair.thumbprint()
        assert (jwk.n, jwk.e) == (members["n"], members["e"])
        assert pair.public_jwk("mine").kid == "mine"
        assert "d" not in jwk.as_dict()

    def test_a_jwt_carries_its_claims_and_a_kid_in_an_rs256_header(self, pair: RsaKeyPair) -> None:
        token = pair.sign_jwt({"sub": "u", "n": 1})

        header = jwt.get_unverified_header(token)
        assert header["alg"] == "RS256"
        assert header["kid"] == pair.thumbprint()
        assert jwt.get_unverified_header(pair.sign_jwt({}, kid="named"))["kid"] == "named"

    def test_a_signed_token_does_not_verify_under_another_algorithm(self, pair: RsaKeyPair) -> None:
        token = pair.sign_jwt({"sub": "u"})

        with pytest.raises(jwt.InvalidAlgorithmError):
            jwt.decode(token, pair.public_jwk().public_key(), algorithms=["HS256"])

    @pytest.mark.parametrize("payload", [b"raw bytes", b"", "grüße — 日本".encode()])
    def test_bytes_are_signed_as_a_jws_that_verifies(
        self, pair: RsaKeyPair, payload: bytes
    ) -> None:
        token = pair.sign_bytes(payload, kid="k1")

        header, body = jws_parts(token)
        assert header["alg"] == "RS256" and header["kid"] == "k1"
        assert body == payload
        public = pair.public_jwk().public_key()
        public.verify(
            unpadded(token.rsplit(".", 1)[1]),
            token.rsplit(".", 1)[0].encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

    def test_a_bundle_is_signed_as_its_claim_under_the_thumbprint(self, pair: RsaKeyPair) -> None:
        claim = BundleClaim(extension="acme.example", version="1.2.3", sha256="ab" * 32)

        header, body = jws_parts(pair.sign_bundle(claim))

        assert header["kid"] == pair.thumbprint()
        assert json.loads(body) == {
            "extension": "acme.example",
            "version": "1.2.3",
            "sha256": "ab" * 32,
        }

    def test_an_asset_is_signed_as_its_claim_under_the_thumbprint(self, pair: RsaKeyPair) -> None:
        claim = AssetClaim(asset="cd" * 32, size=1234)

        header, body = jws_parts(pair.sign_asset(claim))

        assert header["kid"] == pair.thumbprint()
        assert json.loads(body) == {"asset": "cd" * 32, "size": 1234}

    def test_a_token_id_is_32_hex_characters_and_new_every_time(self) -> None:
        ids = {RsaKeyPair.new_jti() for _ in range(200)}

        assert len(ids) == 200
        assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in ids)


def test_a_key_made_by_cryptography_is_accepted_as_it_is(pair: RsaKeyPair) -> None:
    assert RsaKeyPair(pair.private_key).thumbprint() == pair.thumbprint()
    assert isinstance(pair.private_key, rsa.RSAPrivateKey)

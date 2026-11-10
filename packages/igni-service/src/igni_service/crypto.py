"""RSA keys, JWKs, and the two things signed with them.

RS256 everywhere, 2048 bits, the same as igni's own key. A JWK's `kid`
is its RFC 7638 thumbprint, which is also what a super admin compares in
igni's portal before approving a service.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.api_jws import PyJWS
from pydantic import BaseModel, ConfigDict, Field

ALGORITHM = "RS256"
"""The only algorithm on this wire. Chosen here, never by a token's header."""


class Base64Url:
    """base64url without padding, as JOSE writes it."""

    @staticmethod
    def encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    @classmethod
    def uint(cls, value: int) -> str:
        return cls.encode(value.to_bytes((value.bit_length() + 7) // 8 or 1, "big"))


class Jwk(BaseModel):
    """One public key, as a JWK set carries it."""

    model_config = ConfigDict(extra="allow", frozen=True, use_attribute_docstrings=True)

    kty: str
    """The key type: `RSA`."""
    kid: str = ""
    """The key's id; this SDK uses its RFC 7638 thumbprint."""
    n: str | None = None
    """An RSA key's modulus, base64url."""
    e: str | None = None
    """An RSA key's exponent, base64url."""
    alg: str | None = None
    """The algorithm it signs with: `RS256`."""
    use: str | None = None
    """What it is for: `sig`."""

    def as_dict(self) -> dict[str, Any]:
        """The key as JSON, its unset members left out."""
        return self.model_dump(exclude_none=True)

    def public_key(self) -> Any:
        """The key as PyJWT verifies with it."""
        return jwt.PyJWK(self.as_dict(), algorithm=ALGORITHM).key


class JwkSet(BaseModel):
    """A JWK set (RFC 7517): what igni publishes at its JWKS address."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    keys: list[Jwk] = Field(default_factory=list)
    """The keys in the set."""

    def find(self, kid: str) -> Jwk | None:
        """The RSA key with id `kid`, or `None`."""
        return next((key for key in self.keys if key.kid == kid and key.kty == "RSA"), None)


class BundleClaim(BaseModel):
    """What the signature over an extension bundle says (§8)."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    extension: str
    """The extension's manifest `id`."""
    version: str
    """Its manifest `version`."""
    sha256: str
    """The SHA-256 of the bundle's bytes, hex."""


class AssetClaim(BaseModel):
    """What the signature over one uploaded asset says (§8.2)."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    asset: str
    """The asset's SHA-256, hex: its name at igni."""
    size: int
    """Its size in bytes."""


class RsaKeyPair:
    """A private RSA key and what is derived from it."""

    KEY_SIZE = 2048
    """The size of a new key, in bits."""

    def __init__(self, private_key: rsa.RSAPrivateKey) -> None:
        self._private = private_key

    @classmethod
    def generate(cls) -> RsaKeyPair:
        """A new key pair, `KEY_SIZE` bits."""
        return cls(rsa.generate_private_key(public_exponent=65537, key_size=cls.KEY_SIZE))

    @classmethod
    def from_pem(cls, pem: str) -> RsaKeyPair:
        """The key pair in an unencrypted PKCS#8 PEM. Raises `ValueError` for anything but an RSA
        key.
        """
        loaded = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(loaded, rsa.RSAPrivateKey):
            raise ValueError("not an RSA private key")
        return cls(loaded)

    @property
    def private_key(self) -> rsa.RSAPrivateKey:
        """The private key, as `cryptography` holds it."""
        return self._private

    def private_pem(self) -> str:
        """The private key as unencrypted PKCS#8 PEM: keep it secret."""
        return self._private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

    def thumbprint(self) -> str:
        """RFC 7638: SHA-256 over `{"e","kty","n"}`, in that order, no spaces."""
        numbers = self._private.public_key().public_numbers()
        members = {"e": Base64Url.uint(numbers.e), "kty": "RSA", "n": Base64Url.uint(numbers.n)}
        canonical = json.dumps(members, separators=(",", ":"), sort_keys=True).encode()
        return Base64Url.encode(hashlib.sha256(canonical).digest())

    def public_jwk(self, kid: str | None = None) -> Jwk:
        """The public half. `kid` is the thumbprint unless named."""
        numbers = self._private.public_key().public_numbers()
        return Jwk(
            kty="RSA",
            use="sig",
            alg=ALGORITHM,
            kid=kid or self.thumbprint(),
            n=Base64Url.uint(numbers.n),
            e=Base64Url.uint(numbers.e),
        )

    def sign_jwt(self, claims: dict[str, Any], *, kid: str | None = None) -> str:
        """A compact JWT over `claims`, RS256, with `kid` in its header."""
        return jwt.encode(
            claims, self._private, algorithm=ALGORITHM, headers={"kid": kid or self.thumbprint()}
        )

    def sign_bytes(self, payload: bytes, *, kid: str | None = None) -> str:
        """A compact JWS over arbitrary bytes, RS256, with `kid` in its header."""
        return PyJWS().encode(
            payload, self._private, algorithm=ALGORITHM, headers={"kid": kid or self.thumbprint()}
        )

    def sign_bundle(self, claim: BundleClaim) -> str:
        """The signature igni checks on a bundle upload: a JWS over `claim`."""
        return self.sign_bytes(claim.model_dump_json().encode())

    def sign_asset(self, claim: AssetClaim) -> str:
        """The signature igni checks on an asset upload: a JWS over `claim`."""
        return self.sign_bytes(claim.model_dump_json().encode())

    @staticmethod
    def new_jti() -> str:
        """A token id nobody else will use."""
        return uuid.uuid4().hex

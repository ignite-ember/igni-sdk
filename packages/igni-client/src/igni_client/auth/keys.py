"""An app's RSA key: made, loaded, published as a JWK set, and signing assertions."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Final, Literal

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel

#: The only signing algorithm on this wire.
ALGORITHM: Final = "RS256"


class Jwk(BaseModel):
    """One public RSA signing key, as RFC 7517 writes it."""

    kty: Literal["RSA"] = "RSA"
    use: Literal["sig"] = "sig"
    alg: Literal["RS256"] = ALGORITHM
    kid: str
    n: str
    e: str


class JwkSet(BaseModel):
    """A JWK set: what an org admin registers for an app."""

    keys: list[Jwk]


class ClientAssertion(BaseModel):
    """The claims of a `private_key_jwt` client assertion (RFC 7523)."""

    iss: str
    sub: str
    aud: str
    iat: int
    exp: int
    jti: str


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class AppKey:
    """An app's RSA private key."""

    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        self._key = key

    @classmethod
    def from_pem(cls, pem: str) -> AppKey:
        loaded = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(loaded, rsa.RSAPrivateKey):
            raise ValueError("an app's key must be an RSA private key")
        return cls(loaded)

    @staticmethod
    def generate(path: str | Path) -> Path:
        """Make a new RSA key and write it to `path`, readable by its owner only."""
        target = Path(path).expanduser()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            # `os.open`'s mode applies only to a file it creates; one that was already here keeps its own.
            os.fchmod(handle.fileno(), 0o600)
            handle.write(pem)
        return target

    def thumbprint(self) -> str:
        """The key's RFC 7638 thumbprint: its `kid`, and what an admin compares."""
        numbers = self._key.public_key().public_numbers()
        members = {"e": _b64url_uint(numbers.e), "kty": "RSA", "n": _b64url_uint(numbers.n)}
        canonical = json.dumps(members, separators=(",", ":"), sort_keys=True).encode()
        return base64.urlsafe_b64encode(hashlib.sha256(canonical).digest()).rstrip(b"=").decode()

    def jwks(self) -> JwkSet:
        """The public half, as a JWK set."""
        numbers = self._key.public_key().public_numbers()
        return JwkSet(
            keys=[
                Jwk(
                    kid=self.thumbprint(),
                    n=_b64url_uint(numbers.n),
                    e=_b64url_uint(numbers.e),
                )
            ]
        )

    def sign(self, assertion: ClientAssertion) -> str:
        return jwt.encode(
            assertion.model_dump(),
            self._key,
            algorithm=ALGORITHM,
            headers={"kid": self.thumbprint()},
        )

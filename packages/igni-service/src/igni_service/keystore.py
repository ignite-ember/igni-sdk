"""Where a service keeps its own private key.

The key is the deployment's identity: igni registered its public half
and a super admin approved the service by its thumbprint. So every
replica must sign with the same key, and replicas starting together must
end up agreeing on one. That is the whole contract of a `KeyStore`:

* `get()` — the kept key, or `None` before there is one;
* `claim(key)` — keep `key` unless one is already kept, and answer with
  whichever is. Two replicas that each generated a key both call it; one
  wins, and both go on to sign with the winner's.

The private half is sealed with `KeyCipher` before it is stored, so a
store holds ciphertext only. `MemoryKeyStore` is for tests;
`igni_service.sql_keystore.SqlKeyStore` is for a deployment.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict

from igni_service.errors import KeyStoreError


class StoredKey(BaseModel):
    """A kept key: its `kid` (thumbprint) and its private half, unsealed."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    kid: str
    """The key's id: its RFC 7638 thumbprint."""
    private_pem: str
    """The private half, PEM-encoded, unsealed."""


@runtime_checkable
class KeyStore(Protocol):
    """Keeps one key. See the module note for the contract.

    Args:
        args: The positional arguments a concrete implementation's constructor takes;
            the protocol itself does not use them.
        kwargs: The keyword arguments a concrete implementation's constructor takes;
            the protocol itself does not use them.
    """

    async def get(self) -> StoredKey | None:
        """The kept key, or `None` before there is one."""
        ...

    async def claim(self, key: StoredKey) -> StoredKey:
        """Keep `key` unless one is already kept, and answer with whichever is kept.

        Two replicas that each made a key both call it: one wins, and both
        sign with the winner's from then on.

        Args:
            key: The key to keep when none is kept yet: its ``kid`` thumbprint and
                its private half.
        """
        ...


class KeyCipher:
    """Fernet under the service's key encryption key.

    Args:
        key: The Fernet key encryption key the private half is sealed under, as
            ``KeyCipher.generate`` produced it. An empty one leaves the cipher unusable:
            sealing raises ``KeyStoreError``.
    """

    def __init__(self, key: str) -> None:
        self._key = (key or "").strip()

    @staticmethod
    def generate() -> str:
        """A new key encryption key, for an operator to keep."""
        return Fernet.generate_key().decode()

    def _fernet(self) -> Fernet:
        if not self._key:
            raise KeyStoreError(
                "IGNI_KEY_ENCRYPTION_KEY is not set, so this service cannot keep its own key."
            )
        try:
            return Fernet(self._key.encode())
        except (ValueError, TypeError) as exc:
            raise KeyStoreError("IGNI_KEY_ENCRYPTION_KEY is not a Fernet key.") from exc

    def seal(self, plaintext: str) -> str:
        """`plaintext` encrypted under the key encryption key, as Fernet text.

        Args:
            plaintext: The text to encrypt under the key encryption key.
        """
        return self._fernet().encrypt(plaintext.encode()).decode()

    def open(self, sealed: str) -> str:
        """What `seal` sealed. Raises `KeyStoreError` when the key encryption key changed.

        Args:
            sealed: The sealed text, as ``seal`` produced it.
        """
        try:
            return self._fernet().decrypt(sealed.encode()).decode()
        except InvalidToken as exc:
            raise KeyStoreError(
                "This service's key cannot be read with this IGNI_KEY_ENCRYPTION_KEY: it was "
                "changed. Restore the old one, or delete the stored key to make a new identity "
                "(which a super admin must approve again)."
            ) from exc


class MemoryKeyStore:
    """A key kept in this process only. For tests; a restart is a new identity."""

    def __init__(self) -> None:
        self._kept: StoredKey | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> StoredKey | None:
        """The key this process kept, or `None` before there is one."""
        return self._kept

    async def claim(self, key: StoredKey) -> StoredKey:
        """Keep `key` unless one is already kept; answer with whichever is.

        Args:
            key: The key to keep when this process holds none: its ``kid`` thumbprint
                and its private half.
        """
        async with self._lock:
            if self._kept is None:
                self._kept = key
            return self._kept

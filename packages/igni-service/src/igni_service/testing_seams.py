"""Test doubles for the SDK's own seams, which are not igni endpoints.

A clock that moves only when a test moves it, a key store that already
holds an app's key, and a sleep that does not wait, so retries in tests
are instant.
"""

from __future__ import annotations

from igni_service.clock import Clock
from igni_service.keystore import StoredKey


class ManualClock(Clock):
    """A clock that moves only when told to."""

    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self._now = start

    def wall(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class HeldKeyStore:
    """A key store that already holds one key: an app whose key the fake registered."""

    def __init__(self, key: StoredKey) -> None:
        self._key = key

    async def get(self) -> StoredKey | None:
        return self._key

    async def claim(self, key: StoredKey) -> StoredKey:
        return self._key


async def no_sleep(_: float) -> None:
    """Retries in tests do not wait."""


__all__ = ["HeldKeyStore", "ManualClock", "no_sleep"]

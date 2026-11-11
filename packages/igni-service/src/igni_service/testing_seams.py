"""Test doubles for the SDK's own seams, which are not igni endpoints.

A clock that moves only when a test moves it, a key store that already
holds an app's key, and a sleep that does not wait, so retries in tests
are instant.
"""

from __future__ import annotations

from igni_service.clock import Clock
from igni_service.keystore import StoredKey


class ManualClock(Clock):
    """A clock that moves only when told to.

    Args:
        start: The time it starts at, in seconds since the epoch: what both
            `wall` and `monotonic` answer until it is moved.
    """

    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self._now = start

    def wall(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the clock forward `seconds`; both `monotonic` and `wall` move.

        Args:
            seconds: How far the clock moves forward, in seconds.
        """
        self._now += seconds


class HeldKeyStore:
    """A key store that already holds one key: an app whose key the fake registered.

    Args:
        key: The key it holds: the app's private half and its thumbprint,
            as the fake registered it.
    """

    def __init__(self, key: StoredKey) -> None:
        self._key = key

    async def get(self) -> StoredKey | None:
        return self._key

    async def claim(self, key: StoredKey) -> StoredKey:
        """Answer with the key it holds, whatever key is claimed.

        Args:
            key: The key a caller claims to store: the one already held is
                answered instead.
        """
        return self._key


async def no_sleep(_: float) -> None:
    """Retries in tests do not wait.

    Args:
        _: The seconds a sleep would have waited: nothing waits.
    """


__all__ = ["HeldKeyStore", "ManualClock", "no_sleep"]

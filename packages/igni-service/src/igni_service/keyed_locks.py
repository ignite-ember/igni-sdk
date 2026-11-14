"""One asyncio lock per key, held only while somebody holds or waits on it.

A lock per organisation keeps two calls for one organisation from both
asking igni for a token, without making a call for another organisation
wait. A plain `dict` of locks would keep one for every organisation ever
named; these are dropped as soon as nobody holds or waits on them.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass
class KeyedLock:
    """One key's lock, and how many hold or wait on it."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class KeyedLocks:
    """Locks by key, each kept only while it is in use."""

    def __init__(self) -> None:
        self._locks: dict[str, KeyedLock] = {}

    def __len__(self) -> int:
        """How many keys have a lock somebody holds or waits on."""
        return len(self._locks)

    @asynccontextmanager
    async def held(self, key: str) -> AsyncIterator[None]:
        """Hold `key`'s lock for the body of the `async with`.

        Args:
            key: What the lock is for, such as an organisation's id.
        """
        entry = self._locks.setdefault(key, KeyedLock())
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if entry.users == 0:
                del self._locks[key]

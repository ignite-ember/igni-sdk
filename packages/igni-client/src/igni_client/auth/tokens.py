"""A bearer token source, and the token igni server issues and the cache that keeps it."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class TokenSource(Protocol):
    """Anything a target can ask for a bearer token."""

    async def token(self) -> str: ...


class IssuedToken(BaseModel):
    """igni server's answer to a token request."""

    model_config = ConfigDict(extra="ignore")

    access_token: str
    expires_in: int = 600


class TokenCache:
    """One bearer token, kept until `renew_before()` seconds before it runs out.

    The margin is asked for each time a token is kept, as 0.1.0 read
    `RENEW_BEFORE` on every renewal, so a margin set after the source was
    made is honoured.
    """

    def __init__(self, clock: Callable[[], float], *, renew_before: Callable[[], int]) -> None:
        self._clock = clock
        self._renew_before = renew_before
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, fetch: Callable[[], Awaitable[IssuedToken]]) -> str:
        """The kept token, or a new one from `fetch` when there is none or it is near its end."""
        async with self._lock:
            if self._token is not None and self._clock() < self._expires_at:
                return self._token
            issued = await fetch()
            self._token = issued.access_token
            self._expires_at = self._clock() + max(0, issued.expires_in - self._renew_before())
            return self._token

    async def forget(self) -> None:
        """Drop the kept token, so the next `get` fetches a new one."""
        async with self._lock:
            self._token = None

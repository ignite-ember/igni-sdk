"""Where the connection to igni is: opening, open, down, failed for good, or closed."""

from __future__ import annotations

import asyncio
from enum import Enum

from websockets.asyncio.client import ClientConnection

from igni_client.errors import IgniClientError, Unavailable
from igni_client.events import Welcome


class Phase(Enum):
    #: Not connected: before the first open, or after the socket closed and before it opens again.
    DOWN = "down"
    #: A socket is open and waits for igni's `welcome`.
    OPENING = "opening"
    #: igni said welcome; messages go out.
    OPEN = "open"
    #: It will not open again; `Lifecycle.failure` says why.
    FAILED = "failed"
    #: The client closed it.
    CLOSED = "closed"


class Link:
    """One socket opened to igni: the task reading it, and the `welcome` it waits for."""

    def __init__(self, socket: ClientConnection) -> None:
        self.socket = socket
        self.welcomed: asyncio.Future[Welcome] = asyncio.get_running_loop().create_future()
        self.reader: asyncio.Task[None] | None = None


class Lifecycle:
    """The connection's phase, the latest socket opened, and — once it failed — why."""

    def __init__(self) -> None:
        self.phase = Phase.DOWN
        self.link: Link | None = None
        self.failure: IgniClientError | None = None
        self._open = asyncio.Event()

    def opening(self, link: Link) -> None:
        self.phase = Phase.OPENING
        self.link = link

    def opened(self) -> None:
        self.phase = Phase.OPEN
        self.failure = None
        self._open.set()

    def lost(self, link: Link) -> bool:
        """`link` closed. True when it was the live one — not one replaced or closed by us."""
        if self.link is not link or self.phase not in (Phase.OPENING, Phase.OPEN):
            return False
        self.phase = Phase.DOWN
        self._open.clear()
        return True

    def failed(self, error: IgniClientError) -> None:
        self.phase = Phase.FAILED
        self.failure = error
        self._open.clear()

    def close(self) -> Link | None:
        """Mark it closed; the latest link, for the caller to close."""
        self.phase = Phase.CLOSED
        self._open.clear()
        return self.link

    def pending_welcome(self) -> asyncio.Future[Welcome] | None:
        """The latest link's `welcome`, while it has not arrived."""
        if self.link is None or self.link.welcomed.done():
            return None
        return self.link.welcomed

    async def socket(self, timeout: float, where: str) -> ClientConnection:
        """The open socket, waiting up to `timeout` while it is being opened again."""
        if self.failure is not None and self.phase is not Phase.OPEN:
            raise self.failure
        try:
            await asyncio.wait_for(self._open.wait(), timeout)
        except TimeoutError as exc:
            raise self.failure or Unavailable(f"{where} is not connected") from exc
        if self.phase is not Phase.OPEN or self.link is None:
            raise self.failure or Unavailable(f"{where} is not connected")
        return self.link.socket

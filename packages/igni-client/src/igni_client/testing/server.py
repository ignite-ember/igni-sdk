"""igni's socket on loopback: the handshake, a welcome per client, and every message broadcast."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any, Protocol

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from igni_client.models import PushNotification, Welcome
from igni_client.targets import TOKEN_PROTOCOL_PREFIX
from igni_client.testing.inbound import ClientFrame, Received, read_frame
from igni_client.wire import Event

SUBPROTOCOL = "igni.v1"


class Handshake(Protocol):
    """Who may open the socket: a refusal for the request, or `None` to let it through."""

    def refuse(self, connection: ServerConnection, request: Request) -> Response | None: ...


class LocalHandshake:
    """A local igni's check: the per-launch token, offered as a subprotocol, when there is one."""

    def __init__(self, token: str | None) -> None:
        self.token = token

    def refuse(self, connection: ServerConnection, request: Request) -> Response | None:
        if self.token is None:
            return None
        offered = [
            p.strip()
            for value in request.headers.get_all("Sec-WebSocket-Protocol")
            for p in value.split(",")
        ]
        if f"{TOKEN_PROTOCOL_PREFIX}{self.token}" in offered:
            return None
        return connection.respond(HTTPStatus.FORBIDDEN, "Forbidden\n")


#: Sends one message to the client that sent the frame being handled, and no other.
Reply = Callable[[Event], Awaitable[None]]
#: Handles one frame a client sent; `Reply` answers that client alone.
FrameHandler = Callable[[ClientFrame, Reply], Awaitable[None]]


class FakeSocket:
    """The socket clients attach to, and what Fleet does to it under them."""

    def __init__(self, handshake: Handshake, handler: FrameHandler, *, path: str = "") -> None:
        self._handshake = handshake
        self._handler = handler
        self._path = path
        #: Everything clients sent, in order.
        self.received: list[Received] = []
        #: How many connections were accepted.
        self.connections = 0
        self.port = 0
        self._server: Server | None = None
        self._clients: dict[ServerConnection, str] = {}
        self._ids = itertools.count(1)
        self._busy = 0
        self._tasks: set[asyncio.Task[Any]] = set()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}{self._path}"

    async def start(self) -> None:
        self._server = await serve(
            self._serve,
            "127.0.0.1",
            0,
            compression=None,
            process_request=self._handshake.refuse,
            select_subprotocol=lambda _conn, offered: next(
                (p for p in offered if p == SUBPROTOCOL), None
            ),
        )
        self.port = int(next(iter(self._server.sockets)).getsockname()[1])

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ── What happens to a connection ──

    async def move(self) -> None:
        """Fleet moved the VM: every client gets a new `welcome` on the socket it has."""
        for socket in list(self._clients):
            client_id = self._new_client_id()
            self._clients[socket] = client_id
            await self._send(socket, Welcome(client_id=client_id))

    async def drop(self, code: int = 1011, reason: str = "igni keeps going away") -> None:
        """Close every connection with `code`."""
        for socket in list(self._clients):
            await socket.close(code, reason)

    def busy_next(self, count: int = 1) -> None:
        """Answer the next `count` connections "busy, retry" (`1013`), as the gateway does with no room."""
        self._busy = count

    async def broadcast(self, event: Event) -> None:
        """Send `event` to every client attached, as igni does."""
        for socket in list(self._clients):
            await self._send(socket, event)

    async def push(self, channel: str, payload: dict[str, Any], *, session_id: str = "") -> None:
        """Broadcast a push notification on `channel`, as igni's tools and handlers do."""
        await self.broadcast(
            PushNotification(channel=channel, payload=payload, session_id=session_id)
        )

    # ── The socket ──

    async def _serve(self, socket: ServerConnection) -> None:
        self.connections += 1
        if self._busy > 0:
            self._busy -= 1
            await socket.close(1013, "busy, retry")
            return
        client_id = self._new_client_id()
        self._clients[socket] = client_id
        try:
            await self._send(socket, Welcome(client_id=client_id))
            with contextlib.suppress(ConnectionClosed):  # a client going away is not a failure
                async for raw in socket:
                    self._receive(socket, raw)
        finally:
            self._clients.pop(socket, None)

    def _receive(self, socket: ServerConnection, raw: str | bytes) -> None:
        try:
            frame = read_frame(raw)
        except ValueError:  # not a message igni reads: igni passes it over too
            return
        self.received.append(Received(client_id=self._clients.get(socket, ""), frame=frame))

        async def reply(event: Event) -> None:
            await self._send(socket, event)

        task = asyncio.ensure_future(self._handler(frame, reply))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _new_client_id(self) -> str:
        return f"ws-{next(self._ids)}"

    @staticmethod
    async def _send(socket: ServerConnection, event: Event) -> None:
        with contextlib.suppress(ConnectionClosed):  # it left; the broadcast goes on
            await socket.send(event.model_dump_json(by_alias=True))


__all__ = ["FakeSocket", "FrameHandler", "Handshake", "LocalHandshake", "Reply"]

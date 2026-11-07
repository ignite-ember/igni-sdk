"""One connection to igni's socket: requests out, messages routed back.

igni sends every message to every client attached to it — a person's
open window as much as this client — so nothing here assumes a message
is for us. Replies are matched by the `id` of the request they answer;
everything else goes to whoever is listening, filtered by session above.

What can happen to the socket, and what this does about it:

* **igni moved** (Fleet only). When a node drains or fails, the gateway
  wakes the VM elsewhere and reconnects behind us: the socket stays open
  and a second `welcome` arrives. Runs and calls in flight end with
  `RunInterrupted` — they may or may not have finished — and the client
  re-attaches its sessions.
* **The socket closed.** For Fleet, the gateway's `1013` ("busy, retry")
  and `1011` and a dropped line are opened again, with a fresh token,
  backing off. `1008` — not an active producer, or the licence — is final
  (`NotAllowed`). A local igni that closed has stopped (`Unavailable`).
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.asyncio.client import ClientConnection
from websockets.exceptions import WebSocketException

from igni_client.errors import (
    AuthError,
    IgniClientError,
    NotAllowed,
    RpcError,
    RunInterrupted,
    Unavailable,
)
from igni_client.events import Event, RpcResponse, Welcome, parse_event
from igni_client.targets import Target

logger = logging.getLogger(__name__)

#: What an igni in a VM answers before Fleet has bound it to its producer.
UNBOUND = "igni is not bound to a producer yet; retry shortly"

#: Close codes the gateway sends.
BUSY, NOT_A_PRODUCER, FAILED = 1013, 1008, 1011

#: Methods a client never sends: they stop igni, or belong to Fleet's own control connection.
REFUSED_METHODS = frozenset({"shutdown", "vm_sign_in", "deliver_service_events"})


class Interruption:
    """Put on a stream's queue when its run can no longer be followed."""

    def __init__(self, error: IgniClientError) -> None:
        self.error = error


Resync = Callable[[], Awaitable[None]]


class Connection:
    """igni's socket, kept open."""

    #: How long the first `welcome` may take — a VM may be resuming behind it.
    WELCOME_TIMEOUT = 45.0
    #: How long a call waits for its answer.
    RPC_TIMEOUT = 60.0
    #: How often an unbound VM is asked again, and for how long.
    UNBOUND_RETRY_SECONDS = 1.0
    UNBOUND_RETRIES = 30

    def __init__(
        self,
        target: Target,
        *,
        reconnect_attempts: int = 5,
        backoff: float = 0.5,
        backoff_max: float = 8.0,
    ) -> None:
        self.target = target
        self.client_id = ""
        self._reconnect_attempts = reconnect_attempts
        self._backoff = backoff
        self._backoff_max = backoff_max
        self._socket: ClientConnection | None = None
        self._reader: asyncio.Task[None] | None = None
        self._welcomed: asyncio.Future[Welcome] | None = None
        self._ready = asyncio.Event()
        self._failure: IgniClientError | None = None
        self._closing = False
        self._ids = itertools.count(1)
        self._waiting: dict[str, asyncio.Future[Event]] = {}
        self._streams: dict[str, asyncio.Queue[Event | Interruption]] = {}
        self._listeners: list[asyncio.Queue[Event]] = []
        self._resync: list[Resync] = []
        self._tasks: set[asyncio.Task[Any]] = set()

    # ── Lifecycle ──

    async def open(self) -> None:
        """Open the socket and wait for igni's `welcome`.

        Fleet may answer "busy, retry" while it finds room for the VM; that
        is tried again, backing off. A refused credential or a producer that
        is not active is not.
        """
        delay = self._backoff
        for attempt in range(self._reconnect_attempts + 1):
            try:
                await self._open_once()
                return
            except (AuthError, NotAllowed):
                raise
            except Unavailable:
                if not self.target.reconnects or attempt == self._reconnect_attempts:
                    raise
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._backoff_max)

    async def close(self) -> None:
        self._closing = True
        self._ready.clear()
        socket, self._socket = self._socket, None
        if socket is not None:
            with contextlib.suppress(Exception):
                await socket.close()
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
        for task in list(self._tasks):
            task.cancel()
        self._fail_all(Unavailable("the client was closed"))
        await self.target.aclose()

    def on_resync(self, callback: Resync) -> None:
        """Run `callback` after igni moved or the socket was opened again."""
        self._resync.append(callback)

    async def _open_once(self) -> None:
        socket = await self.target.open()
        loop = asyncio.get_running_loop()
        self._welcomed = loop.create_future()
        self._socket = socket
        self._reader = asyncio.create_task(self._read(socket))
        try:
            welcome = await asyncio.wait_for(asyncio.shield(self._welcomed), self.WELCOME_TIMEOUT)
        except TimeoutError as exc:
            with contextlib.suppress(Exception):
                await socket.close()
            raise Unavailable(f"{self.target.describe()} did not say welcome") from exc
        except IgniClientError:
            with contextlib.suppress(Exception):
                await socket.close()
            raise
        self.client_id = welcome.client_id
        self._failure = None
        self._ready.set()

    # ── Sending ──

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids)}"

    async def send(self, frame: dict[str, Any]) -> None:
        """Send one message, waiting for the socket if it is being opened again."""
        if frame.get("type") == "rpc_request" and frame.get("method") in REFUSED_METHODS:
            raise ValueError(f"{frame.get('method')} is not a client's to send")
        socket = await self._connected()
        try:
            await socket.send(json.dumps(frame))
        except (OSError, WebSocketException) as exc:
            raise Unavailable(f"{self.target.describe()} went away: {exc}") from exc

    async def _connected(self) -> ClientConnection:
        if self._failure is not None and not self._ready.is_set():
            raise self._failure
        try:
            await asyncio.wait_for(self._ready.wait(), self.WELCOME_TIMEOUT)
        except TimeoutError as exc:
            raise self._failure or Unavailable(
                f"{self.target.describe()} is not connected"
            ) from exc
        if self._socket is None:
            raise self._failure or Unavailable(f"{self.target.describe()} is not connected")
        return self._socket

    async def rpc(
        self, method: str, args: dict[str, Any] | None = None, *, session_id: str = ""
    ) -> Event:
        """Call `method` and return igni's answer.

        The answer is usually an `RpcResponse` (whose error raises
        `RpcError` here), but some methods answer with a message of their
        own — `list_sessions` with a `SessionListResult` — and that message
        is returned as it is.
        """
        for _ in range(self.UNBOUND_RETRIES):
            reply = await self._call(method, args or {}, session_id)
            if isinstance(reply, RpcResponse) and reply.error:
                if reply.error == UNBOUND:
                    await asyncio.sleep(self.UNBOUND_RETRY_SECONDS)
                    continue
                raise RpcError(method, reply.error)
            return reply
        raise Unavailable(f"{self.target.describe()} was not bound to its producer in time")

    async def _call(self, method: str, args: dict[str, Any], session_id: str) -> Event:
        request_id = self.new_id("rpc")
        future: asyncio.Future[Event] = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future
        try:
            frame: dict[str, Any] = {
                "type": "rpc_request",
                "id": request_id,
                "method": method,
                "args": args,
            }
            if session_id:
                frame["session_id"] = session_id
            await self.send(frame)
            return await asyncio.wait_for(future, self.RPC_TIMEOUT)
        except TimeoutError as exc:
            raise Unavailable(f"{method} got no answer from {self.target.describe()}") from exc
        finally:
            self._waiting.pop(request_id, None)

    # ── Streams and listeners ──

    def open_stream(
        self, request_id: str, queue: asyncio.Queue[Event | Interruption] | None = None
    ) -> asyncio.Queue[Event | Interruption]:
        """Collect every message answering `request_id`. Open it before sending the request.

        Pass `queue` to collect several requests' messages in one place — a
        run and the approvals answered in it.
        """
        if queue is None:
            queue = asyncio.Queue()
        self._streams[request_id] = queue
        return queue

    def close_stream(self, request_id: str) -> None:
        self._streams.pop(request_id, None)

    def listen(self) -> asyncio.Queue[Event]:
        """A queue of every message igni sends, from now on."""
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._listeners.append(queue)
        return queue

    def unlisten(self, queue: asyncio.Queue[Event]) -> None:
        with contextlib.suppress(ValueError):
            self._listeners.remove(queue)

    # ── Reading ──

    async def _read(self, socket: ClientConnection) -> None:
        try:
            async for raw in socket:
                try:
                    decoded = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(decoded, dict):
                    self._route(parse_event(decoded))
        except WebSocketException:
            pass
        finally:
            if self._socket is socket and not self._closing:
                self._socket = None
                self._ready.clear()
                welcomed = self._welcomed
                if welcomed is not None and not welcomed.done():
                    # Closed before igni said welcome: whoever is opening it decides.
                    welcomed.set_exception(self._close_error(socket))
                else:
                    self._spawn(self._closed(socket))

    def _close_error(self, socket: ClientConnection) -> IgniClientError:
        code, reason = socket.close_code, socket.close_reason or ""
        where = self.target.describe()
        if code == NOT_A_PRODUCER:
            return NotAllowed(f"{where} closed the connection: {reason or 'not allowed'}")
        if code == BUSY:
            return Unavailable(f"{where} is busy; retry ({reason or 'busy'})")
        return Unavailable(f"{where} closed the connection ({code}): {reason}")

    def _route(self, event: Event) -> None:
        if isinstance(event, Welcome):
            welcomed = self._welcomed
            if welcomed is not None and not welcomed.done():
                welcomed.set_result(event)
            else:
                # igni moved behind the gateway: a new igni, the same socket.
                self.client_id = event.client_id
                self._interrupt(
                    RunInterrupted("igni moved while this was going; it may have finished")
                )
                self._spawn(self._run_resync())
            return
        for queue in self._listeners:
            queue.put_nowait(event)
        if not event.id:
            return
        waiter = self._waiting.get(event.id)
        if waiter is not None and event.type != "rpc_request":
            if not waiter.done():
                waiter.set_result(event)
            return
        stream = self._streams.get(event.id)
        if stream is not None:
            stream.put_nowait(event)

    async def _closed(self, socket: ClientConnection) -> None:
        code = socket.close_code
        where = self.target.describe()
        if code == NOT_A_PRODUCER or not self.target.reconnects:
            self._failure = self._close_error(socket)
            self._fail_all(self._failure)
            return
        self._interrupt(
            RunInterrupted(f"the connection to {where} dropped ({code}); it may have finished")
        )
        delay = self._backoff
        for attempt in range(1, self._reconnect_attempts + 1):
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._backoff_max)
            try:
                await self._open_once()
            except (AuthError, NotAllowed) as exc:
                self._failure = exc
                self._fail_all(exc)
                return
            except IgniClientError as exc:
                logger.info("igni-client: reconnecting to %s (%d): %s", where, attempt, exc)
                continue
            await self._run_resync()
            return
        self._failure = Unavailable(f"{where} could not be reached again after it closed ({code})")
        self._fail_all(self._failure)

    async def _run_resync(self) -> None:
        for callback in list(self._resync):
            try:
                await callback()
            except IgniClientError as exc:
                logger.warning("igni-client: re-attaching after a move failed: %s", exc)

    def _interrupt(self, error: IgniClientError) -> None:
        """End every call and run in flight: they cannot be followed any more."""
        for waiter in list(self._waiting.values()):
            if not waiter.done():
                waiter.set_exception(error)
        for queue in list(self._streams.values()):
            queue.put_nowait(Interruption(error))

    def _fail_all(self, error: IgniClientError) -> None:
        self._interrupt(error)
        welcomed = self._welcomed
        if welcomed is not None and not welcomed.done():
            welcomed.set_exception(error)

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

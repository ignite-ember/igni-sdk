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
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, overload

from pydantic import BaseModel, TypeAdapter, ValidationError
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import WebSocketException

from igni_client.backoff import Backoff
from igni_client.errors import (
    AuthError,
    IgniClientError,
    NotAllowed,
    RpcError,
    RunInterrupted,
    Unavailable,
)
from igni_client.events import Event, RpcResponse, Welcome, parse_event
from igni_client.frames import REFUSED_METHODS, Frame, RpcRequest
from igni_client.lifecycle import Lifecycle, Link
from igni_client.routing import Router
from igni_client.targets import Target

#: Re-exported: igni-core's protocol test reads it from here.
__all__ = ["REFUSED_METHODS", "Connection"]

logger = logging.getLogger(__name__)

T = TypeVar("T")
E = TypeVar("E", bound=Event)

#: What an igni in a VM answers before Fleet has bound it to its producer.
UNBOUND = "igni is not bound to a producer yet; retry shortly"

#: Close codes the gateway sends.
BUSY, NOT_A_PRODUCER, FAILED = 1013, 1008, 1011

Resync = Callable[[], Awaitable[None]]


class Connection:
    """igni's socket, kept open. `router` hands out what comes back."""

    #: How long the first `welcome` may take — a VM may be resuming behind it.
    WELCOME_TIMEOUT = 45.0
    #: How long a call waits for its answer.
    RPC_TIMEOUT = 60.0
    #: How often an unbound VM is asked again, and for how long.
    UNBOUND_RETRY_SECONDS = 1.0
    UNBOUND_RETRIES = 30

    def __init__(self, target: Target, backoff: Backoff, router: Router) -> None:
        self.target = target
        self.client_id = ""
        self.backoff = backoff
        self.router = router
        self._lifecycle = Lifecycle()
        self._resync: list[Resync] = []
        self._tasks: set[asyncio.Task[Any]] = set()

    # ── Lifecycle ──

    async def open(self) -> None:
        """Open the socket and wait for igni's `welcome`.

        Fleet may answer "busy, retry" while it finds room for the VM; that
        is tried again, backing off. A refused credential or a producer that
        is not active is not.
        """
        delays = self.backoff.delays()
        while True:
            try:
                await self._open_once()
                return
            except (AuthError, NotAllowed):
                raise
            except Unavailable:
                delay = next(delays, None)
                if not self.target.reconnects or delay is None:
                    raise
                await asyncio.sleep(delay)

    async def close(self) -> None:
        link = self._lifecycle.close()
        if link is not None:
            await self._hang_up(link.socket)
            if link.reader is not None:
                link.reader.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await link.reader
        for task in list(self._tasks):
            task.cancel()
        self._fail_all(Unavailable("the client was closed"))
        await self.target.aclose()

    def on_resync(self, callback: Resync) -> None:
        """Run `callback` after igni moved or the socket was opened again."""
        self._resync.append(callback)

    async def _open_once(self) -> None:
        link = Link(await self.target.open())
        self._lifecycle.opening(link)
        link.reader = asyncio.create_task(self._read(link))
        try:
            welcome = await asyncio.wait_for(asyncio.shield(link.welcomed), self.WELCOME_TIMEOUT)
        except TimeoutError as exc:
            await self._hang_up(link.socket)
            raise Unavailable(f"{self.target.describe()} did not say welcome") from exc
        except IgniClientError:
            await self._hang_up(link.socket)
            raise
        self.client_id = welcome.client_id
        self._lifecycle.opened()

    async def _hang_up(self, socket: ClientConnection) -> None:
        try:
            await socket.close()
        except (OSError, WebSocketException) as exc:
            logger.info("igni-client: closing the socket to %s: %s", self.target.describe(), exc)

    # ── Sending ──

    async def send(self, frame: Frame) -> None:
        """Send one message, waiting for the socket if it is being opened again."""
        socket = await self._lifecycle.socket(self.WELCOME_TIMEOUT, self.target.describe())
        try:
            await socket.send(frame.wire())
        except (OSError, WebSocketException) as exc:
            raise Unavailable(f"{self.target.describe()} went away: {exc}") from exc

    async def ask(
        self, method: str, args: dict[str, Any] | None = None, *, session_id: str = ""
    ) -> Event:
        """Call `method` with `args` and return igni's answer as it came.

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

    @overload
    async def rpc(
        self,
        method: str,
        answer: type[E],
        params: BaseModel | None = None,
        *,
        session_id: str = "",
    ) -> E: ...

    @overload
    async def rpc(
        self,
        method: str,
        answer: TypeAdapter[T],
        params: BaseModel | None = None,
        *,
        session_id: str = "",
    ) -> T: ...

    async def rpc(
        self,
        method: str,
        answer: type[Event] | TypeAdapter[Any],
        params: BaseModel | None = None,
        *,
        session_id: str = "",
    ) -> Any:
        """Call one of the methods this client calls itself, and read its answer as `answer`.

        `answer` is either the message the method answers with instead of
        an `RpcResponse` (`list_sessions` answers with a
        `SessionListResult`), or a `TypeAdapter` its `RpcResponse` result
        is read with. Any other answer raises `RpcError`. A field of
        `params` left `None` is left out.
        """
        args = params.model_dump(mode="json", exclude_none=True) if params else {}
        reply = await self.ask(method, args, session_id=session_id)
        if isinstance(answer, TypeAdapter):
            if not isinstance(reply, RpcResponse):
                raise RpcError(method, f"igni answered with {reply.type}")
            try:
                return answer.validate_python(reply.result)
            except ValidationError as exc:
                raise RpcError(
                    method, f"igni's answer is not what the method returns: {exc}"
                ) from exc
        if isinstance(reply, answer):
            return reply
        raise RpcError(method, f"igni answered with {reply.type}")

    @staticmethod
    def result(reply: Event) -> Any:
        """An `RpcResponse`'s result, or the message a method answered with instead."""
        return reply.result if isinstance(reply, RpcResponse) else reply

    async def _call(self, method: str, args: dict[str, Any], session_id: str) -> Event:
        RpcRequest.check_sendable(method)
        # `args` as given, as 0.1.0 sent them: `json.dumps` reads them on the way out.
        request = RpcRequest.model_construct(
            id=self.router.new_id("rpc"), method=method, args=args, session_id=session_id or None
        )
        answer = self.router.expect(request.id)
        try:
            await self.send(request)
            return await asyncio.wait_for(answer, self.RPC_TIMEOUT)
        except TimeoutError as exc:
            raise Unavailable(f"{method} got no answer from {self.target.describe()}") from exc
        finally:
            self.router.forget(request.id)

    # ── Reading ──

    async def _read(self, link: Link) -> None:
        where = self.target.describe()
        try:
            async for raw in link.socket:
                try:
                    decoded = json.loads(raw)
                except ValueError:
                    logger.warning("igni-client: %s sent a message that is not JSON", where)
                    continue
                if not isinstance(decoded, dict):
                    logger.warning("igni-client: %s sent a message that is not an object", where)
                    continue
                self._route(parse_event(decoded))
        except WebSocketException as exc:
            logger.info("igni-client: reading from %s stopped: %s", where, exc)
        finally:
            if self._lifecycle.lost(link):
                if not link.welcomed.done():
                    # Closed before igni said welcome: whoever is opening it decides.
                    link.welcomed.set_exception(self._close_error(link.socket))
                else:
                    self._spawn(self._closed(link.socket))

    def _close_error(self, socket: ClientConnection) -> IgniClientError:
        code, reason = socket.close_code, socket.close_reason or ""
        where = self.target.describe()
        if code == NOT_A_PRODUCER:
            return NotAllowed(f"{where} closed the connection: {reason or 'not allowed'}")
        if code == BUSY:
            return Unavailable(f"{where} is busy; retry ({reason or 'busy'})")
        return Unavailable(f"{where} closed the connection ({code}): {reason}")

    def _route(self, event: Event) -> None:
        if not isinstance(event, Welcome):
            self.router.deliver(event)
            return
        welcomed = self._lifecycle.pending_welcome()
        if welcomed is not None:
            welcomed.set_result(event)
            return
        # igni moved behind the gateway: a new igni, the same socket.
        self.client_id = event.client_id
        self.router.interrupt(
            RunInterrupted("igni moved while this was going; it may have finished")
        )
        self._spawn(self._run_resync())

    async def _closed(self, socket: ClientConnection) -> None:
        code = socket.close_code
        where = self.target.describe()
        if code == NOT_A_PRODUCER or not self.target.reconnects:
            self._fail(self._close_error(socket))
            return
        self.router.interrupt(
            RunInterrupted(f"the connection to {where} dropped ({code}); it may have finished")
        )
        for attempt, delay in enumerate(self.backoff.delays(), start=1):
            await asyncio.sleep(delay)
            try:
                await self._open_once()
            except (AuthError, NotAllowed) as exc:
                self._fail(exc)
                return
            except IgniClientError as exc:
                logger.info("igni-client: reconnecting to %s (%d): %s", where, attempt, exc)
                continue
            await self._run_resync()
            return
        self._fail(Unavailable(f"{where} could not be reached again after it closed ({code})"))

    async def _run_resync(self) -> None:
        for callback in list(self._resync):
            try:
                await callback()
            except IgniClientError as exc:
                logger.warning("igni-client: re-attaching after a move failed: %s", exc)

    def _fail(self, error: IgniClientError) -> None:
        """It will not open again: say so to everything waiting, and to everything sent from now on."""
        self._lifecycle.failed(error)
        self._fail_all(error)

    def _fail_all(self, error: IgniClientError) -> None:
        self.router.interrupt(error)
        welcomed = self._lifecycle.pending_welcome()
        if welcomed is not None:
            welcomed.set_exception(error)

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

"""The socket to the igni host: how `ext.host` reaches igni.

igni starts an extension's process with `IGNI_HOST_URL` and
`IGNI_HOST_SECRET`: a WebSocket on the host's loopback interface and the
secret that says which process this is. Every `get`, `set` and `call` on
`ext.host` is one request on it, and every signal the extension handles
arrives on it. The protocol is igni-core's `docs/HOST_MODEL_PROTOCOL.md` (https://github.com/ignite-ember/igni-core/blob/main/docs/HOST_MODEL_PROTOCOL.md), its
messages `igni_extension.wire`; an extension author never sees it.

A process started without those variables has no socket: its `ext.host`
is `igni_extension.offline.OfflineHost`.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
from collections.abc import Coroutine
from typing import Any

from pydantic import ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from igni_extension.environment import HostEndpoint
from igni_extension.errors import HostError, HostUnavailable, NotConfigured
from igni_extension.hooks import HookHandlers
from igni_extension.service_events import SERVICE_EVENT, ServiceEventHandlers
from igni_extension.signals import SignalHandlers
from igni_extension.wire import (
    HOST_MESSAGE,
    Hello,
    HookMessage,
    HostMessage,
    Op,
    Reply,
    Request,
    SignalMessage,
    SubscribeOutcome,
)

logger = logging.getLogger(__name__)


class HostConnection:
    """One extension process's connection to the igni host (`ext.connection`).

    What an extension author may read or call:

    - `configured` — whether igni gave the process the host's address;
      `False` outside igni.
    - `connected` — whether the socket is open now.
    - `granted`, `schema_version` — what the host said on connecting: the
      `permissions.host` grants this extension holds, and the version of
      its object model. Empty until the first connection.
    - `await connect()` — connect, and subscribe to every handled signal.
      Idempotent. Raises `HostUnavailable` when the host does not answer.
    - `await serve_forever()` — stay connected, reconnecting every
      `RETRY_SECONDS`, until cancelled; returns at once when not
      `configured`. `ext.run()` runs it.
    - `await close()` — close the socket and stop what it was running.

    `request` is how `ext.host` reaches the host; use `ext.host` instead.
    """

    TIMEOUT = 120.0
    """How long a request waits for its answer."""
    RETRY_SECONDS = 2.0
    """Between attempts to reach a host that is not answering yet."""
    MAX_FRAME = 8 * 1024 * 1024
    """The largest frame either side sends."""

    def __init__(
        self,
        endpoint: HostEndpoint,
        signals: SignalHandlers,
        hooks: HookHandlers,
        service_events: ServiceEventHandlers,
    ) -> None:
        self._endpoint = endpoint
        self._signals = signals
        self._hooks = hooks
        self._service_events = service_events
        self._socket: ClientConnection | None = None
        self._reader: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._ids = itertools.count(1)
        self._waiting: dict[int | str, asyncio.Future[Reply]] = {}
        self._hello: asyncio.Future[Hello] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self.granted: list[str] = []
        """What the host said this extension holds, after connecting."""
        self.schema_version = ""
        """The version of its object model the host said it speaks, after connecting."""
        signals.when_new(self._new_signal)

    @property
    def configured(self) -> bool:
        """Whether igni gave this process the host's address (`IGNI_HOST_URL`, `IGNI_HOST_SECRET`)."""
        return self._endpoint.configured

    @property
    def connected(self) -> bool:
        """Whether the socket to the host is open now."""
        return self._socket is not None

    # ── HostLink ──────────────────────────────────────────────────

    async def request(
        self,
        op: str,
        path: str,
        *,
        window: str | None = None,
        session: str | None = None,
        params: dict[str, Any] | None = None,
        value: Any = None,
    ) -> Any:
        """One `get`, `set` or `call` on the host, answered.

        What `ext.host` is made of; use `ext.host` instead. Raises
        `NotConfigured` outside igni, `HostUnavailable` when the host cannot be
        reached, and `HostError` when it refuses.
        """
        if not self.configured:
            raise NotConfigured(
                f"host.{path}: igni did not give this process the host's address "
                "(IGNI_HOST_URL, IGNI_HOST_SECRET) — it is not running inside igni"
            )
        await self.connect()
        reply = await self._send(
            Request(
                op=Op(op),
                path=path,
                window=window,
                session=session,
                params=params or {},
                value=value,
            )
        )
        return reply.result_or_raise()

    # ── The socket ────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        """The secret, and — where there is one — this process's group.

        igni ends the group if the process hangs and it has to restart
        it; it checks that it started the group's leader first.
        """
        headers = {"Authorization": f"Bearer {self._endpoint.secret}"}
        if hasattr(os, "getpgid"):
            headers["X-Igni-Process-Group"] = str(os.getpgid(0))
        return headers

    async def connect(self) -> None:
        """Connect and say which signals are handled. Idempotent."""
        async with self._lock:
            if self._socket is not None:
                return
            try:
                socket = await connect(
                    self._endpoint.url,
                    additional_headers=self._headers(),
                    max_size=self.MAX_FRAME,
                    compression=None,
                )
            except (OSError, WebSocketException) as exc:
                raise HostUnavailable(f"the igni host did not answer: {exc}") from exc
            self._socket = socket
            self._hello = asyncio.get_running_loop().create_future()
            self._reader = asyncio.create_task(self._read(socket))
            try:
                hello = await asyncio.wait_for(asyncio.shield(self._hello), self.TIMEOUT)
            except TimeoutError as exc:
                await self._drop()
                raise HostUnavailable("the igni host did not say hello") from exc
            self.granted = list(hello.granted)
            self.schema_version = hello.schema_version
        wires = self._signals.wires()
        if wires:
            await self._subscribe(wires)

    async def serve_forever(self) -> None:
        """Stay connected while the process runs, so signals keep arriving."""
        if not self.configured:
            return
        while True:
            try:
                await self.connect()
            except HostUnavailable as exc:
                logger.debug("igni: %s; trying again", exc)
                await asyncio.sleep(self.RETRY_SECONDS)
                continue
            reader = self._reader
            if reader is not None:
                # Waited on, not awaited: its ending is not this loop's to raise.
                await asyncio.wait({reader})
                self._report(reader)
            await asyncio.sleep(self.RETRY_SECONDS)

    async def close(self) -> None:
        """Close the socket, and cancel the signal, hook and service event work it started."""
        await self._drop()
        for task in list(self._tasks):
            task.cancel()

    async def _send(self, request: Request) -> Reply:
        socket = self._socket
        if socket is None:
            raise HostUnavailable("not connected to the igni host")
        request_id = next(self._ids)
        future: asyncio.Future[Reply] = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future
        try:
            await socket.send(request.numbered(request_id).frame())
            limit = None if request.waits_on_the_person else self.TIMEOUT
            return await asyncio.wait_for(future, limit)
        except TimeoutError as exc:
            # Before `OSError`, which a `TimeoutError` is.
            raise HostUnavailable(f"host.{request.path} got no answer") from exc
        except (OSError, WebSocketException) as exc:
            raise HostUnavailable(f"the igni host went away: {exc}") from exc
        finally:
            self._waiting.pop(request_id, None)

    async def _subscribe(self, wires: list[str]) -> None:
        reply = await self._send(Request.subscribe(wires))
        outcome = SubscribeOutcome.model_validate(reply.result_or_raise())
        for wire in outcome.not_granted:
            logger.warning(
                "igni: %s will never arrive — its object is not in permissions.host", wire
            )
        for wire in outcome.unknown:
            logger.warning("igni: this igni has no signal %s", wire)

    def _new_signal(self, wire: str) -> None:
        if self._socket is None:
            return  # sent with the rest on connect
        self._spawn(self._subscribe([wire]))

    async def _read(self, socket: ClientConnection) -> None:
        try:
            async for raw in socket:
                try:
                    message: HostMessage = HOST_MESSAGE.validate_json(raw)
                except ValidationError as exc:
                    logger.warning(
                        "igni: skipped a message from the host this SDK does not read: %s", exc
                    )
                    continue
                self._receive(message)
        except WebSocketException as exc:
            logger.debug("igni: the host's socket closed: %s", exc)
        finally:
            if self._socket is socket:
                self._socket = None
            if self._hello is not None and not self._hello.done():
                # Hung up before saying hello: connect() need not wait out TIMEOUT.
                self._hello.set_exception(HostUnavailable("the igni host went away"))
            for waiter in self._waiting.values():
                if not waiter.done():
                    waiter.set_exception(HostUnavailable("the igni host went away"))

    def _receive(self, message: HostMessage) -> None:
        match message:
            case Hello():
                if self._hello is not None and not self._hello.done():
                    self._hello.set_result(message)
            case Reply():
                waiter = self._waiting.get(message.id) if message.id is not None else None
                if waiter is not None and not waiter.done():
                    waiter.set_result(message)
            case SignalMessage():
                # A task, not an await: a handler that reads the model
                # needs this loop free to receive the answer.
                self._spawn(self._signals.deliver(message.signal, message.value))
            case HookMessage():
                # Off the read loop, as a signal is handled; igni waits on
                # a deciding one, against a deadline.
                if message.decides:
                    self._spawn(self._answer(message))
                else:
                    self._spawn(self._hooks.tell(message.event, message.value, message.caller))

    async def _answer(self, hook: HookMessage) -> None:
        hook_id = hook.id or ""
        if hook.event == SERVICE_EVENT:
            answer = await self._service_events.answer(hook_id, hook.value, hook.caller)
        else:
            answer = await self._hooks.answer(hook_id, hook.event, hook.value, hook.caller)
        try:
            (await self._send(Request.answer(answer))).result_or_raise()
        except (HostError, HostUnavailable) as exc:
            # Too late, or the host went away: the event went ahead or not
            # without this answer, as igni decides for a silence.
            logger.warning("igni: the answer to %s did not count: %s", hook.event, exc)

    async def _drop(self) -> None:
        socket, self._socket = self._socket, None
        if socket is not None:
            try:
                await socket.close()
            except (OSError, WebSocketException) as exc:
                logger.debug("igni: closing the host's socket: %s", exc)
        reader, self._reader = self._reader, None
        if reader is not None:
            reader.cancel()
            await asyncio.wait({reader})
            self._report(reader)

    @staticmethod
    def _report(reader: asyncio.Task[None]) -> None:
        """Log the reader's own failure; its being cancelled, or the socket closing, is not one."""
        if reader.cancelled():
            return
        error = reader.exception()
        if error is not None:
            logger.error("igni: reading the host's socket failed", exc_info=error)

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


__all__ = ["HostConnection"]

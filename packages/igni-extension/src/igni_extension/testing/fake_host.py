"""igni's host object model for one extension process, on a loopback socket.

The way igni serves `ext.host`:

    async with FakeHost(values={"chat.processing": False}) as host:
        ext = IgniExtension("acme.example", environ=host.environment())
        assert await ext.host.chat.processing is False
        await host.emit("chat.run_completed", {...})
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import secrets
from collections.abc import Callable
from types import TracebackType
from typing import Any

import anyio
from pydantic import BaseModel, ConfigDict
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from igni_extension.caller import Caller
from igni_extension.host_model import SCHEMA_VERSION
from igni_extension.wire import (
    ErrorBody,
    Hello,
    HookAnswer,
    HookMessage,
    Op,
    Reply,
    Request,
    SignalMessage,
    SubscribeOutcome,
)


class HostCall(BaseModel):
    """One `get`, `set` or `call` an extension made of `FakeHost`.

    What the request asked, without the number the connection gave it, so
    a test can compare it with one it writes down.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)

    op: str
    """`get`, `set` or `call`."""
    path: str
    """The member asked: `chat.processing`, `chat.post`."""
    window: str | None = None
    """The window, for `host.windows.ui(id)`."""
    session: str | None = None
    """The session, for `host.sessions.chat(id)`."""
    params: dict[str, Any] = {}
    """A call's parameters, by name."""
    value: Any = None
    """The value of a `set`."""

    @classmethod
    def of(cls, request: Request) -> HostCall:
        """What `request` asked, without its number.

        Args:
            request: The request the extension sent, with the number the connection gave it.
        """
        return cls(
            op=request.op.value,
            path=request.path,
            window=request.window,
            session=request.session,
            params=dict(request.params),
            value=request.value,
        )


class FakeHost:
    """igni's host object model for one extension process, on a loopback socket.

    Speaks the protocol igni does (`docs/HOST_MODEL_PROTOCOL.md` in igni).
    What it answers is up to the test:

    * `values` — `path -> value` for `get`; a `set` stores into it;
    * `answers` — `path -> value` (or a callable of the params) for `call`;
    * `refusals` — `path -> (code, message)`: that member is refused, as
      igni refuses an object the manifest does not grant;

    `emit(signal, value)` fires a signal at whoever subscribed, and
    `hook(event, value)` asks the extension about a deciding hook event as
    igni does, and returns its answer's parameters as they crossed the
    wire; `tell(event, value)` tells it one
    that decides nothing. Every `get`, `set` and `call` asked is kept in
    `calls`.

    Args:
        extension_id: The extension the host serves: `acme.example`.
        granted: The `permissions.host` grants the hello says the extension holds:
            `["chat.read", "chat.post"]`.
        values: `path -> value` for a `get`; a `set` stores into it.
        answers: `path -> value`, or a callable of the params, for a `call`.
        refusals: `path -> (code, message)`: that member is refused with that code.
    """

    def __init__(
        self,
        *,
        extension_id: str = "acme.example",
        granted: tuple[str, ...] = (),
        values: dict[str, Any] | None = None,
        answers: dict[str, Any] | None = None,
        refusals: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self.extension_id = extension_id
        """The extension the host serves."""
        self.granted = list(granted)
        """The `permissions.host` grants the hello says the extension holds."""
        self.values: dict[str, Any] = dict(values or {})
        """`path -> value` for a `get`; a `set` stores into it. An unknown path is `not_found`."""
        self.answers: dict[str, Any] = dict(answers or {})
        """`path -> value`, or a callable of the params, for a `call`."""
        self.refusals: dict[str, tuple[str, str]] = dict(refusals or {})
        """`path -> (code, message)`: that member is refused with that code."""
        self.secret = secrets.token_urlsafe(16)
        """The secret a process must present: `IGNI_HOST_SECRET` in `environment()`."""
        self.calls: list[HostCall] = []
        """Every `get`, `set` and `call` the extension made, in order."""
        self.subscribed: set[str] = set()
        """The signals the extension subscribed to, by wire name."""
        self.url = ""
        """The socket's address once started: `IGNI_HOST_URL` in `environment()`."""
        self._subscribed_changed = asyncio.Event()
        self._sockets: set[ServerConnection] = set()
        self._server: Server | None = None
        self._hooks: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._hook_ids = itertools.count(1)
        self._handlers: dict[Op, Callable[[Request], Reply]] = {
            Op.ANSWER: self._answer_hook,
            Op.SUBSCRIBE: self._subscribe,
            Op.GET: self._get,
            Op.SET: self._set,
            Op.CALL: self._call,
        }

    def environment(self, **extra: str) -> dict[str, str]:
        """The variables igni starts the process with, for its host.

        Args:
            extra: More variables to hand the process, as igni set them: `IGNI_EXTENSION_DATA`.
        """
        return {"IGNI_HOST_URL": self.url, "IGNI_HOST_SECRET": self.secret, **extra}

    async def __aenter__(self) -> FakeHost:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stop()

    async def start(self) -> None:
        """Listen on a free loopback port. `async with FakeHost()` calls it."""
        self._server = await serve(self._serve, "127.0.0.1", 0, compression=None)
        port = int(next(iter(self._server.sockets)).getsockname()[1])
        self.url = f"ws://127.0.0.1:{port}/v1/host"

    async def stop(self) -> None:
        """Stop listening and close every socket. `async with` calls it on the way out."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def emit(self, signal: str, value: Any) -> None:
        """Fire `signal` (its wire name) at every connection that subscribed.

        Args:
            signal: The signal's wire name: `chat.run_completed`.
            value: The value the signal carries, as the host sends it.
        """
        if signal in self.subscribed:
            await self._send_all(SignalMessage(op="signal", signal=signal, value=value))

    async def hook(
        self, event: str, value: Any, timeout: float = 5.0, *, caller: Caller | None = None
    ) -> dict[str, Any]:
        """Ask the connected extension about a deciding `event`, as igni does.

        Its answer's parameters, as they crossed the wire.

        Args:
            event: The hook event's name, as igni sends it: `PreToolUse`.
            value: The event's value, as igni sends it.
            timeout: Seconds to wait for the extension's answer before giving up.
            caller: The producer the event is for; `None` when it is for nobody.
        """
        await self._connected(timeout)
        hook_id = f"h-{next(self._hook_ids)}"
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._hooks[hook_id] = future
        await self._send_all(self._hook_message(hook_id, event, value, caller))
        try:
            with anyio.fail_after(timeout):
                return await future
        finally:
            self._hooks.pop(hook_id, None)

    async def tell(
        self, event: str, value: Any, timeout: float = 5.0, *, caller: Caller | None = None
    ) -> None:
        """Tell the connected extension an `event` that decides nothing, as igni does.

        Args:
            event: The hook event's name, as igni sends it: `SessionStart`.
            value: The event's value, as igni sends it.
            timeout: Seconds to wait for the extension to be connected before giving up.
            caller: The producer the event is for; `None` when it is for nobody.
        """
        await self._connected(timeout)
        await self._send_all(self._hook_message(None, event, value, caller))

    async def wait_subscribed(self, signal: str, timeout: float = 5.0) -> None:
        """Wait until the extension has subscribed to `signal`.

        Args:
            signal: The signal's wire name: `chat.run_completed`.
            timeout: Seconds to wait for the subscription before giving up.
        """
        with anyio.fail_after(timeout):
            while signal not in self.subscribed:
                self._subscribed_changed.clear()
                await self._subscribed_changed.wait()

    @staticmethod
    def _hook_message(
        hook_id: str | None, event: str, value: Any, caller: Caller | None
    ) -> HookMessage:
        principal = caller.model_dump(mode="json") if caller is not None else None
        return HookMessage(op="hook", id=hook_id, event=event, value=value, principal=principal)

    async def _connected(self, timeout: float) -> None:
        with anyio.fail_after(timeout):
            while not self._sockets:
                await asyncio.sleep(0.01)

    async def _send_all(self, message: SignalMessage | HookMessage) -> None:
        frame = message.model_dump_json()
        for socket in list(self._sockets):
            # A connection closing as the frame goes out misses it, as with igni.
            with contextlib.suppress(ConnectionClosed):
                await socket.send(frame)

    async def _serve(self, socket: ServerConnection) -> None:
        authorization = (
            socket.request.headers.get("Authorization") if socket.request is not None else None
        )
        if authorization != f"Bearer {self.secret}":
            await socket.close(4001, "unauthorized")
            return
        self._sockets.add(socket)
        try:
            hello = Hello(
                op="hello",
                schema_version=SCHEMA_VERSION,
                granted=self.granted,
                extension_id=self.extension_id,
            )
            await socket.send(hello.model_dump_json())
            async for raw in socket:
                reply = self._answer(Request.model_validate_json(raw))
                await socket.send(reply.model_dump_json())
        finally:
            self._sockets.discard(socket)

    def _answer(self, request: Request) -> Reply:
        if request.op in (Op.GET, Op.SET, Op.CALL):
            self.calls.append(HostCall.of(request))
            if request.path in self.refusals:
                code, message = self.refusals[request.path]
                return self._refused(request, code, message)
        return self._handlers[request.op](request)

    def _answer_hook(self, request: Request) -> Reply:
        answer = HookAnswer.model_validate(request.params)
        waiting = self._hooks.get(answer.hook)
        if waiting is None or waiting.done():
            return self._refused(request, "not_found", "nothing waits on it")
        waiting.set_result(dict(request.params))
        return self._ok(request)

    def _subscribe(self, request: Request) -> Reply:
        self.subscribed.update(request.signals)
        self._subscribed_changed.set()
        return self._ok(request, SubscribeOutcome(subscribed=request.signals).model_dump())

    def _get(self, request: Request) -> Reply:
        if request.path not in self.values:
            return self._refused(request, "not_found", request.path)
        return self._ok(request, self.values[request.path])

    def _set(self, request: Request) -> Reply:
        self.values[request.path] = request.value
        return self._ok(request)

    def _call(self, request: Request) -> Reply:
        answer = self.answers.get(request.path)
        return self._ok(request, answer(dict(request.params)) if callable(answer) else answer)

    @staticmethod
    def _ok(request: Request, result: Any = None) -> Reply:
        return Reply(op="reply", id=request.id, ok=True, result=result)

    @staticmethod
    def _refused(request: Request, code: str, message: str) -> Reply:
        return Reply(
            op="reply", id=request.id, ok=False, error=ErrorBody(code=code, message=message)
        )

"""Calling igni's methods: `Caller` sends them, `Call` follows the ones that stream.

Every generated method (`igni_client.api`) goes through a `Caller` — the
connection, and the session the call is for. A method's arguments are
checked against its arguments model before anything is sent; its answer is
read into its result type; an error igni answers raises the `RpcError`
subclass it is.

A method that streams returns a `Call`. Await it for the result:

    result = await session.workflows.run("nightly")

or enter it to follow the events that call causes as well:

    async with session.workflows.run("nightly") as run:
        async for event in run:
            print(event.payload)
        result = await run.result()

`async with` starts listening before the call is sent, so nothing it
causes is missed, and `async for` yields only this call's events — told
apart by what they carry (`igni_client.follow`) — ending when igni has no
more to send for it. Leaving the block stops listening; the call itself is
igni's and goes on.
"""

from __future__ import annotations

import asyncio
import collections
from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, TypeAdapter, ValidationError

from igni_client import access
from igni_client.errors import InvalidArguments, RpcError, UnexpectedAnswer
from igni_client.follow import RULES, Context, Correlation, Rule
from igni_client.models import ErrorMessage, RpcResponse
from igni_client.routing import Interruption
from igni_client.wire import Event

if TYPE_CHECKING:
    from igni_client.connection import Connection

#: `Connection.ask`'s own timeout (`Connection.RPC_TIMEOUT`); kept here so this
#: module does not import the connection, which imports the generated table.
DEFAULT_TIMEOUT = -1.0


@dataclass(frozen=True)
class MethodSpec:
    """One method, as the contract describes it."""

    #: Its name on the wire.
    wire: str
    #: Where it is in Python: `igni.processes.tail`, `session.plan.approve`.
    python: str
    #: `igni` (igni as a whole) or `session` (one session).
    scope: str
    #: Who may call it: `client`, `approver` or `window` (`igni_client.access`).
    access: str
    #: `rpc_response`, or `message` when igni answers with the result itself.
    reply: str
    #: The messages and push channels it causes.
    streams: tuple[str, ...]
    #: The push channels it may cause while it runs, beyond those it streams.
    may_stream: tuple[str, ...]
    #: How long it takes: `instant`, `io`, `network`, `long` or `person`.
    duration: str
    #: A timeout that leaves a healthy call room; `None`: none.
    timeout_seconds: float | None
    #: How its events are told from every other call's, as the contract says;
    #: `None` where the contract says nothing.
    correlate: Correlation | None
    #: Whether its `Call` follows those (`igni_client.follow`).
    followed: bool


def spec(method: str) -> MethodSpec:
    """The generated description of `method`."""
    from igni_client.api import METHODS  # the generated table imports this module

    return METHODS[method]


def timeout_of(method: str) -> float | None:
    """How long to wait for `method`'s answer, as igni's contract says.

    The contract classes every method by how long it takes — `instant`,
    `io`, `network`, `long` or `person` — and gives each a timeout that
    leaves a healthy call room. `None` waits for as long as it takes:
    the call waits for the person.
    """
    try:
        timeout = spec(method).timeout_seconds
    except KeyError:
        return DEFAULT_TIMEOUT
    return None if timeout is None else float(timeout)


def reply_of(method: str) -> str:
    """What `method`'s answer looks like, as igni's contract says.

    `rpc_response` for the methods igni answers with one, `message` for
    those it answers with a message of their own. The events a call
    streams may carry the request's id, so this says which of the frames
    that carry it is the answer.
    """
    try:
        return spec(method).reply
    except KeyError:
        return "rpc_response"


class Caller:
    """Calls igni's methods for one session — or, with no session, for igni as a whole."""

    def __init__(self, conn: Connection, session_id: str = "") -> None:
        self._conn = conn
        #: The session calls are for; empty for igni as a whole.
        self.session_id = session_id

    @property
    def client_id(self) -> str:
        """igni's name for this connection."""
        return self._conn.client_id

    @property
    def conn(self) -> Connection:
        return self._conn

    def new_id(self, prefix: str) -> str:
        """An id of this client's own making, for a call that takes one.

        igni echoes it back on the call's own events — a run's id, the
        writer's own name for a change — so that they can be told from
        another call's.
        """
        return self._conn.router.new_id(prefix)

    async def rpc[R](
        self,
        method: str,
        args: type[BaseModel],
        values: dict[str, Any],
        result: TypeAdapter[R],
    ) -> R:
        """Call `method` with `values` (checked as `args`) and read its answer as `result`."""
        return await self.answer(method, self.arguments(method, args, values), result)

    def follow[R](
        self,
        method: str,
        args: type[BaseModel],
        values: dict[str, Any],
        result: TypeAdapter[R],
    ) -> Call[R, Any]:
        """A `Call` of `method`: await it for the result, or enter it to follow its events too."""
        return Call(self, method, self.arguments(method, args, values), result, RULES[method])

    def arguments(self, method: str, args: type[BaseModel], values: dict[str, Any]) -> BaseModel:
        """`values` as `method`'s arguments, or `InvalidArguments`; `AccessRefused` first
        when this connection cannot make the call."""
        access.check(method, spec(method).access, self._conn.target.standing)
        try:
            return args.model_validate(values)
        except ValidationError as exc:
            raise InvalidArguments(method, str(exc)) from exc

    async def answer[R](
        self, method: str, params: BaseModel, result: TypeAdapter[R], request_id: str = ""
    ) -> R:
        """Send the call and read what igni answers."""
        reply = await self._conn.ask(
            method,
            params.model_dump(mode="json", by_alias=True),
            session_id=self.session_id,
            timeout=timeout_of(method),
            request_id=request_id,
            reply=reply_of(method),
        )
        return read(method, reply, result)

    async def send(self, message: type[BaseModel], values: dict[str, Any]) -> None:
        """Send a message igni answers nothing to."""
        await self._conn.send(self._message(message, values, ""))

    async def request[R](
        self, message: type[BaseModel], values: dict[str, Any], reply: TypeAdapter[R]
    ) -> R:
        """Send a message igni answers with a message of its own, carrying its id."""
        request_id = self._conn.router.new_id("msg")
        frame = self._message(message, values, request_id)
        wire_type = str(getattr(frame, "type", ""))
        answer = await self._conn.exchange(frame, request_id, wire_type)
        if isinstance(answer, ErrorMessage):
            raise RpcError.of(wire_type, answer.text)
        return read(wire_type, answer, reply)

    def _message(self, message: type[BaseModel], values: dict[str, Any], request_id: str) -> Any:
        envelope: dict[str, Any] = {"session_id": self.session_id} if self.session_id else {}
        if request_id:
            envelope["id"] = request_id
        try:
            return message.model_validate({**envelope, **values})
        except ValidationError as exc:
            raise InvalidArguments(message.__name__, str(exc)) from exc


def read[R](method: str, reply: Event, result: TypeAdapter[R]) -> R:
    """The result in `reply`: an `RpcResponse`'s, or the message igni answered with instead."""
    if isinstance(reply, ErrorMessage):
        raise RpcError.of(method, reply.text)
    value: Any = reply.result if isinstance(reply, RpcResponse) else reply
    try:
        return result.validate_python(value)
    except ValidationError as exc:
        raise UnexpectedAnswer(
            method, f"igni's answer is not what the method returns: {exc}"
        ) from exc


class Call[R, E]:
    """One call of a method that streams: awaitable for its result, followable for its events.

    `await call` sends it and returns the result. `async with call:` sends
    it and listens; inside, `async for event in call` yields this call's
    events and `await call.result()` its result.
    """

    def __init__(
        self,
        caller: Caller,
        method: str,
        params: BaseModel,
        result: TypeAdapter[R],
        rule: Rule,
    ) -> None:
        self.method = method
        self._caller = caller
        self._params = params
        self._result = result
        self._rule = rule
        #: The id this call is sent as: what igni's messages carry back
        #: when they are this call's own.
        self._request_id = caller.conn.router.new_id("rpc")
        self._context = Context(
            args=params, session_id=caller.session_id, request_id=self._request_id
        )
        self._queue: asyncio.Queue[Event | Interruption] | None = None
        self._task: asyncio.Future[R] | None = None
        self._held: list[Event] = []
        self._ready: collections.deque[E] = collections.deque()
        self._settled = False
        self._done = False

    # ── The result ──

    def __await__(self) -> Generator[Any, None, R]:
        return self.result().__await__()

    async def result(self) -> R:
        """The call's result: sent now when the call was not entered, else awaited."""
        if self._task is None:
            return await self._caller.answer(
                self.method, self._params, self._result, self._request_id
            )
        return await asyncio.shield(self._task)

    # ── Following ──

    async def __aenter__(self) -> Self:
        if self._task is not None:
            raise RuntimeError(f"this call of {self.method} was already entered")
        self._queue = self._caller.conn.router.follow()
        self._task = asyncio.ensure_future(
            self._caller.answer(self.method, self._params, self._result, self._request_id)
        )
        self._task.add_done_callback(_retrieve)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._queue is not None:
            self._caller.conn.router.unfollow(self._queue)

    def __aiter__(self) -> Self:
        if self._task is None:
            raise RuntimeError(
                f"follow a call's events inside `async with`: async with ….{self.method}(...) as call"
            )
        return self

    async def __anext__(self) -> E:
        assert self._task is not None and self._queue is not None
        while True:
            if self._ready:
                return self._ready.popleft()
            if self._done:
                raise StopAsyncIteration
            if self._task.done() and not self._settled:
                while not self._queue.empty():
                    self._take(self._queue.get_nowait())
                self._settle()
                continue
            get = asyncio.ensure_future(self._queue.get())
            waiting: set[asyncio.Future[Any]] = {get} if self._settled else {get, self._task}
            try:
                await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
            finally:
                if not get.done():
                    get.cancel()
            if get.done() and not get.cancelled():
                self._take(get.result())

    def _take(self, item: Event | Interruption) -> None:
        if isinstance(item, Interruption):
            self._done = True
            raise item.error
        if self._rule.needs_result and not self._settled:
            self._held.append(item)
            return
        self._consider(item)

    def _consider(self, event: Event) -> None:
        if self._done or not self._rule.is_ours(self._context, event, self.method):
            return
        self._ready.append(event)  # type: ignore[arg-type]  # the rule matched one of E
        if self._rule.last(self._context, event):
            self._context.ended = True
            self._done = True

    def _settle(self) -> None:
        assert self._task is not None
        self._settled = True
        error = self._task.exception()
        if error is not None:
            self._done = True
            raise error
        self._context.result = self._task.result()
        self._context.has_result = True
        held, self._held = self._held, []
        for event in held:
            self._consider(event)
        if self._rule.ends_with(self._context):
            self._done = True

    def __repr__(self) -> str:
        return f"Call({self.method})"


def _retrieve(task: asyncio.Future[Any]) -> None:
    """Mark a call's failure as seen: it is raised to whoever awaits or follows it."""
    if not task.cancelled():
        task.exception()


__all__ = ["Call", "Caller", "MethodSpec", "read", "spec", "timeout_of"]

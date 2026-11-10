"""Where each message from igni goes: the call waiting for it, a run's stream, every listener.

igni sends every message to every client attached to it, so nothing here
assumes a message is for us: a reply is matched by the `id` of the
request it answers, and everything goes to whoever listens.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import secrets

from igni_client.errors import IgniClientError
from igni_client.wire import Event


class Interruption:
    """Put on a stream's queue when its run can no longer be followed."""

    def __init__(self, error: IgniClientError) -> None:
        self.error = error


class Router:
    """The requests in flight, the streams open and the listeners, by request id."""

    def __init__(self) -> None:
        # igni sends every client's messages to every client: a request id
        # carries this router's own tag, so another client's never matches it.
        self._tag = secrets.token_hex(4)
        self._ids = itertools.count(1)
        self._waiting: dict[str, asyncio.Future[Event]] = {}
        self._replies: dict[str, str] = {}
        self._streams: dict[str, asyncio.Queue[Event | Interruption]] = {}
        self._listeners: list[asyncio.Queue[Event]] = []
        self._followers: list[asyncio.Queue[Event | Interruption]] = []

    def new_id(self, prefix: str) -> str:
        """A request id no other client of the same igni sends: `run-1f2e3d4c-1`."""
        return f"{prefix}-{self._tag}-{next(self._ids)}"

    # ── Calls ──

    def expect(self, request_id: str, reply: str = "rpc_response") -> asyncio.Future[Event]:
        """The answer to `request_id`, once it arrives. `forget` it when done.

        `reply` is what the answer looks like: `rpc_response` for the
        methods igni answers with one, `message` for those it answers with
        a message of its own. A message that carries the request's id but
        is not the answer — one of the events a call streams — is passed
        over.
        """
        future: asyncio.Future[Event] = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future
        self._replies[request_id] = reply
        return future

    def forget(self, request_id: str) -> None:
        self._waiting.pop(request_id, None)
        self._replies.pop(request_id, None)

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

    def follow(self) -> asyncio.Queue[Event | Interruption]:
        """A queue of every message igni sends from now on, and of what interrupts it.

        A followed call (`igni_client.calls.Call`) reads it: an interruption
        ends what it follows, as it ends a run.
        """
        queue: asyncio.Queue[Event | Interruption] = asyncio.Queue()
        self._followers.append(queue)
        return queue

    def unfollow(self, queue: asyncio.Queue[Event | Interruption]) -> None:
        with contextlib.suppress(ValueError):
            self._followers.remove(queue)

    # ── Delivering ──

    def deliver(self, event: Event) -> None:
        """Hand `event` to every listener, and to the call or stream it answers."""
        for queue in self._listeners:
            queue.put_nowait(event)
        for follower in self._followers:
            follower.put_nowait(event)
        if not event.id:
            return
        waiter = self._waiting.get(event.id)
        if waiter is not None and event.type != "rpc_request" and self._is_answer(event.id, event):
            if not waiter.done():
                waiter.set_result(event)
            return
        stream = self._streams.get(event.id)
        if stream is not None:
            stream.put_nowait(event)

    def _is_answer(self, request_id: str, event: Event) -> bool:
        """Whether `event` is the answer to `request_id`, and not one of its events.

        The events a call streams may carry the request's own id — the
        approvals an attach shows again do — so the id alone does not say
        which is which: what the answer looks like does.
        """
        if self._replies.get(request_id, "rpc_response") == "rpc_response":
            return event.type in ("rpc_response", "error")
        return event.type != "rpc_response"

    def interrupt(self, error: IgniClientError) -> None:
        """End every call and run in flight: they cannot be followed any more."""
        for waiter in list(self._waiting.values()):
            if not waiter.done():
                waiter.set_exception(error)
        for queue in [*self._streams.values(), *self._followers]:
            queue.put_nowait(Interruption(error))

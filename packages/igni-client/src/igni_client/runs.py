"""A run: one prompt, followed from the first token to the end, approvals included.

A run is a stream of `Event`s, across every stream it opens: the prompt's,
and one for each answered approval (see `igni_client.approvals`).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from igni_client.approvals import ApprovalRequested
from igni_client.connection import Connection
from igni_client.errors import NotAllowed
from igni_client.models import (
    ErrorMessage,
    HitlDecision,
    HitlResponseBatch,
    RequirementDetails,
    RunPaused,
    StreamEnd,
    UserMessage,
)
from igni_client.routing import Interruption
from igni_client.wire import Event


class Run:
    """Follows one run across the streams it opens: the prompt's, and each approval's."""

    def __init__(self, conn: Connection, session_id: str) -> None:
        self._conn = conn
        self._session_id = session_id
        self._queue: asyncio.Queue[Event | Interruption] = asyncio.Queue()
        self._open: set[str] = set()
        # The streams opened by answering an approval.
        self._answers: set[str] = set()
        self._pending: ApprovalRequested | None = None

    async def stream(self, frame: UserMessage) -> AsyncIterator[Event | ApprovalRequested]:
        """Send `frame` (a `user_message`) and yield the run until it ends or waits unanswered."""
        try:
            await self._start(frame)
            while self._open:
                item = await self._queue.get()
                if isinstance(item, Interruption):
                    raise item.error
                if isinstance(item, ErrorMessage) and item.id in self._answers:
                    # igni refused the answer: this program may not approve.
                    raise NotAllowed(item.text or "igni refused the approval")
                if isinstance(item, StreamEnd):
                    self._open.discard(item.id)
                    self._conn.router.close_stream(item.id)
                    continue
                if isinstance(item, RunPaused):
                    self._pending = ApprovalRequested(item, self._answer)
                    yield self._pending
                    continue
                if isinstance(item, RequirementDetails) and self._pending is not None:
                    for requirement in self._pending.requirements:
                        if requirement.requirement_id == item.requirement_id:
                            requirement.details = item.details
                            requirement.details_pending = False
                yield item
        finally:
            for request_id in self._open:
                self._conn.router.close_stream(request_id)
            self._open.clear()

    async def _start(self, frame: UserMessage | HitlResponseBatch) -> None:
        self._conn.router.open_stream(frame.id, self._queue)
        self._open.add(frame.id)
        await self._conn.send(frame)

    async def _answer(self, decisions: list[HitlDecision]) -> None:
        request_id = self._conn.router.new_id("hitl")
        self._answers.add(request_id)
        await self._start(
            HitlResponseBatch(id=request_id, session_id=self._session_id, decisions=decisions)
        )


def answer_elsewhere(
    conn: Connection, session_id: str
) -> Callable[[list[HitlDecision]], Awaitable[None]]:
    """How to answer a pause seen outside a run of this client's (`Session.events()`).

    The answer is sent; the resumed run is broadcast like any other, so
    whoever watches the session sees it go on.
    """

    async def answer(decisions: list[HitlDecision]) -> None:
        await conn.send(
            HitlResponseBatch(
                id=conn.router.new_id("hitl"), session_id=session_id, decisions=decisions
            )
        )

    return answer

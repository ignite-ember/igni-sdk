"""A run: one prompt, followed from the first token to the end, approvals included.

A run is a stream of `Event`s. When the agent wants to use a tool that
needs a person's yes, igni pauses the run and the stream yields an
`ApprovalRequested`. Answer it in the loop — `approve()`, `reject()` or
`decide()` — and the same loop carries on with the resumed run:

    async for event in session.send("Clean up the build directory"):
        if isinstance(event, ApprovalRequested):
            await event.approve()

igni asks about every tool call of a pause together, and a call left out
of the answer counts as refused, so each answer covers all of them.

A loop that ends without answering leaves the run waiting on igni's side;
it is offered again the next time the session is opened.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from igni_client.connection import Connection, Interruption
from igni_client.errors import ApprovalRequired, NotAllowed, RunFailed
from igni_client.events import (
    ContentDelta,
    ErrorMessage,
    Event,
    Requirement,
    RequirementDetails,
    RunCompleted,
    RunError,
    RunPaused,
    StreamEnd,
    ToolCompleted,
)

Choice = Literal["once", "always", "similar"]


class Decision(BaseModel):
    """The answer to one tool call waiting for approval."""

    model_config = ConfigDict(frozen=True)

    action: Literal["confirm", "reject"]
    #: How far the answer reaches: this call (`once`), every identical
    #: call (`always`), similar calls (`similar`), or — for a refusal —
    #: `deny` to refuse such calls from now on.
    choice: str = "once"

    @classmethod
    def allow(cls, choice: Choice = "once") -> Decision:
        """Let the call run. `always` and `similar` save a permission rule for next time."""
        return cls(action="confirm", choice=choice)

    @classmethod
    def deny(cls, *, remember: bool = False) -> Decision:
        """Refuse the call. `remember=True` saves a rule refusing it from now on."""
        return cls(action="reject", choice="deny" if remember else "once")


Answer = bool | Decision
Policy = bool | Callable[[Requirement], Answer | Awaitable[Answer]]


class ApprovalRequested:
    """The run paused: these tool calls wait for a yes or a no."""

    def __init__(
        self, paused: RunPaused, answer: Callable[[list[dict[str, Any]]], Awaitable[None]]
    ) -> None:
        self.paused = paused
        self._answer = answer
        self.answered = False

    @property
    def run_id(self) -> str:
        return self.paused.run_id

    @property
    def requirements(self) -> list[Requirement]:
        return self.paused.requirements

    async def approve(self, choice: Choice = "once") -> None:
        """Let every call run."""
        await self.decide({r.requirement_id: Decision.allow(choice) for r in self.requirements})

    async def reject(self, *, remember: bool = False) -> None:
        """Refuse every call."""
        await self.decide(
            {r.requirement_id: Decision.deny(remember=remember) for r in self.requirements}
        )

    async def decide(self, decisions: Mapping[str, Decision]) -> None:
        """Answer each call by its `requirement_id`. Every one must be answered."""
        if self.answered:
            raise RuntimeError("this approval was already answered")
        missing = [r.requirement_id for r in self.requirements if r.requirement_id not in decisions]
        if missing:
            raise ValueError(f"every call needs an answer; missing {missing}")
        await self._answer(
            [
                {
                    "type": "hitl_decision",
                    "requirement_id": r.requirement_id,
                    "action": decisions[r.requirement_id].action,
                    "choice": decisions[r.requirement_id].choice,
                    "set_permission_mode": "",
                }
                for r in self.requirements
            ]
        )
        self.answered = True

    def __repr__(self) -> str:
        names = ", ".join(r.friendly_name or r.tool_name for r in self.requirements)
        return f"ApprovalRequested({names})"


class Reply(BaseModel):
    """What `Session.ask()` returns: the answer, and what happened on the way."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str = ""
    thinking: str = ""
    tools: list[ToolCompleted] = Field(default_factory=list)
    #: The main run's completion, with its token counts and duration.
    completed: RunCompleted | None = None

    def __str__(self) -> str:
        return self.text


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

    async def stream(self, frame: dict[str, Any]) -> AsyncIterator[Event | ApprovalRequested]:
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
                    self._conn.close_stream(item.id)
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
                self._conn.close_stream(request_id)
            self._open.clear()

    async def _start(self, frame: dict[str, Any]) -> None:
        request_id = str(frame["id"])
        self._conn.open_stream(request_id, self._queue)
        self._open.add(request_id)
        await self._conn.send(frame)

    async def _answer(self, decisions: list[dict[str, Any]]) -> None:
        request_id = self._conn.new_id("hitl")
        self._answers.add(request_id)
        await self._start(
            {
                "type": "hitl_response_batch",
                "id": request_id,
                "session_id": self._session_id,
                "decisions": decisions,
            }
        )


async def _decide(policy: Policy, requirement: Requirement) -> Decision:
    if isinstance(policy, bool):
        answer: Answer = policy
    else:
        result = policy(requirement)
        answer = await result if inspect.isawaitable(result) else result
    if isinstance(answer, Decision):
        return answer
    return Decision.allow() if answer else Decision.deny()


async def collect(
    events: AsyncIterator[Event | ApprovalRequested], approve: Policy | None
) -> Reply:
    """`ask()`'s loop: the text, answered approvals, and the main run's completion."""
    reply = Reply()
    text: list[str] = []
    thinking: list[str] = []
    async for event in events:
        if isinstance(event, ApprovalRequested):
            if approve is None:
                raise ApprovalRequired(event.requirements)
            await event.decide(
                {r.requirement_id: await _decide(approve, r) for r in event.requirements}
            )
        elif isinstance(event, ContentDelta):
            (thinking if event.is_thinking else text).append(event.text)
        elif isinstance(event, ToolCompleted):
            reply.tools.append(event)
        elif isinstance(event, RunCompleted) and not event.parent_run_id:
            reply.completed = event
        elif isinstance(event, RunError):
            raise RunFailed(event.error or "the run failed")
    reply.text = "".join(text)
    reply.thinking = "".join(thinking)
    return reply

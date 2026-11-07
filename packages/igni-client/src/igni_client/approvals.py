"""Approvals: a paused run's tool calls, and the answers that resume it.

When the agent wants to use a tool that needs a person's yes, igni pauses
the run and the stream yields an `ApprovalRequested`. Answer it in the
loop — `approve()`, `reject()` or `decide()` — and the same loop carries
on with the resumed run:

    async for event in session.send("Clean up the build directory"):
        if isinstance(event, ApprovalRequested):
            await event.approve()

igni asks about every tool call of a pause together, and a call left out
of the answer counts as refused, so each answer covers all of them.

A loop that ends without answering leaves the run waiting on igni's side;
it is offered again the next time the session is opened.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict

from igni_client.errors import ApprovalRequired
from igni_client.events import Requirement, RunPaused
from igni_client.frames import HitlDecision, Scope

#: How far an allowed call's answer reaches.
Choice = Literal["once", "always", "similar"]


class Decision(BaseModel):
    """The answer to one tool call waiting for approval."""

    model_config = ConfigDict(frozen=True)

    action: Literal["confirm", "reject"]
    choice: Scope = "once"

    @classmethod
    def allow(cls, choice: Choice = "once") -> Decision:
        """Let the call run. `always` and `similar` save a permission rule for next time."""
        return cls(action="confirm", choice=choice)

    @classmethod
    def deny(cls, *, remember: bool = False) -> Decision:
        """Refuse the call. `remember=True` saves a rule refusing it from now on."""
        return cls(action="reject", choice="deny" if remember else "once")

    def frame(self, requirement_id: str) -> HitlDecision:
        """This answer as igni reads it, for the call `requirement_id`."""
        return HitlDecision(requirement_id=requirement_id, action=self.action, choice=self.choice)


Answer = bool | Decision
Policy = bool | Callable[[Requirement], Answer | Awaitable[Answer]]


class ApprovalRequested:
    """The run paused: these tool calls wait for a yes or a no."""

    def __init__(
        self, paused: RunPaused, answer: Callable[[list[HitlDecision]], Awaitable[None]]
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
            [decisions[r.requirement_id].frame(r.requirement_id) for r in self.requirements]
        )
        self.answered = True

    def __repr__(self) -> str:
        names = ", ".join(r.friendly_name or r.tool_name for r in self.requirements)
        return f"ApprovalRequested({names})"


class Approver:
    """Answers every approval a run asks for with one `Policy`, as `ask(approve=...)` does."""

    def __init__(self, policy: Policy | None) -> None:
        self._policy = policy

    async def answer(self, request: ApprovalRequested) -> None:
        """Decide each call of `request`; with no policy, the pause is an error."""
        if self._policy is None:
            raise ApprovalRequired(request.requirements)
        await request.decide(
            {r.requirement_id: await self._decision(self._policy, r) for r in request.requirements}
        )

    @staticmethod
    async def _decision(policy: Policy, requirement: Requirement) -> Decision:
        if isinstance(policy, bool):
            answer: Answer = policy
        else:
            result = policy(requirement)
            answer = await result if inspect.isawaitable(result) else result
        if isinstance(answer, Decision):
            return answer
        return Decision.allow() if answer else Decision.deny()

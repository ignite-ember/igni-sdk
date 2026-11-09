"""Runs, played from a script: prompts, pauses for approval, resumes on the answer, cancels."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from igni_client.models import (
    Cancel,
    HitlDecision,
    HitlResponseBatch,
    InfoMessage,
    QueueMessage,
    RequirementResolved,
    RunPaused,
    StreamEnd,
    UserMessage,
    UserMessageReceived,
)
from igni_client.testing.server import FakeSocket
from igni_client.testing.steps import Delay, Pause, Script, Step, Steps


class Continuation(BaseModel):
    """What a paused run plays once its calls are answered."""

    session_id: str
    steps: list[Step]


class FakeRuns:
    """Plays a run for every prompt, broadcasting it on `socket`."""

    def __init__(self, socket: FakeSocket) -> None:
        self._socket = socket
        #: What a prompt runs. Return the steps of the run for the prompt's text.
        self.script: Script = Steps.echo
        #: Every approval answer, in order: the decisions of each batch.
        self.decisions: list[list[HitlDecision]] = []
        self._paused: dict[str, Continuation] = {}
        self._active: dict[str, str] = {}

    async def prompt(self, message: UserMessage) -> None:
        await self._socket.broadcast(
            UserMessageReceived(
                session_id=message.session_id, text=message.text, client_id=message.client_id
            )
        )
        self._active[message.session_id] = message.id
        await self._play(message.id, message.session_id, list(self.script(message.text)))

    async def queue(self, message: QueueMessage) -> None:
        await self._socket.broadcast(
            UserMessageReceived(session_id=message.session_id, text=message.text, queued=True)
        )

    async def cancel(self, cancel: Cancel) -> None:
        active = self._active.pop(cancel.session_id, "")
        if not active:
            return
        await self._socket.broadcast(
            InfoMessage(id=active, session_id=cancel.session_id, text="Run cancelled by user.")
        )
        await self._socket.broadcast(StreamEnd(id=active, session_id=cancel.session_id))

    async def resume(self, batch: HitlResponseBatch) -> None:
        self.decisions.append(list(batch.decisions))
        continuation: Continuation | None = None
        for decision in batch.decisions:
            await self._socket.broadcast(
                RequirementResolved(
                    session_id=batch.session_id, requirement_id=decision.requirement_id
                )
            )
            continuation = self._paused.pop(decision.requirement_id, None) or continuation
        steps: list[Step] = []
        if continuation is not None:
            rejected = any(d.action == "reject" for d in batch.decisions)
            steps = Steps.rejected() if rejected else list(continuation.steps)
        self._active[batch.session_id] = batch.id
        await self._play(batch.id, batch.session_id, steps)

    async def _play(self, request_id: str, session_id: str, steps: list[Step]) -> None:
        for index, step in enumerate(steps):
            if isinstance(step, Delay):
                await asyncio.sleep(step.seconds)
            elif isinstance(step, Pause):
                await self._pause(request_id, session_id, step, steps[index + 1 :])
                return
            else:
                await self._socket.broadcast(
                    step.model_copy(update={"id": request_id, "session_id": session_id})
                )
        await self._socket.broadcast(StreamEnd(id=request_id, session_id=session_id))
        if self._active.get(session_id) == request_id:
            self._active.pop(session_id, None)

    async def _pause(
        self, request_id: str, session_id: str, pause: Pause, rest: list[Step]
    ) -> None:
        for requirement in pause.requirements:
            self._paused[requirement.requirement_id] = Continuation(
                session_id=session_id, steps=rest
            )
        await self._socket.broadcast(
            RunPaused(
                id=request_id,
                session_id=session_id,
                run_id=Steps.RUN_ID,
                requirements=pause.requirements,
            )
        )
        await self._socket.broadcast(StreamEnd(id=request_id, session_id=session_id))


__all__ = ["Continuation", "FakeRuns"]

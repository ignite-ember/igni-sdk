"""What `Session.ask()` returns: a run's whole answer, gathered from its stream."""

from __future__ import annotations

from collections.abc import AsyncIterator

from pydantic import BaseModel, ConfigDict, Field

from igni_client.approvals import ApprovalRequested, Approver
from igni_client.errors import RunFailed
from igni_client.models import ContentDelta, RunCompleted, RunError, ToolCompleted
from igni_client.wire import Event


class Reply(BaseModel):
    """The answer, and what happened on the way."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str = ""
    thinking: str = ""
    tools: list[ToolCompleted] = Field(default_factory=list)
    #: The main run's completion, with its token counts and duration.
    completed: RunCompleted | None = None

    @classmethod
    async def collect(
        cls, events: AsyncIterator[Event | ApprovalRequested], approver: Approver
    ) -> Reply:
        """Follow `events` to their end, answering each approval with `approver`."""
        reply = cls()
        text: list[str] = []
        thinking: list[str] = []
        async for event in events:
            match event:
                case ApprovalRequested():
                    await approver.answer(event)
                case ContentDelta():
                    (thinking if event.is_thinking else text).append(event.text)
                case ToolCompleted():
                    reply.tools.append(event)
                case RunCompleted() if not event.parent_run_id:
                    reply.completed = event
                case RunError():
                    raise RunFailed(event.error or "the run failed")
        reply.text = "".join(text)
        reply.thinking = "".join(thinking)
        return reply

    def __str__(self) -> str:
        return self.text

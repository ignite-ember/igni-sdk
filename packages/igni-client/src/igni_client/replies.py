"""What `Session.ask()` returns: a run's whole answer, gathered from its stream."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from pydantic import BaseModel, ConfigDict, Field

from igni_client.approvals import ApprovalRequested, Approver
from igni_client.errors import CredentialRefused, RunFailed
from igni_client.models import (
    ContentDelta,
    ErrorMessage,
    RunCompleted,
    RunError,
    RunStarted,
    ToolCompleted,
    VmCredentialState,
)
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
        cls,
        events: AsyncIterator[Event | ApprovalRequested],
        approver: Approver,
        credential: Callable[[], VmCredentialState | None] = lambda: None,
        where: str = "igni",
    ) -> Reply:
        """Follow `events` to their end, answering each approval with `approver`.

        A failed run raises `RunFailed` — or, when `credential` says igni's
        VM credential was refused, the `CredentialRefused` that says how to
        get it back (the run's own error is its cause). `where` names the igni
        and its gateway in that error.

        A prompt igni answers with an `error` and no run at all raises
        `RunFailed` too, in igni's words: igni refused it, or a hook or the
        group policy blocked it. igni's `error` carries no code, so those
        cannot be told apart, and none of them is an empty reply.
        """
        reply = cls()
        text: list[str] = []
        thinking: list[str] = []
        started = False
        unstarted: ErrorMessage | None = None
        async for event in events:
            match event:
                case RunStarted():
                    started = True
                case ErrorMessage() if unstarted is None:
                    unstarted = event
                case ApprovalRequested():
                    await approver.answer(event)
                case ContentDelta():
                    (thinking if event.is_thinking else text).append(event.text)
                case ToolCompleted():
                    reply.tools.append(event)
                case RunCompleted() if not event.parent_run_id:
                    reply.completed = event
                case RunError():
                    failed = RunFailed(event.error or "the run failed")
                    known = credential()
                    refused = (
                        None
                        if known is None
                        else CredentialRefused.of(known.state, known.message, where=where)
                    )
                    if refused is not None:
                        raise refused from failed
                    raise failed
        if unstarted is not None and not started:
            raise RunFailed(unstarted.text or "igni started no run for the prompt")
        reply.text = "".join(text)
        reply.thinking = "".join(thinking)
        return reply

    def __str__(self) -> str:
        return self.text

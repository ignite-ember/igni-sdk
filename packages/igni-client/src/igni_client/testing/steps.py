"""What a scripted run is made of: igni's messages, pauses for approval, and waits."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from igni_client.events import (
    ContentDelta,
    Event,
    Requirement,
    RunCompleted,
    RunStarted,
    ToolCompleted,
)


class Pause(BaseModel):
    """A step of a script: the run stops here until every call is answered."""

    requirements: list[Requirement]


class Delay(BaseModel):
    """A step of a script: wait this long before the next step."""

    seconds: float


Step = Event | Pause | Delay
#: What a prompt runs: the steps of the run, for the prompt's text.
Script = Callable[[str], list[Step]]


class Steps:
    """The runs a script is usually made of."""

    #: The run id every scripted run reports.
    RUN_ID = "r-1"

    @staticmethod
    def answer(text: str, *, model: str = "igni-1", agent: str = "igni") -> list[Step]:
        """The steps of a run that answers `text` and completes."""
        return [
            RunStarted(run_id=Steps.RUN_ID, agent_name=agent, model=model),
            ContentDelta(text=text),
            RunCompleted(run_id=Steps.RUN_ID, input_tokens=10, output_tokens=len(text.split())),
        ]

    @staticmethod
    def echo(text: str) -> list[Step]:
        """The run the fake plays when no script is set: it answers `echo: <text>`."""
        return Steps.answer(f"echo: {text}")

    @staticmethod
    def approval(tool_name: str, *, requirement_id: str = "", **tool_args: Any) -> Pause:
        """A step that pauses the run until a call to `tool_name` is answered."""
        return Pause(
            requirements=[
                Requirement(
                    requirement_id=requirement_id or f"req-{tool_name}",
                    tool_name=tool_name,
                    friendly_name=tool_name.replace("_", " "),
                    tool_args=tool_args,
                )
            ]
        )

    @staticmethod
    def rejected() -> list[Step]:
        """How a run resumes when its call was refused: the call never ran, and it says so."""
        return [
            ToolCompleted(run_id=Steps.RUN_ID, summary="rejected", is_rejected=True),
            *Steps.answer("I did not run it."),
        ]


__all__ = ["Delay", "Pause", "Script", "Step", "Steps"]

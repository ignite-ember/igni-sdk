"""What running a command tells the caller: who it ran as, how the VM woke, its output and its end."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Me(BaseModel):
    """Who the gateway says this client is."""

    model_config = ConfigDict(extra="allow")

    #: `person:<id>`, `app:<id>` or `space:<id>`.
    producer: str
    org: str = ""
    group: str | None = None
    #: When the token this was asked with expires, in Unix seconds.
    expires_at: int = 0

    @property
    def kind(self) -> str:
        return self.producer.partition(":")[0]

    @property
    def id(self) -> str:
        return self.producer.partition(":")[2]


class CommandRecord(BaseModel):
    """igni server's record of a command: its id, state and who asked."""

    model_config = ConfigDict(extra="allow")

    command_id: str = ""
    command: str = ""
    state: str = ""


class Wake(BaseModel):
    """How the VM was woken for a command."""

    model_config = ConfigDict(extra="allow")

    how: str = ""
    node: str = ""
    ms: float | None = None


class CommandOutput(BaseModel):
    """A piece of a command's output, as it was written."""

    stream: Literal["stdout", "stderr"]
    data: bytes

    @property
    def text(self) -> str:
        return self.data.decode(errors="replace")


class CommandFinished(BaseModel):
    """How a command ended."""

    model_config = ConfigDict(extra="allow")

    exit_code: int | None = None
    signal: int | None = None
    timed_out: bool = False
    killed: bool = False
    duration_ms: int | None = None
    #: Why it did not run or did not finish — a VM that could not be woken
    #: (the command then runs at the VM's next wake), a cancellation, a timeout.
    error: str | None = None
    #: `False` when the output arrived in one piece at the end instead of as it was written.
    streamed: bool = True

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.error


__all__ = ["CommandFinished", "CommandOutput", "CommandRecord", "Me", "Wake"]

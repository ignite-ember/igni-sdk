"""What running a command tells the caller: who it ran as, how the VM woke, its output and its end."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    ValidatorFunctionWrapHandler,
    field_validator,
)

#: The VM's state as the gateway's `/v1/me` reports it.
VM_STATES = ("none", "asleep", "waking", "running")


class VmState(BaseModel):
    """The producer's VM as the gateway sees it right now. Reading it never wakes the VM."""

    model_config = ConfigDict(extra="allow")

    #: `none` (never provisioned), `asleep`, `waking` or `running`; kept as
    #: sent, so a newer gateway's word arrives as it is (`VM_STATES` are the known ones).
    state: str = "none"
    #: Whether the person has signed in to igni in the VM: the gateway's flag.
    #: The VM credential's own state is igni's `vm_credential` push (`IgniClient.vm_credential`).
    signed_in: bool = False


class Me(BaseModel):
    """Who the gateway says this client is, and the state of its VM."""

    model_config = ConfigDict(extra="allow")

    #: `person:<id>`, `app:<id>` or `space:<id>`.
    producer: str
    org: str = ""
    group: str | None = None
    #: When the token this was asked with expires, in Unix seconds.
    expires_at: int = 0
    #: The VM's state right now; `None` from a gateway older than the field.
    vm: VmState | None = None

    @field_validator("vm", mode="wrap")
    @classmethod
    def _vm(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        """A `vm` that is not the gateway's shape is no state known, not a failed `me()`."""
        try:
            return handler(value)
        except ValidationError:
            return None

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


__all__ = [
    "VM_STATES",
    "CommandFinished",
    "CommandOutput",
    "CommandRecord",
    "Me",
    "VmState",
    "Wake",
]

"""The gateway's `/v1/commands` contract: the request, each NDJSON line of the answer, a refusal.

The answer's lines carry no `type` field; which one a line is follows from
the key it leads with, and `StreamLine` decides that once, here. A line
this version does not know arrives as `UnknownLine` and is passed over.
"""

from __future__ import annotations

import base64
from typing import Annotated, Any, Literal

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    JsonValue,
    Tag,
    TypeAdapter,
    ValidationError,
    ValidatorFunctionWrapHandler,
    field_validator,
)

from igni_client.commands.models import CommandFinished, CommandOutput, CommandRecord, Wake
from igni_client.errors import AuthError, IgniClientError, NotAllowed, Unavailable

PRODUCER_KINDS = ("person", "app", "space")
MAX_COMMAND_BYTES = 16 * 1024


class ProducerRef(BaseModel):
    """The producer whose VM a command runs in."""

    kind: Literal["person", "app", "space"]
    id: str

    @classmethod
    def parse(cls, producer: str) -> ProducerRef:
        """`kind:id` as a reference; `ValueError` when it is not one."""
        kind, _, producer_id = producer.partition(":")
        if kind not in PRODUCER_KINDS or not producer_id:
            raise ValueError("a producer is 'person:<id>', 'app:<id>' or 'space:<id>'")
        return cls.model_validate({"kind": kind, "id": producer_id})


class CommandRequest(BaseModel):
    """The body of `POST /v1/commands`."""

    producer: ProducerRef
    command: str
    #: Sent as given: a whole or fractional number of seconds.
    timeout_s: int | float

    @staticmethod
    def check(command: str, timeout_s: int) -> None:
        """`ValueError` when `command` or `timeout_s` is outside the gateway's limits."""
        if not command or len(command.encode()) > MAX_COMMAND_BYTES:
            raise ValueError("a command is 1 byte to 16 KiB")
        if not 1 <= timeout_s <= 3600:
            raise ValueError("timeout_s is 1 to 3600")


class CommandAccepted(BaseModel):
    """igni server accepted the command and recorded it."""

    command: CommandRecord

    @field_validator("command", mode="wrap")
    @classmethod
    def _as_given(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        return _as_given(value, handler, CommandRecord)


class VmWoken(BaseModel):
    """The VM was woken for the command."""

    woken: Wake

    @field_validator("woken", mode="wrap")
    @classmethod
    def _as_given(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        return _as_given(value, handler, Wake)


def _as_given(value: Any, handler: ValidatorFunctionWrapHandler, model: type[BaseModel]) -> Any:
    """`value` checked as `model`; one that does not fit is kept as the gateway sent it."""
    try:
        return handler(value)
    except ValidationError:
        if not isinstance(value, dict):
            raise
        return model.model_construct(**value)


class OutputLine(BaseModel):
    """A piece of stdout or stderr, base64-encoded.

    `data_b64` is kept as sent and decoded by `output()`: a missing or null
    one is no bytes, and one that is not base64 raises `binascii.Error` there.
    """

    stream: Literal["stdout", "stderr"]
    data_b64: JsonValue = ""

    @classmethod
    def of(cls, output: CommandOutput) -> OutputLine:
        """The line that carries `output`."""
        return cls(stream=output.stream, data_b64=base64.b64encode(output.data).decode())

    def output(self) -> CommandOutput:
        data = base64.b64decode(str(self.data_b64 or ""))
        return CommandOutput(stream=self.stream, data=data)


class CommandDone(CommandFinished):
    """The command ended; the rest of the line says how. Any true `done` ends it."""

    done: JsonValue

    @staticmethod
    def ending(line: dict[str, Any]) -> CommandFinished:
        """How a done line says the command ended; a field that does not fit raises `ValidationError`."""
        return CommandFinished.model_validate({k: v for k, v in line.items() if k != "done"})

    def finished(self) -> CommandFinished:
        return self.ending(self.model_dump(exclude_unset=True))


class UnknownLine(BaseModel):
    """A line this version does not know. Everything it carried is kept."""

    model_config = ConfigDict(extra="allow")


def line_kind(value: Any) -> str:
    if not isinstance(value, dict):
        return "unknown"
    if isinstance(value.get("command"), dict):
        return "command"
    if isinstance(value.get("woken"), dict):
        return "woken"
    if value.get("done"):
        return "done"
    if value.get("stream") in ("stdout", "stderr"):
        return "stream"
    return "unknown"


StreamLine = Annotated[
    Annotated[CommandAccepted, Tag("command")]
    | Annotated[VmWoken, Tag("woken")]
    | Annotated[CommandDone, Tag("done")]
    | Annotated[OutputLine, Tag("stream")]
    | Annotated[UnknownLine, Tag("unknown")],
    Discriminator(line_kind),
]

STREAM_LINE: TypeAdapter[StreamLine] = TypeAdapter(StreamLine)


class GatewayErrorBody(BaseModel):
    """What the gateway says when it refuses: FastAPI's `detail` or OAuth's `error`."""

    model_config = ConfigDict(extra="allow")

    detail: JsonValue = None
    error_description: JsonValue = None
    error: JsonValue = None

    def reason(self) -> str:
        return str(self.detail or self.error_description or self.error or "")


class GatewayRefusal(BaseModel):
    """A non-200 answer from the gateway, and the error it means for the caller."""

    status_code: int
    detail: str

    @classmethod
    def of(cls, response: httpx.Response) -> GatewayRefusal:
        """The refusal in a (fully read) response."""
        text = response.text.strip()
        try:
            body = GatewayErrorBody.model_validate_json(response.text)
        except ValidationError:  # not a JSON object: the text itself is the reason
            return cls(status_code=response.status_code, detail=text)
        return cls(status_code=response.status_code, detail=body.reason() or text)

    def error(self) -> IgniClientError:
        if self.status_code == 401:
            return AuthError(f"the gateway refused the credential: {self.detail}")
        if self.status_code in (400, 403, 404, 422):
            return NotAllowed(f"the gateway refused: {self.detail}")
        return Unavailable(f"the gateway answered {self.status_code}: {self.detail}")


__all__ = [
    "STREAM_LINE",
    "CommandAccepted",
    "CommandDone",
    "CommandRequest",
    "GatewayErrorBody",
    "GatewayRefusal",
    "OutputLine",
    "ProducerRef",
    "StreamLine",
    "UnknownLine",
    "VmWoken",
]

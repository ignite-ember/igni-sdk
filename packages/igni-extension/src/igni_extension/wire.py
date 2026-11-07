"""The messages on the socket to the igni host, typed.

They mirror igni's `igni_core.extensions.host.wire`, which igni's
`docs/HOST_MODEL_PROTOCOL.md` describes. An extension author never meets
them: `ext.host.chat.post(...)` becomes a `Request`, and what the host
sends back is read as one of `HostMessage`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from igni_extension.errors import HostError


class Op(StrEnum):
    GET = "get"
    SET = "set"
    CALL = "call"
    SUBSCRIBE = "subscribe"
    #: The process's answer to a `hook` message.
    ANSWER = "answer"


class Outcome(StrEnum):
    ALLOW = "allow"
    REJECT = "reject"
    MODIFY = "modify"
    #: The handler could not decide: it raised, or what it was handed was not the event.
    FAILED = "failed"


class HookAnswer(BaseModel):
    """The `params` of an `answer` request: what the extension decided about one hook event."""

    model_config = ConfigDict(extra="forbid")

    #: The `id` of the `hook` message it answers.
    hook: str
    outcome: Outcome
    #: Why, for a reject; what went wrong, for `failed`.
    reason: str = ""
    #: The changed value, for a modify.
    value: Any = None


# ── The extension to the host ─────────────────────────────────────────


class Request(BaseModel):
    """One request on the socket. The connection numbers it as it sends it."""

    model_config = ConfigDict(extra="forbid")

    #: Members whose answer is the person's, so no timeout applies to them.
    WAITS_ON_THE_PERSON: ClassVar[frozenset[str]] = frozenset({"ui.show_dialog"})

    #: Echoed on the reply; `None` until the connection sends it.
    id: int | None = None
    op: Op
    #: `chat.processing` for get and set, `chat.post` for call; empty otherwise.
    path: str = ""
    #: A window other than the active one (`host.windows.ui(id)`).
    window: str | None = None
    #: A session other than the one on screen (`host.sessions.chat(id)`).
    session: str | None = None
    #: A method's parameters, by name.
    params: dict[str, Any] = Field(default_factory=dict)
    #: The value of a `set`.
    value: Any = None
    #: Signal wire names, for a subscribe.
    signals: list[str] = Field(default_factory=list)

    @classmethod
    def subscribe(cls, wires: list[str]) -> Request:
        return cls(op=Op.SUBSCRIBE, signals=wires)

    @classmethod
    def answer(cls, answer: HookAnswer) -> Request:
        return cls(op=Op.ANSWER, params=answer.model_dump(mode="json", exclude_defaults=True))

    @property
    def waits_on_the_person(self) -> bool:
        """A dialog waits on the person, for as long as they take."""
        return self.path in self.WAITS_ON_THE_PERSON

    def numbered(self, request_id: int) -> Request:
        return self.model_copy(update={"id": request_id})

    def frame(self) -> str:
        """The JSON sent: what the host would assume anyway is left out."""
        return self.model_dump_json(exclude_defaults=True)


# ── The host to the extension ─────────────────────────────────────────


class Hello(BaseModel):
    """First on the socket: what this extension holds, and the model's version."""

    op: Literal["hello"]
    schema_version: str = ""
    granted: list[str] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str = "failed"
    message: str = "refused"


class Reply(BaseModel):
    """The answer to one request."""

    op: Literal["reply"]
    id: int | str | None = None
    ok: bool = False
    result: Any = None
    error: ErrorBody | None = None

    def result_or_raise(self) -> Any:
        """The result, or the host's refusal as a `HostError`."""
        if self.ok:
            return self.result
        error = self.error or ErrorBody()
        raise HostError(error.code or "failed", error.message or "refused")


class SignalMessage(BaseModel):
    """A signal fired."""

    op: Literal["signal"]
    #: The signal's wire name (`chat.run_completed`, `session.switched`).
    signal: str
    value: Any = None


class HookMessage(BaseModel):
    """One of igni's hook events. With an `id` it decides something, and igni waits on the answer."""

    op: Literal["hook"]
    id: str | None = None
    event: str
    value: Any = None
    #: Whom the event is for, as a tool call's `_meta["igni/principal"]`.
    principal: dict[str, Any] | None = None

    @property
    def decides(self) -> bool:
        return self.id is not None


class SubscribeOutcome(BaseModel):
    """The result of a subscribe: which signals will arrive, and which never will."""

    subscribed: list[str] = Field(default_factory=list)
    #: Signals whose object the manifest's `permissions.host` lacks.
    not_granted: list[str] = Field(default_factory=list)
    #: Signals this igni does not have.
    unknown: list[str] = Field(default_factory=list)


type HostMessage = Annotated[Hello | Reply | SignalMessage | HookMessage, Field(discriminator="op")]

#: Reads one frame the host sent.
HOST_MESSAGE: TypeAdapter[HostMessage] = TypeAdapter(HostMessage)


__all__ = [
    "HOST_MESSAGE",
    "ErrorBody",
    "Hello",
    "HookAnswer",
    "HookMessage",
    "HostMessage",
    "Op",
    "Outcome",
    "Reply",
    "Request",
    "SignalMessage",
    "SubscribeOutcome",
]

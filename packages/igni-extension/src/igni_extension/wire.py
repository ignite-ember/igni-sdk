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

from igni_extension.caller import Caller
from igni_extension.errors import HostError


class Op(StrEnum):
    """What a request on the host's socket does."""

    GET = "get"
    """Read a property."""
    SET = "set"
    """Write a property."""
    CALL = "call"
    """Call a method."""
    SUBSCRIBE = "subscribe"
    """Ask for signals to be delivered."""
    ANSWER = "answer"
    """The process's answer to a `hook` message."""


class Outcome(StrEnum):
    """What an extension decided about a hook event."""

    ALLOW = "allow"
    """Let it happen as it is."""
    REJECT = "reject"
    """Stop it, with a reason."""
    MODIFY = "modify"
    """Let it happen, changed."""
    FAILED = "failed"
    """The handler could not decide: it raised, or what it was handed was not the event."""


class HookAnswer(BaseModel):
    """The `params` of an `answer` request: what the extension decided about one hook event."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    hook: str
    """The `id` of the `hook` message it answers."""
    outcome: Outcome
    """What was decided."""
    reason: str = ""
    """Why, for a reject; what went wrong, for `failed`."""
    value: Any = None
    """The changed value, for a modify."""


# ── The extension to the host ─────────────────────────────────────────


class Request(BaseModel):
    """One request on the socket. The connection numbers it as it sends it."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    WAITS_ON_THE_PERSON: ClassVar[frozenset[str]] = frozenset({"ui.show_dialog"})
    """Members whose answer is the person's, so no timeout applies to them."""

    id: int | None = None
    """Echoed on the reply; `None` until the connection sends it."""
    op: Op
    """What the request does."""
    path: str = ""
    """`chat.processing` for get and set, `chat.post` for call; empty otherwise."""
    window: str | None = None
    """A window other than the active one (`host.windows.ui(id)`)."""
    session: str | None = None
    """A session other than the one on screen (`host.sessions.chat(id)`)."""
    params: dict[str, Any] = Field(default_factory=dict)
    """A method's parameters, by name."""
    value: Any = None
    """The value of a `set`."""
    signals: list[str] = Field(default_factory=list)
    """Signal wire names, for a subscribe."""

    @classmethod
    def subscribe(cls, wires: list[str]) -> Request:
        """A request to deliver the signals `wires` names."""
        return cls(op=Op.SUBSCRIBE, signals=wires)

    @classmethod
    def answer(cls, answer: HookAnswer) -> Request:
        """A request carrying the answer to one hook event."""
        return cls(op=Op.ANSWER, params=answer.model_dump(mode="json", exclude_defaults=True))

    @property
    def waits_on_the_person(self) -> bool:
        """A dialog waits on the person, for as long as they take."""
        return self.path in self.WAITS_ON_THE_PERSON

    def numbered(self, request_id: int) -> Request:
        """This request with the id the connection sends it under."""
        return self.model_copy(update={"id": request_id})

    def frame(self) -> str:
        """The JSON sent: what the host would assume anyway is left out."""
        return self.model_dump_json(exclude_defaults=True)


# ── The host to the extension ─────────────────────────────────────────


class Hello(BaseModel):
    """First on the socket: what this extension holds, and the model's version."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    op: Literal["hello"]
    protocol: int = 1
    """The protocol's version."""
    schema_version: str = ""
    extension_id: str = ""
    """The extension this connection is for."""
    granted: list[str] = Field(default_factory=list)


class ErrorBody(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)
    code: str = "failed"
    message: str = "refused"


class Reply(BaseModel):
    """The answer to one request."""

    model_config = ConfigDict(use_attribute_docstrings=True)

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

    model_config = ConfigDict(use_attribute_docstrings=True)

    op: Literal["signal"]
    signal: str
    """The signal's wire name (`chat.run_completed`, `session.switched`)."""
    value: Any = None


class HookMessage(BaseModel):
    """One of igni's hook events. With an `id` it decides something, and igni waits on the answer."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    op: Literal["hook"]
    id: str | None = None
    event: str
    value: Any = None
    principal: dict[str, Any] | None = None
    """Whom the event is for, as a tool call's `_meta["igni/principal"]`."""

    @property
    def decides(self) -> bool:
        return self.id is not None

    @property
    def caller(self) -> Caller | None:
        """Whom the event is for; `None` when igni sent none, or a malformed one."""
        return Caller.of(self.principal)


class SubscribeOutcome(BaseModel):
    """The result of a subscribe: which signals will arrive, and which never will."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    subscribed: list[str] = Field(default_factory=list)
    not_granted: list[str] = Field(default_factory=list)
    """Signals whose object the manifest's `permissions.host` lacks."""
    unknown: list[str] = Field(default_factory=list)
    """Signals this igni does not have."""


type HostMessage = Annotated[Hello | Reply | SignalMessage | HookMessage, Field(discriminator="op")]

HOST_MESSAGE: TypeAdapter[HostMessage] = TypeAdapter(HostMessage)
"""Reads one frame the host sent."""


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

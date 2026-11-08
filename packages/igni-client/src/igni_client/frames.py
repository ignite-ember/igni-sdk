"""What this client sends: every message it puts on igni's socket, as a typed model.

Each class is one message igni reads from a client, field for field. A
frame is checked when it is built, so a message igni would refuse — or
one a client must never send — fails here, before the socket.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Methods a client never sends: they stop igni, or belong to Fleet's own control connection.
REFUSED_METHODS = frozenset({"shutdown", "vm_sign_in", "deliver_service_events"})


class Frame(BaseModel):
    """One message to igni."""

    model_config = ConfigDict(frozen=True)

    type: str

    def wire(self) -> str:
        """The frame as igni reads it; a field left unset is left out."""
        return self.model_dump_json(exclude_none=True)


class RpcRequest(Frame):
    """A call to one of igni's methods, answered by a message with the same `id`."""

    type: Literal["rpc_request"] = "rpc_request"
    id: str
    method: str
    args: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None

    @staticmethod
    def check_sendable(method: str) -> None:
        """A plain `ValueError` for a method a client never sends, as 0.1.0 raised it."""
        if method in REFUSED_METHODS:
            raise ValueError(f"{method} is not a client's to send")

    @field_validator("method")
    @classmethod
    def _a_client_s_to_send(cls, method: str) -> str:
        cls.check_sendable(method)
        return method


class UserMessage(Frame):
    """A prompt: starts a run in the session, streamed back under `id`."""

    type: Literal["user_message"] = "user_message"
    id: str
    session_id: str
    text: str
    file_contents: dict[str, str] = Field(default_factory=dict)
    client_id: str
    force: bool = False


class QueueMessage(Frame):
    """A prompt for after the run that is going."""

    type: Literal["queue_message"] = "queue_message"
    session_id: str
    text: str
    client_id: str


class Cancel(Frame):
    """Stop the session's run."""

    type: Literal["cancel"] = "cancel"
    session_id: str


#: How far an approval answer reaches: this call (`once`), every identical
#: call (`always`), similar calls (`similar`), or — for a refusal — `deny`
#: to refuse such calls from now on.
Scope = Literal["once", "always", "similar", "deny"]


class HitlDecision(BaseModel):
    """The answer to one tool call waiting for approval."""

    model_config = ConfigDict(frozen=True)

    type: Literal["hitl_decision"] = "hitl_decision"
    requirement_id: str
    action: Literal["confirm", "reject"]
    choice: Scope
    set_permission_mode: str = ""


class HitlResponseBatch(Frame):
    """The answers to every tool call of a pause, together; the resumed run streams under `id`."""

    type: Literal["hitl_response_batch"] = "hitl_response_batch"
    id: str
    session_id: str
    decisions: list[HitlDecision]

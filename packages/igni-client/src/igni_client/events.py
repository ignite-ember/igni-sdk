"""What igni sends: every message on its socket, as a typed model.

Each class mirrors one message of igni's wire protocol, field for field
(`igni_core.protocol.schemas` in igni-core; a test there holds the two
together). The `type` field picks the class.

They are permissive on purpose. A field a newer igni adds is kept rather
than refused (`model_config = extra="allow"`), and a message type this
version does not know arrives as `Unknown` with everything it carried.
An older client keeps working against a newer igni; it just sees less.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Event(BaseModel):
    """One message from igni.

    `id` is the request it answers (empty for a broadcast), `session_id`
    the session it is about (empty for one about none), `event_seq` its
    place in its stream.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    id: str = ""
    session_id: str = ""
    event_seq: int = 0


class RunEvent(Event):
    """A message about one run. `parent_run_id` is set for a sub-agent's."""

    run_id: str = ""
    parent_run_id: str = ""


class Unknown(Event):
    """A message type this version of igni-client does not know. Every field is kept."""


# ── A run ────────────────────────────────────────────────────────────


class ContentDelta(Event):
    """A piece of the answer as the model writes it; `is_thinking` for its reasoning."""

    type: Literal["content_delta"] = "content_delta"
    text: str = ""
    is_thinking: bool = False


class RunStarted(RunEvent):
    """An agent's run began: the main agent, or a sub-agent it handed work to."""

    type: Literal["run_started"] = "run_started"
    agent_name: str = ""
    model: str = ""


class ReasoningStarted(RunEvent):
    """The model began reasoning before it answers."""

    type: Literal["reasoning_started"] = "reasoning_started"


class ToolStarted(RunEvent):
    """The agent called a tool."""

    type: Literal["tool_started"] = "tool_started"
    tool_name: str = ""
    friendly_name: str = ""
    args_summary: str = ""


class ToolCompleted(RunEvent):
    """A tool returned. `is_error` when it failed; `is_rejected` when it never ran because it was refused."""

    type: Literal["tool_completed"] = "tool_completed"
    summary: str = ""
    full_result: str = ""
    has_markup: bool = False
    diff_rows: list[tuple[str, str]] | None = None
    is_error: bool = False
    is_rejected: bool = False


class ToolError(RunEvent):
    """A tool call failed."""

    type: Literal["tool_error"] = "tool_error"
    error: str = ""


class ModelCompleted(RunEvent):
    """One model call finished, with its token counts."""

    type: Literal["model_completed"] = "model_completed"
    input_tokens: int = 0
    output_tokens: int = 0


class StreamingDone(RunEvent):
    """The answer is complete; igni is still saving the run behind it."""

    type: Literal["streaming_done"] = "streaming_done"


class RunCompleted(RunEvent):
    """A run finished. `reasoning_tokens` is the part of `output_tokens` spent reasoning."""

    type: Literal["run_completed"] = "run_completed"
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    duration: float = 0.0


class RunError(Event):
    """A run failed."""

    type: Literal["run_error"] = "run_error"
    error: str = ""


class Requirement(Event):
    """One tool call waiting for a person's approval."""

    type: Literal["hitl_request"] = "hitl_request"
    requirement_id: str = ""
    tool_name: str = ""
    friendly_name: str = ""
    tool_args: dict[str, Any] = Field(default_factory=dict)
    details: str = ""
    #: igni is still writing `details` (the Bypass check describes the
    #: call); a `RequirementDetails` follows.
    details_pending: bool = False
    #: The agents that led to this call, parent to leaf. Empty for the main agent.
    agent_path: list[str] = Field(default_factory=list)


class RunPaused(RunEvent):
    """A run stopped to ask for approval of one or more tool calls."""

    type: Literal["run_paused"] = "run_paused"
    requirements: list[Requirement] = Field(default_factory=list)


class RequirementResolved(Event):
    """An approval was answered — by this client or by anyone else attached."""

    type: Literal["requirement_resolved"] = "requirement_resolved"
    requirement_id: str = ""


class RequirementDetails(Event):
    """The description of a waiting approval, sent after the request itself."""

    type: Literal["requirement_details"] = "requirement_details"
    requirement_id: str = ""
    details: str = ""


class StreamEnd(Event):
    """The end of the stream a request opened."""

    type: Literal["stream_end"] = "stream_end"


# ── Orchestration ────────────────────────────────────────────────────


class TaskCreated(Event):
    """A task in a team's plan was created."""

    type: Literal["task_created"] = "task_created"
    task_id: str = ""
    title: str = ""
    assignee: str = ""
    status: str = "pending"


class TaskUpdated(Event):
    """A task in a team's plan changed."""

    type: Literal["task_updated"] = "task_updated"
    task_id: str = ""
    status: str = ""
    assignee: str = ""


class TaskIteration(Event):
    """A team's loop went round again."""

    type: Literal["task_iteration"] = "task_iteration"
    iteration: int = 0
    max_iterations: int = 0


class TaskSnapshot(BaseModel):
    """One task, as `TaskStateUpdated` lists it."""

    model_config = ConfigDict(extra="allow")

    task_id: str = ""
    title: str = ""
    status: str = ""
    assignee: str = ""


class TaskStateUpdated(Event):
    """Every task of a team's plan, as it stands."""

    type: Literal["task_state_updated"] = "task_state_updated"
    tasks: list[TaskSnapshot] = Field(default_factory=list)


# ── Sessions and state ───────────────────────────────────────────────


class SessionListEntry(BaseModel):
    """One session, as `Sessions.list()` returns it. Times are Unix seconds."""

    model_config = ConfigDict(extra="allow")

    session_id: str = ""
    name: str = ""
    created_at: int = 0
    updated_at: int = 0
    run_count: int = 0
    summary: str = ""
    agent_name: str = ""


class SessionListResult(Event):
    """The sessions igni keeps."""

    type: Literal["session_list_result"] = "session_list_result"
    sessions: list[SessionListEntry] = Field(default_factory=list)


class SessionCleared(Event):
    """A session was compacted or cleared, and continues as `new_session_id`."""

    type: Literal["session_cleared"] = "session_cleared"
    new_session_id: str = ""
    summary: str = ""


class StatusUpdate(Event):
    """igni's state: the model, the context used, the permission mode, the account."""

    type: Literal["status_update"] = "status_update"
    input_tokens: int = 0
    output_tokens: int = 0
    context_tokens: int = 0
    max_context: int = 0
    model: str = ""
    model_configured: bool = True
    cloud_connected: bool = False
    cloud_org: str = ""
    cloud_email: str = ""
    cloud_name: str = ""
    permission_mode: str = "default"
    theme: dict[str, Any] | None = None


class CommandResult(Event):
    """What a slash command answered."""

    type: Literal["command_result"] = "command_result"
    kind: str = "info"
    content: str = ""
    action: str = "none"
    display_content: str = ""


class InfoMessage(Event):
    """A notice from igni (`info` on the wire), such as "Run cancelled by user."."""

    type: Literal["info"] = "info"
    text: str = ""


class ErrorMessage(Event):
    """An error igni reported outside a run (`error` on the wire)."""

    type: Literal["error"] = "error"
    text: str = ""


class SchedulerEvent(Event):
    """A scheduled task started, finished or failed."""

    type: Literal["scheduler_event"] = "scheduler_event"
    task_id: str = ""
    description: str = ""
    event_type: str = ""
    result: str = ""


# ── Several clients on one igni ──────────────────────────────────────


class Welcome(Event):
    """The first message on a connection. igni sends another after Fleet moves it."""

    type: Literal["welcome"] = "welcome"
    client_id: str = ""


class Typing(Event):
    """What somebody attached is typing, in full."""

    type: Literal["typing"] = "typing"
    text: str = ""
    client_id: str = ""


class UserMessageReceived(Event):
    """A message was accepted into a session — from any client, an extension or a service."""

    type: Literal["user_message_received"] = "user_message_received"
    text: str = ""
    client_id: str = ""
    queued: bool = False
    extension_id: str = ""
    service_client_id: str = ""


class PushNotification(Event):
    """Something changed in igni: a session was named, a plan submitted, a process printed a line."""

    type: Literal["push_notification"] = "push_notification"
    channel: str = ""
    payload: Any = None


class RpcResponse(Event):
    """The answer to a call: `result`, or `error`."""

    type: Literal["rpc_response"] = "rpc_response"
    result: Any = None
    error: str | None = None


EVENT_TYPES: dict[str, type[Event]] = {
    cls.model_fields["type"].default: cls
    for cls in (
        ContentDelta,
        RunStarted,
        ReasoningStarted,
        ToolStarted,
        ToolCompleted,
        ToolError,
        ModelCompleted,
        StreamingDone,
        RunCompleted,
        RunError,
        Requirement,
        RunPaused,
        RequirementResolved,
        RequirementDetails,
        StreamEnd,
        TaskCreated,
        TaskUpdated,
        TaskIteration,
        TaskStateUpdated,
        SessionListResult,
        SessionCleared,
        StatusUpdate,
        CommandResult,
        InfoMessage,
        ErrorMessage,
        SchedulerEvent,
        Welcome,
        Typing,
        UserMessageReceived,
        PushNotification,
        RpcResponse,
    )
}


def parse_event(raw: dict[str, Any]) -> Event:
    """The typed message for one decoded frame. Never raises: what does not fit is `Unknown`."""
    cls = EVENT_TYPES.get(str(raw.get("type", "")))
    if cls is not None:
        try:
            return cls.model_validate(raw)
        except ValidationError:
            pass
    fields = {**raw, "type": str(raw.get("type", ""))}
    try:
        return Unknown.model_validate(fields)
    except ValidationError:
        return Unknown(type=fields["type"])

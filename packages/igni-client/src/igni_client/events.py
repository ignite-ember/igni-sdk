"""What igni sends: every message on its socket, as a typed model.

Each class is generated from igni-core's RPC contract (`igni_client.models`),
field for field; the `type` field picks the class, and a push notification's
`channel` picks its typed class when the contract types that channel.

A push on a channel the contract types is that channel's class (a
`PushNotification` subclass whose `payload` is typed); one on a channel
newer than this igni-client, or whose payload it cannot read, is a plain
`PushNotification` with its payload as JSON.

They are permissive on purpose. A field a newer igni adds is kept rather
than refused (`extra="allow"`). A message whose `type` this version does not
know — one newer than this igni-client — arrives as `Unknown`, with
everything it carried; so does, rarely, a known message whose fields this
version cannot read, and that is logged as a warning. An older client keeps
working against a newer igni; it just sees less.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from igni_client.models import (
    EVENT_TYPES,
    PUSH_TYPES,
    CommandResult,
    ContentDelta,
    ErrorMessage,
    InfoMessage,
    ModelCompleted,
    PushNotification,
    ReasoningStarted,
    Requirement,
    RequirementDetails,
    RequirementResolved,
    RpcResponse,
    RunCompleted,
    RunError,
    RunPaused,
    RunStarted,
    SchedulerEvent,
    SessionCleared,
    SessionListResult,
    StatusUpdate,
    StreamEnd,
    StreamingDone,
    TaskCreated,
    TaskIteration,
    TaskStateUpdated,
    TaskUpdated,
    ToolCompleted,
    ToolError,
    ToolStarted,
    Typing,
    UserMessageReceived,
    Welcome,
)
from igni_client.wire import Event, RunEvent

logger = logging.getLogger(__name__)


class Unknown(Event):
    """A message this version of igni-client does not know. Every field is kept.

    igni sent a `type` newer than this igni-client — upgrade to read it — or,
    rarely, a known message whose fields this version cannot read (logged).
    """


def parse_event(raw: dict[str, Any]) -> Event:
    """The typed message for one decoded frame. Never raises: what does not fit is `Unknown`."""
    kind = str(raw.get("type", ""))
    cls: type[Event] | None = EVENT_TYPES.get(kind)
    if cls is PushNotification:
        typed = PUSH_TYPES.get(str(raw.get("channel", "")))
        if typed is not None:
            try:
                return typed.model_validate(raw)
            except ValidationError as exc:
                logger.warning(
                    "igni-client: igni pushed a %s this version cannot read: %s",
                    raw.get("channel"),
                    exc,
                )
    if cls is not None:
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            logger.warning("igni-client: igni sent a %s this version cannot read: %s", kind, exc)
    fields = {**raw, "type": kind}
    try:
        return Unknown.model_validate(fields)
    except ValidationError:
        return Unknown(type=kind)


__all__ = [
    "EVENT_TYPES",
    "PUSH_TYPES",
    "CommandResult",
    "ContentDelta",
    "ErrorMessage",
    "Event",
    "InfoMessage",
    "ModelCompleted",
    "PushNotification",
    "ReasoningStarted",
    "Requirement",
    "RequirementDetails",
    "RequirementResolved",
    "RpcResponse",
    "RunCompleted",
    "RunError",
    "RunEvent",
    "RunPaused",
    "RunStarted",
    "SchedulerEvent",
    "SessionCleared",
    "SessionListResult",
    "StatusUpdate",
    "StreamEnd",
    "StreamingDone",
    "TaskCreated",
    "TaskIteration",
    "TaskStateUpdated",
    "TaskUpdated",
    "ToolCompleted",
    "ToolError",
    "ToolStarted",
    "Typing",
    "Unknown",
    "UserMessageReceived",
    "Welcome",
    "parse_event",
]

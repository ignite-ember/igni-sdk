"""What this client sends: every message it puts on igni's socket, as a typed model.

Each class is generated from igni-core's RPC contract (`igni_client.models`),
field for field, and checked when it is built, so a message igni would
refuse fails here, before the socket. `Frame.wire()` is what goes out: the
`type` and every field given a value.
"""

from __future__ import annotations

from igni_client.models import (
    Cancel,
    CancelLogin,
    Command,
    HitlDecision,
    HitlResponse,
    HitlResponseBatch,
    McpToggle,
    ModelSwitch,
    QueueMessage,
    RpcRequest,
    SessionList,
    SessionSwitch,
    Shutdown,
    Typing,
    UserMessage,
)
from igni_client.wire import Frame

__all__ = [
    "Cancel",
    "CancelLogin",
    "Command",
    "Frame",
    "HitlDecision",
    "HitlResponse",
    "HitlResponseBatch",
    "McpToggle",
    "ModelSwitch",
    "QueueMessage",
    "RpcRequest",
    "SessionList",
    "SessionSwitch",
    "Shutdown",
    "Typing",
    "UserMessage",
]

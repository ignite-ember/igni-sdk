"""What a client sends the fake, read back into the typed frames the client built."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Discriminator, Tag, TypeAdapter

from igni_client.frames import Cancel, HitlResponseBatch, QueueMessage, RpcRequest, UserMessage


class UnknownFrame(BaseModel):
    """A message the fake does not play. Everything it carried is kept."""

    model_config = ConfigDict(extra="allow", frozen=True)

    type: str = ""


_KINDS = frozenset(
    {"rpc_request", "user_message", "queue_message", "cancel", "hitl_response_batch"}
)


def _frame_kind(value: Any) -> str:
    kind = value.get("type") if isinstance(value, dict) else getattr(value, "type", None)
    return kind if isinstance(kind, str) and kind in _KINDS else "unknown"


ClientFrame = Annotated[
    Annotated[RpcRequest, Tag("rpc_request")]
    | Annotated[UserMessage, Tag("user_message")]
    | Annotated[QueueMessage, Tag("queue_message")]
    | Annotated[Cancel, Tag("cancel")]
    | Annotated[HitlResponseBatch, Tag("hitl_response_batch")]
    | Annotated[UnknownFrame, Tag("unknown")],
    Discriminator(_frame_kind),
]

CLIENT_FRAME: TypeAdapter[ClientFrame] = TypeAdapter(ClientFrame)


class Received(BaseModel):
    """One message a client sent the fake."""

    client_id: str
    frame: ClientFrame


__all__ = ["CLIENT_FRAME", "ClientFrame", "Received", "UnknownFrame"]

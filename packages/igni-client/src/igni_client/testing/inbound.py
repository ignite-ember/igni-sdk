"""What a client sends the fake, read back into the typed frames the client built."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from igni_client.models import FRAME_TYPES
from igni_client.wire import Event, Frame


class UnknownFrame(BaseModel):
    """A message the fake does not read. Everything it carried is kept."""

    model_config = ConfigDict(extra="allow", frozen=True)

    type: str = ""


#: One message a client sent: a typed frame (`igni_client.frames`), or `UnknownFrame`.
ClientFrame = Frame | Event | UnknownFrame


def read_frame(raw: str | bytes) -> ClientFrame:
    """The typed message a client sent, as igni reads it; `ValueError` for what is not one."""
    try:
        decoded: Any = json.loads(raw)
    except ValueError as exc:
        raise ValueError("not JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("not a JSON object")
    cls = FRAME_TYPES.get(str(decoded.get("type", "")))
    if cls is None:
        return UnknownFrame.model_validate(decoded)
    try:
        return cls.model_validate(decoded)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


class Received(BaseModel):
    """One message a client sent the fake."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client_id: str
    frame: ClientFrame


__all__ = ["ClientFrame", "Received", "UnknownFrame", "read_frame"]

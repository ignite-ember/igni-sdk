"""The bases every generated model in `igni_client.models` is built on.

* `Model` — something igni answers with. A field a newer igni adds is kept
  (`extra="allow"`), so an older client keeps working; it just sees less.
* `Args` — a method's arguments. A misspelt argument is refused here,
  before it is sent (`extra="forbid"`).
* `Event` — a message igni sends; `RunEvent` one about a run.
* `Frame` — a message a client sends; `Frame.wire()` is its bytes.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Something igni answers with."""

    model_config = ConfigDict(extra="allow", protected_namespaces=(), use_attribute_docstrings=True)


class Args(BaseModel):
    """A method's arguments, as igni reads them."""

    model_config = ConfigDict(
        extra="forbid", protected_namespaces=(), use_attribute_docstrings=True
    )


class Event(Model):
    """One message from igni.

    `id` is the request it answers (empty for a broadcast), `session_id`
    the session it is about (empty for one about none), `event_seq` its
    place in its stream.
    """

    type: str
    id: str = ""
    session_id: str = ""
    event_seq: int = 0


class RunEvent(Event):
    """A message about one run. `parent_run_id` is set for a sub-agent's."""

    run_id: str = ""
    parent_run_id: str = ""


class Frame(BaseModel):
    """One message to igni."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, protected_namespaces=(), use_attribute_docstrings=True
    )

    type: str
    id: str = ""
    session_id: str = ""
    event_seq: int = 0

    def wire(self) -> str:
        """The frame as igni reads it: its `type` and every field given a value."""
        return to_wire(self)


def to_wire(message: BaseModel) -> str:
    """`message` as JSON: its `type` and the fields it was given, by their wire names.

    A field left at its default is left out, so igni applies its own default
    — the contract's. A value JSON cannot hold raises.
    """
    fields = message.model_dump(mode="json", by_alias=True, exclude_unset=True)
    try:
        return json.dumps({"type": getattr(message, "type", ""), **fields}, allow_nan=False)
    except ValueError as error:
        raise ValueError(
            f"not valid JSON: a NaN or infinite number cannot be sent ({error})"
        ) from error


__all__ = ["Args", "Event", "Frame", "Model", "RunEvent", "to_wire"]

"""The table of a Pydantic model's or a dataclass's own fields.

A model's fields are what its caller builds it from, so the reference page
shows them as a table of their own: each field's name, type, default, and
the description the model gives it. A class with neither kind of field has
no table.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from pydantic import BaseModel

from tools.py_signature import annotation_text, stable_repr


class FieldRow(BaseModel):
    """One field's row: every cell already escaped for a Markdown table."""

    name: str
    type: str
    default: str
    description: str = ""

    def line(self, *, described: bool) -> str:
        """The row, with the description column only when the table has one."""
        cells = [f"`{self.name}`", f"`{self.type}`", self.default]
        if described:
            cells.append(self.description)
        return "| " + " | ".join(cells) + " |"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _model_rows(cls: type, model_fields: dict[str, Any]) -> list[FieldRow]:
    """A Pydantic model's own fields: those it annotates, not those it inherits."""
    own = getattr(cls, "__annotations__", {})
    rows: list[FieldRow] = []
    for name, info in model_fields.items():
        if name not in own:
            continue
        if info.is_required():
            default = "required"
        elif info.default_factory is not None:
            default = "factory"
        else:
            default = f"`{stable_repr(info.default)}`"
        rows.append(
            FieldRow(
                name=name,
                type=_cell(annotation_text(own.get(name, info.annotation))),
                default=default,
                description=_cell((info.description or "").replace("\n", " ")),
            )
        )
    return rows


def _dataclass_rows(cls: type) -> list[FieldRow]:
    """A dataclass's public fields, but not one kept out of both its constructor and repr."""
    rows: list[FieldRow] = []
    for f in dataclasses.fields(cls):
        if f.name.startswith("_") or (not f.init and f.repr is False):
            continue
        if f.default is not dataclasses.MISSING:
            default = f"`{stable_repr(f.default)}`"
        elif f.default_factory is not dataclasses.MISSING:
            default = "factory"
        else:
            default = "required"
        rows.append(FieldRow(name=f.name, type=_cell(annotation_text(f.type)), default=default))
    return rows


def field_rows(cls: type) -> list[FieldRow]:
    """The rows of ``cls``'s field table; none when it is neither a model nor a dataclass."""
    model_fields = getattr(cls, "model_fields", None)
    if isinstance(model_fields, dict):
        return _model_rows(cls, model_fields)
    if dataclasses.is_dataclass(cls):
        return _dataclass_rows(cls)
    return []


def field_table(rows: list[FieldRow]) -> list[str]:
    """The table of ``rows``, with no description column when no field says what it is."""
    if not rows:
        return []
    if any(row.description for row in rows):
        head = ["| Field | Type | Default | Description |", "|---|---|---|---|"]
        return [*head, *(row.line(described=True) for row in rows), ""]
    head = ["| Field | Type | Default |", "|---|---|---|"]
    return [*head, *(row.line(described=False) for row in rows), ""]


__all__ = ["FieldRow", "field_rows", "field_table"]

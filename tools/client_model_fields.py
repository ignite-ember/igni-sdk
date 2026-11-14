"""A contract model's fields as a table, and the line naming the models it is part of:
what the models page and the events page both show of a model."""

from __future__ import annotations

from typing import Any

from tools.client_doc_links import ClientSources
from tools.client_python import Imports, field_name
from tools.wire_prose import cell, rst


class ModelFields:
    """The fields table of one contract def, as igni-client's model types it."""

    def __init__(self, sources: ClientSources) -> None:
        self.sources = sources

    def table(self, def_name: str) -> list[str]:
        schema = self.sources.contract.defs[def_name]
        props: dict[str, Any] = schema.get("properties", {})
        if not props:
            return ["No fields.", ""]
        required = set(schema.get("required", []))
        described = any(s.get("description") or "const" in s for s in props.values())
        out = (
            ["| Field | Type | Default | Description |", "|---|---|---|---|"]
            if described
            else ["| Field | Type | Default |", "|---|---|---|"]
        )
        for prop, prop_schema in props.items():
            row = self._row(prop, prop_schema, required=prop in required)
            if described:
                const = f"always `{prop_schema['const']!r}`. " if "const" in prop_schema else ""
                row += f" {cell(const + rst(prop_schema.get('description', '')))} |"
            out.append(row)
        out.append("")
        return out

    def _row(self, prop: str, prop_schema: dict[str, Any], *, required: bool) -> str:
        python = field_name(prop)
        name = f"`{python}`" + (f" (wire `{prop}`)" if python != prop else "")
        annotation = self.sources.types.annotation(prop_schema, Imports())
        if "default" in prop_schema:
            default = f"`{prop_schema['default']!r}`"
        elif required:
            default = "required"
        else:
            kind = prop_schema.get("type")
            default = "`{}`" if kind == "object" else "`[]`" if kind == "array" else "`None`"
            # The model says `X | None` for a field that defaults to None.
            if default == "`None`" and annotation != "None" and not annotation.endswith("| None"):
                annotation += " | None"
        return f"| {name} | {self.sources.type_md(annotation, in_table=True)} | {default} |"

    def used_in(self, names: list[str]) -> str:
        """The line naming the models ``names`` are, linked."""
        unique = sorted(dict.fromkeys(self.sources.types.class_name(n) for n in names))
        return "**Part of** " + ", ".join(self.sources.type_md(n) for n in unique) + "."


__all__ = ["ModelFields"]

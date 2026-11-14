"""``igni_client.models``: every def a client sends or reads, as a Pydantic model."""

from __future__ import annotations

from typing import Any

from tools.client_plan import Plan, push_class
from tools.client_python import BANNER, Imports, docstring, field_name

#: Fields a run's events carry besides the envelope: the base ``RunEvent`` declares them.
_RUN_FIELDS = ("run_id", "parent_run_id")


class ModelsGenerator:
    """Every def a client sends or reads, as a Pydantic model or a type alias."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.contract = plan.contract
        self.types = plan.types
        self.imports = Imports()
        self.messages = plan.message_of_def()
        #: The bases in ``igni_client.wire`` the generated classes derive from.
        self.bases_used: set[str] = set()

    def generate(self) -> str:
        names = sorted(self.plan.defs_in | self.plan.defs_out)
        enums = [n for n in names if self.types.is_enum(n)]
        classes = [n for n in names if not self.types.is_enum(n)]
        body: list[str] = []
        for name in enums:
            body += self._enum(name)
        for name in classes:
            body += self._class(name)
        for channel in sorted(self.contract.push_channels):
            body += self._push(channel)
        for wire in self.plan.placements:
            # A method's result may be a union the models do not use: name it here.
            self.types.annotation(self.contract.methods[wire].result, Imports())
        unions: list[str] = []
        for alias in sorted(self.types.unions):
            unions += self._union(alias)
        tables = self._tables()
        head = self._head()
        return "\n".join([*head, *body, *unions, *tables]) + "\n"

    def _head(self) -> list[str]:
        out = [
            '"""Every type igni-client sends or reads, as igni-core\'s RPC contract defines it.',
            "",
            BANNER.format(version=self.contract.version),
            "",
            "Messages a client reads are `Event`s (a run's, `RunEvent`s); messages it",
            "sends are `Frame`s; arguments are `Args`; everything else is a `Model`.",
            'A model a client reads keeps a field a newer igni adds (`extra="allow"`).',
            '"""',
            "",
            "from __future__ import annotations",
            "",
        ]
        if self.imports.datetime:
            out.append("from datetime import datetime")
        typing = sorted(self.imports.typing)
        if typing:
            out.append(f"from typing import {', '.join(typing)}")
        out.append("")
        pydantic = sorted(self.imports.pydantic)
        if pydantic:
            out.append(f"from pydantic import {', '.join(pydantic)}")
            out.append("")
        out.append(f"from igni_client.wire import {', '.join(sorted(self.bases_used))}")
        out.append("")
        return out

    def _use_base(self, base: str) -> str:
        self.bases_used.add(base)
        return base

    def _enum(self, name: str) -> list[str]:
        schema = self.contract.defs[name]
        self.imports.typing.add("Literal")
        values = ", ".join(repr(v) for v in schema["enum"])
        out = ["", ""]
        described = schema.get("description") or f"The values of {name}."
        out += [f"#: {line}".rstrip() for line in described.strip().splitlines()]
        out.append(f"type {self.types.class_name(name)} = Literal[{values}]")
        return out

    def _base(self, name: str, props: dict[str, Any]) -> str:
        wire = self.messages.get(name)
        if wire is not None:
            direction = self.contract.messages[wire].direction
            if direction == "to_igni":
                return self._use_base("Frame")
            if all(f in props for f in _RUN_FIELDS):
                return self._use_base("RunEvent")
            return self._use_base("Event")
        if name in self.plan.defs_out:
            return self._use_base("Model")
        return self._use_base("Args")

    def _class(self, name: str) -> list[str]:
        schema = self.contract.defs[name]
        props: dict[str, Any] = schema.get("properties", {})
        required = set(schema.get("required", []))
        cls = self.types.class_name(name)
        base = self._base(name, props)
        wire = self.messages.get(name)
        doc = (
            schema.get("description")
            or (self.contract.messages[wire].doc if wire else "")
            or f"{schema.get('title', name)}."
        )
        if wire is not None:
            doc = f"{doc.rstrip()}\n\nOn the wire: ``{wire}``."
        out = ["", "", f"class {cls}({base}):"]
        out += docstring(doc, "    ")
        aliased = any(field_name(p) != p for p in props)
        if aliased:
            self.imports.pydantic.add("ConfigDict")
            out += [
                "",
                "    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)",
            ]
        if props:
            out.append("")
        for prop in props:
            out += self._field(prop, props[prop], prop in required)
        return out

    def _field(self, prop: str, schema: dict[str, Any], required: bool) -> list[str]:
        python = field_name(prop)
        annotation = self.types.annotation(schema, self.imports)
        kwargs: list[str] = []
        default: str | None = None
        if "default" in schema:
            value = schema["default"]
            if isinstance(value, list | dict) and value:
                ref = self.contract.ref_name(schema)
                maker = f"{self.types.class_name(ref)}.model_validate" if ref else ""
                kwargs.append(f"default_factory=lambda: {maker}({value!r})")
            elif isinstance(value, list):
                kwargs.append("default_factory=list")
            elif isinstance(value, dict):
                kwargs.append("default_factory=dict")
            else:
                default = repr(value)
        elif not required:
            kind = schema.get("type")
            if kind == "object":
                kwargs.append("default_factory=dict")
            elif kind == "array":
                kwargs.append("default_factory=list")
            else:
                if not annotation.endswith("| None") and annotation != "None":
                    annotation += " | None"
                default = "None"
        if python != prop:
            kwargs.append(f"alias={prop!r}")
        if "minLength" in schema:
            kwargs.append(f"min_length={schema['minLength']}")
        if kwargs:
            self.imports.pydantic.add("Field")
            if default is not None:
                kwargs.insert(0, f"default={default}")
            line = f"    {python}: {annotation} = Field({', '.join(kwargs)})"
        elif default is not None:
            line = f"    {python}: {annotation} = {default}"
        else:
            line = f"    {python}: {annotation}"
        out = [line]
        if schema.get("description"):
            out += docstring(schema["description"], "    ")
        return out

    def _push(self, channel: str) -> list[str]:
        spec = self.contract.push_channels[channel]
        payload = self.types.annotation(spec.schema_, self.imports)
        self.imports.typing.add("Literal")
        doc = spec.doc or f"A push on ``{channel}``."
        doc = f"{doc.rstrip()}\n\nOn the wire: ``push_notification`` on the channel ``{channel}``."
        out = ["", "", f"class {push_class(channel)}(PushNotification):"]
        out += docstring(doc, "    ")
        out += [
            "",
            f"    channel: Literal[{channel!r}] = {channel!r}",
            f"    payload: {payload}  # type: ignore[assignment]",
        ]
        return out

    def _union(self, alias: str) -> list[str]:
        union = self.types.unions[alias]
        members = " | ".join(self.types.class_name(n) for n in union.members)
        kinds = len(union.members)
        out = ["", ""]
        if union.told_by:
            self.imports.typing.add("Annotated")
            self.imports.pydantic.add("Field")
            out.append(f"#: One of {kinds} kinds, told apart by ``{union.told_by}``.")
            out.append(
                f'type {alias} = Annotated[{members}, Field(discriminator="{union.told_by}")]'
            )
        else:
            out.append(
                f"#: One of {kinds} kinds. Nothing in the contract tells them apart: "
                "the one that fits best is taken."
            )
            out.append(f"type {alias} = {members}")
        return out

    def _tables(self) -> list[str]:
        events: list[str] = []
        frames: list[str] = []
        for wire_type in sorted(self.contract.messages):
            message = self.contract.messages[wire_type]
            cls = self.types.class_name(self.contract.message_def(wire_type))
            if message.direction in ("to_client", "both"):
                events.append(f"    {wire_type!r}: {cls},")
            if message.direction in ("to_igni", "both"):
                frames.append(f"    {wire_type!r}: {cls},")
        pushes = [f"    {c!r}: {push_class(c)}," for c in sorted(self.contract.push_channels)]
        return [
            "",
            "",
            "#: Every message igni sends, by its wire `type`.",
            "EVENT_TYPES: dict[str, type[Event]] = {",
            *events,
            "}",
            "",
            "#: Every message a client sends, by its wire `type`.",
            "FRAME_TYPES: dict[str, type[Frame | Event]] = {",
            *frames,
            "}",
            "",
            "#: Every push channel the contract types, by channel.",
            "PUSH_TYPES: dict[str, type[PushNotification]] = {",
            *pushes,
            "}",
        ]


__all__ = ["ModelsGenerator"]

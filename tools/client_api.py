"""``igni_client.api``: every method a client calls, on the class its placement names."""

from __future__ import annotations

import re

from tools.client_contract import Correlation
from tools.client_names import (
    ACCESS_NOTES,
    FOLLOWED,
    HAND_WRITTEN_NAMESPACES,
    MESSAGE_DOCS,
    MESSAGE_METHODS,
    NAMESPACES,
    NOT_FOR_CLIENTS,
    OWNER_DOCS,
    UNFOLLOWED,
)
from tools.client_plan import Placement, Plan, class_for_group
from tools.client_python import BANNER, ENVELOPE, ContractError, docstring
from tools.client_signatures import MethodSignatures, Param


class ApiGenerator(MethodSignatures):
    """Every method a client calls, on the class its placement names."""

    def __init__(self, plan: Plan) -> None:
        super().__init__(plan)
        #: Whether a class has a method named ``list``, so the module needs ``builtins``.
        self.builtins = False

    def generate(self) -> str:
        groups = self.plan.groups()
        results = self._results()
        events = self._event_aliases()
        classes: list[str] = []
        for group in sorted(groups, key=lambda g: (g.count("."), g)):
            if "." in group:
                classes += self._namespace(group, groups[group])
        for owner in ("igni", "session"):
            classes += self._owner(owner, groups.get(owner, []), groups)
        table = self._table()
        head = self._head()
        return "\n".join([*head, *results, *events, *table, *classes]) + "\n"

    def _head(self) -> list[str]:
        out = [
            '"""Every method a client calls, typed: igni\'s RPC methods by namespace.',
            "",
            BANNER.format(version=self.contract.version),
            "",
            "`IgniApi` is what `IgniClient` adds for igni as a whole, and `SessionApi`",
            "what `Session` adds for one session. A method that streams returns a",
            "`Call`: await it for the result, or `async with` it to follow its events too.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
        ]
        if self.builtins:
            out.append("import builtins")
        if self.imports.datetime:
            out.append("from datetime import datetime")
        typing = sorted(self.imports.typing)
        if typing:
            out.append(f"from typing import {', '.join(typing)}")
        out.append("")
        pydantic = sorted({"TypeAdapter", *self.imports.pydantic})
        out.append(f"from pydantic import {', '.join(pydantic)}")
        out.append("")
        out.append("from igni_client.calls import Call, Caller, MethodSpec")
        out.append("from igni_client.follow import Correlation")
        out.append("from igni_client.models import (")
        out += [f"    {m}," for m in sorted(self.models)]
        out.append(")")
        out.append("")
        return out

    def _results(self) -> list[str]:
        out = ["", "# What each method answers, read with these."]
        for wire in sorted(self.plan.placements):
            annotation = self.result_type(wire)
            out.append(
                f"{self.adapter_name(wire)}: TypeAdapter[{annotation}] = TypeAdapter({annotation})"
            )
        for name, (reply, _path) in sorted(MESSAGE_METHODS.items()):
            if reply:
                cls = self._use(self.types.class_name(self.contract.message_def(reply)))
                out.append(f"{self.adapter_name(name)}: TypeAdapter[{cls}] = TypeAdapter({cls})")
        return out

    def _event_aliases(self) -> list[str]:
        out = ["", "", "# What each method that is followed causes."]
        for wire in sorted(FOLLOWED):
            classes = [self._use(c) for c in self.plan.event_classes(wire)]
            out.append(f"type {self.event_alias(wire)} = {' | '.join(classes)}")
        return out

    @staticmethod
    def _correlation(correlation: Correlation | None) -> str:
        """The contract's correlation, as the Python the generated table holds."""
        if correlation is None:
            return "None"
        parts = [f"by={correlation.by!r}"]
        if correlation.source:
            parts.append(f"source={correlation.source!r}")
        if correlation.equals:
            parts.append(f"equals={correlation.equals!r}")
        return f"Correlation({', '.join(parts)})"

    def _table(self) -> list[str]:
        out = [
            "",
            "#: Every method a client calls, by wire name: who may call it, how igni",
            "#: answers it, how long it takes, and what it streams.",
            "METHODS: dict[str, MethodSpec] = {",
        ]
        for wire in sorted(self.plan.placements):
            m = self.contract.methods[wire]
            placement = self.plan.placements[wire]
            streams = "".join(f"{s!r}, " for s in m.streams)
            may = "".join(f"{s!r}, " for s in m.may_stream)
            out.append(
                f"    {wire!r}: MethodSpec(wire={wire!r}, python={placement.path!r}, "
                f"scope={m.scope!r}, access={m.access!r}, reply={m.reply!r}, "
                f"streams=({streams}), may_stream=({may}), "
                f"duration={m.duration!r}, timeout_seconds={m.timeout_seconds!r}, "
                f"correlate={self._correlation(m.correlate)}, followed={wire in FOLLOWED}),"
            )
        out.append("}")
        out += [
            "",
            "#: igni's methods a client never calls, and why.",
            "NOT_FOR_CLIENTS: dict[str, str] = {",
        ]
        out += [f"    {w!r}: {r!r}," for w, r in sorted(NOT_FOR_CLIENTS.items())]
        out.append("}")
        out += [
            "",
            "#: Methods that stream, but whose events igni gives a client nothing to",
            "#: tell apart from another call's: they return their result only.",
            "UNFOLLOWED: dict[str, str] = {",
        ]
        out += [f"    {w!r}: {r!r}," for w, r in sorted(UNFOLLOWED.items())]
        out.append("}")
        return out

    def _method(self, placement: Placement) -> list[str]:
        if placement.wire in MESSAGE_METHODS:
            return self._message_method(placement)
        method = self.contract.methods[placement.wire]
        params, model = self.params(placement)
        result = self.result_type(placement.wire)
        values = ", ".join(f"{p.name!r}: {p.value}" for p in params)
        adapter = self.adapter_name(placement.wire)
        doc = method.doc
        if placement.wire in FOLLOWED:
            doc += "\n\n" + FOLLOWED[placement.wire]
        elif placement.wire in UNFOLLOWED:
            doc += "\n\nNot followed: " + UNFOLLOWED[placement.wire]
        if method.access != "client":
            doc += "\n\n" + ACCESS_NOTES[method.access]
        sig = self.signature(placement, params)
        if placement.wire in FOLLOWED:
            out = [
                "",
                f"    def {placement.name}({sig}) -> Call[{result}, {self.event_alias(placement.wire)}]:",
            ]
            out += docstring(doc, "        ")
            out.append(
                f"        return self._caller.follow({placement.wire!r}, {model}, {{{values}}}, {adapter})"
            )
            return out
        out = ["", f"    async def {placement.name}({sig}) -> {result}:"]
        out += docstring(doc, "        ")
        out.append(
            f"        return await self._caller.rpc({placement.wire!r}, {model}, {{{values}}}, {adapter})"
        )
        return out

    def _message_method(self, placement: Placement) -> list[str]:
        wire_type = placement.wire
        reply, _ = MESSAGE_METHODS[wire_type]
        message = self.contract.messages[wire_type]
        def_name = self.contract.message_def(wire_type)
        cls = self._use(self.types.class_name(def_name))
        schema = self.contract.defs[def_name]
        params: list[Param] = []
        for prop, prop_schema in schema.get("properties", {}).items():
            if prop in ENVELOPE:
                continue
            if prop == "client_id":
                params.append(
                    Param(name=prop, annotation="", default=None, value="self._caller.client_id")
                )
                continue
            annotation = self._use(self.types.annotation(prop_schema, self.imports))
            default = repr(prop_schema["default"]) if "default" in prop_schema else None
            params.append(Param(name=prop, annotation=annotation, default=default, value=prop))
        values = ", ".join(f"{p.name!r}: {p.value}" for p in params)
        sig = self.signature(placement, params)
        doc = MESSAGE_DOCS.get(wire_type, message.doc)
        doc += f"\n\nSent as igni's ``{wire_type}`` message."
        if reply:
            result = self._use(self.types.class_name(self.contract.message_def(reply)))
            doc += f" igni answers with ``{reply}``."
            out = ["", f"    async def {placement.name}({sig}) -> {result}:"]
            out += docstring(doc, "        ")
            out.append(
                f"        return await self._caller.request({cls}, {{{values}}}, "
                f"{self.adapter_name(wire_type)})"
            )
            return out
        out = ["", f"    async def {placement.name}({sig}) -> None:"]
        out += docstring(doc, "        ")
        out.append(f"        await self._caller.send({cls}, {{{values}}})")
        return out

    def _namespace(self, group: str, members: list[Placement]) -> list[str]:
        cls = class_for_group(group)
        doc = NAMESPACES.get(group)
        if doc is None:
            raise ContractError(f"namespace {group} has no description in NAMESPACES")
        out = ["", "", f"class {cls}:"]
        if group in HAND_WRITTEN_NAMESPACES:
            doc += (
                f"\n\nThe generated base of ``{HAND_WRITTEN_NAMESPACES[group]}``, "
                f"which is ``{group}``."
            )
        out += docstring(doc, "    ")
        out += [
            "",
            "    def __init__(self, caller: Caller) -> None:",
            "        self._caller = caller",
        ]
        for placement in sorted(members, key=lambda p: p.name):
            out += self._method(placement)
        if any(p.name == "list" for p in members):
            out = self._builtin_list(out)
        return out

    def _builtin_list(self, lines: list[str]) -> list[str]:
        """In a class with a method named ``list``, ``list[...]`` in a signature is that method."""
        self.builtins = True
        return [
            re.sub(r"(?<![\w.])list\[", "builtins.list[", line)
            if line.lstrip().startswith(("def ", "async def "))
            else line
            for line in lines
        ]

    def _owner(
        self, owner: str, members: list[Placement], groups: dict[str, list[Placement]]
    ) -> list[str]:
        out = ["", "", f"class {class_for_group(owner)}:"]
        out += docstring(OWNER_DOCS[owner], "    ")
        namespaces = [
            g
            for g in sorted(groups)
            if g.startswith(owner + ".") and g not in HAND_WRITTEN_NAMESPACES
        ]
        out += [""]
        for group in namespaces:
            out.append(f"    {group.split('.', 1)[1]}: {class_for_group(group)}")
            out += docstring(NAMESPACES[group], "    ")
        out += [
            "",
            "    def __init__(self, caller: Caller) -> None:",
            "        self._caller = caller",
        ]
        for group in namespaces:
            out.append(f"        self.{group.split('.', 1)[1]} = {class_for_group(group)}(caller)")
        for placement in sorted(members, key=lambda p: p.name):
            out += self._method(placement)
        return out


__all__ = ["ApiGenerator"]

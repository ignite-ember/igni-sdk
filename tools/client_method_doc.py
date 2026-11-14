"""One igni-client method's section on its reference page: its summary, signature,
parameters, result, notes, wire name and example."""

from __future__ import annotations

import re
from typing import Any

from tools.client_doc_links import ClientSources
from tools.client_example_check import ClientExamples
from tools.client_method_notes import MethodNotes
from tools.client_names import FOLLOWED, MESSAGE_DOCS, MESSAGE_METHODS
from tools.client_plan import Placement
from tools.client_python import ENVELOPE, Imports, field_name
from tools.client_signatures import Param
from tools.markdown_pages import signature
from tools.wire_prose import WireProse, cell, rst

_SENTENCE_BREAK = re.compile(r"(?<=[.;:])\s+(?=[A-Z`(*])")
_PARAMETER_HEADER = ["| Parameter | Type | Default | Meaning |", "|---|---|---|---|"]


class ParameterMeanings:
    """What each parameter is, and the parameters nothing explains."""

    def __init__(self, prose: WireProse) -> None:
        self.prose = prose
        #: ``wire.parameter`` of every parameter neither the schema nor the doc explains.
        self.missing: list[str] = []

    def meaning(self, wire: str, prop: str, schema: dict[str, Any], doc: str) -> str:
        """What a parameter is: its own description, else what the method's doc says of it."""
        if schema.get("description"):
            return self.prose.prose(schema["description"], wire)
        for sentence in _SENTENCE_BREAK.split(" ".join(doc.split())):
            if f"``{prop}``" in sentence:
                return self.prose.prose(sentence, wire)
        self.missing.append(f"{wire}.{prop}")
        return "—"


def _default_text(default: str | None) -> str:
    return "required" if default is None else f"`{default}`"


class MethodSection:
    """The section of one method, or of one message igni-client sends as a method."""

    def __init__(
        self,
        sources: ClientSources,
        notes: MethodNotes,
        meanings: ParameterMeanings,
        examples: ClientExamples,
    ) -> None:
        self.sources = sources
        self.notes = notes
        self.meanings = meanings
        self.examples = examples

    def section(self, wire: str) -> list[str]:
        placement = self.sources.layout.placements[wire]
        if wire in MESSAGE_METHODS:
            return self._message(wire, placement)
        return self._method(wire, placement)

    def _parameter_row(self, param: Param, meaning: str) -> str:
        annotation = self.sources.type_md(param.annotation.replace("builtins.", ""), in_table=True)
        return (
            f"| `{param.name}` | {annotation} | {_default_text(param.default)} | {cell(meaning)} |"
        )

    def _method(self, wire: str, placement: Placement) -> list[str]:
        sources, prose = self.sources, self.sources.prose
        method = sources.contract.methods[wire]
        params, _ = sources.api.params(placement)
        shown = [p for p in params if p.annotation]
        sig = sources.api.signature(placement, params).replace("builtins.", "")
        result = sources.api.result_type(wire).replace("builtins.", "")
        followed = wire in FOLLOWED
        if followed:
            alias = sources.api.event_alias(wire)
            code = signature(f"def {placement.name}", sig, f" -> Call[{result}, {alias}]")
        else:
            code = signature(f"async def {placement.name}", sig, f" -> {result}")
        doc_paragraphs = method.doc.strip().split("\n\n")
        summary = prose.prose(doc_paragraphs[0].replace("\n", " "), wire)
        rest = [prose.prose(p, wire) for p in doc_paragraphs[1:]]
        note = ""
        if not shown:
            taken = prose.argument_free([summary, *rest])
            summary, rest = taken[0].text, [t.text for t in taken[1:]]
            note = next((t.note for t in taken if t.note), "")
        out = [f"## {sources.layout.heading(placement)}", ""]
        out += [summary, ""] if summary else []
        out += ["```python", code, "```", ""]
        for paragraph in rest:
            out += [paragraph, ""] if paragraph else []
        own_session = prose.own_session(wire)
        if shown:
            args_def = sources.contract.ref_name(method.args) or ""
            props = sources.contract.defs[args_def].get("properties", {}) if args_def else {}
            by_python = {field_name(p): p for p in props}
            out += _PARAMETER_HEADER
            for p in shown:
                prop = by_python[p.name]
                meaning = self.meanings.meaning(wire, prop, props[prop], method.doc)
                out.append(self._parameter_row(p, meaning))
            out.append("")
            if own_session:
                out += ["`session_id` is this session's own, so it is not a parameter.", ""]
        else:
            out += [self._no_arguments(note, own_session=own_session), ""]
        if followed:
            out += [
                f"**Returns** a {sources.type_md('Call')} — await it for the result, "
                f"{sources.type_md(result)}, or `async with` it to follow its events too.",
                "",
            ]
        else:
            out += [f"**Returns** {sources.type_md(result)}.", ""]
        out += self.notes.streams(wire)
        out += self.notes.duration(wire)
        out += self.notes.access(method.access)
        out += self.notes.raises(method.access, followed=followed, sends_only=False)
        out += [
            f"**On the wire** RPC method `{wire}`, scope `{method.scope}`, area "
            f"`{method.area}`; igni answers with `{method.reply}`.",
            "",
        ]
        out += self.examples.example(wire, placement, params)
        return out

    @staticmethod
    def _no_arguments(note: str, *, own_session: bool) -> str:
        """The line a parameter table would be: with igni-core's note and the own session."""
        brackets = [
            n for n in (note, "`session_id` is this session's own" if own_session else "") if n
        ]
        return "Takes no arguments" + (f" ({'; '.join(brackets)})" if brackets else "") + "."

    def _message(self, wire: str, placement: Placement) -> list[str]:
        sources = self.sources
        reply, _ = MESSAGE_METHODS[wire]
        message = sources.contract.messages[wire]
        schema = sources.contract.defs[sources.contract.message_def(wire)]
        props = {
            p: s
            for p, s in schema.get("properties", {}).items()
            if p not in ENVELOPE and p != "client_id"
        }
        result = sources.types.class_name(sources.contract.message_def(reply)) if reply else "None"
        params = [
            Param(
                name=prop,
                annotation=sources.types.annotation(prop_schema, Imports()),
                default=repr(prop_schema["default"]) if "default" in prop_schema else None,
                value=prop,
            )
            for prop, prop_schema in props.items()
        ]
        sig = ", ".join(
            ["self"]
            + [
                f"{p.name}: {p.annotation}" + (f" = {p.default}" if p.default else "")
                for p in params
            ]
        )
        doc = MESSAGE_DOCS.get(wire, message.doc)
        paragraphs = doc.strip().split("\n\n")
        out = [
            f"## {sources.layout.heading(placement)}",
            "",
            rst(paragraphs[0].replace("\n", " ")),
            "",
            "```python",
            signature(f"async def {placement.name}", sig, f" -> {result}"),
            "```",
            "",
        ]
        for paragraph in paragraphs[1:]:
            out += [rst(paragraph), ""]
        if params:
            out += _PARAMETER_HEADER
            for p in params:
                meaning = self.meanings.meaning(wire, p.name, props[p.name], doc)
                out.append(self._parameter_row(p, meaning))
            out.append("")
        out += [f"**Returns** {sources.type_md(result)}.", ""]
        out += self.notes.access("client")
        out += self.notes.raises("client", followed=False, sends_only=not reply)
        answered = f", answered by igni's `{reply}`" if reply else "; igni answers nothing"
        out += [f"**On the wire** the message `{wire}`{answered}.", ""]
        out += self.examples.example(wire, placement, params)
        return out


__all__ = ["MethodSection", "ParameterMeanings"]

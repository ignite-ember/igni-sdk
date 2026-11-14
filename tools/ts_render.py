"""The Markdown of an npm package's reference page.

A page is a table of its names, then each name in full: its signature in
a fenced block, its parameters, its JSDoc, the other public names it
mentions, and its members — an interface's fields, a class's methods —
with a parameter table for each method.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from tools.param_docs import cell, code, jsdoc_params, strip_jsdoc_params
from tools.reference_area import Area, ReferencePage
from tools.ts_jsdoc import markdown, summary
from tools.ts_member_types import CallableHead
from tools.ts_model import Declaration, Member, PropTypes
from tools.ts_module import Module
from tools.ts_parameters import parameter_table, signature_parameters

#: An identifier: a name a signature mentions, which may be another public name.
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def anchor_of(name: str) -> str:
    """The anchor of a name's heading on its page."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class TsPageRenderer:
    """Writes the pages of one package, its modules read and its links known."""

    def __init__(
        self, modules: dict[str, Module], link: Callable[[str], str | None] | None
    ) -> None:
        self.modules = modules
        self.link = link

    def page(self, area: Area, entries: list[Declaration]) -> ReferencePage:
        """One area's page, and how many of its names have no JSDoc."""
        out: list[str] = []
        if area.note:
            out += [area.note, ""]
        out += [
            "Read from the source: every name below, its signature, its JSDoc, and — "
            "for a type or a class — its own members.",
            "",
            "| Name | Kind | Defined in | What it is |",
            "|---|---|---|---|",
        ]
        for entry in entries:
            out.append(
                f"| [`{entry.name}`](#{anchor_of(entry.name)}) | {entry.kind} "
                f"| `{entry.exported_from}` | {summary(entry.doc) or '—'} |"
            )
        out.append("")
        for entry in entries:
            out += self._entry(entry)
        undocumented = sum(1 for entry in entries if not summary(entry.doc))
        return ReferencePage(body="\n".join(out), undocumented=undocumented)

    def _entry(self, entry: Declaration) -> list[str]:
        prop_types = self._prop_types(entry)
        out = [f"## {entry.name}", ""]
        out += ["```typescript", entry.signature, "```", ""]
        out += parameter_table(
            signature_parameters(entry.params, prop_types), jsdoc_params(entry.doc)
        )
        doc = markdown(strip_jsdoc_params(entry.doc))
        if doc:
            out += [doc, ""]
        out += self._also(entry)
        if entry.members:
            out += self._member_table(entry.members)
            out.append("")
            out += self._member_parameters(entry, prop_types)
        return out

    def _prop_types(self, entry: Declaration) -> PropTypes:
        """The interfaces a declaration's module declares: where its props' types are read."""
        module = self.modules.get(entry.exported_from)
        if module is None:
            return PropTypes()
        return PropTypes.of(list(module.declarations.values()))

    def _member_parameters(self, entry: Declaration, prop_types: PropTypes) -> list[str]:
        """The parameters of a declaration's methods, a table each.

        A method's own JSDoc says what each of its parameters is; the
        table says it where a reader looks for it.
        """
        out: list[str] = []
        for member in entry.members:
            if member.kind != "method":
                continue
            head = CallableHead.parse(member.type)
            params = signature_parameters(head.params if head else "", prop_types)
            if not params:
                continue
            out += [f"### {entry.name}.{member.name}()", ""]
            out += parameter_table(params, jsdoc_params(member.doc))
        return out

    def _member_table(self, members: list[Member]) -> list[str]:
        """The table of a declaration's members.

        A column for what a member is, but only when a member says it:
        a table of dashes is a table that says nothing. The Python
        reference drops its description column the same way.
        """
        summaries = [cell(summary(member.doc)) for member in members]
        documented = any(summaries)
        rows = []
        for member, said in zip(members, summaries, strict=True):
            type_ = code(member.type) if member.type else "—"
            name = f"{member.name}?" if member.optional else member.name
            row = f"| `{name}` | {member.kind} | {type_} |"
            rows.append(f"{row} {said} |" if documented else row)
        if not documented:
            return ["| Member | Kind | Type |", "|---|---|---|", *rows]
        return ["| Member | Kind | Type | What it is |", "|---|---|---|---|", *rows]

    def _also(self, entry: Declaration) -> list[str]:
        """The other public names this one's signature names, linked to where they are."""
        if self.link is None:
            return []
        targets: dict[str, str] = {}
        for name in _IDENT.findall(entry.signature):
            if name == entry.name or name in targets:
                continue
            target = self.link(name)
            if target is not None:
                targets[name] = target
        if not targets:
            return []
        links = ", ".join(f"[`{name}`]({target})" for name, target in targets.items())
        return [f"**Also** {links}.", ""]


__all__ = ["TsPageRenderer", "anchor_of"]

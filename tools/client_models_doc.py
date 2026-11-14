"""igni-client's models reference page: every model it reads or sends that is not a
message, field by field, with the methods that return it and the models it is
part of."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from tools.client_doc_layout import CLIENT_PACKAGE, EVENTS_PAGE, MODELS_PAGE
from tools.client_doc_links import ClientSources
from tools.client_model_fields import ModelFields
from tools.client_names import MESSAGE_METHODS
from tools.markdown_pages import tidy
from tools.site_page import REFERENCE, Page, url
from tools.wire_prose import rst

_IN_MESSAGES = "In messages and push notifications"
_IN_ARGUMENTS = "In arguments"
#: The keys of a schema whose values are data, not schemas that name defs.
_DATA_KEYS = ("default", "const", "enum")


class ModelUses(BaseModel):
    """Where each def is used: the methods returning it, and the models it is part of."""

    returned_by: dict[str, list[str]]
    used_in: dict[str, list[str]]


class ModelsPage:
    """The models reference page."""

    def __init__(self, sources: ClientSources, fields: ModelFields) -> None:
        self.sources = sources
        self.fields = fields

    # ── What is on it ──

    def _args_defs(self) -> dict[str | None, list[str]]:
        """Each method's argument model → the methods taking it."""
        contract = self.sources.contract
        out: dict[str | None, list[str]] = {}
        for wire in sorted(self.sources.plan.placements):
            out.setdefault(contract.ref_name(contract.methods[wire].args), []).append(wire)
        return out

    def _names(self) -> list[str]:
        return sorted(self.sources.plan.defs_in | self.sources.plan.defs_out)

    def _models(self) -> list[str]:
        """Every def that is neither a message nor a method's arguments."""
        args = self._args_defs()
        return [n for n in self._names() if n not in self.sources.messages and n not in args]

    def _classes(self) -> list[str]:
        return [n for n in self._models() if not self.sources.types.is_enum(n)]

    def undocumented(self) -> int:
        """How many of the page's models the contract does not describe."""
        defs = self.sources.contract.defs
        return sum(1 for name in self._classes() if not defs[name].get("description"))

    def _direct_refs(self, schema: Any) -> set[str]:
        found: set[str] = set()
        stack = [schema]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                ref = self.sources.contract.ref_name(node)
                if ref is not None:
                    found.add(ref)
                    continue
                stack.extend(v for k, v in node.items() if k not in _DATA_KEYS)
            elif isinstance(node, list):
                stack.extend(node)
        found.discard("JsonValue")
        return found

    def _uses(self) -> ModelUses:
        contract, types = self.sources.contract, self.sources.types
        returned_by: dict[str, list[str]] = {}
        for wire in sorted(self.sources.plan.placements):
            for ref in self._direct_refs(contract.methods[wire].result):
                returned_by.setdefault(ref, []).append(wire)
        used_in: dict[str, list[str]] = {}
        for name in self._names():
            for ref in self._direct_refs(contract.defs[name].get("properties", {})):
                used_in.setdefault(ref, []).append(name)
        for alias, union in types.unions.items():
            for member in union.members:
                used_in.setdefault(member, []).append(alias)
        return ModelUses(returned_by=returned_by, used_in=used_in)

    def _groups(self) -> dict[str, list[str]]:
        """The page's classes, grouped by the first reference page whose methods reach them."""
        layout, contract = self.sources.layout, self.sources.contract
        group_of: dict[str, str] = {}
        for slug, title, _ in layout.pages:
            for wire, page in layout.page_of.items():
                if page != slug or wire in MESSAGE_METHODS:
                    continue
                for ref in self.sources.plan.closure([contract.methods[wire].result]):
                    group_of.setdefault(ref, title)
        groups: dict[str, list[str]] = {}
        for name in self._classes():
            if name in group_of:
                group = group_of[name]
            elif name in self.sources.plan.defs_out:
                group = _IN_MESSAGES
            else:
                group = _IN_ARGUMENTS
            groups.setdefault(group, []).append(name)
        order = [t for _, t, _ in layout.pages] + [_IN_MESSAGES, _IN_ARGUMENTS]
        return {g: groups[g] for g in order if g in groups}

    # ── The page ──

    def page(self, order: int) -> Page:
        uses = self._uses()
        body = [
            "Every type igni-client reads or sends that is not a message, as igni-core's "
            "contract defines it: its fields, their types and defaults, and where it is "
            "used. They are Pydantic models in `igni_client.models`. A model igni-client "
            'reads keeps a field a newer igni adds (`extra="allow"`). Messages and push '
            f"notifications are in [Events]({url(CLIENT_PACKAGE, EVENTS_PAGE)}).",
            "",
            "Grouped by the first reference page whose methods return them.",
            "",
        ]
        for group, names in self._groups().items():
            body += [f"## {group}", ""]
            for name in names:
                body += self._model(name, uses)
        body += self._unions(uses)
        body += self._enums(uses)
        body += self._arguments()
        return Page(
            CLIENT_PACKAGE,
            MODELS_PAGE,
            "Models reference",
            "Every model igni-client reads or sends, field by field, with the methods that "
            "return it and the models it is part of.",
            REFERENCE,
            order,
            tidy(body),
            source="contracts/rpc-contract.json",
        )

    def _model(self, name: str, uses: ModelUses) -> list[str]:
        schema = self.sources.contract.defs[name]
        out = [f"### {self.sources.types.class_name(name)}", ""]
        if schema.get("description"):
            out += [rst(schema["description"]), ""]
        out += self.fields.table(name)
        if name in uses.returned_by:
            links = ", ".join(self.sources.layout.method_link(w) for w in uses.returned_by[name])
            out += [f"**Returned by** {links}.", ""]
        if name in uses.used_in:
            out += [self.fields.used_in(uses.used_in[name]), ""]
        return out

    def _unions(self, uses: ModelUses) -> list[str]:
        types = self.sources.types
        out = ["## Unions", ""]
        for alias in sorted(types.unions):
            union = types.unions[alias]
            linked = " \\| ".join(self.sources.type_md(types.class_name(m)) for m in union.members)
            out += [f"### {alias}", "", f"One of {linked}.", ""]
            out.append(
                f"Told apart by `{union.told_by}`."
                if union.told_by
                else "Nothing in the contract tells them apart: the one that fits best is taken."
            )
            out.append("")
            if alias in uses.used_in:
                out += [self.fields.used_in(uses.used_in[alias]), ""]
        return out

    def _enums(self, uses: ModelUses) -> list[str]:
        out = ["## Enumerations", ""]
        for name in (n for n in self._models() if self.sources.types.is_enum(n)):
            schema = self.sources.contract.defs[name]
            out += [f"### {self.sources.types.class_name(name)}", ""]
            if schema.get("description"):
                out += [rst(schema["description"]), ""]
            out.append("One of " + ", ".join(f"`{v!r}`" for v in schema["enum"]) + ".")
            out.append("")
            if name in uses.used_in:
                out += [self.fields.used_in(uses.used_in[name]), ""]
        return out

    def _arguments(self) -> list[str]:
        """The argument models, each with the methods taking it.

        An argument model with no fields that several methods share is said once, as
        what every method without arguments takes, rather than as a list of them.
        """
        out = [
            "## Arguments",
            "",
            "Each method's arguments are a model of their own, which igni-client fills from "
            "the method's parameters and checks before sending. Their fields are the "
            "parameters on the method's page.",
            "",
            "| Model | Methods |",
            "|---|---|",
        ]
        defs = self.sources.contract.defs
        for def_name, wires in sorted(self._args_defs().items(), key=lambda x: x[0] or ""):
            if def_name is None:
                continue
            if len(wires) > 1 and not defs[def_name].get("properties"):
                methods = "every method that takes no arguments"
            else:
                methods = ", ".join(self.sources.layout.method_link(w) for w in wires)
            out.append(f"| `{self.sources.types.class_name(def_name)}` | {methods} |")
        return out


__all__ = ["ModelUses", "ModelsPage"]

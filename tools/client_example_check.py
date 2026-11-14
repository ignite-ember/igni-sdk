"""Each igni-client method's example: the hand-written one, or one generated for a
read that needs no argument, and the check that it calls its method as the
method can be called."""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from typing import Any

from tools.client_doc_links import ClientSources
from tools.client_examples import EXAMPLES
from tools.client_names import FOLLOWED, MESSAGE_METHODS
from tools.client_plan import Placement
from tools.client_python import ENVELOPE, field_name, snake
from tools.client_signatures import Param
from tools.site_page import DocsError

#: A method needs no example of its own when its wire name says it reads and
#: it takes no argument: one is generated from its result.
READS = re.compile(
    r"^(get_|list_|count_|loop_status$|notifications_counts$|notifications_list$|check_for_update$)"
)

#: The fields an example prints first, when the model has them.
_PREFERRED_FIELDS = ("id", "name", "status", "pid", "role")


def check_example(placement: Placement, params: Sequence[Param], code: str) -> None:
    """The example parses, calls its method, and passes only arguments the method takes."""
    try:
        tree = ast.parse(
            "async def _example():\n"
            + "\n".join("    " + line for line in code.strip("\n").split("\n"))
        )
    except SyntaxError as exc:
        raise DocsError(f"the example of {placement.path}() is not Python: {exc}") from exc
    names = {p.name for p in params if p.annotation}
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _dotted(node.func) == placement.path
    ]
    if not calls:
        raise DocsError(f"the example of {placement.path}() does not call it")
    for call in calls:
        for keyword in call.keywords:
            if keyword.arg is not None and keyword.arg not in names:
                raise DocsError(
                    f"the example of {placement.path}() passes {keyword.arg}=, which it does not take"
                )
        if len(call.args) > len(names):
            raise DocsError(f"the example of {placement.path}() passes too many arguments")


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _variable(method_name: str) -> str:
    """The variable an example keeps a method's result in: not the builtin ``list``."""
    return "listed" if method_name == "list" else method_name


def _nullable(schema: dict[str, Any]) -> bool:
    return any(m.get("type") == "null" for m in schema.get("anyOf", []))


class ClientExamples:
    """The example under each method's section."""

    def __init__(self, sources: ClientSources) -> None:
        self.sources = sources

    def example(self, wire: str, placement: Placement, params: Sequence[Param]) -> list[str]:
        code = EXAMPLES.get(wire)
        if code is None:
            code = self.generated(wire, placement, params)
        if code is None:
            raise DocsError(
                f"{placement.path}() ({wire}) has no example: add one to EXAMPLES in "
                "tools/client_examples.py"
            )
        check_example(placement, params, code)
        return ["**Example**", "", "```python", code.strip("\n"), "```", ""]

    def generated(self, wire: str, placement: Placement, params: Sequence[Param]) -> str | None:
        """An example for a method that only reads and needs no argument."""
        if wire in FOLLOWED or wire in MESSAGE_METHODS or not READS.match(wire):
            return None
        if any(p.annotation and p.default is None for p in params):
            return None
        contract = self.sources.contract
        call = f"await {placement.path}()"
        result = contract.methods[wire].result
        ref = contract.ref_name(result)
        items = (
            contract.ref_name(result.get("items", {})) if result.get("type") == "array" else None
        )
        if items is not None:
            var = snake(self.sources.types.class_name(items))
            return f"for {var} in {call}:\n    print({self._shown(var, items)})\n"
        if ref is not None and not self.sources.types.is_enum(ref):
            return self._assigned(placement, call, ref, nullable=_nullable(result))
        if _nullable(result):
            inner = next(
                (contract.ref_name(m) for m in result["anyOf"] if m.get("type") != "null"),
                None,
            )
            if inner:
                return self._assigned(placement, call, inner, nullable=True)
        return f"print({call})\n"

    def _assigned(self, placement: Placement, call: str, def_name: str, *, nullable: bool) -> str:
        var = _variable(placement.name)
        shown = self._shown(var, def_name)
        if nullable:
            return f"{var} = {call}\nif {var} is not None:\n    print({shown})\n"
        return f"{var} = {call}\nprint({shown})\n"

    def _shown(self, var: str, def_name: str) -> str:
        """What the example prints of ``var``: its first two fields, or itself."""
        return ", ".join(f"{var}.{f}" for f in self.first_fields(def_name)) or var

    def first_fields(self, def_name: str) -> list[str]:
        props = self.sources.contract.defs[def_name].get("properties", {})
        envelope = ENVELOPE if def_name in self.sources.messages else ()
        names = [p for p in props if p not in envelope]
        preferred = [p for p in names if p in _PREFERRED_FIELDS]
        chosen = (preferred + [p for p in names if p not in preferred])[:2]
        return [field_name(p) for p in chosen]


__all__ = ["READS", "ClientExamples", "check_example"]

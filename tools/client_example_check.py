"""Each igni-client method's example, in Python and TypeScript: the hand-written
pair, or one generated for a read that needs no argument, the check that it calls
its method as the method can be called, and the type-check of the TypeScript
against the real ``@ignite-ember/igni-client``."""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tools.client_doc_links import ClientSources
from tools.client_examples import EXAMPLES, TS_EXAMPLES
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
        ts = TS_EXAMPLES.get(wire)
        if code is None:
            code = self.generated(wire, placement, params)
            ts = self.ts_generated(wire, placement, params)
        if code is None:
            raise DocsError(
                f"{placement.path}() ({wire}) has no example: add one to EXAMPLES in "
                "tools/client_examples.py"
            )
        check_example(placement, params, code)
        if ts is None:
            raise DocsError(
                f"{placement.path}() ({wire}) has a Python example but no TypeScript one: "
                "add one to TS_EXAMPLES in tools/client_examples.py"
            )
        return [
            "**Example**",
            "",
            "```python",
            code.strip("\n"),
            "```",
            "",
            "```typescript",
            ts.strip("\n"),
            "```",
            "",
        ]

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

    def ts_generated(self, wire: str, placement: Placement, params: Sequence[Param]) -> str | None:
        """The TypeScript twin of :meth:`generated`, for a read that needs no argument.

        The same shape as the Python one, written the TypeScript way: ``for … of``
        over an array, ``console.log`` and a ``!== null`` guard for a nullable
        result. The method name is the same, and a field is the wire name the
        TypeScript model keeps rather than the Python snake-cased one.
        """
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
            return (
                f"for (const {var} of {call}) {{\n"
                f"  console.log({self._shown_ts(var, items)});\n}}\n"
            )
        if ref is not None and not self.sources.types.is_enum(ref):
            return self._ts_assigned(placement, call, ref, nullable=_nullable(result))
        if _nullable(result):
            inner = next(
                (contract.ref_name(m) for m in result["anyOf"] if m.get("type") != "null"),
                None,
            )
            if inner:
                return self._ts_assigned(placement, call, inner, nullable=True)
        return f"console.log({call});\n"

    def _ts_assigned(
        self, placement: Placement, call: str, def_name: str, *, nullable: bool
    ) -> str:
        var = _variable(placement.name)
        shown = self._shown_ts(var, def_name)
        if nullable:
            return f"const {var} = {call};\nif ({var} !== null) {{\n  console.log({shown});\n}}\n"
        return f"const {var} = {call};\nconsole.log({shown});\n"

    def _shown(self, var: str, def_name: str) -> str:
        """What the Python example prints of ``var``: its first two fields, or itself."""
        return ", ".join(f"{var}.{f}" for f in self.first_fields(def_name)) or var

    def _shown_ts(self, var: str, def_name: str) -> str:
        """What the TypeScript example logs of ``var``: its first two fields, or itself.

        The field is the wire name as the TypeScript model keeps it (``activeForm``),
        not snake-cased the Python way (``active_form``)."""
        return ", ".join(f"{var}.{p}" for p in self._chosen_props(def_name)) or var

    def _chosen_props(self, def_name: str) -> list[str]:
        """The first two wire fields an example shows, preferred ones first."""
        props = self.sources.contract.defs[def_name].get("properties", {})
        envelope = ENVELOPE if def_name in self.sources.messages else ()
        names = [p for p in props if p not in envelope]
        preferred = [p for p in names if p in _PREFERRED_FIELDS]
        return (preferred + [p for p in names if p not in preferred])[:2]

    def first_fields(self, def_name: str) -> list[str]:
        return [field_name(p) for p in self._chosen_props(def_name)]


#: The import every harnessed example gets: an open ``igni`` and a ``session``.
_TS_HARNESS_IMPORT = 'import { IgniClient, Session } from "@ignite-ember/igni-client";'


def ts_example_source(examples: Sequence[tuple[str, str]]) -> str:
    """One TypeScript file from the examples: each in its own ``async`` function.

    ``examples`` is ``(label, code)`` pairs, as ``make sdk-docs`` emits them in
    the ``typescript`` blocks. Each becomes a function taking an open ``igni``
    and a ``session`` — the variables the reference says every example runs with
    — so the client's whole surface is in scope. ``import`` lines an example
    carries (``node:fs/promises`` and the like) are hoisted to the top and
    de-duplicated, because an import cannot sit inside a function.
    """
    imports: dict[str, None] = {_TS_HARNESS_IMPORT: None}
    bodies: list[str] = []
    for index, (label, code) in enumerate(examples, 1):
        kept: list[str] = []
        for line in code.strip("\n").split("\n"):
            if line.startswith("import ") and line.rstrip().endswith(";"):
                imports.setdefault(line, None)
            else:
                kept.append(line)
        body = "\n".join(("  " + line if line.strip() else "") for line in kept)
        bodies.append(
            f"async function example_{index}"
            f"(igni: IgniClient, session: Session): Promise<void> {{  // {label}\n"
            f"{body}\n}}"
        )
    return "\n".join(imports) + "\n\n" + "\n\n".join(bodies) + "\n"


def type_check_ts(root: Path, examples: Sequence[tuple[str, str]]) -> tuple[bool, str]:
    """Type-check the TypeScript examples against the real client.

    Returns ``(ok, output)``. The examples are put through ``tsc`` with
    igni-client's own compiler settings, the client resolved to its source
    (``packages/igni-client/src``), so no prior build is needed. An example that
    does not compile makes ``ok`` false and names itself in ``output``.
    """
    source = ts_example_source(examples)
    with tempfile.TemporaryDirectory(dir=root) as directory:
        work = Path(directory)
        (work / "examples.ts").write_text(source, encoding="utf-8")
        config = {
            "extends": "../tsconfig.json",
            "compilerOptions": {
                "noEmit": True,
                "skipLibCheck": True,
                "baseUrl": "..",
                "paths": {"@ignite-ember/igni-client": ["packages/igni-client/src/index.ts"]},
            },
            "include": ["examples.ts"],
        }
        (work / "tsconfig.json").write_text(json.dumps(config), encoding="utf-8")
        done = subprocess.run(  # noqa: S603 — tsc, on our own generated file
            ["npx", "tsc", "-p", str(work / "tsconfig.json")],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    return done.returncode == 0, done.stdout + done.stderr


def have_tsc(root: Path) -> bool:
    """Whether ``npx`` and igni-client's TypeScript are installed to type-check with."""
    return shutil.which("npx") is not None and (root / "node_modules/typescript").exists()


__all__ = [
    "READS",
    "ClientExamples",
    "check_example",
    "have_tsc",
    "ts_example_source",
    "type_check_ts",
]

"""igni-client's exceptions, read from its ``errors.py``, and the errors reference page."""

from __future__ import annotations

import ast
from pathlib import Path

from pydantic import BaseModel

from tools.client_contract import RpcContract
from tools.client_doc_layout import CLIENT_PACKAGE, ERRORS_PAGE
from tools.markdown_pages import tidy
from tools.site_page import REFERENCE, Page
from tools.wire_prose import cell, rst


class ErrorClass(BaseModel):
    """One exception class: its name, the names of its bases, and its docstring."""

    name: str
    bases: list[str]
    doc: str

    @property
    def summary(self) -> str:
        return self.doc.split("\n\n", 1)[0].replace("\n", " ")


def read_errors(path: Path) -> list[ErrorClass]:
    """igni-client's exceptions, read from its ``errors.py`` without importing it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        ErrorClass(
            name=node.name,
            bases=[b.id for b in node.bases if isinstance(b, ast.Name)],
            doc=ast.get_docstring(node) or "",
        )
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    ]


class ErrorCatalog:
    """igni-client's exceptions, in the order ``errors.py`` defines them."""

    def __init__(self, errors: list[ErrorClass]) -> None:
        self.by_name = {e.name: e for e in errors}

    def __contains__(self, name: object) -> bool:
        return name in self.by_name

    def items(self) -> list[tuple[str, ErrorClass]]:
        return list(self.by_name.items())

    def children(self) -> dict[str, list[str]]:
        """Each class's name → the classes whose first base it is."""
        out: dict[str, list[str]] = {}
        for name, error in self.by_name.items():
            out.setdefault(error.bases[0] if error.bases else "", []).append(name)
        return out


class ErrorsPage:
    """The page of every error igni-client raises, how they are related, and igni's codes."""

    def __init__(self, errors: ErrorCatalog, contract: RpcContract) -> None:
        self.errors = errors
        self.contract = contract

    def page(self, order: int) -> Page:
        body = [
            "Everything igni-client raises on purpose is an `IgniClientError`. Each "
            "method's page lists the ones it raises; this is each error's own "
            "documentation, from `igni_client.errors`.",
            "",
            "```text",
        ]
        children = self.errors.children()
        for root in children.get("Exception", []):
            body += self._tree(root, 0, children)
        body += ["```", ""]
        body += self._codes()
        for name, error in self.errors.items():
            body += [
                f"## {name}",
                "",
                "```python",
                f"class {name}({', '.join(error.bases)})",
                "```",
                "",
            ]
            if error.doc:
                body += [rst(error.doc), ""]
        return Page(
            CLIENT_PACKAGE,
            ERRORS_PAGE,
            "Errors reference",
            "Every error igni-client raises, how they are related, and when each is raised.",
            REFERENCE,
            order,
            tidy(body),
            source="packages/igni-client/src/igni_client/errors.py",
        )

    def _tree(self, name: str, depth: int, children: dict[str, list[str]]) -> list[str]:
        extra = self.errors.by_name[name].bases[1:]
        also = f"  (also {', '.join(extra)})" if extra else ""
        out = ["    " * depth + name + also]
        for child in children.get(name, []):
            out += self._tree(child, depth + 1, children)
        return out

    def _codes(self) -> list[str]:
        if not self.contract.errors:
            return []
        out = [
            "## What igni answers with",
            "",
            "igni names its refusals and failures with a code (`RpcResponse.code`), "
            "and says what each means. igni-client does not branch on the code: it "
            "reads igni's own sentence and raises the `RpcError` kind that sentence "
            "names (`MethodFailed` when it names none). These are the codes igni's "
            "contract defines.",
            "",
            "| Code | What it means |",
            "|---|---|",
        ]
        out += [f"| `{code}` | {cell(meaning)} |" for code, meaning in self.contract.errors.items()]
        out.append("")
        return out


__all__ = ["ErrorCatalog", "ErrorClass", "ErrorsPage", "read_errors"]

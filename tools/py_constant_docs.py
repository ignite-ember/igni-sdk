"""The docstrings of a package's module-level constants, read from its source.

A module-level constant is documented the way PEP 258 says: a string
literal right after the assignment. Python does not keep that anywhere at
runtime — ``SCHEMA_VERSION.__doc__`` is the version, not the sentence — so
it is read from the source the way the convention intends a tool to read
it.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path


class ConstantDocs:
    """The constants' docstrings across every source file of a package.

    The files are read, not imported: a module that does work at import
    time should not be made to do it because a document was being written
    about it. A file that cannot be read or parsed is passed over.
    """

    def __init__(self, modules: tuple[str, ...]) -> None:
        #: Every module body of the package, in the order its files are found.
        self.bodies = [body for source in self._sources(modules) if (body := self._parse(source))]

    def doc(self, name: str) -> str:
        """The docstring of the constant ``name``, or ``""`` when it has none.

        The constant is looked for across the package, not only in the
        module that re-exports it: ``igni_extension.testing`` exports
        ``Minter``, which ``igni_extension.testing.token_endpoint`` defines
        and documents. A constant with no such literal has no docstring,
        and the page says so rather than inventing one.
        """
        for body in self.bodies:
            for index, node in enumerate(body):
                if not self._assigns(node, name):
                    continue
                following = body[index + 1] if index + 1 < len(body) else None
                if (
                    isinstance(following, ast.Expr)
                    and isinstance(following.value, ast.Constant)
                    and isinstance(following.value.value, str)
                ):
                    return inspect.cleandoc(following.value.value)
        return ""

    @staticmethod
    def _assigns(node: ast.stmt, name: str) -> bool:
        """Whether ``node`` is an assignment to the bare name ``name``."""
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            return False
        return any(isinstance(target, ast.Name) and target.id == name for target in targets)

    @staticmethod
    def _parse(source: str) -> list[ast.stmt]:
        try:
            return ast.parse(Path(source).read_text(encoding="utf-8")).body
        except (OSError, SyntaxError, UnicodeDecodeError):
            return []

    @staticmethod
    def _sources(modules: tuple[str, ...]) -> list[str]:
        """Every source file of the package: each module's file, and each package's tree."""
        found: list[str] = []
        for module_name in modules:
            module = importlib.import_module(module_name)
            path = getattr(module, "__file__", None)
            if path:
                found.append(path)
            for root in getattr(module, "__path__", []):
                found += [str(source) for source in sorted(Path(root).rglob("*.py"))]
        return list(dict.fromkeys(found))


__all__ = ["ConstantDocs"]

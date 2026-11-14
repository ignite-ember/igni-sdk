"""One TypeScript source file: its declarations, and what it exports."""

from __future__ import annotations

import re
from pathlib import Path

from tools.ts_declarations import DeclarationReader
from tools.ts_jsdoc import doc_before
from tools.ts_model import Declaration
from tools.ts_text import TsText

#: A declaration at the top level of a file: nothing before it on its line.
#: A declaration inside a function body is indented, and is not one.
_DECL_AT_TOP = re.compile(
    r"(?m)^(?P<export>export\s+)?(?:(?P<declare>declare\s+))?"
    r"(?P<abstract>abstract\s+)?(?P<async>async\s+)?"
    r"(?P<kind>function|class|interface|type|enum|const|let|var)\s+"
)

#: An export list: ``export { A, B } from "./x"`` or ``export type { A }``.
_EXPORT_LIST = re.compile(r"(?m)^export\s+(?:type\s+)?\{")

#: A whole module exported: ``export * from "./x"``.
_EXPORT_STAR = re.compile(r"(?m)^export\s+\*\s+from\s+")


class Module:
    """One TypeScript source file: its declarations, and what it exports.

    A file exports in three ways: a declaration marked ``export``, a list
    (``export { A, B } from "./x"``) and a whole module (``export * from
    "./x"``). All three are read here, so a name the package's entry point
    re-exports is found in the file that declares it.
    """

    def __init__(self, path: Path, name: str) -> None:
        self.path = path
        self.name = name
        self.text = path.read_text(encoding="utf-8")
        #: Every declaration in the file, exported or not.
        self.declarations: dict[str, Declaration] = {}
        #: The names the file exports itself, in the order it declares them.
        #:
        #: A dict rather than a set, and the order matters: a set of
        #: strings iterates in whatever order the interpreter's hash
        #: seed gives it, which differs between two runs of the same
        #: program. The pages would then be written one way by
        #: ``make sdk-docs`` and another by the staleness test, and
        #: neither would be wrong — only different.
        self.exported: dict[str, None] = {}
        #: A name the file re-exports → the module it comes from ("" for its own).
        self.reexports: dict[str, str] = {}
        #: A name exported under another one (``A as B``) → the name it has where it is declared.
        self.aliases: dict[str, str] = {}
        #: The modules the file exports whole.
        self.stars: list[str] = []
        self._read_declarations()
        self._read_export_lists()
        self._read_export_stars()

    def _read_declarations(self) -> None:
        text = self.text
        reader = DeclarationReader(self.name)
        starts = list(_DECL_AT_TOP.finditer(text))
        for index, match in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
            declaration = reader.read(
                text[match.start() : end], match, doc_before(text, match.start())
            )
            if declaration is None:
                continue
            self.declarations[declaration.name] = declaration
            if match.group("export"):
                self.exported[declaration.name] = None

    def _read_export_lists(self) -> None:
        text = self.text
        for match in _EXPORT_LIST.finditer(text):
            open_brace = text.index("{", match.start())
            close = TsText(text).match_bracket(open_brace, "{", "}")
            from_match = re.match(r"\s*from\s+['\"]([^'\"]+)['\"]", text[close:])
            specifier = from_match.group(1) if from_match else ""
            for item in text[open_brace + 1 : close - 1].split(","):
                self._export_item(item, specifier)

    def _export_item(self, item: str, specifier: str) -> None:
        """One name of an export list: ``A``, ``type A`` or ``A as B``."""
        name = item.strip()
        if not name:
            return
        if name.startswith("type "):
            name = name[len("type ") :].strip()
        # `A as B` exports A under the name B.
        original, _, renamed = name.rpartition(" as ")
        name = renamed.strip() if original else name
        if original and original.strip() != name:
            self.aliases[name] = original.strip()
        self.reexports[name] = specifier
        if not specifier:
            self.exported[name] = None

    def _read_export_stars(self) -> None:
        for match in _EXPORT_STAR.finditer(self.text):
            from_match = re.match(r"\s*['\"]([^'\"]+)['\"]", self.text[match.end() :])
            if from_match:
                self.stars.append(from_match.group(1))


__all__ = ["Module"]

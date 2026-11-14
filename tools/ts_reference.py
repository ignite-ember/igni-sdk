"""The npm SDKs' reference pages, read from their TypeScript.

The Python packages' reference is read from the code itself
(``tools/py_reference.py``: ``inspect`` for the signatures, the
docstrings for the words). The npm packages have no such runtime to
ask, so this reads their TypeScript source the same way: every exported
declaration, its signature, its members and the JSDoc above it.

The shape of a page matches the Python ones, so a reader sees one table
of names and then each name in full:

* a table — the name, what kind of thing it is, and the first line of
  its JSDoc;
* then the name itself — its signature in a fenced block, its JSDoc as
  Markdown, and its members (an interface's fields, a class's methods)
  in a table.

The reading is done in parts: ``ts_text`` walks a source as code,
``ts_module`` and ``ts_declarations`` find a file's declarations and
exports, ``ts_members`` and ``ts_member_types`` read their members,
``ts_parameters`` their parameters, and ``ts_render`` writes the page.
This module traces each public name to the file that declares it and
cuts the names into pages.

Nothing is written by hand: ``make sdk-docs`` writes these pages, and
``tests/test_the_sdk_docs_are_generated.py`` fails when what is checked
in differs from what the sources generate.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tools.reference_area import Anchor, Area, ReferencePage
from tools.ts_jsdoc import is_internal
from tools.ts_model import Declaration, Member, ReferenceError_
from tools.ts_module import Module
from tools.ts_render import TsPageRenderer, anchor_of


class TsReference:
    """The reference pages of one npm package's public names.

    A name is documented where it is *declared*, not where it is
    re-exported: ``index.ts`` of ``@ignite-ember/ui-react`` re-exports
    sixty names from nine files, and each of them is read from the file
    that declares it.
    """

    def __init__(
        self,
        package: str,
        src: Path,
        areas: list[Area],
        link: Callable[[str], str | None] | None = None,
        entries: tuple[str, ...] = ("index.ts",),
    ) -> None:
        self.package = package
        self.src = src
        self.areas = areas
        self.link = link
        #: The package's entry points: the files whose exports are its
        #: public surface — the main one, and any subpath it publishes.
        self.entries = entries
        self.modules: dict[str, Module] = {}
        self.placed: dict[str, list[Declaration]] = {}
        self._load()
        #: Every name the package publishes.
        self.public: set[str] = {name for entry in self.entries for name in self.entry_names(entry)}

    # ── Reading the sources ──

    def _load(self) -> None:
        pending: list[str] = list(self.entries)
        for area in self.areas:
            pending.extend(area.sources)
        while pending:
            name = pending.pop(0)
            if name in self.modules:
                continue
            path = self.src / name
            if not path.exists():
                raise ReferenceError_(f"{self.package}: no source file {name}")
            module = Module(path, name)
            self.modules[name] = module
            for specifier in [*module.stars, *module.reexports.values()]:
                target = self.target(name, specifier) if specifier else ""
                if target and target not in self.modules:
                    pending.append(target)

    def target(self, module_name: str, specifier: str) -> str:
        """The file a ``from "./x"`` names, relative to the package's ``src``.

        The source names its own neighbours the way Node will find them
        after the build — ``./bridge.js`` for ``bridge.ts`` — because the
        emitted JavaScript has to find its neighbours by name. The
        declarations are in the TypeScript, so that is what is looked
        for.
        """
        if not specifier.startswith("."):
            return ""
        base = Path(module_name).parent
        stem = (base / specifier[2:]).as_posix()
        if stem.endswith((".js", ".jsx")):
            stem = stem.rsplit(".", 1)[0]
        for candidate in (
            stem + ".ts",
            stem + ".tsx",
            stem + "/index.ts",
            stem + "/index.tsx",
        ):
            if (self.src / candidate).exists():
                return candidate
        return ""

    def _module_at(self, module: Module, specifier: str) -> Module | None:
        """The read module a specifier in ``module`` names; ``None`` when it names none."""
        target = self.target(module.name, specifier)
        return self.modules.get(target) if target else None

    def exported_names(self, module: Module, seen: set[str] | None = None) -> list[str]:
        """The names a module exports, in the order it exports them.

        Two modules that export each other whole are a cycle, not a
        reason to recurse for ever: each is read once.
        """
        seen = seen if seen is not None else set()
        if module.name in seen:
            return []
        seen.add(module.name)
        out: dict[str, None] = dict.fromkeys([*module.exported, *module.reexports])
        for specifier in module.stars:
            star = self._module_at(module, specifier)
            if star is not None:
                out.update(dict.fromkeys(self.exported_names(star, seen)))
        return list(out)

    def entry_names(self, entry: str | None = None) -> list[str]:
        """The names an entry point exports: the package's own, or a subpath's."""
        module = self.modules.get(entry or self.entries[0])
        if module is None:
            return []
        return self.exported_names(module)

    def resolve(
        self, module: Module, name: str, seen: set[tuple[str, str]] | None = None
    ) -> Declaration | None:
        """The declaration of a name a module exports.

        ``seen`` holds every (module, name) already asked about: two
        modules that re-export each other are a cycle, not a recursion.
        """
        seen = seen if seen is not None else set()
        key = (module.name, name)
        if key in seen:
            return None
        seen.add(key)
        if name in module.aliases:
            return self._resolve_alias(module, name, seen)
        declaration = module.declarations.get(name)
        if declaration is not None:
            return declaration
        specifier = module.reexports.get(name)
        if specifier:
            source = self._module_at(module, specifier)
            return self.resolve(source, name, seen) if source is not None else None
        for star in module.stars:
            source = self._module_at(module, star)
            found = self.resolve(source, name, seen) if source is not None else None
            if found is not None:
                return found
        return None

    def _resolve_alias(
        self, module: Module, name: str, seen: set[tuple[str, str]]
    ) -> Declaration | None:
        """A name exported under another (``A as B``): the original's declaration, renamed."""
        original = module.aliases[name]
        specifier = module.reexports.get(name, "")
        if specifier:
            source = self._module_at(module, specifier)
            found = self.resolve(source, original, seen) if source is not None else None
        else:
            found = module.declarations.get(original)
        return found.renamed(name) if found is not None else None

    # ── The pages ──

    def _documented(self, module: Module) -> list[Declaration]:
        """The public names a module exports that are documented: not marked ``@internal``."""
        out: list[Declaration] = []
        for name in self.exported_names(module):
            if name not in self.public:
                continue
            declaration = self.resolve(module, name)
            if declaration is not None and not is_internal(declaration.doc):
                out.append(declaration)
        return out

    def place(self) -> dict[str, list[Declaration]]:
        """Every public name, and the area it is on.

        A public name no area takes is an error, and so is an area that
        takes none: the pages are then a description of the package that
        is true of all of it.
        """
        if self.placed:
            return self.placed
        placed = {area.slug: self.entries_of(area) for area in self.areas}
        covered = {entry.name for entries in placed.values() for entry in entries}
        visible = {
            declaration.name
            for entry in self.entries
            if entry in self.modules
            for declaration in self._documented(self.modules[entry])
        }
        unplaced = sorted(visible - covered)
        if unplaced:
            raise ReferenceError_(f"public names no reference page takes: {unplaced}")
        empty = [slug for slug, entries in placed.items() if not entries]
        if empty:
            raise ReferenceError_(f"reference pages with no public name: {empty}")
        self.placed = placed
        return placed

    def anchors(self) -> dict[str, Anchor]:
        """Every documented name → its page's slug and its anchor."""
        return {
            entry.name: Anchor(slug=slug, anchor=anchor_of(entry.name))
            for slug, entries in self.place().items()
            for entry in entries
        }

    def entries_of(self, area: Area) -> list[Declaration]:
        """The declarations on a page, in the order the modules export them.

        Only names the package publishes are on it: a module's own
        helper is not public just because it is exported.
        """
        out: dict[str, Declaration] = {}
        for source in area.sources:
            module = self.modules.get(source)
            if module is None:
                continue
            for declaration in self._documented(module):
                out.setdefault(declaration.name, declaration)
        return list(out.values())

    def page(self, area: Area) -> ReferencePage:
        """The Markdown of one area's page, and how many names it left undocumented."""
        return TsPageRenderer(self.modules, self.link).page(area, self.place()[area.slug])

    def anchor(self, name: str) -> str:
        """The anchor of a name's heading on its page."""
        return anchor_of(name)


__all__ = [
    "Area",
    "Declaration",
    "Member",
    "Module",
    "ReferenceError_",
    "TsReference",
]

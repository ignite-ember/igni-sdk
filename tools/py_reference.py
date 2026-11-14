"""A Python package's public names, read from the package itself, as reference pages.

igni-service and igni-extension are written by hand, so their reference on
the site (``tools/sdk_docs.py``) is read from them: every name in a module's
``__all__``, its signature as ``inspect`` reports it, its docstring, and, for
a class, its fields and its own public methods and properties. Nothing is
added that the code does not say; a name with no docstring is shown with its
signature alone.

Under every signature is the table of its parameters: what each one is
called, what type it is, what it defaults to, and what it means. The
meaning is read from the docstring's own ``Args:`` section
(``tools/param_docs.py``); a parameter no docstring documents is said to be
undocumented, because a reference that guesses what a parameter is would be
wrong rather than useful.

Which page a name is on is decided by the module that defines it, through a
table of areas the caller gives; a public name no area takes is an error.

This module places the names and assembles the pages. A name's section is
written by ``tools/py_render.py``, from its signature (``tools/py_signature.py``),
its docstring (``tools/py_docstring.py``), its fields (``tools/py_fields.py``)
and, for a constant, the docstring its source gives it
(``tools/py_constant_docs.py``).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

from pydantic import BaseModel

from tools.py_constant_docs import ConstantDocs
from tools.py_docstring import docstring_markdown
from tools.py_entry import Entry
from tools.py_render import EntryRenderer
from tools.py_signature import CallableSignature, annotation_text, stable_repr
from tools.reference_area import Area


class ReferenceError_(ValueError):
    """A public name has no page, or a page names a module with no public name."""


class Anchor(BaseModel):
    """Where a documented name is: the slug of its page and the anchor of its heading."""

    slug: str
    anchor: str


class ReferencePage(BaseModel):
    """A page's Markdown body (no title), and how many names on it have no docstring."""

    body: str
    undocumented: int


def _public_names(modules: tuple[str, ...]) -> list[Entry]:
    """Every name in each module's ``__all__``, once per module that exports it."""
    out: dict[str, Entry] = {}
    for module_name in modules:
        module = importlib.import_module(module_name)
        for name in module.__all__:
            entry = Entry(name=name, obj=getattr(module, name), exported_from=module_name)
            out.setdefault(entry.key, entry)
    return list(out.values())


class PythonReference:
    """The reference pages of one package's public names."""

    def __init__(
        self,
        package: str,
        modules: tuple[str, ...],
        areas: list[Area],
        link: Callable[[str], str | None],
    ) -> None:
        """Read and place the package's public names.

        Args:
            package: The package the pages document: ``igni_service``.
            modules: The modules whose ``__all__`` is public: the package and its ``testing``.
            areas: The pages, each with the modules and constants it takes.
            link: The page and anchor of a documented name, for links between them.
        """
        self.package = package
        self.areas = areas
        self.entries = _public_names(modules)
        self.placed = self._place()
        self.renderer = EntryRenderer(link, ConstantDocs(modules))

    def _area_of(self, entry: Entry) -> Area | None:
        """The first area one of whose sources takes ``entry``."""
        for area in self.areas:
            if any(entry.taken_by(source) for source in area.sources):
                return area
        return None

    def _place(self) -> dict[str, list[Entry]]:
        placed: dict[str, list[Entry]] = {area.slug: [] for area in self.areas}
        unplaced: list[str] = []
        for entry in self.entries:
            area = self._area_of(entry)
            if area is None:
                unplaced.append(f"{entry.exported_from}.{entry.name} ({entry.home})")
                continue
            placed[area.slug].append(entry)
        if unplaced:
            raise ReferenceError_(f"public names no reference page takes: {unplaced}")
        empty = [slug for slug, entries in placed.items() if not entries]
        if empty:
            raise ReferenceError_(f"reference pages with no public name: {empty}")
        return placed

    def anchors(self) -> dict[str, Anchor]:
        """Every documented name → where its section is; the first page that has it wins."""
        out: dict[str, Anchor] = {}
        for slug, entries in self.placed.items():
            for entry in entries:
                out.setdefault(entry.name, Anchor(slug=slug, anchor=entry.anchor))
        return out

    def page(self, area: Area) -> ReferencePage:
        """The page of ``area``: where to import from, a table of its names, a section each."""
        entries = self.placed[area.slug]
        modules = sorted({e.home.split(":")[0] for e in entries})
        imports = sorted({e.exported_from for e in entries})
        out = [
            "Read from the code: every public name below, its signature and its docstring. "
            "Import "
            + ", ".join(f"`{m}`" for m in imports)
            + " — defined in "
            + ", ".join(f"`{m}`" for m in modules)
            + ".",
            "",
            "| Name | What it is |",
            "|---|---|",
        ]
        for entry in entries:
            summary = self.renderer.docstring(entry).summary()
            out.append(f"| [`{entry.name}`](#{entry.anchor}) | {summary or '—'} |")
        out.append("")
        undocumented = 0
        for entry in entries:
            section = self.renderer.render(entry)
            out += section.lines
            undocumented += section.undocumented
        return ReferencePage(body="\n".join(out), undocumented=undocumented)


__all__ = [
    "Anchor",
    "Area",
    "CallableSignature",
    "Entry",
    "PythonReference",
    "ReferenceError_",
    "ReferencePage",
    "annotation_text",
    "docstring_markdown",
    "stable_repr",
]

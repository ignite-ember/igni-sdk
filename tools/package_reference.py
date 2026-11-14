"""The reference pages of the hand-written packages, read from their code.

igni-service's and igni-extension's public names, a page per area
(``tools/py_reference.py``); the npm packages' names, read from their
TypeScript (``tools/ts_reference.py``); and the stylesheet's tokens and classes,
read from the CSS itself (``tools/css_reference.py``). Which page a name is on
is ``tools/reference_areas.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from tools.css_reference import CssReference
from tools.markdown_pages import tidy
from tools.py_reference import PythonReference
from tools.reference_area import Anchor, Area, ReferencePage
from tools.reference_areas import NPM_AREAS, NPM_ENTRIES, PYTHON_AREAS
from tools.site_packages import Package
from tools.site_page import REFERENCE, PackagePages, PackageReport, Page, url
from tools.ts_reference import TsReference

#: How many names a reference page's description lists before "…".
_NAMES_LISTED = 6


class _PlacedName(Protocol):
    @property
    def name(self) -> str: ...


class AnchorLinker:
    """Links between one package's reference pages: a name → its page and heading.

    A reference reads its anchors once it has placed its names, and renders its
    pages with the links after: ``learn`` hands it the anchors in between.
    """

    def __init__(self, site: str) -> None:
        self.site = site
        self.anchors: dict[str, Anchor] = {}

    def learn(self, anchors: dict[str, Anchor]) -> None:
        self.anchors = anchors

    def link(self, name: str) -> str | None:
        anchor = self.anchors.get(name)
        if anchor is None:
            return None
        return url(self.site, f"reference-{anchor.slug}", anchor.anchor)


def _description(names: Sequence[_PlacedName], read_as: str) -> str:
    """A reference page's description: the first names on it, and how they were read."""
    listed = ", ".join(e.name for e in names[:_NAMES_LISTED])
    more = "…" if len(names) > _NAMES_LISTED else ""
    return f"Reference: {listed}{more} — {read_as}."


def _area_page(
    package: Package, area: Area, page: ReferencePage, order: int, description: str, source: str
) -> Page:
    return Page(
        package.site,
        f"reference-{area.slug}",
        area.title,
        description,
        REFERENCE,
        order,
        tidy(page.body.split("\n")),
        source=source,
    )


class PythonPackageReference:
    """igni-service's or igni-extension's reference pages: its public names."""

    def __init__(self, package: Package) -> None:
        self.package = package
        self.areas = list(PYTHON_AREAS[package.name])

    def pages(self, start: int) -> PackagePages:
        package = self.package
        linker = AnchorLinker(package.site)
        reference = PythonReference(
            package.module, (package.module, f"{package.module}.testing"), self.areas, linker.link
        )
        linker.learn(reference.anchors())
        pages: list[Page] = []
        undocumented = 0
        for index, area in enumerate(self.areas):
            page = reference.page(area)
            undocumented += page.undocumented
            placed = reference.placed[area.slug]
            pages.append(
                _area_page(
                    package,
                    area,
                    page,
                    start + index,
                    _description(placed, "signatures and docstrings, read from the code"),
                    f"{package.module}'s public names ({placed[0].exported_from}.__all__ "
                    "and its testing module)",
                )
            )
        return PackagePages(pages=pages, report=PackageReport(undocumented=undocumented))


class NpmPackageReference:
    """An npm package's reference pages: its names, read from its TypeScript source."""

    def __init__(self, package: Package, root: Path) -> None:
        self.package = package
        self.root = root
        self.areas = list(NPM_AREAS[package.site])

    def pages(self, start: int) -> PackagePages:
        package = self.package
        linker = AnchorLinker(package.site)
        reference = TsReference(
            package.name,
            self.root / package.path / "src",
            self.areas,
            link=linker.link,
            entries=NPM_ENTRIES[package.site],
        )
        reference.place()
        linker.learn(reference.anchors())
        pages: list[Page] = []
        undocumented = 0
        for index, area in enumerate(self.areas):
            page = reference.page(area)
            undocumented += page.undocumented
            pages.append(
                _area_page(
                    package,
                    area,
                    page,
                    start + index,
                    _description(
                        reference.placed[area.slug], "signatures and JSDoc, read from the source"
                    ),
                    f"{package.path}/src/{area.sources[0]}",
                )
            )
        return PackagePages(pages=pages, report=PackageReport(undocumented=undocumented))


class CssPackageReference:
    """The stylesheet's reference: the tokens it defines and the classes it styles."""

    def __init__(self, package: Package, root: Path) -> None:
        self.package = package
        self.root = root

    def pages(self, start: int) -> PackagePages:
        package = self.package
        source = f"{package.path}/igni-ui.css"
        text = (self.root / source).read_text("utf-8")
        reference = CssReference(package.name, source, text)
        tokens, token_count = reference.tokens_page()
        classes, class_count = reference.classes_page()
        pages = [
            Page(
                package.site,
                "reference-tokens",
                "Design tokens",
                "Every custom property the stylesheet defines, its fallback, and the "
                "classes that use it.",
                REFERENCE,
                start,
                tidy(tokens.split("\n")),
                source=source,
            ),
            Page(
                package.site,
                "reference-classes",
                "Classes",
                "Every class the stylesheet defines, in the sections the stylesheet "
                "itself uses, and what each one sets.",
                REFERENCE,
                start + 1,
                tidy(classes.split("\n")),
                source=source,
            ),
        ]
        report = PackageReport(tokens=token_count, classes=class_count)
        return PackagePages(pages=pages, report=report)


def package_reference(
    package: Package, root: Path
) -> PythonPackageReference | NpmPackageReference | CssPackageReference:
    """The reference of a hand-written package, by what kind of package it is."""
    if package.kind == "python":
        return PythonPackageReference(package)
    if package.site == "ui-css":
        return CssPackageReference(package, root)
    return NpmPackageReference(package, root)


__all__ = [
    "AnchorLinker",
    "CssPackageReference",
    "NpmPackageReference",
    "PythonPackageReference",
    "package_reference",
]

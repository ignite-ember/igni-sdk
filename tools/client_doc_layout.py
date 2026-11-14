"""Where each of igni-client's methods is in its reference on the site.

Every method is on one reference page (``REFERENCE_PAGES`` in
``tools/client_names.py``), under a heading of its path; the models, events,
errors and access pages are shared by every method.
"""

from __future__ import annotations

from collections.abc import Sequence

from tools.client_names import MESSAGE_METHODS, REFERENCE_PAGES
from tools.client_plan import Placement, Plan
from tools.markdown_pages import site_id
from tools.site_page import DocsError, url

#: The package the reference is of, as the site routes it.
CLIENT_PACKAGE = "igni-client"

#: The pages every method's page links to.
ACCESS_PAGE = "access"
MODELS_PAGE = "models-reference"
EVENTS_PAGE = "events-reference"
ERRORS_PAGE = "errors-reference"

#: One reference page: its slug, its title, and the paths and groups it takes.
ReferencePageSpec = tuple[str, str, tuple[str, ...]]


class ClientLayout:
    """Every method's placement, and the reference page each one is on."""

    def __init__(self, plan: Plan, pages: Sequence[ReferencePageSpec] | None = None) -> None:
        self.plan = plan
        #: The reference pages; ``REFERENCE_PAGES`` unless a caller gives others.
        self.pages: Sequence[ReferencePageSpec] = REFERENCE_PAGES if pages is None else pages
        self.placements = self._placements()
        self.page_of = self._page_of()
        #: Def name → the wire type of the message it is.
        self.messages = plan.message_of_def()

    def _placements(self) -> dict[str, Placement]:
        out = dict(self.plan.placements)
        for wire, (_, path) in MESSAGE_METHODS.items():
            out[wire] = Placement.of(wire, path)
        return out

    def _page_of(self) -> dict[str, str]:
        """Wire name → the slug of the page it is on.

        A page takes a method named by its path (``session.run_shell``), and every
        method of a namespace it names (``igni.processes``) that no page names."""
        paths = {p.path for p in self.placements.values()}
        groups = {p.group for p in self.placements.values()}
        named = {s for _, _, sources in self.pages for s in sources if s in paths}
        taken: dict[str, list[str]] = {}
        for slug, _, sources in self.pages:
            unknown = [s for s in sources if s not in paths and s not in groups]
            if unknown:
                raise DocsError(f"REFERENCE_PAGES' {slug} names what igni-client lacks: {unknown}")
            for wire, placement in self.placements.items():
                if placement.path in sources or (
                    placement.group in sources and placement.path not in named
                ):
                    taken.setdefault(wire, []).append(slug)
        unplaced = sorted(set(self.placements) - set(taken))
        if unplaced:
            raise DocsError(
                "methods no page in REFERENCE_PAGES (tools/client_names.py) takes: "
                + ", ".join(self.placements[w].path for w in unplaced)
            )
        twice = {w: s for w, s in taken.items() if len(s) > 1}
        if twice:
            raise DocsError(f"methods on two reference pages: {twice}")
        return {wire: slugs[0] for wire, slugs in taken.items()}

    def on_page(self, slug: str) -> list[str]:
        """The wire names on page ``slug``, in the order the page names their sources."""
        sources = next(s for page, _, s in self.pages if page == slug)
        wires = [w for w, s in self.page_of.items() if s == slug]
        return sorted(wires, key=lambda w: (self._rank(sources, w), self.placements[w].path))

    def _rank(self, sources: tuple[str, ...], wire: str) -> int:
        placement = self.placements[wire]
        for index, source in enumerate(sources):
            if source in (placement.path, placement.group):
                return index
        return len(sources)

    @staticmethod
    def heading(placement: Placement) -> str:
        return f"{placement.path}()"

    def method_url(self, wire: str) -> str:
        placement = self.placements[wire]
        return url(CLIENT_PACKAGE, self.page_of[wire], site_id(self.heading(placement)))

    def method_link(self, wire: str) -> str:
        return f"[`{self.placements[wire].path}()`]({self.method_url(wire)})"


__all__ = [
    "ACCESS_PAGE",
    "CLIENT_PACKAGE",
    "ERRORS_PAGE",
    "EVENTS_PAGE",
    "MODELS_PAGE",
    "ClientLayout",
    "ReferencePageSpec",
]

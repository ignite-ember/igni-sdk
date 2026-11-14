"""igni-client's README on the site: its generated API reference becomes links to the
reference pages, and a link into that reference follows its heading to the page."""

from __future__ import annotations

import re

from tools.client_doc_layout import (
    ACCESS_PAGE,
    CLIENT_PACKAGE,
    ERRORS_PAGE,
    EVENTS_PAGE,
    MODELS_PAGE,
    ClientLayout,
)
from tools.client_reference import README_END, README_START
from tools.markdown_pages import fenced, github_anchor, plain
from tools.reference_area import Anchor
from tools.site_page import DocsError, url

_HEADING = re.compile(r"(#{1,6})\s+(.+?)\s*$")


class ClientReadmeSite:
    """igni-client's README text, as the site shows it."""

    def __init__(self, layout: ClientLayout, text: str, path: str) -> None:
        self.layout = layout
        self.text = text
        self.path = path

    def spliced(self) -> str:
        """The README with its generated reference replaced by links to the reference pages."""
        start, end = self.text.find(README_START), self.text.find(README_END)
        if start < 0 or end < start:
            raise DocsError(f"{self.path} has no generated API reference")
        return self.text[:start] + self.replacement() + self.text[end + len(README_END) :]

    def replacement(self) -> str:
        """What the site shows in place of the README's generated reference: links to the
        reference pages."""
        out = ["", "| Page | Namespaces and methods |", "|---|---|"]
        for slug, title, sources in self.layout.pages:
            out.append(
                f"| [{title}]({url(CLIENT_PACKAGE, slug)}) | "
                + ", ".join(f"`{s}`" for s in sources)
                + " |"
            )
        out += [
            "",
            f"[Who may call what]({url(CLIENT_PACKAGE, ACCESS_PAGE)}) · "
            f"[Models]({url(CLIENT_PACKAGE, MODELS_PAGE)}) · "
            f"[Events]({url(CLIENT_PACKAGE, EVENTS_PAGE)}) · "
            f"[Errors]({url(CLIENT_PACKAGE, ERRORS_PAGE)})",
            "",
        ]
        return "\n".join(out)

    def anchors(self) -> dict[str, Anchor]:
        """The README's anchors for headings in its generated reference → their page."""
        group_page: dict[str, str] = {}
        for wire, slug in self.layout.page_of.items():
            group_page.setdefault(self.layout.placements[wire].group, slug)
        out: dict[str, Anchor] = {}
        in_region = False
        seen: dict[str, int] = {}
        for line, code in fenced(self.text.split("\n")):
            if README_START in line:
                in_region = True
            if README_END in line:
                in_region = False
            match = None if code else _HEADING.match(line)
            if not match:
                continue
            base = github_anchor(match.group(2))
            count = seen.get(base, 0)
            seen[base] = count + 1
            if not in_region:
                continue
            anchor = base if count == 0 else f"{base}-{count}"
            target = self._target(plain(match.group(2)), group_page)
            if target is not None:
                out[anchor] = target
        return out

    @staticmethod
    def _target(text: str, group_page: dict[str, str]) -> Anchor | None:
        if text in group_page:
            return Anchor(slug=group_page[text], anchor="")
        if text == "Who may call what":
            return Anchor(slug=ACCESS_PAGE, anchor="")
        if text == "Not for clients":
            return Anchor(slug=ACCESS_PAGE, anchor="not-for-clients")
        return None


__all__ = ["ClientReadmeSite"]

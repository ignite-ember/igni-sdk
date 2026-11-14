"""One package README, cut into the site's guide pages at its top-level sections.

An overview (what comes before the first ``##``), then ``Installing``,
``Quick start``, ``Concepts``, ``Guides`` and the rest, each a page; a link to a
heading follows the heading to the page it is on (``tools/markdown_pages.py``
cuts the README and rewrites the links).
"""

from __future__ import annotations

from functools import partial

from tools.markdown_pages import (
    PageError,
    ReadmePages,
    first_sentences,
    lift,
    plain,
    rewrite_links,
    site_id,
    tidy,
)
from tools.reference_area import Anchor
from tools.site_packages import Package
from tools.site_page import BASE, GUIDE, SITE, Page, url

#: Sections of a README that are not pages: its table of contents, which the
#: site's sidebar replaces.
SKIPPED_SECTIONS = frozenset({"Contents"})


class ReadmeSite:
    """One package README, as the site's guide pages."""

    def __init__(
        self,
        package: Package,
        text: str,
        *,
        description: str,
        extra_anchors: dict[str, Anchor] | None = None,
    ) -> None:
        self.package = package
        self.description = description
        self.readme = ReadmePages(text, f"{package.path}/README.md")
        #: GitHub anchors of headings the site moves elsewhere → where they are now.
        self.extra = extra_anchors or {}
        self.slugs: dict[str | None, str] = {None: "overview"}
        for section in self.readme.sections:
            if section.title in SKIPPED_SECTIONS:
                continue
            self.slugs[section.title] = site_id(section.title)

    def resolve(self, current: str, anchor: str) -> str:
        """Where the README's ``#anchor`` is on the site, from page ``current``."""
        anchors = self.readme.anchors()
        if anchor in self.extra:
            slug, target = self.extra[anchor].slug, self.extra[anchor].anchor
        elif anchor in anchors:
            section, target = anchors[anchor]
            if section not in self.slugs:
                raise PageError(
                    f"{self.readme.path} links to #{anchor}, in a section that is not a page"
                )
            slug = self.slugs[section]
        else:
            raise PageError(f"{self.readme.path} links to #{anchor}, which it has no heading for")
        if slug == current:
            return f"#{target}" if target else "#"
        return url(self.package.site, slug, target)

    def pages(self, start: int = 0) -> list[Page]:
        name = self.package.site
        pages: list[Page] = []
        intro = [
            line
            for line in self.readme.intro
            if f"{SITE}{BASE}/{name}" not in line  # the README's link to these pages
        ]
        pages.append(
            Page(
                name,
                "overview",
                "Overview",
                self.description,
                GUIDE,
                start,
                tidy(rewrite_links(intro, lambda a: self.resolve("overview", a), self.readme.path)),
                source=f"{self.readme.path} (before its first section)",
            )
        )
        order = start
        for section in self.readme.sections:
            if section.title in SKIPPED_SECTIONS:
                continue
            order += 1
            slug = self.slugs[section.title]
            body = rewrite_links(lift(section.lines), partial(self.resolve, slug), self.readme.path)
            pages.append(
                Page(
                    name,
                    slug,
                    plain(section.title),
                    first_sentences("\n".join(section.lines)),
                    GUIDE,
                    order,
                    tidy(body),
                    source=f"{self.readme.path}, “{plain(section.title)}”",
                )
            )
        return pages


__all__ = ["SKIPPED_SECTIONS", "ReadmeSite"]

"""Cutting a package README into pages for the site, and the Markdown helpers that needs.

A README is one long page on PyPI. On the site (``tools/sdk_docs.py``) each of
its top-level sections (``## Installing``, ``## Concepts``…) is a page of its
own, its headings lifted a level so the section's ``###`` are the page's
``##`` — what the site's table of contents lists. What comes before the first
section is the package's overview. Nothing is copied by hand: the README is
the one source, and the pages are regenerated from it.

A link inside the README (``[Call](#call)``) names a heading by GitHub's
anchor for it; on the site that heading is on some page, under the id the
site gives it. Every such link is rewritten to that page and id, and a link
to a heading the README does not have is an error, not a dead link.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

#: Where the repository's files are, for a README's relative links: on the
#: site they become links to the repository.
REPO_BLOB = "https://github.com/ignite-ember/igni-sdk/blob/main"


class PageError(ValueError):
    """A README cannot be cut into pages as it is."""


def fenced(lines: list[str]) -> Iterator[tuple[str, bool]]:
    """Each line, and whether it is inside (or opens or closes) a fenced code block."""
    fence = ""
    for line in lines:
        stripped = line.lstrip()
        if fence:
            yield line, True
            if stripped.startswith(fence) and not stripped[len(fence) :].strip():
                fence = ""
            continue
        match = re.match(r"(`{3,}|~{3,})", stripped)
        if match:
            fence = match.group(1)
            yield line, True
            continue
        yield line, False


def plain(text: str) -> str:
    """A heading's or a sentence's text without Markdown: what a reader sees."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Underscores stay: inside a word (`check_for_update`) they are not emphasis.
    return text.replace("`", "").replace("**", "").strip()


def site_id(text: str) -> str:
    """The id the site gives a heading (``headingId`` in its docs manifest)."""
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", plain(text).lower()))


def github_anchor(text: str) -> str:
    """GitHub's (and PyPI's) anchor for a heading, before duplicates are numbered."""
    slug = text.strip().lower()
    slug = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", slug)
    slug = re.sub(r"[^\w\- ]", "", slug)
    return slug.replace(" ", "-")


def strip_comments(text: str) -> str:
    """``text`` without HTML comments outside code: the site does not render HTML."""
    out: list[str] = []
    lines = text.split("\n")
    in_comment = False
    for line, code in fenced(lines):
        if code and not in_comment:
            out.append(line)
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
                rest = line.split("-->", 1)[1]
                if rest.strip():
                    out.append(rest)
            continue
        line = re.sub(r"<!--.*?-->", "", line)
        if "<!--" in line:
            in_comment = True
            line = line.split("<!--", 1)[0]
            if line.strip():
                out.append(line)
            continue
        out.append(line)
    return "\n".join(out)


def first_sentences(markdown: str, limit: int = 220) -> str:
    """The first paragraph of prose in ``markdown``, as plain text, cut at a sentence."""
    paragraph: list[str] = []
    for line, code in fenced(markdown.split("\n")):
        stripped = line.strip()
        if code or stripped.startswith(("#", "|", "<", "-", "*", ">", "1.")) and not paragraph:
            if paragraph:
                break
            continue
        if not stripped:
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    text = plain(" ".join(paragraph))
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return cut[: end + 1] if end > 60 else cut.rsplit(" ", 1)[0] + "…"


@dataclass
class Section:
    """One top-level section of a README."""

    title: str
    lines: list[str]


@dataclass
class Heading:
    level: int
    text: str
    #: Which section it is in: ``None`` for the overview.
    section: str | None


@dataclass
class ReadmePages:
    """A README, cut at its ``##`` headings."""

    text: str
    #: Where the README is in the repository (``packages/igni-client/README.md``).
    path: str
    title: str = ""
    intro: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    headings: list[Heading] = field(default_factory=list)

    def __post_init__(self) -> None:
        current: Section | None = None
        for line, code in fenced(strip_comments(self.text).split("\n")):
            match = None if code else re.match(r"(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if match and len(match.group(1)) == 1 and not self.title:
                self.title = match.group(2)
                self.headings.append(Heading(1, match.group(2), None))
                continue
            if match and len(match.group(1)) == 2:
                current = Section(match.group(2), [])
                self.sections.append(current)
                self.headings.append(Heading(2, current.title, current.title))
                continue
            if match:
                self.headings.append(
                    Heading(len(match.group(1)), match.group(2), current.title if current else None)
                )
            (current.lines if current else self.intro).append(line)
        if not self.title:
            raise PageError(f"{self.path} has no `# title`")

    def anchors(self) -> dict[str, tuple[str | None, str]]:
        """GitHub's anchor for every heading → (its section, its id on the site; empty for
        the section itself)."""
        seen: dict[str, int] = {}
        out: dict[str, tuple[str | None, str]] = {}
        for heading in self.headings:
            base = github_anchor(heading.text)
            count = seen.get(base, 0)
            seen[base] = count + 1
            anchor = base if count == 0 else f"{base}-{count}"
            target = "" if heading.level <= 2 else site_id(heading.text)
            out[anchor] = (heading.section, target)
        return out


def lift(lines: list[str], by: int = 1) -> list[str]:
    """Headings ``by`` levels higher, outside code: a section's ``###`` become ``##``."""
    out: list[str] = []
    for line, code in fenced(lines):
        match = None if code else re.match(r"(#{2,6})(\s+.*)$", line)
        out.append(f"{match.group(1)[by:]}{match.group(2)}" if match else line)
    return out


def rewrite_links(
    lines: list[str],
    anchor: Callable[[str], str],
    readme_path: str,
) -> list[str]:
    """In-README links (``(#x)``) through ``anchor``, relative ones to the repository."""
    base = posixpath.dirname(readme_path)

    def relative(match: re.Match[str]) -> str:
        target = match.group(2)
        if re.match(r"^[a-z][a-z0-9+.-]*:|^/|^#", target):
            return match.group(0)
        path, _, hash_ = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(base, path))
        return f"{match.group(1)}({REPO_BLOB}/{resolved}{'#' + hash_ if hash_ else ''})"

    out: list[str] = []
    for line, code in fenced(lines):
        if code:
            out.append(line)
            continue
        line = re.sub(r"\]\(#([^)\s]+)\)", lambda m: f"]({anchor(m.group(1))})", line)
        line = re.sub(r"(\])\(([^)\s]+)\)", relative, line)
        out.append(line)
    return out


#: Black's line length: a signature longer than this gets one parameter a line.
SIGNATURE_WIDTH = 88


def split_params(params: str) -> list[str]:
    """``a: int, b: dict[str, int] = {}`` → its parameters, at top-level commas only."""
    out: list[str] = []
    depth = 0
    quote = ""
    current = ""
    escaped = False
    for char in params:
        if quote:
            current += char
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            out.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        out.append(current.strip())
    return out


def signature(head: str, params: str, tail: str = "", width: int = SIGNATURE_WIDTH) -> str:
    """``head(params)tail`` on one line when it fits in ``width``, else as black
    writes it: one parameter a line, each with a trailing comma."""
    one_line = f"{head}({params}){tail}"
    parts = split_params(params)
    if len(one_line) <= width or not parts:
        return one_line
    body = "".join(f"    {part},\n" for part in parts)
    return f"{head}(\n{body}){tail}"


def tidy(lines: list[str]) -> str:
    """Lines as a page body: no runs of blank lines, no blank start or end."""
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"


__all__ = [
    "REPO_BLOB",
    "Heading",
    "PageError",
    "ReadmePages",
    "Section",
    "fenced",
    "first_sentences",
    "github_anchor",
    "lift",
    "plain",
    "rewrite_links",
    "signature",
    "split_params",
    "site_id",
    "strip_comments",
    "tidy",
]

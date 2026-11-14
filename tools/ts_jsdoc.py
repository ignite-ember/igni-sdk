"""JSDoc comments as the reference pages show them.

A declaration's JSDoc is the words of its page: its first paragraph is
what a table cell says, the whole of it (less its ``@param`` tags, which
the parameter table shows) is what follows the signature.
"""

from __future__ import annotations

import re

#: The longest summary a table cell shows before it is cut at a sentence.
_SUMMARY_LIMIT = 200


def markdown(text: str) -> str:
    """JSDoc text whose ``*`` margin is already gone, as Markdown."""
    text = re.sub(r"\{@link\s+([^}]+)\}", r"`\1`", text)
    return text.strip()


def jsdoc_markdown(doc: str) -> str:
    """A JSDoc comment as Markdown: the ``*`` of every line gone, the
    tags that are prose kept, the rest dropped."""
    if not doc:
        return ""
    body = doc.strip()
    if body.startswith("/**"):
        body = body[3:]
    if body.endswith("*/"):
        body = body[:-2]
    lines = [re.sub(r"^\s*\* ?", "", line).rstrip() for line in body.split("\n")]
    return markdown("\n".join(lines).strip("\n"))


def is_internal(doc: str) -> bool:
    """Whether a JSDoc marks its name ``@internal``: not part of the documented surface."""
    return "@internal" in doc


def summary(doc: str) -> str:
    """A JSDoc's first paragraph, as one line: what a table cell shows."""
    lines: list[str] = []
    for line in jsdoc_markdown(doc).split("\n"):
        stripped = line.strip()
        if stripped.startswith(("@", "```", "---", "|")):
            break
        if not stripped:
            if lines:
                break
            continue
        lines.append(stripped)
    out = re.sub(r"\s+", " ", " ".join(lines)).strip()
    if len(out) <= _SUMMARY_LIMIT:
        return out
    cut = out[:_SUMMARY_LIMIT]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return cut[: end + 1] if end > 40 else cut.rsplit(" ", 1)[0] + "…"


def doc_before(text: str, index: int) -> str:
    """The JSDoc block that ends just before ``index``, if there is one."""
    head = text[:index].rstrip()
    if not head.endswith("*/"):
        return ""
    start = head.rfind("/**")
    if start < 0:
        return ""
    between = head[start + 3 : -2].strip()
    if not between.startswith("*") and "\n" not in between:
        # A one-line comment: `/** … */`
        return f"/** {between} */"
    return head[start:]


__all__ = ["doc_before", "is_internal", "jsdoc_markdown", "markdown", "summary"]

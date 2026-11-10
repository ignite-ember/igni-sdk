'''What a parameter is, read from the docstring that documents it.

igni's house style is Google-style: a docstring says what a method
does, and an ``Args:`` section says what each of its parameters is —

    """What ``seal`` sealed.

    Args:
        sealed: The sealed text, as ``seal`` produced it.
    """

The TypeScript packages say the same thing in JSDoc, one ``@param`` a
line, the name and then what it is —

    /**
     * What ``seal`` sealed.
     *
     * @param sealed — the sealed text, as ``seal`` produced it.
     */

This module reads both, and writes the table the reference pages show
under a signature: the parameter's name, its type, its default and
what it means.

A parameter no docstring documents is said to be undocumented. The
generator never guesses what a parameter is: a page that says "not
documented yet" is a page that tells the reader, and a page that
guessed would be a page that lied.
'''

from __future__ import annotations

import re

#: What the table says of a parameter no docstring documents.
UNDOCUMENTED = "Not documented yet."


def cell(text: str) -> str:
    """``text`` fit for one cell of a Markdown table."""
    return " ".join(text.split()).replace("|", "\\|")


def code(text: str) -> str:
    """``text`` as code in a table cell: backticked, and its pipes escaped.

    A pipe inside code still ends a cell in Markdown, so a union type
    is written `` `str \\| None` ``.
    """
    return f"`{text.replace('|', chr(92) + '|')}`"


def table(rows: list[tuple[str, str, str, str]]) -> list[str]:
    """The table of a method's parameters, as the reference pages show it.

    Each row is the parameter's name, its type, its default and what it
    means. A method with no parameters has no table at all.
    """
    if not rows:
        return []
    out = ["| Parameter | Type | Default | Meaning |", "|---|---|---|---|"]
    for name, type_, default, meaning in rows:
        out.append(f"| `{name}` | {type_} | {default} | {cell(meaning)} |")
    out.append("")
    return out


# ── Python ────────────────────────────────────────────────────────

#: A parameter's line in an ``Args:`` section: its name, and what it is.
_ARG_LINE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:\s*(?P<text>.*)$")


def _indent(line: str) -> int:
    """How far a line is indented."""
    return len(line) - len(line.lstrip())


def python_args(doc: str) -> dict[str, str]:
    """What each parameter is, from a docstring's ``Args:`` section.

    The section is the one headed ``Args:``: one indented line a
    parameter — its name, a colon, and what it is. A meaning may run
    over as many lines as it needs; the lines under it are its own.
    """
    out: dict[str, str] = {}
    lines = doc.split("\n")
    index = 0
    while index < len(lines):
        if lines[index].strip() != "Args:":
            index += 1
            continue
        base = _indent(lines[index])
        index += 1
        block: list[tuple[int, str]] = []
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                block.append((0, ""))
                index += 1
                continue
            if _indent(line) <= base:
                break
            block.append((_indent(line), line.strip()))
            index += 1
        out.update(_python_block(block))
    return out


def _python_block(block: list[tuple[int, str]]) -> dict[str, str]:
    """The parameters of one ``Args:`` section, from its lines."""
    depths = [indent for indent, text in block if text]
    if not depths:
        return {}
    least = min(depths)
    texts: dict[str, list[str]] = {}
    order: list[str] = []
    name = ""
    for indent, text in block:
        if not text:
            continue
        if indent == least:
            match = _ARG_LINE.match(text)
            if match is None:
                name = ""
                continue
            name = match.group("name")
            if name not in texts:
                texts[name] = []
                order.append(name)
            texts[name].append(match.group("text"))
            continue
        if name:
            texts[name].append(text)
    return {key: " ".join(part for part in texts[key] if part).strip() for key in order}


def strip_python_args(doc: str) -> str:
    """The docstring without its ``Args:`` section.

    The section says what the parameters are, and the reference page
    shows that in the table under the signature. Saying it twice would
    be saying it twice.
    """
    lines = doc.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != "Args:":
            out.append(lines[index])
            index += 1
            continue
        base = _indent(lines[index])
        index += 1
        while index < len(lines):
            line = lines[index]
            if line.strip() and _indent(line) <= base:
                break
            index += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


# ── TypeScript ────────────────────────────────────────────────────

#: A ``@param`` line in a JSDoc: the name, and what it is.
_JSDOC_PARAM = re.compile(
    r"^@param\s+(?:\{[^}]*\}\s*)?(?P<name>[A-Za-z_$][\w$]*)\s*(?:[—–-]\s*)?(?P<text>.*)$"
)


def jsdoc_lines(doc: str) -> list[str]:
    """A JSDoc comment's lines, without its ``/**``, ``*/`` and ``*``."""
    body = doc.strip()
    if body.startswith("/**"):
        body = body[3:]
    elif body.startswith("/*"):
        body = body[2:]
    if body.endswith("*/"):
        body = body[:-2]
    return [re.sub(r"^\s*\*\s?", "", line) for line in body.split("\n")]


def jsdoc_params(doc: str) -> dict[str, str]:
    """What each parameter is, from a JSDoc's ``@param`` lines.

    A ``@param`` line is the name, then what it is. The lines under it
    are its own, until a blank line or the next tag.
    """
    texts: dict[str, list[str]] = {}
    order: list[str] = []
    name = ""
    for line in jsdoc_lines(doc):
        stripped = line.strip()
        match = _JSDOC_PARAM.match(stripped)
        if match:
            name = match.group("name")
            if name not in texts:
                texts[name] = []
                order.append(name)
            texts[name].append(match.group("text"))
            continue
        if not stripped or stripped.startswith("@"):
            name = ""
            continue
        if name:
            texts[name].append(stripped)
    return {key: " ".join(part for part in texts[key] if part).strip() for key in order}


def strip_jsdoc_params(doc: str) -> str:
    """The JSDoc without its ``@param`` lines.

    The lines say what the parameters are, and the reference page shows
    that in the table under the signature. Saying it twice would be
    saying it twice.
    """
    out: list[str] = []
    skipping = False
    for line in jsdoc_lines(doc):
        stripped = line.strip()
        if _JSDOC_PARAM.match(stripped):
            skipping = True
            continue
        if skipping and stripped and not stripped.startswith("@"):
            # The rest of the parameter's meaning: the table says it.
            continue
        skipping = False
        out.append(line)
    return "\n".join(out).strip()


__all__ = [
    "UNDOCUMENTED",
    "cell",
    "code",
    "jsdoc_params",
    "python_args",
    "strip_jsdoc_params",
    "strip_python_args",
    "table",
]

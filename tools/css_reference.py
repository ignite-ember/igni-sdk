"""The stylesheet's own reference: its tokens and its classes.

``@ignite-ember/ui-css`` ships one file of CSS and nothing else — no
types, no functions, no runtime — so its reference is a reading of
that file: the custom properties it defines (the tokens, and the
fallback each carries) and the classes it styles (what each one
sets), grouped by the stylesheet's own sections.

The file is the source of truth and is read as it is written: the
comments above a rule are its documentation, and are carried over as
such. The comment above a custom property says what that property is
for, and the table of tokens says it too. Nothing is added that the
CSS does not say.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from tools.param_docs import UNDOCUMENTED, cell

#: A section marker: the dashes a section's title is written between.
_SECTION = re.compile(r"──\s*(.+?)\s*──")

#: A custom property: ``--name: value;``.
_TOKEN = re.compile(r"^(--[A-Za-z0-9_-]+)\s*:\s*(.+)$")

#: A class in a selector: ``.name``.
_CLASS = re.compile(r"\.(-?[A-Za-z_][\w-]*)")

#: The at-rules whose body holds rules of their own.
_AT_RULES = ("@media", "@supports", "@layer", "@container", "@keyframes")


class CssError(ValueError):
    """The stylesheet cannot be read as it is."""


@dataclass(frozen=True)
class Rule:
    """One rule: its selector, what it sets, and what the CSS says of it."""

    selector: str
    declarations: tuple[tuple[str, str], ...]
    note: str = ""

    @property
    def classes(self) -> tuple[str, ...]:
        """The classes it selects, in the order they appear."""
        out: list[str] = []
        for name in _CLASS.findall(self.selector):
            if name not in out:
                out.append(name)
        return tuple(out)

    @property
    def properties(self) -> tuple[str, ...]:
        """The properties it sets."""
        return tuple(name for name, _ in self.declarations)


@dataclass
class Section:
    """One section of the stylesheet: a title, what it says, and its rules."""

    title: str
    note: str = ""
    rules: list[Rule] = field(default_factory=list)
    #: The custom properties it defines: their name, their value, and
    #: what the comment above each of them says.
    tokens: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class Token:
    """One custom property: its name, its fallback, and what the CSS says of it."""

    name: str
    value: str
    note: str = ""
    #: What the comment above the property says it is for.
    meaning: str = ""


def _match_brace(text: str, start: int) -> int:
    """The index of the ``}`` that closes the ``{`` at ``start``.

    A comment is skipped whole. An apostrophe in a comment is not the
    start of a string, and a string is not a comment: a reader that
    cannot tell them apart reads neither.
    """
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
            continue
        if char in "'\"":
            quote = char
            index += 1
            while index < len(text) and text[index] != quote:
                index += 2 if text[index] == "\\" else 1
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise CssError("a rule is never closed")


def _pieces(body: str) -> list[tuple[str, list[str]]]:
    """A block cut into declarations, each with the comments above it.

    A ``;`` inside a string or inside parentheses (``url(data:...;base64,...)``)
    is part of the value, not the end of the declaration. A comment is not
    a declaration; it belongs to the declaration under it.
    """
    out: list[tuple[str, list[str]]] = []
    comments: list[str] = []
    text: list[str] = []
    depth = 0
    index = 0
    while index < len(body):
        if body.startswith("/*", index):
            end = body.find("*/", index + 2)
            stop = len(body) if end < 0 else end
            comment = body[index + 2 : stop].strip()
            index = stop + 2
            if comment:
                comments.append(_prose(comment, None))
            text.append(" ")
            continue
        char = body[index]
        if char in "'\"":
            stop = index + 1
            while stop < len(body) and body[stop] != char:
                stop += 2 if body[stop] == "\\" else 1
            text.append(body[index : stop + 1])
            index = stop + 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        elif char == ";" and depth == 0:
            out.append(("".join(text), comments))
            comments = []
            text = []
            index += 1
            continue
        text.append(char)
        index += 1
    out.append(("".join(text), comments))
    return out


def _declarations(body: str) -> list[tuple[str, str]]:
    """The declarations of a block: ``property: value`` a piece."""
    out: list[tuple[str, str]] = []
    for part, _comments in _pieces(body):
        declaration = _one_declaration(part)
        if declaration is not None:
            out.append(declaration)
    return out


def _split_selector(prelude: str) -> list[str]:
    """A rule's selector, one a piece: ``a, b`` is two selectors."""
    out = []
    for part in prelude.split(","):
        text = " ".join(part.split())
        if text:
            out.append(text)
    return out


def _token_declarations(body: str) -> list[tuple[str, str, str]]:
    """The custom properties of a block, and what each of them is for.

    A comment above a property says what that property is for; the
    comment belongs to the property under it, not to the block.
    """
    out: list[tuple[str, str, str]] = []
    pending: list[str] = []
    for part, comments in _pieces(body):
        pending += comments
        declaration = _one_declaration(part)
        if declaration is None:
            continue
        name, value = declaration
        out.append((name, value, " ".join(pending).strip()))
        pending = []
    return out


def _one_declaration(text: str) -> tuple[str, str] | None:
    """One ``property: value`` declaration, or ``None`` when there is none."""
    text = text.strip()
    if not text or ":" not in text:
        return None
    name, _, value = text.partition(":")
    return name.strip(), value.strip()


class Stylesheet:
    """One stylesheet, read into its sections, its rules and its tokens."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.header = ""
        self.sections: list[Section] = []
        self._parse()

    def _parse(self) -> None:
        text = self.text
        index = 0
        current: Section | None = None
        pending: list[str] = []
        prelude: list[str] = []
        while index < len(text):
            if text.startswith("/*", index):
                end = text.find("*/", index)
                if end < 0:
                    raise CssError("a comment is never closed")
                comment = text[index + 2 : end].strip()
                index = end + 2
                marker = _SECTION.search(comment)
                if marker:
                    current = Section(title=marker.group(1), note=_prose(comment, marker))
                    self.sections.append(current)
                    pending = []
                elif comment:
                    pending.append(_prose(comment, None))
                continue
            char = text[index]
            if char in "'\"":
                # A string: it runs to the quote that closes it, and every
                # character in it is part of the selector.
                quote = char
                prelude.append(char)
                index += 1
                while index < len(text) and text[index] != quote:
                    prelude.append(text[index])
                    index += 1
                if index >= len(text):
                    raise CssError("a string is never closed")
                prelude.append(text[index])
                index += 1
                continue
            if char == "{":
                end = _match_brace(text, index)
                body = text[index + 1 : end]
                selector = " ".join("".join(prelude).split())
                prelude = []
                index = end + 1
                self._block(selector, body, current, pending, top=current is None)
                pending = []
                continue
            if char in ";}":
                prelude = []
                index += 1
                continue
            prelude.append(char)
            index += 1
        if not self.sections and self.header:
            self.sections.append(Section(title="The stylesheet", note=self.header))

    def _block(
        self,
        selector: str,
        body: str,
        current: Section | None,
        pending: list[str],
        *,
        top: bool,
    ) -> None:
        """What a block holds: a rule, an at-rule, or the tokens."""
        note = " ".join(pending).strip()
        if selector.startswith("@"):
            name = selector.split()[0].lower()
            if name in _AT_RULES:
                # The rules inside belong to the section they are in.
                self._rules_in(body, current, note, selector)
                return
            return
        declarations = _declarations(body)
        if not declarations:
            return
        if current is None:
            if top and note and not self.header:
                self.header = note
            return
        if all(name.startswith("--") for name, _ in declarations):
            current.tokens.extend(_token_declarations(body))
            return
        for one in _split_selector(selector):
            current.rules.append(Rule(one, tuple(declarations), note))

    def _rules_in(
        self,
        body: str,
        current: Section | None,
        note: str,
        at_rule: str = "",
    ) -> None:
        """The rules inside an at-rule's block."""
        index = 0
        prelude: list[str] = []
        while index < len(body):
            char = body[index]
            if body.startswith("/*", index):
                end = body.find("*/", index)
                if end < 0:
                    raise CssError("a comment is never closed")
                index = end + 2
                continue
            if char in "'\"":
                quote = char
                prelude.append(char)
                index += 1
                while index < len(body) and body[index] != quote:
                    prelude.append(body[index])
                    index += 1
                if index >= len(body):
                    raise CssError("a string is never closed")
                prelude.append(body[index])
                index += 1
                continue
            if char == "{":
                end = _match_brace(body, index)
                selector = " ".join("".join(prelude).split())
                prelude = []
                inner = body[index + 1 : end]
                index = end + 1
                if selector.startswith("@"):
                    self._rules_in(inner, current, note, selector)
                    continue
                declarations = _declarations(inner)
                if not declarations or current is None:
                    continue
                for one in _split_selector(selector):
                    current.rules.append(Rule(one, tuple(declarations), _at_note(note, at_rule)))
                continue
            if char in ";}":
                prelude = []
                index += 1
                continue
            prelude.append(char)
            index += 1

    # ── What the stylesheet holds ──

    def tokens(self) -> list[Token]:
        """Every custom property it defines, in the order it defines them."""
        out: list[Token] = []
        seen: set[str] = set()
        for section in self.sections:
            for name, value, meaning in section.tokens:
                if name in seen:
                    continue
                seen.add(name)
                out.append(Token(name, value, section.note, meaning))
        return out

    def classes(self) -> list[tuple[Section, Rule]]:
        """Every rule that selects a class, with the section it is in."""
        out: list[tuple[Section, Rule]] = []
        seen: set[tuple[str, str]] = set()
        for section in self.sections:
            for rule in section.rules:
                if not rule.classes:
                    continue
                key = (rule.selector, ",".join(rule.properties))
                if key in seen:
                    continue
                seen.add(key)
                out.append((section, rule))
        return out

    def users_of(self, token: str) -> list[str]:
        """The classes whose rules use ``var(--token)``."""
        # ``var(--a`` is followed by ``)``, ``,`` or a space; ``var(--a-b)``
        # is another token's.
        needle = re.compile(rf"var\(\s*{re.escape(token)}(?![\w-])")
        out: list[str] = []
        for _section, rule in self.classes():
            if any(needle.search(value) for _name, value in rule.declarations):
                for name in rule.classes:
                    if name not in out:
                        out.append(name)
        return out


def _at_note(note: str, at_rule: str) -> str:
    """What a rule says of itself, and the at-rule it is under."""
    parts = [part for part in (note, at_rule) if part]
    return " ".join(parts)


def _prose(comment: str, marker: re.Match[str] | None) -> str:
    """A comment's prose: what it says, without the dashes of its title."""
    text = comment
    if marker is not None:
        text = text[marker.end() :]
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        if stripped.startswith("─"):
            continue
        if stripped:
            lines.append(stripped)
    return " ".join(lines)


class CssReference:
    """The reference pages of one stylesheet: its tokens and its classes."""

    def __init__(
        self,
        package: str,
        path: str,
        text: str,
        link: Callable[[str], str | None] | None = None,
    ) -> None:
        self.package = package
        self.path = path
        self.sheet = Stylesheet(text)
        self.link = link

    # ── The pages ──

    def tokens_page(self) -> tuple[str, int]:
        """The Markdown of the tokens page, and how many tokens it left out."""
        tokens = self.sheet.tokens()
        out: list[str] = []
        out += [
            "Every custom property the stylesheet defines, and the value it falls "
            "back to. The bridge overwrites these on `:root` when the extension "
            "connects, so inside igni the live values apply; the fallback is what "
            "you see on your own, and what applies before the bridge answers.",
            "",
            "| Token | Fallback | Used by | Meaning |",
            "|---|---|---|---|",
        ]
        for token in tokens:
            users = self.sheet.users_of(token.name)
            shown = ", ".join(f"`.{name}`" for name in users[:6])
            if len(users) > 6:
                shown += " …"
            # A token no class reads is still published — the bridge
            # writes it on `:root` — so it is worth saying so plainly
            # rather than leaving a dash.
            out.append(
                f"| `{token.name}` | `{token.value}` | {shown or 'nothing here'} "
                f"| {cell(token.meaning) or UNDOCUMENTED} |"
            )
        out.append("")
        for token in tokens:
            out += [f"## {token.name}", "", f"`{token.value}`", ""]
            if token.meaning:
                out += [token.meaning, ""]
            if token.note:
                out += [token.note, ""]
        return "\n".join(out), len(tokens)

    def classes_page(self) -> tuple[str, int]:
        """The Markdown of the classes page, and how many classes it left out."""
        out: list[str] = []
        out += [
            "Every class the stylesheet defines, in the sections the stylesheet "
            "itself uses. The class names match igni's own: a control here is the "
            "control there.",
            "",
        ]
        count = 0
        for section in self.sheet.sections:
            rules = [rule for rule in section.rules if rule.classes]
            if not rules:
                continue
            out += [f"## {section.title}", ""]
            if section.note:
                out += [section.note, ""]
            out += ["| Class | Selector | What it sets |", "|---|---|---|"]
            for rule in rules:
                count += len(rule.classes)
                properties = ", ".join(f"`{name}`" for name in rule.properties)
                out.append(f"| `.{rule.classes[0]}` | `{rule.selector}` | {properties} |")
            out.append("")
        return "\n".join(out), count


__all__ = ["CssError", "CssReference", "Rule", "Section", "Stylesheet", "Token"]

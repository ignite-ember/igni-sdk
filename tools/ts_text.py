"""TypeScript source as code: where its brackets close and its statements end.

A bracket inside a string, a template literal, a comment or a regular
expression literal is not a bracket. ``TsText`` walks a source once with
all four skipped, and every question the reader asks of a source — where
does this bracket close, where does this statement end, how deep is this
line — is answered from that one walk.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from tools.ts_model import ReferenceError_, TypeParameters

#: The characters a regular expression literal can follow: an expression
#: may start there, so a ``/`` after one opens a regex and not a division.
_REGEX_AFTER = frozenset("(,=:[!&|?{};+-*%~^<>")

#: The words a regular expression literal can follow, for the same reason.
_REGEX_AFTER_WORDS = frozenset(
    {
        "await",
        "case",
        "delete",
        "do",
        "else",
        "in",
        "instanceof",
        "new",
        "of",
        "return",
        "throw",
        "typeof",
        "void",
        "yield",
    }
)

_OPENERS = "([{"
_CLOSERS = ")]}"


class TsText:
    """One piece of TypeScript source, read as code."""

    def __init__(self, text: str) -> None:
        self.text = text

    # ── Comments and regular expressions ──

    def prev_significant_index(self, index: int) -> int:
        """The index of the last character before ``index`` that is not a space or a comment.

        -1 when there is none.
        """
        text = self.text
        position = index - 1
        while position >= 0:
            char = text[position]
            if char in " \t\n\r":
                position -= 1
                continue
            if char == "/" and position > 0 and text[position - 1] == "*":
                start = text.rfind("/*", 0, position)
                if start < 0:
                    return position
                position = start - 1
                continue
            if char == "/" and position > 0 and text[position - 1] == "/":
                position = text.rfind("\n", 0, position)
                continue
            return position
        return -1

    def is_regex_start(self, index: int) -> bool:
        """Whether the ``/`` at ``index`` opens a regular expression."""
        position = self.prev_significant_index(index)
        if position < 0:
            return True
        previous = self.text[position]
        if previous in _REGEX_AFTER:
            return True
        if not previous.isalpha():
            return False
        # The word may be a space or a comment away from the slash.
        word = re.search(r"[A-Za-z_$][\w$]*$", self.text[: position + 1])
        return word is not None and word.group(0) in _REGEX_AFTER_WORDS

    def regex_end(self, index: int) -> int:
        """The index just past the regular expression literal at ``index``."""
        text = self.text
        position = index + 1
        in_class = False
        while position < len(text):
            char = text[position]
            if char == "\\":
                position += 2
                continue
            if char == "[":
                in_class = True
            elif char == "]":
                in_class = False
            elif char == "/" and not in_class:
                return position + 1
            elif char == "\n":
                break
            position += 1
        return index + 1

    # ── The walk ──

    def code_indexes(self, start: int = 0) -> Iterator[int]:
        """The index of every character from ``start`` that is code.

        Strings, template literals, comments and regular expressions are
        stepped over whole; the newline that ends a line comment is code.
        """
        text = self.text
        index = start
        quote = ""
        while index < len(text):
            char = text[index]
            if quote:
                if char == "\\":
                    index += 2
                    continue
                if char == quote:
                    quote = ""
                index += 1
                continue
            if char in "'\"`":
                quote = char
                index += 1
                continue
            if text.startswith("//", index):
                end = text.find("\n", index)
                index = len(text) if end < 0 else end
                continue
            if text.startswith("/*", index):
                end = text.find("*/", index)
                index = len(text) if end < 0 else end + 2
                continue
            if char == "/" and self.is_regex_start(index):
                index = self.regex_end(index)
                continue
            yield index
            index += 1

    def match_bracket(self, start: int, open_char: str, close_char: str) -> int:
        """The index just past the bracket that closes the one at ``start``."""
        depth = 0
        for index in self.code_indexes(start):
            char = self.text[index]
            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    return index + 1
        raise ReferenceError_("an unclosed bracket")

    def statement_end(self, start: int, *, newline_ends: bool = True) -> int:
        """The index just past the ``;`` that ends a statement — or the newline.

        A type alias runs over as many lines as it needs — a union, one
        member a line — so for one, ``newline_ends`` is off and only the
        ``;`` ends it.
        """
        depth = 0
        for index in self.code_indexes(start):
            char = self.text[index]
            if char in _OPENERS:
                depth += 1
            elif char in _CLOSERS:
                depth -= 1
            elif char == ";" and depth == 0:
                return index + 1
            elif char == "\n" and depth == 0 and newline_ends:
                return index
        return len(self.text)

    def line_depths(self) -> list[int]:
        """The nesting depth at the start of every line.

        A member of an interface or a class is at the top level of its body:
        a parameter line is not, however much it looks like one.
        """
        line_starts = [0, *(match.end() for match in re.finditer("\n", self.text))]
        code = self.code_indexes()
        pending = next(code, None)
        depth = 0
        depths: list[int] = []
        for line_start in line_starts:
            while pending is not None and pending < line_start:
                char = self.text[pending]
                if char in _OPENERS:
                    depth += 1
                elif char in _CLOSERS:
                    depth -= 1
                pending = next(code, None)
            depths.append(depth)
        return depths

    # ── Small reads ──

    def skip_space(self, index: int) -> int:
        """The first index at or after ``index`` that is not white space."""
        text = self.text
        while index < len(text) and text[index] in " \t\n\r":
            index += 1
        return index

    def type_parameters(self, start: int) -> TypeParameters:
        """The ``<...>`` of type parameters at ``start``, and where it ends."""
        index = self.skip_space(start)
        if index >= len(self.text) or self.text[index] != "<":
            return TypeParameters(text="", end=start)
        end = self.match_bracket(index, "<", ">")
        return TypeParameters(text=self.text[index:end], end=end)


__all__ = ["TsText"]

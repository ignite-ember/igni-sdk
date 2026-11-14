"""Fragments of TypeScript: a type or a parameter list, as text to show or to split.

A signature on a reference page is the source's own text, put on one
line and with its comments gone. A parameter list is split at its
top-level commas, a parameter at its top-level ``=`` and ``:``. These
are stateless reads of a string; ``tools/ts_text.py`` is the walk over a
whole source.
"""

from __future__ import annotations

import re

from tools.ts_model import Partition

#: What a signature returns, written after its colon and before its body.
RETURN_TYPE = re.compile(r"\s*:\s*([^{;]+?)\s*(?=\{|;|\Z)", re.S)


def strip_comments(text: str) -> str:
    """A fragment without its comments — and with its strings intact."""
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in "'\"":
            end = skip_string(text, index)
            out.append(text[index:end])
            index = end
            continue
        if text.startswith("//", index):
            while index < length and text[index] != "\n":
                index += 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
            out.append(" ")
            continue
        out.append(char)
        index += 1
    return "".join(out)


def one_line(text: str) -> str:
    """A signature's text on one line, the way it is written in the source."""
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r",\s*\)", ")", text)
    text = re.sub(r",\s*,", ",", text)
    return text


def tight_generics(text: str) -> str:
    """A type's generic lists on one line, without the spaces a line break leaves.

    Only for types: a value's text is left alone, so a string that
    happens to hold a ``<`` keeps it.
    """
    text = one_line(text)
    text = re.sub(r"<\s+", "<", text)
    text = re.sub(r"\s+>", ">", text)
    return text


def parameter_list(params: str) -> str:
    """A parameter list as a signature shows it: one line, no comments, no trailing comma."""
    return re.sub(r",\s*$", "", one_line(strip_comments(params)))


def skip_string(text: str, index: int) -> int:
    """The index just past the string that starts at ``index``."""
    quote = text[index]
    index += 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return min(index, len(text))


def top_level(text: str, separator: str) -> list[int]:
    """The indexes of every ``separator`` that is not inside a bracket.

    A bracket is a bracket of any kind, and a string is a string: the
    comma in ``Record<string, number>`` and the one in ``"a, b"`` are
    not separators.
    """
    out: list[int] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "'\"`":
            index = skip_string(text, index)
            continue
        if text.startswith("=>", index):
            index += 2
            continue
        if char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth -= 1
        elif char == separator and depth == 0:
            out.append(index)
        index += 1
    return out


def split_top_level(text: str, separator: str = ",") -> list[str]:
    """``text`` split on a separator that is not inside a bracket."""
    out: list[str] = []
    start = 0
    for index in top_level(text, separator):
        out.append(text[start:index])
        start = index + 1
    out.append(text[start:])
    return out


def partition_top_level(text: str, separator: str) -> Partition:
    """``text`` at its first top-level ``separator``."""
    indexes = top_level(text, separator)
    if not indexes:
        return Partition(before=text, separator="", after="")
    index = indexes[0]
    return Partition(before=text[:index], separator=separator, after=text[index + 1 :])


__all__ = [
    "RETURN_TYPE",
    "one_line",
    "parameter_list",
    "partition_top_level",
    "skip_string",
    "split_top_level",
    "strip_comments",
    "tight_generics",
    "top_level",
]

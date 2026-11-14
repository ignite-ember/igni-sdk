"""A Python docstring, as the reference pages show it.

A docstring is written in reST-flavoured prose: ``:class:`~pkg.Thing```
roles, double backticks, indented examples, and an ``Args:`` section. The
reference pages want Markdown, the ``Args:`` section as the meanings in a
parameter table (``tools/param_docs.py``), and the first paragraph as the
one-line summary in a page's table of names.
"""

from __future__ import annotations

import inspect
import re

from pydantic import BaseModel

from tools.markdown_pages import plain
from tools.param_docs import python_args, strip_python_args

#: A reST role around a name: ``:class:`~pkg.Thing```.
_ROLE = re.compile(r":(?:class|meth|func|attr|data|mod|exc|obj):`~?([^`]+)`")

#: The longest a summary in a page's table of names is, in plain characters.
SUMMARY_LIMIT = 200


def _code_spans(text: str) -> str:
    """reST roles and double backticks written as Markdown code."""
    return _ROLE.sub(r"`\1`", text).replace("``", "`")


def _in_list(out: list[str]) -> bool:
    """Whether the last paragraph is a list item, whose indented lines continue it."""
    for line in reversed(out):
        if not line.strip():
            continue
        return bool(re.match(r"\s*([-*+]|\d+\.)\s", line))
    return False


def _fence(block: list[str]) -> list[str]:
    """An indented example as a Python block, its trailing blank lines dropped."""
    while block and not block[-1].strip():
        block.pop()
    indent = min(len(b) - len(b.lstrip()) for b in block if b.strip())
    return ["```python", *(b[indent:] if b.strip() else "" for b in block), "```", ""]


def docstring_markdown(doc: str | None) -> str:
    """A docstring as Markdown: reST roles and double backticks as code, indented
    examples as Python blocks."""
    if not doc:
        return ""
    out: list[str] = []
    block: list[str] = []
    previous_blank = True
    for line in _code_spans(doc).split("\n"):
        indented = line.startswith("    ") and line.strip()
        if block:
            if indented or not line.strip():
                block.append(line)
                continue
            out += _fence(block)
            block = []
        if indented and previous_blank and not _in_list(out):
            block.append(line)
            continue
        out.append(line)
        previous_blank = not line.strip()
    if block:
        out += _fence(block)
    return "\n".join(out).strip()


class Docstring(BaseModel):
    """One name's docstring: empty when the name has none."""

    text: str = ""

    @classmethod
    def own(cls, owner: type) -> Docstring:
        """A class's own docstring, never one it inherits."""
        doc = owner.__dict__.get("__doc__")
        return cls(text=inspect.cleandoc(doc) if isinstance(doc, str) else "")

    @classmethod
    def of(cls, obj: object) -> Docstring:
        """A function's docstring, as ``inspect`` cleans it."""
        return cls(text=inspect.getdoc(obj) or "")

    @property
    def present(self) -> bool:
        return bool(self.text)

    def meanings(self) -> dict[str, str]:
        """What the ``Args:`` section says each parameter means."""
        return python_args(self.text)

    def markdown(self) -> list[str]:
        """The docstring, its ``Args:`` section taken out, as Markdown lines and a blank."""
        doc = docstring_markdown(strip_python_args(self.text))
        return [doc, ""] if doc else []

    def summary(self) -> str:
        """The first paragraph on one line, cut near ``SUMMARY_LIMIT`` characters."""
        if not self.text:
            return ""
        first = self.text.strip().split("\n\n", 1)[0].replace("\n", " ")
        first = _code_spans(first).replace("|", "\\|")
        if len(plain(first)) <= SUMMARY_LIMIT:
            return first
        return first[:SUMMARY_LIMIT].rsplit(" ", 1)[0] + "…"


__all__ = ["Docstring", "docstring_markdown"]

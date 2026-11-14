"""One public name's section of a Python reference page.

A function's section is its ``def`` line, its parameter table and its
docstring. A class's is its ``class`` line (with its constructor, unless
it is an enum, an exception or a protocol), its constructor's parameters
when it has no fields, its docstring, the table of its members or its
fields, and a section of each of its own public methods and properties. A
constant's is its value and the docstring its source gives it
(``tools/py_constant_docs.py``).
"""

from __future__ import annotations

import enum
import inspect
import typing
from collections.abc import Callable
from functools import cached_property
from typing import Any

from pydantic import BaseModel

from tools.markdown_pages import signature
from tools.py_constant_docs import ConstantDocs
from tools.py_docstring import Docstring
from tools.py_entry import Entry
from tools.py_fields import field_rows, field_table
from tools.py_signature import CallableSignature, stable_repr, type_name


class RenderedEntry(BaseModel):
    """A section's Markdown lines, and how many names in it have no docstring."""

    lines: list[str]
    undocumented: int = 0


def _python(*code: str) -> list[str]:
    """``code`` as a Python block, and the blank line after it."""
    return ["```python", *code, "```", ""]


def _def(name: str, func: Any, sig: CallableSignature) -> str:
    """The ``def`` line of ``func``, ``async`` when it is a coroutine function."""
    prefix = "async def" if inspect.iscoroutinefunction(func) else "def"
    return signature(f"{prefix} {name}", sig.text(), sig.arrow())


def _is_member(name: str, value: Any) -> bool:
    """Whether a class attribute is a public method or property the page shows."""
    if name.startswith("_") or name.startswith("model_"):
        return False
    wrapped = isinstance(value, staticmethod | classmethod | property | cached_property)
    return wrapped or inspect.isfunction(value)


def _own_members(cls: type) -> dict[str, Any]:
    """A class's own public methods and properties by name, in the order it defines them."""
    return {name: value for name, value in vars(cls).items() if _is_member(name, value)}


def _decorator(member: Any) -> str:
    """The decorator a member's line is written under, or ``""`` for a plain method."""
    if isinstance(member, property | cached_property):
        return "@property"
    if isinstance(member, classmethod):
        return "@classmethod"
    if isinstance(member, staticmethod):
        return "@staticmethod"
    return ""


def _builds_no_instance(cls: type) -> bool:
    """An enum, an exception or a protocol: a class whose constructor a caller does not call.

    A protocol says what a class must do, and a constructor line would say a
    caller may build one. A class is a protocol when it names
    ``typing.Protocol`` among its own bases, as PEP 544 defines it.
    """
    return issubclass(cls, enum.Enum | BaseException) or typing.Protocol in cls.__bases__


class EntryRenderer:
    """Writes the section of each public name of one package."""

    def __init__(self, link: Callable[[str], str | None], constants: ConstantDocs) -> None:
        #: The page and anchor of a documented name, for links between them.
        self.link = link
        self.constants = constants

    def docstring(self, entry: Entry) -> Docstring:
        """The docstring of ``entry``: a class's own, a function's, a constant's from source."""
        if entry.kind == "class":
            return Docstring.own(entry.obj)
        if entry.kind == "function":
            return Docstring.of(entry.obj)
        return Docstring(text=self.constants.doc(entry.name))

    def render(self, entry: Entry) -> RenderedEntry:
        """The section of ``entry``, under its ``##`` heading."""
        if entry.kind == "class":
            body = self._class(entry.name, entry.obj)
        elif entry.kind == "function":
            body = self._function(entry)
        else:
            body = self._constant(entry)
        return RenderedEntry(
            lines=[f"## {entry.title}", "", *body.lines], undocumented=body.undocumented
        )

    def _function(self, entry: Entry) -> RenderedEntry:
        sig = CallableSignature.of(entry.obj)
        doc = self.docstring(entry)
        lines = [*_python(_def(entry.name, entry.obj, sig)), *sig.table(doc.meanings())]
        return RenderedEntry(lines=lines + doc.markdown(), undocumented=0 if doc.present else 1)

    def _constant(self, entry: Entry) -> RenderedEntry:
        value = entry.obj
        lines = _python(f"{entry.name}: {type_name(value)} = {stable_repr(value)}")
        doc = self.docstring(entry)
        return RenderedEntry(lines=lines + doc.markdown(), undocumented=0 if doc.present else 1)

    def _class(self, name: str, cls: type) -> RenderedEntry:
        bases = [b for b in cls.__bases__ if b is not object]
        base_text = ", ".join(b.__name__ for b in bases)
        doc = Docstring.own(cls)
        fields = field_rows(cls)
        if _builds_no_instance(cls):
            out = _python(f"class {name}({base_text})")
        else:
            head = f"class {name}({base_text})" if base_text else f"class {name}"
            out = _python(head, signature(name, CallableSignature.of(cls).text()))
            if not fields:
                # A class whose fields are not a table of their own: what
                # its constructor takes is what the caller needs to know.
                init = CallableSignature.of(vars(cls).get("__init__"), skip_self=True)
                out += init.table(doc.meanings())
        out += self._based_on(bases)
        out += doc.markdown()
        if issubclass(cls, enum.Enum):
            out += ["| Member | Value |", "|---|---|"]
            out += [f"| `{m.name}` | `{stable_repr(m.value)}` |" for m in cls]
            out.append("")
        else:
            out += field_table(fields)
        undocumented = 0 if doc.present else 1
        for member_name, member in _own_members(cls).items():
            section = self._member(name, member_name, member)
            out += section.lines
            undocumented += section.undocumented
        return RenderedEntry(lines=out, undocumented=undocumented)

    def _based_on(self, bases: list[type]) -> list[str]:
        """The line linking the bases this reference documents; none when it documents none."""
        links = [(b.__name__, self.link(b.__name__)) for b in bases]
        documented = [f"[`{name}`]({url})" for name, url in links if url]
        if not documented:
            return []
        return ["Based on " + ", ".join(documented) + ".", ""]

    def _member(self, owner: str, name: str, member: Any) -> RenderedEntry:
        if isinstance(member, property | cached_property):
            getter = member.fget if isinstance(member, property) else member.func
            sig = CallableSignature.of(getter, skip_self=True)
            heading = f"### {owner}.{name}"
            line = f"{name}: {sig.returns}" if sig.returns else name
            source = getter
        else:
            source = member.__func__ if isinstance(member, staticmethod | classmethod) else member
            sig = CallableSignature.of(source, skip_self=not isinstance(member, staticmethod))
            heading = f"### {owner}.{name}()"
            line = _def(name, source, sig)
        decorator = _decorator(member)
        code = [decorator, line] if decorator else [line]
        doc = Docstring.of(source)
        lines = [heading, "", *_python(*code), *sig.table(doc.meanings()), *doc.markdown()]
        return RenderedEntry(lines=lines, undocumented=0 if doc.present else 1)


__all__ = ["EntryRenderer", "RenderedEntry"]

"""The type a reference page shows for a member: a field's, a method's, an accessor's.

A method and a field holding an arrow function both have a head — type
parameters, then parameters in parentheses — and it is read once, by
``CallableHead``, for both. Whether ``= ...`` gives a field an arrow
function at all, and what that function's type is, is one parse too:
``ArrowFunction``.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from tools.ts_fragment import RETURN_TYPE, parameter_list, strip_comments, tight_generics
from tools.ts_model import ReferenceError_
from tools.ts_parameters import public_parameters
from tools.ts_text import TsText

#: What an arrow function written as a field's value starts with: ``async``,
#: type parameters, then a parenthesis — or a lone parameter and the arrow.
_ARROW_START = re.compile(r"=\s*(?:async\s+)?(?:<|\(|[A-Za-z_$][\w$]*\s*=>)")

#: An arrow function of one parameter, written without parentheses.
_LONE_PARAMETER = re.compile(r"([A-Za-z_$][\w$]*)\s*=>")

#: What a method's type says it returns, written after its arrow.
_ARROW_RETURNS = re.compile(r"\s*=>\s*([^{;]+?)\s*(?=\{|;|\Z)", re.S)


class CallableHead(BaseModel):
    """The head of something callable: ``<T>(name: string, ...)`` and what follows it."""

    #: The type parameters, on one line; empty when there are none.
    generics: str
    #: What the parentheses hold, as the source spells it.
    params: str
    #: Everything after the closing parenthesis.
    tail: str

    @classmethod
    def parse(cls, text: str) -> CallableHead | None:
        """The head at the start of ``text``; ``None`` when there is none, or it never closes."""
        text = text.strip()
        try:
            generics = TsText(text).type_parameters(0)
            text = text[generics.end :].lstrip()
            if not text.startswith("("):
                return None
            end = TsText(text).match_bracket(0, "(", ")")
        except ReferenceError_:
            return None
        return cls(
            generics=tight_generics(generics.text), params=text[1 : end - 1], tail=text[end:]
        )

    def signature(self, returns: str) -> str:
        """The head as a member's type shows it: no private parameters, and what it returns."""
        one = f"{self.generics}({parameter_list(public_parameters(self.params))})"
        return f"{one} => {returns}" if returns else one


def _top_level_arrow(text: str) -> int:
    """Where the ``=>`` that ends an arrow function's head is: right after the
    parameters, or after the ``: Type`` that follows them. ``-1`` when none."""
    stripped = text.lstrip()
    offset = len(text) - len(stripped)
    if stripped.startswith("=>"):
        return offset
    if not stripped.startswith(":"):
        return -1
    depth = 0
    for index, char in enumerate(stripped):
        closes_generic = char == ">" and stripped[index - 1 : index] != "="
        if char in "([{<":
            depth += 1
        elif char in ")]}" or closes_generic:
            depth -= 1
        elif depth == 0 and stripped[index : index + 2] == "=>":
            return offset + index
        elif depth == 0 and char in ";\n":
            return -1
    return -1


class ArrowFunction(BaseModel):
    """An arrow function given to a field as its value: ``= (value: T): void => ...``.

    Its body is not a type, so only the head and the return type it
    declares are kept.
    """

    #: The head, for a function with parentheses; ``None`` for ``x => ...``.
    head: CallableHead | None = None
    #: The one parameter of ``x => ...``.
    lone: str = ""
    #: The return type the function declares; empty when it declares none.
    returns: str = ""

    @classmethod
    def parse(cls, rest: str) -> ArrowFunction | None:
        """The arrow function ``rest`` (``= ...``) gives; ``None`` when it gives another value."""
        text = rest.lstrip()
        if not _ARROW_START.match(text):
            return None
        text = re.sub(r"^async\s+", "", text[1:].lstrip())
        lone = _LONE_PARAMETER.match(text)
        if lone:
            return cls(lone=lone.group(1))
        head = CallableHead.parse(text)
        if head is None:
            return None
        arrow = _top_level_arrow(head.tail)
        if arrow < 0:
            return None
        declared = head.tail[:arrow].strip()
        return cls(head=head, returns=declared[1:].strip() if declared.startswith(":") else "")

    def type(self) -> str:
        """The function's type as a member's row shows it."""
        if self.head is None:
            return f"({self.lone})"
        return self.head.signature(self.returns)


def method_type(rest: str) -> str:
    """A method's type: its type parameters, its parameters and what it returns.

    A method's own type parameters come before its parenthesis, and a
    caller needs them: ``call<T>(name) => Promise<T>``.
    """
    head = CallableHead.parse(rest)
    if head is None:
        return ""
    returns = _ARROW_RETURNS.match(head.tail) or RETURN_TYPE.match(head.tail)
    return head.signature(returns.group(1).strip() if returns else "")


def accessor_type(rest: str, setter: bool) -> str:
    """A getter's or a setter's type: what it reads, or what it is given."""
    head = CallableHead.parse(rest)
    if head is None:
        return ""
    if setter:
        return strip_comments(head.params).strip()
    returns = re.match(r"\s*:\s*([^{;]+?)\s*(?:\{|;|$)", head.tail, re.S)
    return returns.group(1).strip() if returns else ""


def field_type(rest: str) -> str:
    """A field's type: what is between its colon and its end.

    The type ends at its semicolon, at the end of its line, or at the
    ``=`` that gives it a value; what follows is the next member's
    documentation. An arrow is not a value, and a line that ends or
    starts with ``|`` or ``&`` is a union written one member a line.
    """
    text = rest.strip()
    if ":" not in text:
        return ""
    type_ = strip_comments(text.partition(":")[2]).strip()
    depth = 0
    for index, char in enumerate(type_):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif depth == 0 and char in ";=\n":
            if char == "=" and type_[index : index + 2] == "=>":
                continue
            if char == "\n" and (
                type_[:index].rstrip().endswith(("|", "&"))
                or type_[index:].lstrip().startswith(("|", "&"))
            ):
                continue
            type_ = type_[:index]
            break
    return tight_generics(type_.strip()).lstrip("| ")


__all__ = ["ArrowFunction", "CallableHead", "accessor_type", "field_type", "method_type"]

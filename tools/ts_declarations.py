"""One top-level TypeScript declaration, read into a ``Declaration``.

A declaration starts with its keyword. What follows its name decides
what the page shows: a function's parameters and return type, an
interface's or a class's members, a type alias's value, a constant's
type or its literal. Each keyword has one reader, chosen from a table.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import cast

from pydantic import BaseModel

from tools.ts_fragment import RETURN_TYPE, one_line, parameter_list, strip_comments, tight_generics
from tools.ts_members import MemberReader, enum_members
from tools.ts_model import Declaration, DeclarationKind, Member
from tools.ts_text import TsText

#: The name a declaration gives, right after its keyword.
_NAME = re.compile(r"([A-Za-z_$][\w$]*)")

#: The longest literal a constant's signature shows: with a type, and without.
_TYPED_LITERAL_LIMIT = 60
_LITERAL_LIMIT = 80


class DeclarationHead(BaseModel):
    """What every declaration has: its keyword, its name, its type parameters, its JSDoc."""

    kind: DeclarationKind
    name: str
    #: The source after the name, to the next declaration.
    after: str
    #: The type parameters, on one line; empty when there are none.
    generics: str
    #: Where in ``after`` the type parameters end.
    generics_end: int
    is_async: bool
    doc: str
    module: str

    def declaration(
        self,
        signature: str,
        body: str = "",
        params: str = "",
        members: list[Member] | None = None,
    ) -> Declaration:
        return Declaration(
            name=self.name,
            kind=self.kind,
            signature=signature,
            doc=self.doc,
            body=body.strip("\n"),
            params=params,
            members=members or [],
            exported_from=self.module,
        )


class DeclarationReader:
    """Reads the declarations of one module, one chunk at a time."""

    def __init__(self, module: str) -> None:
        self.module = module
        self._readers: dict[str, Callable[[DeclarationHead], Declaration | None]] = {
            "function": self._function,
            "interface": self._block,
            "class": self._block,
            "enum": self._block,
            "type": self._type_alias,
            "const": self._value,
            "let": self._value,
            "var": self._value,
        }

    def read(self, chunk: str, match: re.Match[str], doc: str) -> Declaration | None:
        """The declaration ``chunk`` holds, ``match`` having found its keyword."""
        kind = cast(DeclarationKind, match.group("kind"))
        rest = chunk[match.end("kind") - match.start() :].lstrip()
        name_match = _NAME.match(rest)
        if not name_match:
            return None
        after = rest[name_match.end() :]
        generics = TsText(after).type_parameters(0)
        head = DeclarationHead(
            kind=kind,
            name=name_match.group(1),
            after=after,
            generics=tight_generics(generics.text),
            generics_end=generics.end,
            is_async=bool(match.group("async")),
            doc=doc,
            module=self.module,
        )
        return self._readers[kind](head)

    def _function(self, head: DeclarationHead) -> Declaration | None:
        after = head.after
        open_paren = after.find("(")
        if open_paren < 0:
            return None
        params_end = TsText(after).match_bracket(open_paren, "(", ")")
        params = parameter_list(after[open_paren + 1 : params_end - 1])
        prefix = "async function" if head.is_async else "function"
        signature = f"{prefix} {head.name}{head.generics}({params})"
        returns = RETURN_TYPE.match(after[params_end:])
        if returns:
            signature += f": {returns.group(1).strip()}"
        return head.declaration(signature, params=params)

    def _block(self, head: DeclarationHead) -> Declaration | None:
        """An interface, a class or an enum: a body in braces, and its members."""
        after = head.after
        # Past the type parameters: a default there may be a ``{}``.
        brace = after.find("{", head.generics_end)
        if brace < 0:
            return None
        body_end = TsText(after).match_bracket(brace, "{", "}")
        body = after[brace + 1 : body_end - 1]
        clause = tight_generics(after[head.generics_end : brace].strip())
        signature = f"{head.kind} {head.name}{head.generics}"
        if clause:
            signature += f" {clause}"
        members = enum_members(body) if head.kind == "enum" else MemberReader(body).members()
        return head.declaration(signature, body=body, members=members)

    def _type_alias(self, head: DeclarationHead) -> Declaration | None:
        after = head.after
        end = TsText(after).statement_end(head.generics_end, newline_ends=False)
        value = after[head.generics_end : end].strip().lstrip("=").strip().rstrip(";").strip()
        shown = one_line(strip_comments(value)).lstrip("| ")
        return head.declaration(f"type {head.name}{head.generics} = {shown}")

    def _value(self, head: DeclarationHead) -> Declaration | None:
        """A ``const`` (or ``let``, ``var``): its type and short literal, or an object's members."""
        end = TsText(head.after).statement_end(0)
        text = head.after[:end].strip().rstrip(";").strip()
        if text.startswith(":"):
            annotation, _, literal = text[1:].partition("=")
            signature = f"const {head.name}: {one_line(annotation.strip())}"
            literal = one_line(literal.strip())
            if literal and len(literal) <= _TYPED_LITERAL_LIMIT:
                signature += f" = {literal}"
            return head.declaration(signature)
        value = text.lstrip("=").strip()
        signature = f"const {head.name}"
        if value.startswith("{") and value.endswith("}"):
            # An object literal: what it holds is its members.
            body = value[1:-1]
            return head.declaration(
                signature, body=body, members=MemberReader(body, statements=True).members()
            )
        literal = one_line(value)
        if literal and len(literal) <= _LITERAL_LIMIT:
            signature += f" = {literal}"
        return head.declaration(signature)


__all__ = ["DeclarationHead", "DeclarationReader"]

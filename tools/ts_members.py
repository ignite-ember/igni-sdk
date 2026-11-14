"""The members of an interface, a class, an enum or an object literal.

A member starts at the top level of its body — a parameter line is
inside one, however much it looks like a member — and runs to the next
member. What a member is (a field, a method, an accessor) decides how
its type is read, and who may reach it decides whether it is on the page.
"""

from __future__ import annotations

import re

from tools.ts_fragment import strip_comments
from tools.ts_jsdoc import doc_before, is_internal
from tools.ts_member_types import ArrowFunction, accessor_type, field_type, method_type
from tools.ts_model import Member, MemberKind
from tools.ts_text import TsText

#: A member of an interface or a class: a name, and a ``(``, a ``<`` or a
#: ``:`` after it, at the start of a line — or an ``=`` giving it a value,
#: which is a member only when the value is an arrow function.
_MEMBER_START = re.compile(
    r"^[ \t]*((?:(?:public|private|protected|readonly|static|abstract|declare|override"
    r"|async|get|set)\s+)*)"
    r"([A-Za-z_$][\w$]*)\s*\??\s*(?=[(:<]|=(?![=>]))",
    re.M,
)

#: The modifiers that keep a member from a caller outside its class.
_HIDDEN_MODIFIER = re.compile(r"(?:^|\s)(?:private|protected)\s")

#: The modifier that makes a member a getter or a setter, last before its name.
_ACCESSOR_MODIFIER = re.compile(r"(?:^|\s)(get|set)\s+$")

#: Words that are not members of anything: a statement, not a declaration.
_KEYWORDS = frozenset(
    {
        "await",
        "break",
        "case",
        "catch",
        "class",
        "const",
        "continue",
        "default",
        "delete",
        "do",
        "else",
        "export",
        "extends",
        "finally",
        "for",
        "function",
        "if",
        "import",
        "in",
        "instanceof",
        "let",
        "new",
        "of",
        "return",
        "super",
        "switch",
        "this",
        "throw",
        "try",
        "typeof",
        "var",
        "void",
        "while",
        "yield",
    }
)


class _MemberStart:
    """Where one member starts in its body, and the arrow function it is given, if any."""

    def __init__(self, match: re.Match[str], arrow: ArrowFunction | None) -> None:
        self.match = match
        self.arrow = arrow

    @property
    def modifiers(self) -> str:
        return self.match.group(1)

    @property
    def name(self) -> str:
        return self.match.group(2)

    @property
    def optional(self) -> bool:
        return "?" in self.match.group(0)


class MemberReader:
    """Reads the members out of one body.

    ``statements`` says the body is an object literal rather than a
    declaration: there a word like ``default`` is a statement of a
    ``switch`` and not a member. In a declaration it is a name —
    ``default`` is a field of igni's model registry, and a reserved word
    is a fine name for a field.
    """

    def __init__(self, body: str, statements: bool = False) -> None:
        self.body = body
        self.statements = statements

    def members(self) -> list[Member]:
        """The members a caller can reach, in the order the body declares them."""
        starts = self._starts()
        out: list[Member] = []
        for index, start in enumerate(starts):
            end = starts[index + 1].match.start() if index + 1 < len(starts) else len(self.body)
            member = self._member(start, end)
            if member is not None:
                out.append(member)
        return out

    def _starts(self) -> list[_MemberStart]:
        """Where each member starts: one a line, at the top level of the body.

        A parameter on the same line as a member is part of it, and a
        field given a plain value — ``static readonly PATH = "/x"`` — is a
        constant, not something to call.
        """
        depths = TsText(self.body).line_depths()
        starts: list[_MemberStart] = []
        seen_lines: set[int] = set()
        for match in _MEMBER_START.finditer(self.body):
            line = self.body.count("\n", 0, match.start())
            if line in seen_lines or (line < len(depths) and depths[line] != 0):
                continue
            after = self.body[match.end() :]
            arrow = None
            if after.lstrip().startswith("="):
                arrow = ArrowFunction.parse(after)
                if arrow is None:
                    continue
            seen_lines.add(line)
            starts.append(_MemberStart(match, arrow))
        return starts

    def _is_reachable(self, start: _MemberStart, doc: str) -> bool:
        """Whether a member is part of the surface a reader is looking at.

        A statement's keyword is no member; one marked ``@internal`` owes
        nothing; a private or protected one a caller cannot reach.
        """
        if self.statements and start.name in _KEYWORDS:
            return False
        return not is_internal(doc) and not _HIDDEN_MODIFIER.search(start.modifiers)

    def _member(self, start: _MemberStart, end: int) -> Member | None:
        doc = doc_before(self.body, start.match.start())
        if not self._is_reachable(start, doc):
            return None
        rest = self.body[start.match.end() : end]
        accessor = _ACCESSOR_MODIFIER.search(start.modifiers)
        kind: MemberKind
        if accessor:
            kind, type_ = "accessor", accessor_type(rest, setter=accessor.group(1) == "set")
        elif start.arrow is not None:
            kind, type_ = "method", start.arrow.type()
        elif rest.lstrip().startswith(("(", "<")):
            kind, type_ = "method", method_type(rest)
        else:
            kind, type_ = "field", field_type(rest)
        return Member(name=start.name, kind=kind, type=type_, doc=doc, optional=start.optional)


def enum_members(body: str) -> list[Member]:
    """The members of an enum: a name and the value it is given."""
    out: list[Member] = []
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        # A member ends with its comma, and may be followed by a comment.
        stripped = strip_comments(stripped).strip().rstrip(",").strip()
        match = re.match(r"([A-Za-z_$][\w$]*)\s*(?:=\s*(.+))?$", stripped)
        if match:
            out.append(
                Member(name=match.group(1), kind="member", type=match.group(2) or "", doc="")
            )
    return out


__all__ = ["MemberReader", "enum_members"]

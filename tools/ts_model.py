"""What the TypeScript reader finds: declarations, their members and parameters.

``tools/ts_reference.py`` reads an npm package's TypeScript into reference
pages. These are the typed values its parts hand each other — a
declaration, a member of one, a parameter, a property a pattern takes —
so no part returns a tuple whose positions the next part has to know.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class ReferenceError_(ValueError):
    """A public name has no page, or a page names a module with no public name."""


#: What a declaration at the top of a file is: the keyword that opens it.
DeclarationKind = Literal["function", "class", "interface", "type", "enum", "const", "let", "var"]

#: What a member is: a field, a method, a getter or setter, or an enum's member.
MemberKind = Literal["field", "method", "accessor", "member"]


class Member(BaseModel):
    """One member of an interface or a class."""

    name: str
    kind: MemberKind
    type: str
    doc: str
    #: Whether the member may be left out — a field written ``name?``.
    optional: bool = False


class Parameter(BaseModel):
    """One parameter of a TypeScript signature."""

    name: str
    type: str
    default: str
    optional: bool
    #: Whether the parameter takes the rest of what is left: ``...rest``.
    rest: bool = False


class Declaration(BaseModel):
    """One exported declaration."""

    name: str
    kind: DeclarationKind
    signature: str
    doc: str
    #: The declaration's own text: an interface's or a class's body.
    body: str = ""
    #: The parameters a function takes, as the source spells them.
    params: str = ""
    members: list[Member] = Field(default_factory=list)
    exported_from: str = ""

    def renamed(self, name: str) -> Declaration:
        """This declaration exported under another name (``A as B``).

        The page names it as the package does, signature included.
        """
        signature = re.sub(rf"\b{re.escape(self.name)}\b", name, self.signature, count=1)
        return self.model_copy(update={"name": name, "signature": signature})


class TypeParameters(BaseModel):
    """A declaration's ``<...>`` type parameters, and the index just past them.

    ``text`` is empty, and ``end`` is where the search started, when there
    are none.
    """

    text: str
    end: int


class Partition(BaseModel):
    """A text cut at its first top-level separator: before it, the separator, after it.

    ``separator`` is empty, and ``after`` too, when the text holds none.
    """

    before: str
    separator: str
    after: str


class PatternProperty(BaseModel):
    """One property an object pattern takes: ``{ name = default, ...rest }``."""

    name: str
    default: str
    rest: bool


class PropertyType(BaseModel):
    """A property's type, and whether it may be left out (``name?``)."""

    type: str
    optional: bool


class PropTypes(BaseModel):
    """The interfaces a module declares, each its fields' types.

    A component's props are written as a pattern, and a pattern says no
    type of its own: the type is the interface it is annotated with.
    """

    interfaces: dict[str, dict[str, PropertyType]] = Field(default_factory=dict)

    @classmethod
    def of(cls, declarations: list[Declaration]) -> PropTypes:
        """The fields of every interface among ``declarations``."""
        return cls(
            interfaces={
                declaration.name: {
                    member.name: PropertyType(type=member.type, optional=member.optional)
                    for member in declaration.members
                }
                for declaration in declarations
                if declaration.kind == "interface"
            }
        )

    def fields(self, annotation: str) -> dict[str, PropertyType]:
        """The fields of the interface a pattern is annotated with; none when it is not one."""
        return self.interfaces.get(annotation, {})


__all__ = [
    "Declaration",
    "DeclarationKind",
    "Member",
    "MemberKind",
    "Parameter",
    "Partition",
    "PatternProperty",
    "PropTypes",
    "PropertyType",
    "ReferenceError_",
    "TypeParameters",
]

"""The parameters of a TypeScript signature, and the table a page shows them in.

A parameter is its name, its type, and the default it is given when the
source writes one. A parameter written as a pattern — ``{ variant, size }``
— is a component's props: the props are what a caller writes, so the
props are what the table lists.
"""

from __future__ import annotations

import re

from tools.param_docs import UNDOCUMENTED, ParameterRow, code, table
from tools.ts_fragment import partition_top_level, split_top_level, strip_comments
from tools.ts_model import Parameter, PatternProperty, PropertyType, PropTypes

#: A parameter a constructor keeps for itself: ``private env``.
HIDDEN_PARAMETER = re.compile(
    r"^(?:(?:public|readonly|override|static|declare|async)\s+)*(?:private|protected)\s"
)

#: The modifiers a constructor's parameter may carry before its name.
_PARAMETER_MODIFIERS = re.compile(
    r"^(?:(?:public|private|protected|readonly|override|static|declare|async)\s+)+"
)


def public_parameters(text: str) -> str:
    """A parameter list without the ``private`` and ``protected`` parameters.

    A constructor's ``private env`` is a field of the class and not
    something a caller passes.
    """
    parts = [
        part.strip()
        for part in split_top_level(strip_comments(text))
        if part.strip() and not HIDDEN_PARAMETER.match(part.strip())
    ]
    return ", ".join(parts)


def object_pattern_properties(pattern: str) -> list[PatternProperty]:
    """The properties an object pattern takes: its name, its default, its rest.

    A pattern renames as it binds: ``{ base: givenBase }`` takes the
    property ``base`` and calls it ``givenBase`` in the body. The table
    names the property, which is what a caller writes.
    """
    out: list[PatternProperty] = []
    for part in split_top_level(pattern.strip()[1:-1]):
        part = part.strip()
        if not part:
            continue
        rest = part.startswith("...")
        if rest:
            part = part[3:].strip()
        valued = partition_top_level(part, "=")
        name = partition_top_level(valued.before, ":").before
        out.append(
            PatternProperty(
                name=name.strip(),
                default=valued.after.strip() if valued.separator else "",
                rest=rest,
            )
        )
    return out


def inline_object_properties(type_: str) -> dict[str, PropertyType]:
    """The properties of a type written in place: ``{ name: string; size?: number }``.

    A component whose props are not worth an interface annotates its
    pattern with the object type itself; the type and whether the property
    may be left out are read from it the same way.
    """
    inner = strip_comments(type_).strip()[1:-1]
    parts = split_top_level(inner, ";")
    if len(parts) == 1:
        parts = split_top_level(inner, ",")
    out: dict[str, PropertyType] = {}
    for part in parts:
        typed = partition_top_level(part.strip(), ":")
        if not typed.separator:
            continue
        name = typed.before.strip()
        out[name.rstrip("?").strip()] = PropertyType(
            type=typed.after.strip(), optional=name.endswith("?")
        )
    return out


def _pattern_parameters(pattern: str, annotation: str, prop_types: PropTypes) -> list[Parameter]:
    """The props a pattern parameter takes, typed by the annotation it carries."""
    known = prop_types.fields(annotation)
    if not known and annotation.startswith("{"):
        known = inline_object_properties(annotation)
    out: list[Parameter] = []
    for prop in object_pattern_properties(pattern):
        typed = known.get(prop.name, PropertyType(type="", optional=not prop.default))
        out.append(
            Parameter(
                name=prop.name,
                type=typed.type,
                default=prop.default,
                optional=typed.optional and not prop.rest,
                rest=prop.rest,
            )
        )
    return out


def signature_parameters(text: str, prop_types: PropTypes | None = None) -> list[Parameter]:
    """The parameters a TypeScript signature's parentheses hold.

    A name with a ``?`` is optional: the caller may leave it out. A
    pattern's props take their types from the interface the pattern is
    annotated with, when the module declares one.
    """
    known = prop_types or PropTypes()
    out: list[Parameter] = []
    for part in split_top_level(text):
        part = part.strip()
        if not part or HIDDEN_PARAMETER.match(part):
            continue
        # The first top-level ``=`` is the default: what is left of it is
        # the name, and its type when it has one.
        valued = partition_top_level(part, "=")
        typed = partition_top_level(valued.before, ":")
        head = typed.before.strip()
        annotation = typed.after.strip()
        if head.startswith("{") and head.endswith("}"):
            out += _pattern_parameters(head, annotation, known)
            continue
        # A parameter may carry several modifiers — ``protected readonly
        # link`` — and the name a caller writes is what is left once
        # every one of them is gone.
        name = _PARAMETER_MODIFIERS.sub("", head).strip()
        optional = name.endswith("?")
        name = name.rstrip("?").strip()
        rest = name.startswith("...")
        if rest:
            name = name[3:].strip()
        out.append(
            Parameter(
                name=name,
                type=annotation,
                default=valued.after.strip(),
                optional=optional,
                rest=rest,
            )
        )
    return out


def parameter_table(params: list[Parameter], meanings: dict[str, str]) -> list[str]:
    """The table of a signature's parameters, as the reference pages show it.

    A parameter the JSDoc does not document is said to be undocumented:
    the generator does not guess what a parameter is.
    """
    rows: list[ParameterRow] = []
    for param in params:
        if param.default:
            default = code(param.default)
        elif param.optional or param.rest:
            default = "optional"
        else:
            default = "required"
        rows.append(
            ParameterRow(
                name=param.name,
                type=code(param.type) if param.type else "—",
                default=default,
                meaning=meanings.get(param.name) or UNDOCUMENTED,
            )
        )
    return table(rows)


__all__ = [
    "HIDDEN_PARAMETER",
    "inline_object_properties",
    "object_pattern_properties",
    "parameter_table",
    "public_parameters",
    "signature_parameters",
]

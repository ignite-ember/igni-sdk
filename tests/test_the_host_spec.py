"""The host grammar refuses a schema that contradicts itself, and reads one that does not.

``tools/host_spec.py`` is igni-sdk's copy of igni-core's grammar. The one
test that reads the published schema back whole proves the copy accepts
what igni-core publishes; a copy that accepted everything would pass it.
These tests build small schemas and say what the grammar must refuse, in
one message, and what its lookups answer.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from tools.host_spec import (
    HostSchema,
    ObjectSpec,
    PermissionSpec,
    TypeSpec,
    field,
    method,
    param,
    prop,
    signal,
    typedef,
)

PERMS = (PermissionSpec(name="chat", doc="d"), PermissionSpec(name="files", doc="d"))


def _object(path: str = "chat", **kwargs: Any) -> ObjectSpec:
    kwargs.setdefault("doc", "d")
    kwargs.setdefault("permission", None)
    return ObjectSpec(path=path, **kwargs)


def _schema(*objects: ObjectSpec, types: tuple[TypeSpec, ...] = ()) -> HostSchema:
    return HostSchema(version="1.0.0", permissions=PERMS, types=types, objects=objects)


def _refusal(*objects: ObjectSpec, types: tuple[TypeSpec, ...] = ()) -> str:
    with pytest.raises(ValidationError) as caught:
        _schema(*objects, types=types)
    return str(caught.value)


def _tree() -> HostSchema:
    """A schema with a root object, a nested one and a per-session one."""
    return _schema(
        _object(
            "",
            properties=(prop("version", "str", "d", constant=True),),
            signals=(signal("ready", "None", "d"),),
            methods=(method("ping", "d", param("n", "int")),),
        ),
        _object(
            "chat",
            permission="chat",
            per_session=True,
            properties=(
                prop("title", "str", "d", changed_by=["title_changed"]),
                prop("open", "bool", "d", changed_by=["chat.moved"], permission="files"),
            ),
            signals=(
                signal("title_changed", "str", "d"),
                signal("moved", "None", "d", wire="chat_moved", always=True),
            ),
            methods=(
                method("post", "d", param("text", "str"), elsewhere="files"),
                method("peek", "d", result="list[Item] | None", always=True),
            ),
        ),
        types=(typedef("Item", "d", field("id", "str")),),
    )


# ── The published schema ──


def test_a_type_defined_twice_or_not_in_pascal_case_is_refused() -> None:
    twice = (typedef("Item", "d"), typedef("Item", "d"))
    assert "a type is defined twice" in _refusal(types=twice)
    for name in ("item", "Item_x", "1Item", "Item\n", ""):
        with pytest.raises(ValidationError, match="PascalCase"):
            typedef(name, "d")
    assert typedef("Item2", "d").name == "Item2"


@pytest.mark.parametrize(
    "path", ["Chat", "chat.", ".chat", "chat..a", "chat-a", "1chat", "chat\n", "chat.a\n"]
)
def test_an_object_path_that_is_not_dotted_lowercase_is_refused(path: str) -> None:
    assert f"object path {path!r} is not dotted lowercase" in _refusal(_object(path))


@pytest.mark.parametrize("name", ["Name", "na-me", "1name", "na me", "naïve", "name\n", "_name"])
def test_a_member_or_parameter_name_that_is_not_lowercase_is_refused(name: str) -> None:
    member = _refusal(_object("a", signals=(signal(name, "str", "d"),)))
    assert "not a lowercase name" in member
    parameter = _refusal(_object("a", methods=(method("m", "d", param(name, "str")),)))
    assert f"a.m({name}): not a lowercase name" in parameter


def test_a_problem_on_the_root_object_names_its_member_without_a_leading_dot() -> None:
    message = _refusal(
        _object(
            "",
            permission="nope",
            properties=(prop("p", "Gone", "d"),),
            methods=(method("m", "d", result="Gone"),),
        )
    )
    assert "\n  p: unknown type 'Gone'" in message
    assert "\n  p: every property has a change signal" in message
    assert "\n  m: unknown type 'Gone' in 'Gone'" in message
    assert "the root object: permission 'nope' is not declared" in message
    assert "\n  .p" not in message
    assert "\n  .m" not in message


# ── Lookups ──

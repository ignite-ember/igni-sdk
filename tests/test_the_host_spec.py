"""The host grammar refuses a schema that contradicts itself, and reads one that does not.

``tools/host_spec.py`` is igni-sdk's copy of igni-core's grammar. The one
test that reads the published schema back whole proves the copy accepts
what igni-core publishes; a copy that accepted everything would pass it.
These tests build small schemas and say what the grammar must refuse, in
one message, and what its lookups answer.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tools.host_codegen import HOST_SCHEMA, SCHEMA_FILE
from tools.host_spec import (
    SCALARS,
    ErrorCode,
    FieldSpec,
    HostSchema,
    MethodSpec,
    ObjectSpec,
    ParamSpec,
    PermissionSpec,
    PropertySpec,
    SignalSpec,
    TypeExpr,
    TypeSpec,
    field,
    method,
    param,
    prop,
    schema_json,
    signal,
    type_words,
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


def test_the_published_schema_reads_back_with_frozen_models_that_forbid_extras() -> None:
    raw = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    assert schema_json(HOST_SCHEMA) == raw
    with pytest.raises(ValidationError):
        HostSchema.model_validate({**raw, "surprise": 1})
    with pytest.raises(ValidationError):
        HostSchema.model_validate(
            {**raw, "types": [{**raw["types"][0], "surprise": 1}, *raw["types"][1:]]}
        )
    with pytest.raises(ValidationError):
        HOST_SCHEMA.version = "9"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        HOST_SCHEMA.objects[0].doc = "x"  # type: ignore[misc]


def test_the_grammar_is_this_repositorys_own_and_imports_nothing_of_igni_core() -> None:
    """Codegen reads igni-core's published JSON; it does not import igni-core."""
    tools = Path(__file__).resolve().parent.parent / "tools"
    for name in ("host_spec.py", "host_codegen.py"):
        tree = ast.parse((tools / name).read_text(encoding="utf-8"))
        imported = {
            part
            for node in ast.walk(tree)
            for part in (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
        }
        assert not [m for m in imported if m.split(".")[0] == "igni_core"], name


# ── What the validator refuses ──


def test_a_consistent_schema_is_accepted() -> None:
    schema = _tree()
    assert schema.permission_names() == {"chat", "files"}


def test_a_type_defined_twice_or_not_in_pascal_case_is_refused() -> None:
    twice = (typedef("Item", "d"), typedef("Item", "d"))
    assert "a type is defined twice" in _refusal(types=twice)
    for name in ("item", "Item_x", "1Item", "Item\n", ""):
        with pytest.raises(ValidationError, match="PascalCase"):
            typedef(name, "d")
    assert typedef("Item2", "d").name == "Item2"


def test_an_object_defined_twice_is_refused() -> None:
    assert "an object is defined twice" in _refusal(_object("a"), _object("a"))


@pytest.mark.parametrize(
    "path", ["Chat", "chat.", ".chat", "chat..a", "chat-a", "1chat", "chat\n", "chat.a\n"]
)
def test_an_object_path_that_is_not_dotted_lowercase_is_refused(path: str) -> None:
    assert f"object path {path!r} is not dotted lowercase" in _refusal(_object(path))


def test_dotted_paths_and_the_empty_root_path_are_accepted() -> None:
    schema = _schema(_object(""), _object("chat"), _object("chat.approvals_2"))
    assert [o.path for o in schema.objects] == ["", "chat", "chat.approvals_2"]


def test_an_undeclared_permission_is_refused_wherever_it_is_named() -> None:
    message = _refusal(
        _object(
            "a",
            permission="nope",
            properties=(prop("p", "str", "d", constant=True, permission="p_nope"),),
            signals=(signal("s", "str", "d", permission="s_nope"),),
            methods=(method("m", "d", permission="m_nope"),),
        )
    )
    assert "a: permission 'nope' is not declared" in message
    assert "a.p: permission 'p_nope' is not declared" in message
    assert "a.s: permission 's_nope' is not declared" in message
    assert "a.m: permission 'm_nope' is not declared" in message


@pytest.mark.parametrize("name", ["Name", "na-me", "1name", "na me", "naïve", "name\n", "_name"])
def test_a_member_or_parameter_name_that_is_not_lowercase_is_refused(name: str) -> None:
    member = _refusal(_object("a", signals=(signal(name, "str", "d"),)))
    assert "not a lowercase name" in member
    parameter = _refusal(_object("a", methods=(method("m", "d", param(name, "str")),)))
    assert f"a.m({name}): not a lowercase name" in parameter


def test_a_member_name_used_twice_on_one_object_is_refused_across_kinds() -> None:
    message = _refusal(
        _object(
            "a",
            properties=(prop("x", "str", "d", constant=True),),
            signals=(signal("x", "str", "d"),),
            methods=(method("x", "d"),),
        )
    )
    assert message.count("a.x: defined twice") == 2


def test_a_member_stage_other_than_one_or_two_is_refused() -> None:
    for stage in (0, 3, -1):
        message = _refusal(_object("a", methods=(method("m", "d", stage=stage),)))
        assert "a.m: stage must be 1 or 2" in message
    schema = _schema(_object("a", methods=(method("m", "d", stage=2),)))
    assert schema.stage_two() == ["a.m"]


def test_a_type_word_that_is_neither_scalar_nor_declared_is_refused_everywhere() -> None:
    message = _refusal(
        _object(
            "a",
            properties=(prop("p", "dict[str, Gone]", "d", constant=True),),
            signals=(signal("s", "list[Gone]", "d"),),
            methods=(method("m", "d", param("x", "Gone | None"), result="Gone"),),
        ),
        types=(typedef("Held", "d", field("f", "Gone")),),
    )
    assert "Held.f: unknown type 'Gone' in 'Gone'" in message
    assert "a.p: unknown type 'Gone' in 'dict[str, Gone]'" in message
    assert "a.s: unknown type 'Gone' in 'list[Gone]'" in message
    assert "a.m(x): unknown type 'Gone' in 'Gone | None'" in message
    assert "a.m: unknown type 'Gone' in 'Gone'" in message


def test_every_scalar_and_every_declared_type_is_a_known_type_word() -> None:
    types = (typedef("Item", "d"),)
    for word in sorted(SCALARS):
        _schema(_object("a", methods=(method("m", "d", result=f"list[{word}]"),)))
    _schema(_object("a", methods=(method("m", "d", result="dict[str, Item] | None"),)), types=types)


def test_a_property_must_name_a_signal_or_be_constant() -> None:
    message = _refusal(_object("a", properties=(prop("p", "str", "d"),)))
    assert "a.p: every property has a change signal" in message
    own = _object(
        "a",
        properties=(prop("p", "str", "d", changed_by=["s"]),),
        signals=(signal("s", "str", "d"),),
    )
    assert _schema(own).object("a") == own


def test_changed_by_must_name_a_signal_of_this_or_another_object() -> None:
    other = _object(
        "b", signals=(signal("s", "str", "d"),), properties=(prop("k", "str", "d", constant=True),)
    )
    message = _refusal(
        _object(
            "a",
            properties=(
                prop("local", "str", "d", changed_by=["missing"]),
                prop("method", "str", "d", changed_by=["m"]),
                prop("far", "str", "d", changed_by=["b.s"]),
                prop("far_prop", "str", "d", changed_by=["b.k"]),
                prop("far_object", "str", "d", changed_by=["nowhere.s"]),
            ),
            methods=(method("m", "d"),),
        ),
        other,
    )
    assert "a.local: changed_by 'missing' is not a signal" in message
    assert "a.method: changed_by 'm' is not a signal" in message
    assert "a.far: " not in message
    assert "a.far_prop: changed_by 'b.k' is not a signal" in message
    assert "a.far_object: changed_by 'nowhere.s' is not a signal" in message


def test_two_signals_with_one_wire_name_are_refused() -> None:
    twice = _refusal(
        _object("a", signals=(signal("s", "str", "d", wire="x"), signal("t", "str", "d", wire="x")))
    )
    assert "a.t: wire name 'x' also used by a.s" in twice
    collision = _refusal(
        _object("a", signals=(signal("s", "str", "d"),)),
        _object("", signals=(signal("a.s", "str", "d", always=True),)),
    )
    assert "wire name 'a.s' also used by" in collision


def test_an_object_cannot_belong_to_both_a_window_and_a_session() -> None:
    assert "a: belongs to a window or a session, not both" in _refusal(
        _object("a", per_window=True, per_session=True)
    )
    _schema(_object("a", per_window=True), _object("b", per_session=True))


def test_elsewhere_needs_a_session_object_and_a_declared_permission() -> None:
    plain = _refusal(_object("a", methods=(method("m", "d", elsewhere="files"),)))
    assert "a.m: elsewhere, on an object no session owns" in plain
    window = _refusal(_object("a", per_window=True, methods=(method("m", "d", elsewhere="files"),)))
    assert "a.m: elsewhere, on an object no session owns" in window
    undeclared = _refusal(
        _object("a", per_session=True, methods=(method("m", "d", elsewhere="nope"),))
    )
    assert "a.m: elsewhere permission 'nope' is not declared" in undeclared
    _schema(_object("a", per_session=True, methods=(method("m", "d", elsewhere="files"),)))


def test_every_problem_is_reported_in_one_message() -> None:
    message = _refusal(
        _object(
            "A",
            permission="nope",
            properties=(prop("p", "Gone", "d"),),
            methods=(method("m", "d", stage=7),),
        ),
        types=(typedef("T", "d"), typedef("T", "d")),
    )
    assert message.count("the host schema is inconsistent") == 1
    for part in (
        "a type is defined twice",
        "object path 'A'",
        "permission 'nope'",
        "unknown type 'Gone'",
        "stage must be 1 or 2",
        "every property has a change signal",
    ):
        assert part in message


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


def test_lookups_find_objects_types_and_members_and_resolve_refuses_the_unknown() -> None:
    schema = _tree()
    assert schema.object("chat") is schema.objects[1]
    assert schema.object("") is schema.objects[0]
    assert schema.object("missing") is None
    assert schema.type("Item") is schema.types[0]
    assert schema.type("item") is None
    owner, member = schema.resolve("chat.post")
    assert (owner.path, member.name) == ("chat", "post")
    owner, member = schema.resolve("ping")
    assert (owner.path, member.name) == ("", "ping")
    for bad in ("chat.nope", "nope.post", "nope", "chat.approvals.post", ""):
        with pytest.raises(KeyError):
            schema.resolve(bad)


def test_member_paths_list_every_member_with_root_members_bare() -> None:
    assert _tree().member_paths() == [
        "version",
        "ready",
        "ping",
        "chat.title",
        "chat.open",
        "chat.title_changed",
        "chat.moved",
        "chat.post",
        "chat.peek",
    ]


def test_a_signal_travels_under_its_wire_or_its_path_and_name() -> None:
    schema = _tree()
    root, chat = schema.objects
    assert schema.wire_name(root, root.signals[0]) == "ready"
    assert schema.wire_name(chat, chat.signals[0]) == "chat.title_changed"
    assert schema.wire_name(chat, chat.signals[1]) == "chat_moved"
    found = schema.signal_by_wire("chat_moved")
    assert found is not None and (found[0].path, found[1].name) == ("chat", "moved")
    found = schema.signal_by_wire("ready")
    assert found is not None and found[0].path == ""
    assert schema.signal_by_wire("chat.moved") is None
    assert schema.signal_by_wire("nope") is None


def test_a_member_has_its_own_grant_else_the_objects_unless_always() -> None:
    chat = _tree().object("chat")
    assert chat is not None
    title, opened = chat.properties
    moved = chat.signals[1]
    post, peek = chat.methods
    assert chat.permission_of(title) == "chat"
    assert chat.permission_of(opened) == "files"
    assert chat.permission_of(post) == "chat"
    assert chat.permission_of(moved) is None
    assert chat.permission_of(peek) is None
    assert moved.inherit_permission is False
    assert title.inherit_permission is True
    always_with_own = signal("s", "str", "d", permission="files", always=True)
    assert chat.permission_of(always_with_own) == "files"


def test_member_finds_a_property_a_signal_or_a_method_by_name() -> None:
    chat = _tree().object("chat")
    assert chat is not None
    assert isinstance(chat.member("title"), PropertySpec)
    assert isinstance(chat.member("moved"), SignalSpec)
    assert isinstance(chat.member("post"), MethodSpec)
    assert chat.member("nope") is None


def test_stage_two_lists_members_of_every_kind_with_root_members_bare() -> None:
    schema = _schema(
        _object(
            "",
            properties=(prop("p", "str", "d", constant=True, stage=2),),
            signals=(signal("s", "str", "d", stage=2), signal("t", "str", "d")),
        ),
        _object("a", methods=(method("m", "d", stage=2), method("n", "d"))),
    )
    assert schema.stage_two() == ["p", "s", "a.m"]
    assert _tree().stage_two() == []


# ── Type expressions ──


@pytest.mark.parametrize(
    ("expression", "tree"),
    [
        ("str", ("scalar", "str")),
        ("json", ("scalar", "json")),
        ("None", ("scalar", "None")),
        ("Item", ("named", "Item")),
        ("  Item  ", ("named", "Item")),
        ("list[Item]", ("list", ("named", "Item"))),
        ("list[ Item ]", ("list", ("named", "Item"))),
        ("dict[str, int]", ("dict", ("scalar", "int"))),
        ("dict[str,int]", ("dict", ("scalar", "int"))),
        ("Item | None", ("optional", ("named", "Item"))),
        ("list[Item] | None", ("optional", ("list", ("named", "Item")))),
        ("list[Item | None]", ("list", ("optional", ("named", "Item")))),
        ("list[dict[str, T | None]]", ("list", ("dict", ("optional", ("named", "T"))))),
        ("T | None | None", ("optional", ("optional", ("named", "T")))),
    ],
)
def test_a_type_expression_parses_into_its_tree(expression: str, tree: Any) -> None:
    def shape(node: TypeExpr) -> Any:
        if node.kind in ("scalar", "named"):
            return (node.kind, node.name)
        assert node.item is not None
        return (node.kind, shape(node.item))

    assert shape(TypeExpr.parse(expression)) == tree


@pytest.mark.parametrize(
    "expression",
    ["", " ", "foo", "item", "dict[int, str]", "list[", "list[Item", "list[Item]]", "list[]",
     "Item | Other", "str|None", "| None", "dict[str]", "Item[]", "list[Item] | list[Other]"],
)  # fmt: skip
def test_anything_else_is_not_a_type_expression(expression: str) -> None:
    with pytest.raises(ValueError, match="not a type expression|not a type"):
        TypeExpr.parse(expression)


def test_type_words_leave_out_list_and_dict_and_keep_scalars() -> None:
    assert type_words("list[dict[str, T | None]]") == ["str", "T", "None"]
    assert type_words("Item") == ["Item"]
    assert type_words("list[json]") == ["json"]
    assert type_words("") == []


# ── Builders and the error codes ──


def test_the_builders_construct_the_specs_with_their_defaults() -> None:
    assert field("a", "str") == FieldSpec(name="a", type="str", doc="", optional=False)
    assert field("a", "str", "d", optional=True).optional is True
    assert param("a", "int") == ParamSpec(name="a", type="int", doc="", optional=False)
    assert param("a", "int", "d", optional=True).doc == "d"
    made = prop("p", "str", "d")
    assert (made.changed_by, made.writable, made.constant, made.permission, made.stage) == (
        (),
        False,
        False,
        None,
        1,
    )
    assert made.inherit_permission is True
    full = prop("p", "str", "d", changed_by=["a", "b"], writable=True, constant=True, always=True)
    assert full.changed_by == ("a", "b")
    assert (full.writable, full.constant, full.inherit_permission) == (True, True, False)
    s = signal("s", "str", "d")
    assert (s.wire, s.permission, s.inherit_permission, s.stage) == (None, None, True, 1)
    made_method = method("m", "d", param("a", "str"), param("b", "int"))
    assert [p.name for p in made_method.params] == ["a", "b"]
    assert (made_method.result, made_method.elsewhere, made_method.inherit_permission) == (
        "None",
        None,
        True,
    )
    assert method("m", "d", always=True, stage=2, elsewhere="x").elsewhere == "x"
    assert method("m", "d").params == ()
    t = typedef("T", "d", field("a", "str"))
    assert [f.name for f in t.fields] == ["a"]


def test_the_error_codes_are_the_eight_wire_words() -> None:
    assert {code.name: code.value for code in ErrorCode} == {
        "NOT_GRANTED": "not_granted",
        "NOT_FOUND": "not_found",
        "INVALID": "invalid",
        "READ_ONLY": "read_only",
        "STAGE_2": "stage_2",
        "REFUSED": "refused",
        "UNAVAILABLE": "unavailable",
        "FAILED": "failed",
    }
    assert ErrorCode("refused") is ErrorCode.REFUSED
    assert f"{ErrorCode.FAILED}" == "failed"


def test_schema_json_is_plain_json_that_reads_back() -> None:
    schema = _tree()
    dumped = schema_json(schema)
    assert json.loads(json.dumps(dumped)) == dumped
    assert dumped["objects"][1]["methods"][0]["elsewhere"] == "files"
    assert HostSchema.model_validate(dumped) == schema

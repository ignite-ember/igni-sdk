"""The client generator's own rules: what it refuses, what it writes, what it generates.

``test_the_client_api_is_generated.py`` pins that the checked-in client is
what the contract generates. This pins the generator itself, apart from the
checked-in copy: every contract it refuses, how it names and types what the
contract says, and the code it writes, run as a caller would run it.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import importlib
import inspect
import json
import shutil
import sys
import types
from pathlib import Path
from typing import Any, get_args

import pytest

from tools import client_codegen
from tools.client_codegen import (
    ACCESS_NOTES,
    API_OUTPUT,
    MODELS_OUTPUT,
    README,
    ApiGenerator,
    ClientApi,
    ContractError,
    Imports,
    ModelsGenerator,
    Placement,
    Plan,
    ReferenceGenerator,
    Types,
    class_for_group,
    docstring,
    field_name,
    hoisted,
    pascal,
    push_class,
    ruff_format,
    snake,
)
from tools.client_contract import CONTRACT_FILE, RpcContract
from tools.client_names import (
    FOLLOWED,
    METHODS,
    NAMESPACES,
    NOT_FOR_CLIENTS,
    SELF_MADE,
    UNFOLLOWED,
    UNION_NAMES,
)

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_CONFIG = Path("packages/igni-client/pyproject.toml")
CONTRACT = RpcContract.read()


def _contract(edit: Any) -> RpcContract:
    raw = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    edit(raw)
    return RpcContract.model_validate(raw)


def _wire() -> types.ModuleType:
    """igni-client's wire bases. The package is not installed into this repository's
    environment: what the generator writes runs against its own source, whose
    dependencies the SDKs already pull in."""
    src = str(ROOT / "packages" / "igni-client" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    return importlib.import_module("igni_client.wire")


def _run(source: str) -> types.ModuleType:
    """Generated source, run as a module (it needs only igni_client)."""
    _wire()
    module = types.ModuleType("generated")
    # Pydantic resolves the annotations of a class against its module.
    sys.modules["generated"] = module
    exec(compile(source, "<generated>", "exec"), module.__dict__)  # noqa: S102
    return module


def _models(contract: RpcContract = CONTRACT) -> types.ModuleType:
    return _run(ModelsGenerator(Plan(contract)).generate())


def _api(contract: RpcContract = CONTRACT) -> tuple[types.ModuleType, str]:
    text = ApiGenerator(Plan(contract)).generate()
    return _run(text), text


# ── Names ─────────────────────────────────────────────────────────────


def test_names_are_snake_pascal_and_clear_of_keywords_and_basemodel() -> None:
    assert snake("activeForm") == "active_form"
    assert snake("runID2Next") == "run_id2_next"
    assert snake("already_snake") == "already_snake"
    assert pascal("read_process_tail") == "ReadProcessTail"
    assert pascal("igni.processes") == "IgniProcesses"
    assert push_class("process_line") == "ProcessLinePush"
    assert class_for_group("igni.processes") == "IgniProcesses"
    assert class_for_group("session") == "SessionApi"
    assert class_for_group("igni") == "IgniApi"
    assert field_name("activeForm") == "active_form"
    assert field_name("class") == "class_"
    assert field_name("from") == "from_"
    for reserved in ("json", "dict", "copy", "schema", "validate", "fields", "construct"):
        assert field_name(reserved) == reserved + "_"
    assert field_name("text") == "text"


@pytest.mark.parametrize(
    "path, owner, namespace, name, group",
    [
        ("igni.check_for_update", "igni", "", "check_for_update", "igni"),
        ("igni.processes.tail", "igni", "processes", "tail", "igni.processes"),
        ("session.status", "session", "", "status", "session"),
        ("session.runs.interrupted", "session", "runs", "interrupted", "session.runs"),
    ],
)
def test_a_placement_reads_its_path_back(
    path: str, owner: str, namespace: str, name: str, group: str
) -> None:
    placed = Placement.of("wire", path)
    assert (placed.owner, placed.namespace, placed.name) == (owner, namespace, name)
    assert placed.path == path
    assert placed.group == group


@pytest.mark.parametrize("path", ["tail", "other.status", "igni.a.b.c", "session.a.b.c", ""])
def test_a_placement_refuses_a_wrong_owner_or_depth(path: str) -> None:
    with pytest.raises(ContractError, match="wire"):
        Placement.of("wire", path)


@pytest.mark.parametrize(
    "text",
    [
        "One line.",
        'Ends in a quote "',
        'Ends in two quotes ""',
        "A path C:\\dir\\ and a tab \\t",
        'Has """triple""" quotes and more """"',
        'First line\nsecond line\n\nafter a blank\n  indented\nends with a quote"',
        "Line one\\\nline two",
        "  padded  ",
    ],
)
def test_a_docstring_reads_back_as_the_text_whatever_it_holds(text: str) -> None:
    lines = docstring(text, "    ")
    # The source is a statement; run it for the string it is.
    value = ast.literal_eval("\n".join(line.removeprefix("    ") for line in lines))
    # A text that ends in a quote is given a space, so that the closing quotes are the closing.
    assert value.strip() == text.strip()
    assert value.startswith(text.strip())
    assert all(line.startswith("    ") or not line for line in lines)


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_a_docstring_of_nothing_is_nothing(text: str) -> None:
    assert docstring(text, "    ") == []


def test_ruff_sorts_imports_then_formats(tmp_path: Path) -> None:
    out = ruff_format("import b\nimport a\nx   =  {'k':1}\n", tmp_path / "m.py")
    assert out == 'import a\nimport b\n\nx = {"k": 1}\n'


def test_ruff_refusing_the_text_is_a_contract_error(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match=r"ruff could not format the generated m\.py"):
        ruff_format("def (:\n", tmp_path / "m.py")


# ── Refusals ──────────────────────────────────────────────────────────


def test_a_name_for_a_method_igni_lacks_fails() -> None:
    def drop(raw: dict[str, Any]) -> None:
        del raw["methods"]["get_todos"]

    with pytest.raises(ContractError, match="names methods igni lacks.*get_todos"):
        Plan(_contract(drop))


def test_a_method_both_placed_and_not_for_clients_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(NOT_FOR_CLIENTS, "get_todos", "because")
    with pytest.raises(ContractError, match="both named and not for clients.*get_todos"):
        Plan(CONTRACT)


@pytest.mark.parametrize("access", ["page", "platform"])
def test_a_page_or_platform_call_cannot_be_placed_for_clients(access: str) -> None:
    def edit(raw: dict[str, Any]) -> None:
        raw["methods"]["get_todos"]["access"] = access

    with pytest.raises(ContractError, match=f"get_todos is a {access} call"):
        Plan(_contract(edit))


def test_a_scope_that_disagrees_with_the_placement_fails() -> None:
    def edit(raw: dict[str, Any]) -> None:
        raw["methods"]["get_todos"]["scope"] = "igni"

    with pytest.raises(ContractError, match="get_todos has scope igni but is placed at"):
        Plan(_contract(edit))


def test_a_method_that_streams_must_be_followed_or_say_why_not() -> None:
    def edit(raw: dict[str, Any]) -> None:
        raw["methods"]["get_todos"]["may_stream"] = ["push_notification:todos_updated"]

    with pytest.raises(ContractError, match=r"undecided \['get_todos'\]"):
        Plan(_contract(edit))


def test_a_decision_for_a_method_that_does_not_stream_fails() -> None:
    def edit(raw: dict[str, Any]) -> None:
        raw["methods"]["cancel_run"]["streams"] = []
        raw["methods"]["cancel_run"]["may_stream"] = []

    with pytest.raises(ContractError, match=r"not causing events \['cancel_run'\]"):
        Plan(_contract(edit))


def test_two_methods_with_one_python_name_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(METHODS, "get_todos", METHODS["get_status"])
    with pytest.raises(ContractError, match=r"two methods share a name.*session\.status"):
        Plan(CONTRACT)


def test_a_message_a_client_may_send_must_be_decided() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["messages"]["brand_new_message"] = copy.deepcopy(raw["messages"]["typing"])

    with pytest.raises(ContractError, match=r"undecided \['brand_new_message'\]"):
        Plan(_contract(add))


def test_a_decision_for_a_message_igni_does_not_take_fails() -> None:
    def drop(raw: dict[str, Any]) -> None:
        del raw["messages"]["typing"]

    with pytest.raises(ContractError, match=r"unknown \['typing'\]"):
        Plan(_contract(drop))


def test_a_namespace_without_a_description_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(NAMESPACES, "igni.processes")
    with pytest.raises(ContractError, match="namespace igni.processes has no description"):
        ApiGenerator(Plan(CONTRACT)).generate()


def test_a_method_whose_args_are_not_a_def_fails() -> None:
    def edit(raw: dict[str, Any]) -> None:
        raw["methods"]["get_todos"]["args"] = {"type": "object", "properties": {}}

    with pytest.raises(ContractError, match="get_todos: args is not a def"):
        ApiGenerator(Plan(_contract(edit))).generate()


def test_an_argument_igni_client_makes_for_itself_cannot_be_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(SELF_MADE, "read_process_tail", {"pid": "1"})
    with pytest.raises(ContractError, match="read_process_tail: pid is required"):
        ApiGenerator(Plan(CONTRACT)).generate()


# ── Hoisting a push channel's payload ─────────────────────────────────


def _channel(edit: Any) -> RpcContract:
    def add(raw: dict[str, Any]) -> None:
        edit(raw)

    return _contract(add)


def _payload(*props: str, title: str = "FooEvent") -> dict[str, Any]:
    return {
        "title": title,
        "type": "object",
        "properties": {p: {"type": "string"} for p in props},
    }


def test_a_payload_written_in_place_becomes_a_def_of_its_title() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["push_channels"] = {"foo": {"doc": "d", "schema": _payload("a")}}

    lifted = hoisted(_channel(add))
    assert lifted.push_channels["foo"].schema_ == {"$ref": "#/defs/FooEvent"}
    assert lifted.defs["FooEvent"] == _payload("a")


def test_a_payload_that_shares_a_title_with_a_different_def_is_named_payload() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["defs"]["FooEvent"] = _payload("channel", "a")
        raw["push_channels"] = {"foo": {"doc": "d", "schema": _payload("a")}}

    lifted = hoisted(_channel(add))
    assert lifted.push_channels["foo"].schema_ == {"$ref": "#/defs/FooPayload"}
    assert lifted.defs["FooPayload"] == _payload("a")
    assert lifted.defs["FooEvent"] == _payload("channel", "a")


def test_a_payload_whose_title_and_payload_name_both_clash_fails() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["defs"]["FooEvent"] = _payload("channel", "a")
        raw["defs"]["FooPayload"] = _payload("other")
        raw["push_channels"] = {"foo": {"doc": "d", "schema": _payload("a")}}

    with pytest.raises(ContractError, match="FooEvent is defined twice, differently"):
        hoisted(_channel(add))


def test_hoisting_leaves_the_contract_it_was_given_alone() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["push_channels"] = {"foo": {"doc": "d", "schema": _payload("a")}}

    contract = _channel(add)
    hoisted(contract)
    assert "FooEvent" not in contract.defs
    assert contract.push_channels["foo"].schema_ == _payload("a")


def test_a_push_channel_with_no_doc_is_described_by_its_name() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["push_channels"] = {"foo": {"schema": _payload("a")}}

    text = ModelsGenerator(Plan(_channel(add))).generate()
    assert "A push on ``foo``." in text
    assert "On the wire: ``push_notification`` on the channel ``foo``." in text
    models = _run(text)
    push = models.FooPush
    assert push.model_fields["channel"].default == "foo"
    assert models.PUSH_TYPES["foo"] is push


# ── Types ─────────────────────────────────────────────────────────────


def _annotation(schema: dict[str, Any]) -> tuple[str, Imports]:
    imports = Imports()
    return Types(CONTRACT).annotation(schema, imports), imports


@pytest.mark.parametrize(
    "schema, expected",
    [
        ({}, "JsonValue"),
        (
            {"type": ["object", "array", "string", "number", "integer", "boolean", "null"]},
            "JsonValue",
        ),
        ({"type": "string"}, "str"),
        ({"type": "integer"}, "int"),
        ({"type": "number"}, "float"),
        ({"type": "boolean"}, "bool"),
        ({"type": "null"}, "None"),
        ({"const": "x"}, "Literal['x']"),
        ({"enum": ["a", 2]}, "Literal['a', 2]"),
        ({"type": ["string", "null"]}, "str | None"),
        ({"anyOf": [{"type": "string"}, {"type": "null"}]}, "str | None"),
        ({"anyOf": [{"type": "null"}]}, "None"),
        ({"anyOf": [{"type": "string"}, {"type": "string"}]}, "str"),
        ({"oneOf": [{"type": "integer"}, {"type": "string"}]}, "int | str"),
        ({"type": "array", "items": {"type": "integer"}}, "list[int]"),
        ({"type": "array"}, "list[JsonValue]"),
        (
            {"type": "array", "prefixItems": [{"type": "string"}, {"type": "integer"}]},
            "tuple[str, int]",
        ),
        ({"type": "object"}, "dict[str, JsonValue]"),
        ({"type": "object", "additionalProperties": {"type": "integer"}}, "dict[str, int]"),
        ({"type": "object", "additionalProperties": True}, "dict[str, JsonValue]"),
        ({"$ref": "#/defs/Error"}, "ErrorMessage"),
        ({"$ref": "#/defs/NoArgs"}, "NoArgs"),
    ],
)
def test_a_json_schema_becomes_its_python_annotation(schema: dict[str, Any], expected: str) -> None:
    assert _annotation(schema)[0] == expected


def test_what_an_annotation_needs_is_asked_for() -> None:
    assert "Literal" in _annotation({"const": "x"})[1].typing
    assert "Literal" in _annotation({"enum": ["x"]})[1].typing
    assert "JsonValue" in _annotation({})[1].pydantic
    dated, imports = _annotation({"type": "string", "format": "date-time"})
    assert dated == "datetime"
    assert imports.datetime
    assert not _annotation({"type": "string"})[1].datetime


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "properties": {"a": {"type": "string"}}},
        {"type": "weird"},
        {"format": "x"},
    ],
)
def test_a_schema_it_cannot_say_in_python_fails(schema: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        _annotation(schema)


def _kinds(raw: dict[str, Any]) -> None:
    def kind(value: str | None) -> dict[str, Any]:
        props: dict[str, Any] = {"other": {"type": "string"}}
        if value is not None:
            props["kind"] = {"const": value}
        return {"type": "object", "properties": props}

    raw["defs"]["KindA"] = kind("a")
    raw["defs"]["KindB"] = kind("b")
    raw["defs"]["KindC"] = kind("a")
    raw["defs"]["KindNone"] = kind(None)


def test_a_union_is_told_apart_by_a_field_every_member_fixes_to_its_own_value() -> None:
    types_ = Types(_contract(_kinds))
    assert types_.discriminator(["KindA", "KindB"]) == "kind"
    assert types_.discriminator(["KindA", "KindC"]) is None
    assert types_.discriminator(["KindA", "KindNone"]) is None
    assert types_.discriminator(["KindA", "KindB", "KindC"]) is None


def test_a_union_of_defs_takes_its_name_and_discriminator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(UNION_NAMES, frozenset({"KindA", "KindB"}), "KindAorB")
    types_ = Types(_contract(_kinds))
    named = types_.annotation(
        {"anyOf": [{"$ref": "#/defs/KindA"}, {"$ref": "#/defs/KindB"}, {"type": "null"}]},
        Imports(),
    )
    assert named == "KindAorB | None"
    assert types_.unions["KindAorB"] == ("kind", ["KindA", "KindB"])
    told = types_.annotation(
        {
            "oneOf": [{"$ref": "#/defs/KindA"}, {"$ref": "#/defs/KindB"}],
            "discriminator": {"propertyName": "other"},
        },
        Imports(),
    )
    assert told == "KindAorB"
    assert types_.unions["KindAorB"][0] == "other"


# ── models.py, run ────────────────────────────────────────────────────


def _probe(raw: dict[str, Any]) -> None:
    raw["defs"]["ProbeSub"] = {
        "title": "ProbeSub",
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
    }
    raw["defs"]["ProbeMode"] = {"title": "ProbeMode", "enum": ["fast", "slow"]}
    raw["defs"]["ProbeModel"] = {
        "title": "ProbeModel",
        "type": "object",
        "description": 'A probe: C:\\dir, """quoted""" and a last "word"',
        "properties": {
            "json": {"type": "string", "description": "The json."},
            "activeForm": {"type": "string"},
            "class": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "meta": {"type": "object"},
            "limit": {"type": "integer", "default": 5},
            "name": {"type": "string", "minLength": 2},
            "numbers": {"type": "array", "items": {"type": "integer"}, "default": [1, 2]},
            "sub": {"$ref": "#/defs/ProbeSub", "default": {"x": 3}},
            "mode": {"$ref": "#/defs/ProbeMode"},
            "pair": {
                "type": "array",
                "prefixItems": [{"type": "string"}, {"type": "integer"}],
            },
            "when": {"type": "string", "format": "date-time"},
            "nothing": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": ["json", "activeForm", "name", "mode", "pair"],
    }
    raw["methods"]["get_todos"]["result"] = {"$ref": "#/defs/ProbeModel"}


def _probed() -> types.ModuleType:
    return _models(_contract(_probe))


def _made(models: types.ModuleType, **given: Any) -> Any:
    values: dict[str, Any] = {
        "json": "j",
        "activeForm": "a",
        "name": "nm",
        "mode": "fast",
        "pair": ["p", 1],
    }
    return models.ProbeModel(**{**values, **given})


def test_a_field_igni_names_like_python_or_pydantic_is_aliased() -> None:
    probe = _made(_probed(), **{"class": "c"})
    assert (probe.json_, probe.active_form, probe.class_) == ("j", "a", "c")
    assert probe.model_dump(by_alias=True)["json"] == "j"
    assert probe.model_dump()["activeForm"] == "a"
    by_name = _probed().ProbeModel(
        json_="j", active_form="a", name="nm", mode="slow", pair=("p", 1)
    )
    assert by_name.json_ == "j"


def test_what_a_field_leaves_out_takes_the_contract_s_default() -> None:
    models = _probed()
    probe = _made(models)
    assert probe.class_ is None
    assert probe.when is None
    assert probe.nothing is None
    assert probe.tags == [] and probe.meta == {}
    assert probe.limit == 5
    assert probe.numbers == [1, 2]
    assert probe.sub == models.ProbeSub(x=3)
    other = _made(models)
    probe.tags.append("x")
    probe.numbers.append(3)
    assert other.tags == [] and other.numbers == [1, 2]


def test_a_field_s_bounds_and_types_are_the_contract_s() -> None:
    models = _probed()
    with pytest.raises(ValueError, match="at least 2"):
        _made(models, name="a")
    with pytest.raises(ValueError, match="json"):
        models.ProbeModel(activeForm="a", name="nm", mode="fast", pair=("p", 1))
    with pytest.raises(ValueError, match="mode"):
        _made(models, mode="medium")
    assert get_args(models.ProbeMode.__value__) == ("fast", "slow")
    assert _made(models, pair=["q", 2]).pair == ("q", 2)


def test_a_description_is_the_class_and_field_docstring_however_it_is_written() -> None:
    models = _probed()
    assert models.ProbeModel.__doc__.strip() == 'A probe: C:\\dir, """quoted""" and a last "word"'
    assert models.ProbeSub.__doc__ == "ProbeSub."


def test_a_class_is_a_frame_an_event_a_run_event_or_a_model_by_what_it_is() -> None:
    models = _models()
    wire = _wire()
    plan = Plan(CONTRACT)
    for wire_type, message in CONTRACT.messages.items():
        cls = getattr(models, plan.types.class_name(CONTRACT.message_def(wire_type)))
        props = CONTRACT.defs[CONTRACT.message_def(wire_type)].get("properties", {})
        if message.direction == "to_igni":
            assert issubclass(cls, wire.Frame), wire_type
        elif "run_id" in props and "parent_run_id" in props:
            assert issubclass(cls, wire.RunEvent), wire_type
        else:
            assert issubclass(cls, wire.Event), wire_type
        assert (wire_type in models.EVENT_TYPES) == (message.direction != "to_igni")
        assert (wire_type in models.FRAME_TYPES) == (message.direction != "to_client")
    assert issubclass(models.ProcessRow, wire.Model)
    assert issubclass(models.ProcessArgs, wire.Args)


def test_an_enum_def_is_a_literal_alias_of_its_values() -> None:
    models = _models()
    plan = Plan(CONTRACT)
    enums = [n for n in plan.defs_in | plan.defs_out if plan.types.is_enum(n)]
    assert enums
    for name in enums:
        alias = getattr(models, plan.types.class_name(name))
        assert get_args(alias.__value__) == tuple(CONTRACT.defs[name]["enum"]), name


def test_the_push_table_has_every_channel_the_contract_types() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["push_channels"] = {"foo": {"doc": "d", "schema": _payload("a")}}

    assert _models(_channel(add)).PUSH_TYPES.keys() == {"foo"}
    assert _models().PUSH_TYPES.keys() == CONTRACT.push_channels.keys()


# ── api.py, called ────────────────────────────────────────────────────


class FakeCaller:
    """What a generated method calls: it records, and answers with what it was asked."""

    session_id = "s-1"
    client_id = "c-1"

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-made"

    async def rpc(self, method: str, args: Any, values: dict[str, Any], result: Any) -> Any:
        self.calls.append(("rpc", method, args.__name__, values))
        return ("rpc", method)

    def follow(self, method: str, args: Any, values: dict[str, Any], result: Any) -> Any:
        self.calls.append(("follow", method, args.__name__, values))
        return ("follow", method)

    async def request(self, message: Any, values: dict[str, Any], reply: Any) -> Any:
        self.calls.append(("request", message.__name__, values))
        return ("request", message.__name__)

    async def send(self, message: Any, values: dict[str, Any]) -> None:
        self.calls.append(("send", message.__name__, values))


def _method(api: types.ModuleType, caller: FakeCaller, path: str) -> Any:
    owner, *rest = path.split(".")
    target: Any = (api.IgniApi if owner == "igni" else api.SessionApi)(caller)
    for part in rest:
        target = getattr(target, part)
    return target


def test_a_method_sends_its_wire_name_args_model_and_values() -> None:
    api, _ = _api()
    caller = FakeCaller()
    answer = asyncio.run(_method(api, caller, "igni.processes.tail")(5))
    assert answer == ("rpc", "read_process_tail")
    asyncio.run(_method(api, caller, "igni.processes.tail")(6, tail=7))
    assert caller.calls == [
        ("rpc", "read_process_tail", "ProcessTailArgs", {"pid": 5, "tail": 200}),
        ("rpc", "read_process_tail", "ProcessTailArgs", {"pid": 6, "tail": 7}),
    ]


def test_a_method_on_a_session_fills_its_own_session_id_and_does_not_ask_for_it() -> None:
    api, _ = _api()
    caller = FakeCaller()
    search = _method(api, caller, "session.history.search")
    assert "session_id" not in inspect.signature(search).parameters
    asyncio.run(search("needle"))
    asyncio.run(_method(api, caller, "session.history.get")())
    assert caller.calls[0][3] == {"limit": 50, "query": "needle", "session_id": "s-1"}
    assert caller.calls[1][3] == {"session_id": "s-1"}


def test_a_method_followed_returns_the_call_and_the_others_are_awaited() -> None:
    api, _ = _api()
    caller = FakeCaller()
    for wire_name, path in METHODS.items():
        if ".".join(path.split(".")[:2]) in client_codegen.HAND_WRITTEN_NAMESPACES:
            continue
        method = _method(api, caller, path)
        assert inspect.iscoroutinefunction(method) == (wire_name not in FOLLOWED), wire_name


def test_an_argument_with_an_empty_default_is_sent_empty_not_missing() -> None:
    api, _ = _api()
    caller = FakeCaller()
    run = _method(api, caller, METHODS["run_workflow"])
    run("flow")
    run("flow", args={"k": 1})
    assert caller.calls[0][3] == {"name": "flow", "args": {}}
    assert caller.calls[1][3] == {"name": "flow", "args": {"k": 1}}
    mark = _method(api, caller, METHODS["notifications_mark_read"])
    mark()
    assert caller.calls[2][3] == {"ids": None, "source": None}


def test_an_id_igni_echoes_is_the_callers_or_made_by_the_client() -> None:
    api, _ = _api()
    caller = FakeCaller()
    path = METHODS["execute_scheduled_task"]
    run = _method(api, caller, path)
    run("do it")
    run("do it", run_id="mine")
    assert caller.calls[0][3] == {"description": "do it", "run_id": "run-made"}
    assert caller.calls[1][3] == {"description": "do it", "run_id": "mine"}
    window = _method(api, caller, METHODS["window_model"])
    window(op="hydrate", window="w")
    window(op="hydrate", window="w", **{"token": "mine"})
    field = "token"
    assert caller.calls[2][3][field] == "change-made"
    assert caller.calls[3][3][field] == "mine"


def test_a_message_sent_as_a_method_fills_the_client_id_and_skips_the_envelope() -> None:
    api, _ = _api()
    caller = FakeCaller()
    assert asyncio.run(_method(api, caller, "session.command")("/help")) == ("request", "Command")
    assert asyncio.run(_method(api, caller, "session.typing")("hi")) is None
    assert asyncio.run(_method(api, caller, "igni.auth.cancel_login")()) is None
    assert caller.calls[0] == ("request", "Command", {"text": "/help"})
    assert caller.calls[1] == ("send", "Typing", {"client_id": "c-1", "text": "hi"})
    assert caller.calls[2] == ("send", "CancelLogin", {})
    for path in ("session.command", "session.typing"):
        params = inspect.signature(_method(api, caller, path)).parameters
        assert not set(params) & {"type", "id", "session_id", "event_seq", "client_id"}


def test_a_lone_argument_goes_by_position_and_the_rest_by_keyword() -> None:
    api, _ = _api()
    caller = FakeCaller()
    tail = inspect.signature(_method(api, caller, "igni.processes.tail")).parameters
    assert tail["pid"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert tail["tail"].kind is inspect.Parameter.KEYWORD_ONLY
    assert tail["tail"].default == 200
    upload = inspect.signature(_method(api, caller, "session.upload_attachment")).parameters
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in upload.values())
    assert upload["content_base64"].default is inspect.Parameter.empty
    sole = inspect.signature(_method(api, caller, "session.command")).parameters["text"]
    assert sole.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and sole.default == ""


def test_a_class_with_a_method_named_list_names_the_builtin_in_signatures() -> None:
    _, text = _api()
    tree = ast.parse(text)
    assert any(n.names[0].name == "builtins" for n in tree.body if isinstance(n, ast.Import))
    listing = 0
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
        has_list = any(m.name == "list" for m in methods)
        for method in methods:
            names = (
                {n.id for n in ast.walk(method.returns) if isinstance(n, ast.Name)}
                if method.returns
                else set()
            )
            for arg in method.args.args + method.args.kwonlyargs:
                if arg.annotation:
                    names |= {n.id for n in ast.walk(arg.annotation) if isinstance(n, ast.Name)}
            if has_list:
                assert "list" not in names, (cls.name, method.name)
                listing += 1
    assert listing > 5


def test_every_method_documents_how_it_is_followed_and_who_may_call_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(FOLLOWED, "cancel_run")
    monkeypatch.setitem(UNFOLLOWED, "cancel_run", "its events carry no id of its own.")
    api, _ = _api()
    caller = FakeCaller()
    cancel = _method(api, caller, "session.cancel")
    assert inspect.iscoroutinefunction(cancel)
    assert (
        (cancel.__doc__ or "").rstrip().endswith("Not followed: its events carry no id of its own.")
    )
    assert asyncio.run(cancel()) == ("rpc", "cancel_run")
    approve = _method(api, caller, METHODS["approve_plan"])
    assert FOLLOWED["approve_plan"] in (approve.__doc__ or "")
    model = _method(api, caller, METHODS["window_model"])
    assert ACCESS_NOTES["window"] in (model.__doc__ or "")
    assert ACCESS_NOTES["window"] not in (approve.__doc__ or "")


# ── The tables and the reference ──────────────────────────────────────


def test_the_method_table_says_what_the_contract_says() -> None:
    api, _ = _api()
    plan = Plan(CONTRACT)
    assert set(api.METHODS) == set(plan.placements)
    for wire_name, spec in api.METHODS.items():
        contract = CONTRACT.methods[wire_name]
        assert spec.python == METHODS[wire_name]
        assert spec.scope == contract.scope
        assert spec.access == contract.access
        assert spec.reply == contract.reply
        assert spec.streams == tuple(contract.streams)
        assert spec.may_stream == tuple(contract.may_stream)
        assert spec.duration == contract.duration
        assert spec.timeout_seconds == contract.timeout_seconds
        assert spec.followed == (wire_name in FOLLOWED)
        want = contract.correlate
        got = spec.correlate
        assert (got is None) == (want is None), wire_name
        if want is not None and got is not None:
            assert (got.by, got.source, got.equals) == (want.by, want.source, want.equals)
    assert api.NOT_FOR_CLIENTS == NOT_FOR_CLIENTS
    assert api.UNFOLLOWED == UNFOLLOWED


def test_a_followed_method_has_an_event_alias_of_what_it_causes() -> None:
    api, text = _api()
    plan = Plan(CONTRACT)
    for wire_name in FOLLOWED:
        alias = pascal(wire_name) + "Event"
        assert hasattr(api, alias), wire_name
        classes = plan.event_classes(wire_name)
        line = next(x for x in text.splitlines() if x.startswith(f"type {alias} = "))
        assert line.removeprefix(f"type {alias} = ").split(" | ") == classes


def _reference(contract: RpcContract = CONTRACT) -> str:
    plan = Plan(contract)
    return ReferenceGenerator(plan, ApiGenerator(plan)).generate()


def test_the_reference_has_a_block_for_every_method_a_client_calls() -> None:
    text = _reference()
    plan = Plan(CONTRACT)
    for wire_name, placement in plan.placements.items():
        method = CONTRACT.methods[wire_name]
        assert f"<code>{'' if wire_name in FOLLOWED else 'await '}{placement.path}(" in text
        assert f"Wire method `{wire_name}` · access `{method.access}`" in text
    for name, (reply, path) in client_codegen.MESSAGE_METHODS.items():
        assert f"<code>await {path}(" in text
        assert f"Message `{name}`" + (f", answered by `{reply}`" if reply else "") in text
    assert "<code>await session.typing(text)</code> → <code>None</code>" in text
    assert "<code>await session.command(text)</code> → <code>CommandResult</code>" in text


def test_the_reference_lists_what_is_not_for_clients_and_why() -> None:
    text = _reference()
    section = text[text.index("#### Not for clients") :]
    for wire_name, reason in NOT_FOR_CLIENTS.items():
        assert f"| `{wire_name}` | {reason} |" in section
    for wire_name, reason in client_codegen.MESSAGES_NOT_SENT.items():
        assert f"| `{wire_name}` | {reason} |" in section
    assert text.rstrip().endswith("<!-- api-reference:end -->")
    assert text.startswith("<!-- api-reference:start -->")


def test_the_reference_says_who_may_call_what_only_when_the_contract_does() -> None:
    assert "#### Who may call what" in _reference()

    def clear(raw: dict[str, Any]) -> None:
        raw["access"] = ""

    assert "Who may call what" not in _reference(_contract(clear))


def test_the_reference_says_a_method_is_not_followed_and_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(FOLLOWED, "cancel_run")
    monkeypatch.setitem(UNFOLLOWED, "cancel_run", "nothing tells its events apart.")
    text = _reference()
    assert "Not followed: nothing tells its events apart." in text
    assert "<code>await session.cancel()" in text


def test_the_reference_s_markup_is_escaped_and_rst_is_markdown() -> None:
    assert ReferenceGenerator._html("Call[a<b>, c&d]") == "Call[a&lt;b&gt;, c&amp;d]"
    assert ReferenceGenerator._md(":class:`~igni.Foo` and :meth:`bar` and ``x``") == (
        "`igni.Foo` and `bar` and `x`"
    )
    assert ReferenceGenerator.anchor("igni.processes") == "igniprocesses"
    assert ReferenceGenerator.anchor("Session Runs-x") == "session-runs-x"
    assert "``" not in _reference().split("#### Not for clients")[0].replace("```", "")


# ── Writing and checking ──────────────────────────────────────────────


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A copy of what the generator needs to write, with igni-client's ruff settings."""
    (tmp_path / "contracts").mkdir()
    shutil.copy(CONTRACT_FILE, tmp_path / "contracts" / "rpc-contract.json")
    package = tmp_path / "packages" / "igni-client"
    (package / "src" / "igni_client").mkdir(parents=True)
    shutil.copy(ROOT / README, package / "README.md")
    shutil.copy(ROOT / PACKAGE_CONFIG, package / "pyproject.toml")
    return tmp_path


def test_write_makes_what_is_missing_and_a_second_run_writes_nothing(workspace: Path) -> None:
    client = ClientApi(workspace)
    missing = client.stale()
    assert missing == [workspace / MODELS_OUTPUT, workspace / API_OUTPUT]
    assert client.write() == missing
    assert client.stale() == []
    assert client.write() == []
    for output in (MODELS_OUTPUT, API_OUTPUT, README):
        assert (workspace / output).read_text(encoding="utf-8") == (ROOT / output).read_text(
            encoding="utf-8"
        )


def test_a_file_that_differs_is_stale_and_is_the_only_one_rewritten(workspace: Path) -> None:
    client = ClientApi(workspace)
    client.write()
    api = workspace / API_OUTPUT
    api.write_text(api.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    assert client.stale() == [api]
    assert client.write() == [api]
    assert client.stale() == []


def test_only_the_readme_between_its_markers_is_written(workspace: Path) -> None:
    client = ClientApi(workspace)
    client.write()
    readme = workspace / README
    text = readme.read_text(encoding="utf-8")
    start = text.index("<!-- api-reference:start -->")
    end = text.index("<!-- api-reference:end -->")
    edited = (
        "Before.\n" + text[start : start + 30] + "stale reference\n" + text[end:] + "\nAfter.\n"
    )
    readme.write_text(edited, encoding="utf-8")
    assert client.stale() == [readme]
    assert client.write() == [readme]
    healed = readme.read_text(encoding="utf-8")
    assert healed.startswith("Before.\n<!-- api-reference:start -->")
    assert healed.endswith(text[end:] + "\nAfter.\n")
    assert "stale reference" not in healed


def test_a_missing_readme_is_a_contract_error(workspace: Path) -> None:
    (workspace / README).unlink()
    with pytest.raises(ContractError, match="no <!-- api-reference:start -->"):
        ClientApi(workspace).outputs()


@pytest.mark.parametrize(
    "readme",
    [
        "no markers",
        "<!-- api-reference:start --> only the start",
        "only the end <!-- api-reference:end -->",
        "<!-- api-reference:end --> before <!-- api-reference:start -->",
    ],
)
def test_a_readme_without_its_markers_in_order_is_refused(readme: str) -> None:
    with pytest.raises(ContractError, match="api-reference:start"):
        ClientApi.splice(readme, "NEW")


def test_splice_replaces_everything_between_the_markers_and_nothing_else() -> None:
    readme = "a\n<!-- api-reference:start -->old<!-- api-reference:end -->\nb\n"
    assert (
        ClientApi.splice(readme, "<!-- api-reference:start -->NEW<!-- api-reference:end -->")
        == "a\n<!-- api-reference:start -->NEW<!-- api-reference:end -->\nb\n"
    )


def test_the_command_prints_each_file_it_wrote_and_exits_clean(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(client_codegen, "ROOT", workspace)
    monkeypatch.setattr(client_codegen, "ClientApi", lambda: ClientApi(workspace, CONTRACT))
    assert client_codegen.main() == 0
    assert capsys.readouterr().out.splitlines() == [
        f"wrote {MODELS_OUTPUT}",
        f"wrote {API_OUTPUT}",
    ]
    assert client_codegen.main() == 0
    assert capsys.readouterr().out == ""


def test_the_command_is_what_make_runs() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "tools/client_codegen.py" in makefile or "tools.client_codegen" in makefile


def test_the_module_exports_what_the_tests_and_the_command_use() -> None:
    for name in client_codegen.__all__:
        assert hasattr(client_codegen, name), name
    assert {"ClientApi", "ContractError", "Plan"} <= set(client_codegen.__all__)

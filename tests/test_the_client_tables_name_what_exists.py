"""The contract reader and the hand-kept tables the client is generated from.

``tools/client_contract.py`` reads igni-core's contract strictly; the tables
in ``tools/client_names.py`` and ``tools/client_examples.py`` say what the
generator does with it. A misspelled key in a table would otherwise be
ignored in silence, and the generator must refuse a table that is not
whole.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tools.client_codegen import ContractError, Placement, Plan
from tools.client_contract import (
    CONTRACT_FILE,
    PUSH_PREFIX,
    Correlation,
    MessageContract,
    MethodContract,
    PushChannelContract,
    RpcContract,
)
from tools.client_examples import EXAMPLES
from tools.client_names import (
    CLASS_NAMES,
    FOLLOWED,
    HAND_WRITTEN_NAMESPACES,
    MESSAGE_METHODS,
    MESSAGES_NOT_SENT,
    METHODS,
    NAMESPACES,
    OWN_SESSION_ARG,
    REFERENCE_PAGES,
    SELF_MADE,
    UNION_NAMES,
)
from tools.sdk_docs import DocsError, SdkDocs

ROOT = Path(__file__).resolve().parent.parent
RAW: dict[str, Any] = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
CONTRACT = RpcContract.read()


def _raw() -> dict[str, Any]:
    return copy.deepcopy(RAW)


def _args(wire: str) -> dict[str, Any]:
    name = CONTRACT.ref_name(CONTRACT.methods[wire].args)
    assert name is not None
    return CONTRACT.defs[name]


def _method() -> dict[str, Any]:
    return _raw()["methods"]["get_todos"]


# -- the reader ---------------------------------------------------------


def test_the_reader_reads_the_file_it_is_given(tmp_path: Path) -> None:
    raw = _raw()
    raw["errors"] = {"boom": "it broke"}
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert RpcContract.read(path).errors == {"boom": "it broke"}
    assert RpcContract.read().errors == CONTRACT.errors


def test_a_missing_or_malformed_file_is_not_read(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        RpcContract.read(tmp_path / "nothing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValidationError):
        RpcContract.read(broken)
    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(UnicodeDecodeError):
        RpcContract.read(binary)


def test_a_key_the_models_do_not_know_fails_at_every_level() -> None:
    def in_method(raw: dict[str, Any]) -> None:
        raw["methods"]["get_todos"]["extra_key"] = 1

    def in_message(raw: dict[str, Any]) -> None:
        raw["messages"]["command"]["extra_key"] = 1

    def in_duration(raw: dict[str, Any]) -> None:
        raw["durations"]["instant"]["extra_key"] = 1

    def in_channel(raw: dict[str, Any]) -> None:
        raw["push_channels"]["background_process_done"]["extra_key"] = 1

    def in_correlation(raw: dict[str, Any]) -> None:
        raw["methods"]["approve_plan"]["correlate"]["extra_key"] = 1

    for edit in (in_method, in_message, in_duration, in_channel, in_correlation):
        raw = _raw()
        edit(raw)
        with pytest.raises(ValidationError, match="extra_key"):
            RpcContract.model_validate(raw)


@pytest.mark.parametrize("field", ["area", "summary", "doc", "scope", "access", "args", "result"])
def test_a_method_missing_a_required_field_is_refused(field: str) -> None:
    method = _method()
    del method[field]
    with pytest.raises(ValidationError, match=field):
        MethodContract.model_validate(method)


@pytest.mark.parametrize("field", ["version", "defs", "methods", "messages"])
def test_a_contract_missing_a_required_part_is_refused(field: str) -> None:
    raw = _raw()
    del raw[field]
    with pytest.raises(ValidationError, match=field):
        RpcContract.model_validate(raw)


def test_a_scope_access_direction_or_reply_outside_its_set_is_refused() -> None:
    for field, value in (
        ("scope", "everywhere"),
        ("access", "anyone"),
        ("reply", "shout"),
    ):
        method = _method()
        method[field] = value
        with pytest.raises(ValidationError, match=field):
            MethodContract.model_validate(method)
    message = copy.deepcopy(RAW["messages"]["command"])
    message["direction"] = "sideways"
    with pytest.raises(ValidationError, match="direction"):
        MessageContract.model_validate(message)


def test_what_a_method_leaves_out_has_its_default() -> None:
    method = _method()
    for key in ("streams", "reply", "may_stream", "correlate", "duration", "timeout_seconds"):
        method.pop(key, None)
    read = MethodContract.model_validate(method)
    assert read.streams == []
    assert read.may_stream == []
    assert read.reply == "rpc_response"
    assert read.correlate is None
    assert read.duration == ""
    assert read.timeout_seconds is None
    raw = _raw()
    for key in ("push_channels", "access", "durations", "errors"):
        raw.pop(key, None)
    bare = RpcContract.model_validate(raw)
    assert (bare.push_channels, bare.access, bare.durations, bare.errors) == ({}, "", {}, {})


def test_from_and_schema_are_read_as_source_and_schema_() -> None:
    correlation = Correlation.model_validate({"by": "id", "from": "request.id"})
    assert (correlation.source, correlation.equals) == ("request.id", "")
    assert Correlation.model_validate({"by": "channel"}).source == ""
    with pytest.raises(ValidationError):
        Correlation.model_validate({"by": "id", "source": "request.id"})
    schema = {"$ref": "#/defs/X"}
    assert (
        MessageContract.model_validate({"direction": "both", "doc": "d", "schema": schema}).schema_
        == schema
    )
    assert PushChannelContract.model_validate({"schema": schema}).schema_ == schema
    assert PushChannelContract.model_validate({"schema": schema}).doc == ""
    with pytest.raises(ValidationError):
        PushChannelContract.model_validate({"schema_": schema})


def test_a_timeout_is_a_number_or_none() -> None:
    method = _method()
    method["timeout_seconds"] = 30
    assert MethodContract.model_validate(method).timeout_seconds == 30
    method["timeout_seconds"] = None
    assert MethodContract.model_validate(method).timeout_seconds is None


def test_a_read_contract_cannot_be_changed() -> None:
    with pytest.raises(ValidationError):
        CONTRACT.version = 99  # type: ignore[misc]
    with pytest.raises(ValidationError):
        CONTRACT.methods["get_todos"].area = "x"  # type: ignore[misc]


def test_ref_name_is_the_def_a_ref_names_and_none_for_what_is_no_ref() -> None:
    name = next(iter(CONTRACT.defs))
    assert CONTRACT.ref_name({"$ref": f"#/defs/{name}"}) == name
    assert CONTRACT.ref_name({"$ref": name}) == name
    assert CONTRACT.ref_name({"type": "string"}) is None
    assert CONTRACT.ref_name({"$ref": 3}) is None
    assert CONTRACT.ref_name({}) is None


def test_a_ref_to_no_def_is_a_key_error() -> None:
    with pytest.raises(KeyError, match="names no def"):
        CONTRACT.ref_name({"$ref": "#/defs/NoSuchDef"})


def test_message_def_is_the_def_of_the_messages_schema() -> None:
    for wire, message in CONTRACT.messages.items():
        assert CONTRACT.message_def(wire) == CONTRACT.ref_name(message.schema_)


def test_message_def_refuses_an_unknown_message_and_one_that_is_no_ref() -> None:
    with pytest.raises(KeyError):
        CONTRACT.message_def("no_such_message")
    raw = _raw()
    raw["messages"]["command"]["schema"] = {"type": "object"}
    with pytest.raises(ValueError, match="command is not a \\$ref"):
        RpcContract.model_validate(raw).message_def("command")


def test_a_push_channels_stream_name_starts_with_the_prefix() -> None:
    assert PUSH_PREFIX == "push_notification:"
    streamed = {s for m in CONTRACT.methods.values() for s in [*m.streams, *m.may_stream]}
    assert any(s.startswith(PUSH_PREFIX) for s in streamed)
    assert {s.removeprefix(PUSH_PREFIX) for s in streamed if s.startswith(PUSH_PREFIX)} <= set(
        CONTRACT.push_channels
    )


# -- the tables ---------------------------------------------------------


def test_every_table_key_names_a_method_a_message_or_a_def_that_exists() -> None:
    assert set(OWN_SESSION_ARG) <= set(METHODS)
    for wire in OWN_SESSION_ARG:
        assert CONTRACT.methods[wire].scope == "session", wire
        assert "session_id" in _args(wire)["properties"], wire
    for wire, made in SELF_MADE.items():
        assert wire in METHODS, wire
        args = _args(wire)
        assert set(made) <= set(args["properties"]), wire
        assert not set(made) & set(args.get("required", [])), wire
    assert set(FOLLOWED) <= set(METHODS)
    assert set(CLASS_NAMES) <= set(CONTRACT.defs)
    assert set(MESSAGE_METHODS) <= set(CONTRACT.messages)
    assert set(MESSAGES_NOT_SENT) <= set(CONTRACT.messages)
    assert set(HAND_WRITTEN_NAMESPACES) <= set(NAMESPACES)


def test_a_class_name_is_not_taken_twice() -> None:
    targets = list(CLASS_NAMES.values())
    assert len(targets) == len(set(targets))
    assert not set(targets) & set(CONTRACT.defs) - set(CLASS_NAMES)
    assert len(UNION_NAMES.values()) == len(set(UNION_NAMES.values()))
    assert not set(UNION_NAMES.values()) & set(CONTRACT.defs)
    assert not set(UNION_NAMES.values()) & set(targets)


def test_no_two_methods_share_a_python_path() -> None:
    paths = [Placement.of(w, p).path for w, p in METHODS.items()]
    assert len(paths) == len(set(paths))
    assert not set(paths) & {p for _, (_, p) in MESSAGE_METHODS.items()}


def test_an_example_is_kept_only_for_a_method_or_message_that_exists() -> None:
    assert set(EXAMPLES) <= set(METHODS) | set(MESSAGE_METHODS)


def test_a_message_the_tables_leave_undecided_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(MESSAGES_NOT_SENT, "shutdown")
    with pytest.raises(ContractError, match="undecided.*shutdown"):
        Plan(RpcContract.read())


def test_a_message_the_tables_decide_but_igni_lacks_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(MESSAGES_NOT_SENT, "gone_message", "it is not there")
    with pytest.raises(ContractError, match="unknown.*gone_message"):
        Plan(RpcContract.read())


def test_a_method_placed_against_its_scope_fails_without_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert CONTRACT.methods["get_todos"].scope == "session"
    monkeypatch.setitem(METHODS, "get_todos", "igni.todos.get")
    with pytest.raises(ContractError, match="get_todos has scope session"):
        Plan(RpcContract.read())


def test_two_methods_on_one_path_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    other = next(w for w, p in METHODS.items() if p.startswith("session.") and w != "get_todos")
    monkeypatch.setitem(METHODS, other, METHODS["get_todos"])
    with pytest.raises(ContractError, match="share a name"):
        Plan(RpcContract.read())


def test_a_method_named_that_igni_lacks_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(METHODS, "retired_call", "igni.retired.call")
    with pytest.raises(ContractError, match="retired_call"):
        Plan(RpcContract.read())


def test_a_page_that_names_nothing_the_client_has_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.sdk_docs.REFERENCE_PAGES",
        [*REFERENCE_PAGES, ("extra", "Extra", ("igni.no_such_thing",))],
    )
    with pytest.raises(DocsError, match="extra.*igni.no_such_thing"):
        SdkDocs(ROOT).pages()


def test_a_method_on_no_page_and_a_method_on_two_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    slug, title, sources = REFERENCE_PAGES[0]
    taken = METHODS["check_for_update"]
    monkeypatch.setattr(
        "tools.sdk_docs.REFERENCE_PAGES",
        [(slug, title, tuple(s for s in sources if s != taken)), *REFERENCE_PAGES[1:]],
    )
    with pytest.raises(DocsError, match="no page.*igni.check_for_update"):
        SdkDocs(ROOT).pages()
    monkeypatch.setattr(
        "tools.sdk_docs.REFERENCE_PAGES",
        [*REFERENCE_PAGES, ("again", "Again", (taken,))],
    )
    with pytest.raises(DocsError, match="two reference pages"):
        SdkDocs(ROOT).pages()

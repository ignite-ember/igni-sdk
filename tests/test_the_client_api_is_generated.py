"""igni-client is igni-core's RPC contract, typed: generated from it, and current.

``tools/client_codegen.py`` writes igni-client's models (``igni_client.models``),
its methods (``igni_client.api``) and the API reference in its README from
``contracts/rpc-contract.json``, this repository's copy of the contract
igni-core publishes. Refresh the copy and forget ``make client-api``, and
this fails: a client must never be typed for an igni that does not exist.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tools.client_codegen import (
    ApiGenerator,
    ClientApi,
    ContractError,
    ModelsGenerator,
    Plan,
    ReferenceGenerator,
    push_class,
)
from tools.client_contract import CONTRACT_FILE, RpcContract
from tools.client_names import (
    FOLLOWED,
    METHODS,
    NAMESPACES,
    NOT_FOR_CLIENTS,
    SCOPE_EXCEPTIONS,
    UNFOLLOWED,
)

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = RpcContract.read()


def test_the_checked_in_client_is_what_the_contract_generates() -> None:
    stale = ClientApi(ROOT).stale()
    assert not stale, (
        f"generated from an older contract: {[str(p.relative_to(ROOT)) for p in stale]}. "
        "Run `make client-api`."
    )


def test_the_reader_takes_the_whole_contract() -> None:
    """``tools/client_contract.py`` refuses a key it does not know, so nothing is skipped."""
    raw = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    assert set(raw) <= set(RpcContract.model_fields)
    for method in raw["methods"].values():
        assert set(method) <= {
            "area",
            "summary",
            "doc",
            "scope",
            "access",
            "args",
            "result",
            "streams",
            "reply",
            "may_stream",
            "correlate",
            "duration",
            "timeout_seconds",
        }


def test_every_method_is_a_client_s_or_says_why_not() -> None:
    assert set(METHODS) | set(NOT_FOR_CLIENTS) == set(CONTRACT.methods)
    for wire in NOT_FOR_CLIENTS:
        assert CONTRACT.methods[wire].access in ("page", "platform"), wire
    for wire, path in METHODS.items():
        assert path.split(".")[0] == CONTRACT.methods[wire].scope or wire in SCOPE_EXCEPTIONS


def test_every_method_that_streams_is_followed_or_says_why_not() -> None:
    """A method a client can follow is one igni's contract says how to tell apart.

    That is a method that streams messages of its own, or one that says
    how a client tells its messages from another's — ``correlate``. A
    call whose messages carry the id of another call's (`execute_scheduled_task`
    and the run it starts) is followed too.
    """
    followable = {w for w, m in CONTRACT.methods.items() if m.streams or m.correlate} - set(
        NOT_FOR_CLIENTS
    )
    assert set(FOLLOWED) | set(UNFOLLOWED) == followable
    assert not set(FOLLOWED) & set(UNFOLLOWED)


def test_every_namespace_is_described() -> None:
    groups = {".".join(p.split(".")[:2]) for p in METHODS.values() if p.count(".") == 2}
    assert groups == set(NAMESPACES)


def _contract(edit: Any) -> RpcContract:
    raw = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    edit(raw)
    return RpcContract.model_validate(raw)


def test_a_method_igni_adds_fails_until_it_is_named() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["methods"]["brand_new"] = copy.deepcopy(raw["methods"]["get_todos"])

    with pytest.raises(ContractError, match="brand_new"):
        Plan(_contract(add))


def test_a_union_with_no_name_fails() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["methods"]["get_todos"]["result"] = {
            "anyOf": [{"$ref": "#/defs/UserTurn"}, {"$ref": "#/defs/AssistantTurn"}]
        }

    with pytest.raises(ContractError, match="no name"):
        ApiGenerator(Plan(_contract(add))).generate()


def test_a_key_igni_core_adds_to_the_file_fails_the_read() -> None:
    raw = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    raw["something_new"] = {}
    with pytest.raises(ValueError, match="something_new"):
        RpcContract.model_validate(raw)


def test_typed_push_channels_become_classes_and_type_what_a_call_streams() -> None:
    """igni-core is adding ``push_channels``; the generator types each one when it lands."""

    def add(raw: dict[str, Any]) -> None:
        raw["defs"]["ProcessLinePayload"] = {
            "title": "ProcessLinePayload",
            "type": "object",
            "description": "One line a background process printed.",
            "properties": {
                "pid": {"anyOf": [{"type": "integer"}, {"type": "null"}], "title": "Pid"},
                "line": {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Line"},
            },
            "required": ["pid", "line"],
        }
        raw["push_channels"] = {
            "process_line": {
                "doc": "A line a background process printed.",
                "schema": {"$ref": "#/defs/ProcessLinePayload"},
            }
        }

    plan = Plan(_contract(add))
    models = ModelsGenerator(plan).generate()
    api_gen = ApiGenerator(plan)
    api = api_gen.generate()
    ReferenceGenerator(plan, api_gen).generate()
    ast.parse(models)
    ast.parse(api)
    assert f"class {push_class('process_line')}(PushNotification):" in models
    assert "payload: ProcessLinePayload" in models
    assert "'process_line': ProcessLinePush," in models
    alias = next(
        line for line in api.splitlines() if line.startswith("type StopBackgroundProcessEvent")
    )
    assert "ProcessLinePush" in alias and "PushNotification" in alias


def test_the_generated_files_carry_the_contract_s_version() -> None:
    from tools.client_codegen import API_OUTPUT, MODELS_OUTPUT

    for path in (MODELS_OUTPUT, API_OUTPUT):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert f"(version {CONTRACT.version})" in text, path

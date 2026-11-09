"""Every generated method, through the fake: its arguments as the contract says, its result typed.

For each method in `igni_client.api.METHODS` the test calls the Python method
with a value for every argument, has the fake answer with a value of the
method's result type, and checks both ends: what went out is the contract's
arguments schema, field for field (`contracts/rpc-contract.json`, the copy
this repository builds against); what came back is the result, read into its
model. A message a client sends as a method is checked the same way.
"""

from __future__ import annotations

import inspect
import json
import typing
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from igni_client import Call, IgniClient, Session
from igni_client.api import METHODS, NOT_FOR_CLIENTS, UNFOLLOWED, IgniApi, SessionApi
from igni_client.calls import MethodSpec
from igni_client.follow import RULES
from igni_client.models import EVENT_TYPES, FRAME_TYPES, RpcRequest, Typing
from igni_client.testing import FakeIgni, UnknownFrame, sample
from igni_client.wire import Event, to_wire

CONTRACT_FILE = Path(__file__).resolve().parents[3] / "contracts" / "rpc-contract.json"
CONTRACT: dict[str, Any] = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))


def _validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator({**schema, "defs": CONTRACT["defs"]})


def _target(owner: Any, path: str) -> Any:
    node = owner
    for part in path.split(".")[1:]:
        node = getattr(node, part)
    return node


def _arguments(method: Any) -> dict[str, Any]:
    """A value for every parameter `method` takes, by its annotation."""
    hints = typing.get_type_hints(method)
    return {
        name: sample(hints[name]) for name in inspect.signature(method).parameters if name != "self"
    }


def _result_type(method: Any) -> Any:
    returns = typing.get_type_hints(method)["return"]
    if typing.get_origin(returns) is Call:
        return typing.get_args(returns)[0]
    return returns


def test_every_method_of_the_contract_is_generated_or_not_for_clients() -> None:
    assert set(METHODS) | set(NOT_FOR_CLIENTS) == set(CONTRACT["methods"])
    for wire, spec in METHODS.items():
        assert spec.wire == wire
        contract = CONTRACT["methods"][wire]
        assert (spec.scope, spec.access, spec.reply, list(spec.streams)) == (
            contract["scope"],
            contract["access"],
            contract["reply"],
            contract["streams"],
        )


def test_every_method_is_where_its_scope_says() -> None:
    for wire, spec in METHODS.items():
        owner = IgniApi if spec.python.startswith("igni.") else SessionApi
        if wire == "attach_session":
            continue  # igni.sessions, hand-extended: checked through the client below
        node: Any = owner
        parts = spec.python.split(".")[1:]
        for part in parts[:-1]:
            node = typing.get_type_hints(node)[part]
        assert inspect.isfunction(getattr(node, parts[-1])), spec.python


def test_followed_methods_are_exactly_those_with_a_rule() -> None:
    followed = {w for w, s in METHODS.items() if s.followed}
    assert followed == set(RULES)
    streaming = {w for w, s in METHODS.items() if s.streams}
    assert streaming == followed | set(UNFOLLOWED)


@pytest.mark.parametrize("spec", [METHODS[w] for w in sorted(METHODS)], ids=sorted(METHODS))
async def test_the_method_round_trips_through_the_fake(spec: MethodSpec) -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        owner: IgniClient | Session = igni if spec.python.startswith("igni.") else session
        method = _target(owner, spec.python)
        arguments = _arguments(method)
        expected = sample(_result_type(method))
        fake.methods.answers[spec.wire] = expected
        fake.methods.calls.clear()

        result = await method(**arguments)

    [call] = [c for c in fake.methods.calls if c.method == spec.wire]
    contract = CONTRACT["methods"][spec.wire]
    errors = [e.message for e in _validator(contract["args"]).iter_errors(call.args)]
    assert not errors, f"{spec.wire} sent arguments the contract refuses: {errors}"
    args_def = contract["args"]["$ref"].rsplit("/", 1)[-1]
    assert set(call.args) == set(CONTRACT["defs"][args_def]["properties"]), (
        "every argument is sent, by its wire name"
    )
    for name, value in arguments.items():
        sent = (
            value.model_dump(mode="json", by_alias=True) if isinstance(value, BaseModel) else value
        )
        wire_name = next(
            (p for p in call.args if p.replace("_", "").lower() == name.replace("_", "").lower()),
            name,
        )
        assert json.loads(json.dumps(call.args[wire_name])) == json.loads(
            json.dumps(sent, default=str)
        ), name
    if spec.wire in (
        "get_chat_history",
        "search_chat",
        "truncate_history",
        "get_pending_messages",
        "get_interrupted_runs",
        "discard_interrupted_run",
    ):
        assert call.args["session_id"] == session.id, "a session names itself"
    assert (call.session_id or "") == (
        "" if spec.scope == "igni" or spec.wire == "attach_session" else session.id
    )
    if isinstance(expected, Event):
        assert type(result) is type(expected)
        assert result.model_dump(exclude={"id", "session_id"}) == expected.model_dump(
            exclude={"id", "session_id"}
        )
    else:
        assert result == expected
    result_errors = [
        e.message
        for e in _validator(contract["result"]).iter_errors(
            json.loads(json.dumps(_jsonable(expected), default=str))
        )
    ]
    assert not result_errors, f"the sampled result is not the contract's: {result_errors}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


@pytest.mark.parametrize(
    ("path", "wire_type", "fields"),
    [
        ("session.command", "command", {"text": "/help"}),
        ("session.typing", "typing", {"text": "half a thought"}),
        ("igni.auth.cancel_login", "cancel_login", {}),
    ],
)
async def test_a_message_sent_as_a_method_is_the_contract_s(
    path: str, wire_type: str, fields: dict[str, Any]
) -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        owner: Any = igni if path.startswith("igni.") else session
        answer = await _target(owner, path)(*fields.values())
        if wire_type == "cancel_login":
            await _until(lambda: fake.logins_cancelled == 1)

    [frame] = [r.frame for r in fake.socket.received if r.frame.type == wire_type]
    assert not isinstance(frame, UnknownFrame)
    schema = CONTRACT["messages"][wire_type]["schema"]
    wire = json.loads(to_wire(frame))
    def_name = schema["$ref"].rsplit("/", 1)[-1]
    defaults = {p for p, s in CONTRACT["defs"][def_name]["properties"].items() if "default" in s}
    refused = [
        e.message
        for e in _validator(schema).iter_errors(wire)
        # `typing` travels both ways and is published as igni writes it, every field
        # present; igni reads it with each field's default.
        if not (e.validator == "required" and e.message.split("'")[1] in defaults)
    ]
    assert not refused
    for name, value in fields.items():
        assert getattr(frame, name) == value
    if wire_type == "command":
        assert answer.content == "ran /help" and answer.id == frame.id
    if wire_type == "typing":
        assert isinstance(frame, Typing) and frame.client_id == igni.client_id
        assert frame.session_id == session.id


def test_every_message_has_its_class_and_direction() -> None:
    to_client = {t for t, m in CONTRACT["messages"].items() if m["direction"] != "to_igni"}
    to_igni = {t for t, m in CONTRACT["messages"].items() if m["direction"] != "to_client"}
    assert set(EVENT_TYPES) == to_client
    assert set(FRAME_TYPES) == to_igni
    for wire_type, cls in {**EVENT_TYPES, **FRAME_TYPES}.items():
        schema_def = CONTRACT["messages"][wire_type]["schema"]["$ref"].rsplit("/", 1)[-1]
        properties = set(CONTRACT["defs"][schema_def]["properties"])
        wire_names = {f.alias or n for n, f in cls.model_fields.items()}
        assert wire_names == properties, wire_type
        assert cls.model_fields["type"].default == wire_type


def test_the_rpc_request_a_client_sends_is_the_contract_s() -> None:
    request = RpcRequest(id="rpc-1", method="get_todos", args={"a": 1})
    wire = json.loads(request.wire())
    assert wire == {"type": "rpc_request", "id": "rpc-1", "method": "get_todos", "args": {"a": 1}}
    schema = CONTRACT["messages"]["rpc_request"]["schema"]
    assert not list(_validator(schema).iter_errors(wire))


async def _until(condition: Any, timeout: float = 5.0) -> None:
    import asyncio

    async def wait() -> None:
        while not condition():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait(), timeout)

"""`igni_extension.wire`: the frames the SDK sends, and how each frame the host sends is read."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from igni_extension import HostError
from igni_extension.wire import (
    HOST_MESSAGE,
    Hello,
    HookAnswer,
    HookMessage,
    Op,
    Outcome,
    Reply,
    Request,
    SignalMessage,
    SubscribeOutcome,
)


def read(frame: dict[str, Any]) -> Any:
    return HOST_MESSAGE.validate_json(json.dumps(frame))


def test_the_enums_hold_the_hosts_words() -> None:
    assert [op.value for op in Op] == ["get", "set", "call", "subscribe", "answer"]
    assert [outcome.value for outcome in Outcome] == ["allow", "reject", "modify", "failed"]


@pytest.mark.parametrize(
    ("frame", "model"),
    [
        ({"op": "hello"}, Hello),
        ({"op": "reply"}, Reply),
        ({"op": "signal", "signal": "chat.run_completed"}, SignalMessage),
        ({"op": "hook", "event": "SessionStart"}, HookMessage),
    ],
)
def test_each_frame_is_read_as_the_model_of_its_op(frame: dict[str, Any], model: type) -> None:
    assert type(read(frame)) is model


@pytest.mark.parametrize("frame", [{"op": "get"}, {"op": "nonsense"}, {"event": "x"}])
def test_a_frame_of_an_op_the_host_does_not_send_is_refused(frame: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        read(frame)


def test_a_hello_defaults_to_protocol_one_and_nothing_granted() -> None:
    hello = read({"op": "hello"})

    assert (hello.protocol, hello.schema_version, hello.extension_id, hello.granted) == (
        1,
        "",
        "",
        [],
    )
    assert read({"op": "hello", "protocol": 2, "granted": ["chat"]}).granted == ["chat"]


def test_a_signal_carries_its_name_and_value() -> None:
    signal = read({"op": "signal", "signal": "session.switched", "value": {"id": "s"}})

    assert (signal.signal, signal.value) == ("session.switched", {"id": "s"})
    assert read({"op": "signal", "signal": "x"}).value is None


def test_a_reply_that_says_ok_returns_its_result_even_when_empty() -> None:
    assert read({"op": "reply", "id": 1, "ok": True, "result": [1]}).result_or_raise() == [1]
    assert read({"op": "reply", "id": 1, "ok": True}).result_or_raise() is None


@pytest.mark.parametrize("reply_id", [1, "r-1", None])
def test_a_reply_may_be_numbered_by_text_or_not_at_all(reply_id: int | str | None) -> None:
    assert read({"op": "reply", "id": reply_id, "ok": True}).id == reply_id


@pytest.mark.parametrize(
    ("error", "code", "message"),
    [
        (None, "failed", "refused"),
        ({}, "failed", "refused"),
        ({"code": "", "message": ""}, "failed", "refused"),
        ({"code": "not_found"}, "not_found", "refused"),
        ({"code": "invalid", "message": "bad value"}, "invalid", "bad value"),
    ],
)
def test_a_refusal_without_a_body_or_with_an_empty_one_says_failed_and_refused(
    error: dict[str, str] | None, code: str, message: str
) -> None:
    reply = read({"op": "reply", "id": 1, "ok": False, "error": error})

    with pytest.raises(HostError) as refused:
        reply.result_or_raise()
    assert (refused.value.code, str(refused.value)) == (code, message)


def test_a_reply_without_an_ok_is_a_refusal() -> None:
    with pytest.raises(HostError):
        read({"op": "reply", "id": 1, "result": 1}).result_or_raise()


def test_a_hook_decides_only_with_an_id() -> None:
    assert read({"op": "hook", "id": "h", "event": "PlanSubmit"}).decides
    assert not read({"op": "hook", "event": "SessionStart"}).decides


def test_a_request_refuses_a_field_the_host_does_not_know() -> None:
    with pytest.raises(ValidationError):
        Request(op=Op.GET, nonsense=1)  # type: ignore[call-arg]


def test_a_hook_answer_refuses_a_field_the_host_does_not_know() -> None:
    with pytest.raises(ValidationError):
        HookAnswer(hook="h", outcome=Outcome.ALLOW, nonsense=1)  # type: ignore[call-arg]


def test_a_subscribe_names_the_signals_and_sends_nothing_else() -> None:
    frame = json.loads(Request.subscribe(["a.b", "c.d"]).numbered(2).frame())

    assert frame == {"id": 2, "op": "subscribe", "signals": ["a.b", "c.d"]}


def test_numbering_a_request_copies_it_and_keeps_every_other_field() -> None:
    request = Request(
        op=Op.SET, path="chat.processing", window="w", session="s", value=False, params={"a": 1}
    )

    numbered = request.numbered(9)

    assert request.id is None
    assert numbered.id == 9
    assert numbered.model_copy(update={"id": None}) == request


def test_a_set_to_false_or_zero_is_sent_but_a_value_left_unset_is_not() -> None:
    assert json.loads(Request(op=Op.SET, path="p", value=False).frame())["value"] is False
    assert json.loads(Request(op=Op.SET, path="p", value=0).frame())["value"] == 0
    assert "value" not in json.loads(Request(op=Op.GET, path="p").frame())


def test_an_answer_leaves_out_an_empty_reason_and_an_unset_value() -> None:
    allow = Request.answer(HookAnswer(hook="h", outcome=Outcome.ALLOW))
    modify = Request.answer(HookAnswer(hook="h", outcome=Outcome.MODIFY, value={"plan": "p"}))
    failed = Request.answer(HookAnswer(hook="h", outcome=Outcome.FAILED, reason="raised"))

    assert allow.params == {"hook": "h", "outcome": "allow"}
    assert modify.params == {"hook": "h", "outcome": "modify", "value": {"plan": "p"}}
    assert failed.params == {"hook": "h", "outcome": "failed", "reason": "raised"}


def test_unicode_and_large_payloads_survive_the_frame() -> None:
    text = "héllo ✓ " * 50_000
    frame = Request(op=Op.CALL, path="chat.post", params={"text": text}).numbered(1).frame()

    assert json.loads(frame)["params"]["text"] == text


def test_a_subscribe_outcome_defaults_to_nothing_and_reads_each_list() -> None:
    empty = SubscribeOutcome.model_validate({})
    assert (empty.subscribed, empty.not_granted, empty.unknown) == ([], [], [])

    outcome = SubscribeOutcome.model_validate(
        {"subscribed": ["a"], "not_granted": ["b"], "unknown": ["c"]}
    )
    assert (outcome.subscribed, outcome.not_granted, outcome.unknown) == (["a"], ["b"], ["c"])


def test_a_bad_frame_is_reported_against_the_model_its_op_names_only() -> None:
    with pytest.raises(ValidationError) as bad:
        read({"op": "reply", "id": [1]})

    assert {error["loc"][0] for error in bad.value.errors()} == {"reply"}

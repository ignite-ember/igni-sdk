"""The host socket's messages, as `igni_extension.wire` writes and reads them."""

from __future__ import annotations

import json

import pytest

from igni_extension import Caller, CallerKind, HostError
from igni_extension.wire import (
    HOST_MESSAGE,
    HookAnswer,
    HookMessage,
    Op,
    Outcome,
    Reply,
    Request,
)


def test_a_request_sends_only_what_the_host_would_not_assume() -> None:
    get = Request(op=Op.GET, path="chat.processing").numbered(3)
    assert json.loads(get.frame()) == {"id": 3, "op": "get", "path": "chat.processing"}

    call = Request(op=Op.CALL, path="chat.post", session="s-1", params={"text": "hi"}).numbered(4)
    assert json.loads(call.frame()) == {
        "id": 4,
        "op": "call",
        "path": "chat.post",
        "session": "s-1",
        "params": {"text": "hi"},
    }


def test_an_answer_carries_the_hook_answer_as_its_params() -> None:
    answer = HookAnswer(hook="h-1", outcome=Outcome.REJECT, reason="no")
    frame = json.loads(Request.answer(answer).numbered(1).frame())
    assert frame == {
        "id": 1,
        "op": "answer",
        "params": {"hook": "h-1", "outcome": "reject", "reason": "no"},
    }


def test_a_dialog_waits_on_the_person() -> None:
    assert Request(op=Op.CALL, path="ui.show_dialog").waits_on_the_person
    assert not Request(op=Op.CALL, path="chat.post").waits_on_the_person


def test_a_refusal_raises_the_hosts_code() -> None:
    reply = HOST_MESSAGE.validate_json(
        json.dumps(
            {"op": "reply", "id": 1, "ok": False, "error": {"code": "not_granted", "message": "no"}}
        )
    )
    assert isinstance(reply, Reply)
    with pytest.raises(HostError) as refused:
        reply.result_or_raise()
    assert refused.value.code == "not_granted"


def test_a_told_hook_decides_nothing() -> None:
    told = HOST_MESSAGE.validate_json(
        json.dumps({"op": "hook", "id": None, "event": "SessionStart"})
    )
    assert isinstance(told, HookMessage) and not told.decides


def test_a_hook_names_its_caller_from_the_principal() -> None:
    principal = {"kind": "person", "id": "u-ada", "org": "org-acme", "group": "g-legal"}
    hook = HookMessage(op="hook", id="h-1", event="PlanSubmit", principal=principal)

    assert hook.caller == Caller(
        kind=CallerKind.PERSON, id="u-ada", org="org-acme", group="g-legal"
    )
    assert hook.principal == principal
    assert "caller" not in json.loads(hook.model_dump_json())


@pytest.mark.parametrize("principal", [None, {}, {"kind": "person"}, {"kind": "robot", "id": "r"}])
def test_a_hook_without_a_readable_principal_has_no_caller(
    principal: dict[str, str] | None,
) -> None:
    hook = HookMessage(op="hook", event="SessionStart", principal=principal)

    assert hook.caller is None

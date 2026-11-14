"""What a frame puts on the wire when a value is not JSON."""

from __future__ import annotations

import json
import math

import pytest
from pydantic import ValidationError

from igni_client.models import RpcRequest
from igni_client.wire import Event, Model, RunEvent


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_a_number_json_cannot_hold_is_refused_not_sent_as_invalid_json(value: float) -> None:
    request = RpcRequest(id="1", method="m", args={"a": value})
    with pytest.raises(ValueError, match="not valid JSON"):
        request.wire()


def test_an_ordinary_number_is_sent() -> None:
    sent = json.loads(RpcRequest(id="1", method="m", args={"a": 1.5, "b": 0}).wire())
    assert sent["args"] == {"a": 1.5, "b": 0}


def test_a_number_json_cannot_hold_is_refused_wherever_it_sits_in_the_frame() -> None:
    nested = RpcRequest(id="1", method="m", args={"a": {"b": [1, {"c": math.nan}]}})

    with pytest.raises(ValueError, match="not valid JSON"):
        nested.wire()


def test_a_frame_sends_its_type_first_then_only_the_fields_it_was_given() -> None:
    wire = RpcRequest(id="1", method="m", args={}).wire()

    assert json.loads(wire) == {"type": "rpc_request", "id": "1", "method": "m", "args": {}}
    assert wire.startswith('{"type": "rpc_request"')
    assert "session_id" not in wire, "left at its default, igni applies its own"


def test_a_field_given_its_default_value_is_still_sent() -> None:
    sent = json.loads(RpcRequest(id="1", method="m", args={}, session_id="").wire())

    assert sent["session_id"] == ""


def test_text_is_sent_as_json_escapes_that_read_back_the_same() -> None:
    text = 'héllo "wörld" ☃ \n'

    wire = RpcRequest(id="1", method="m", args={"text": text}).wire()

    assert wire.isascii(), "the frame is plain ASCII on the wire"
    assert json.loads(wire)["args"]["text"] == text


def test_what_igni_answers_keeps_a_field_a_newer_igni_adds() -> None:
    class Answer(Model):
        known: str = ""

    answer = Answer.model_validate({"known": "a", "added_in_a_newer_igni": 3})

    assert answer.known == "a"
    assert answer.model_extra == {"added_in_a_newer_igni": 3}


def test_a_message_from_igni_has_empty_ids_and_no_place_in_a_stream_until_it_says_so() -> None:
    event = Event(type="info_message")
    run_event = RunEvent(type="run_started")

    assert (event.id, event.session_id, event.event_seq) == ("", "", 0)
    assert (run_event.run_id, run_event.parent_run_id) == ("", "")
    assert RunEvent(type="x", run_id="r", parent_run_id="p").parent_run_id == "p"
    with pytest.raises(ValidationError, match="type"):
        Event.model_validate({})

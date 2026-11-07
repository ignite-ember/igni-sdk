"""The gateway's `/v1/commands` lines and refusals, parsed into their models."""

from __future__ import annotations

import httpx
import pytest

from igni_client import AuthError, NotAllowed, Unavailable
from igni_client.commands.wire import (
    STREAM_LINE,
    CommandAccepted,
    CommandDone,
    CommandRequest,
    GatewayRefusal,
    OutputLine,
    ProducerRef,
    UnknownLine,
    VmWoken,
)


def test_each_line_is_told_apart_by_the_key_it_carries() -> None:
    accepted = STREAM_LINE.validate_json('{"command": {"command_id": "c-1", "command": "ls"}}')
    woken = STREAM_LINE.validate_json('{"woken": {"how": "paused", "node": "n1", "ms": 12.345}}')
    output = STREAM_LINE.validate_json('{"stream": "stderr", "data_b64": "b2sK"}')
    done = STREAM_LINE.validate_json('{"done": true, "exit_code": 0, "duration_ms": 5}')
    unknown = STREAM_LINE.validate_json('{"progress": 0.5}')

    assert isinstance(accepted, CommandAccepted) and accepted.command.command_id == "c-1"
    assert isinstance(woken, VmWoken) and woken.woken.ms == 12.345
    assert isinstance(output, OutputLine) and output.output().text == "ok\n"
    assert isinstance(done, CommandDone) and done.finished().ok
    assert isinstance(unknown, UnknownLine) and unknown.model_extra == {"progress": 0.5}


def test_a_request_outside_the_gateway_s_limits_is_refused_before_it_is_sent() -> None:
    with pytest.raises(ValueError, match="16 KiB"):
        CommandRequest.check("", 10)
    with pytest.raises(ValueError, match="timeout_s"):
        CommandRequest.check("ls", 0)
    with pytest.raises(ValueError, match="'person:<id>'"):
        ProducerRef.parse("robot:r-1")


@pytest.mark.parametrize(
    ("status", "body", "error", "reason"),
    [
        (401, {"error": "invalid_token"}, AuthError, "invalid_token"),
        (403, {"detail": "not your VM"}, NotAllowed, "not your VM"),
        (400, {"error_description": "bad producer"}, NotAllowed, "bad producer"),
        (503, None, Unavailable, "busy"),
    ],
)
def test_a_refusal_says_why_in_the_gateway_s_words(
    status: int, body: dict[str, str] | None, error: type[Exception], reason: str
) -> None:
    response = httpx.Response(status, json=body) if body else httpx.Response(status, text="busy")

    refused = GatewayRefusal.of(response).error()

    assert isinstance(refused, error) and reason in str(refused)

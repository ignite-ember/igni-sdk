"""The gateway's `/v1/commands` lines and refusals, parsed into their models."""

from __future__ import annotations

import logging

import httpx
import pytest

from igni_client import AuthError, Fleet, NotAllowed, Person, Unavailable
from igni_client.commands import CommandRun
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


def _run(*lines: str, status: int = 200) -> CommandRun:
    """A run of `ls` whose gateway answers with `lines`, one NDJSON line each."""

    def gateway(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content="".join(f"{line}\n" for line in lines))

    fleet = Fleet(
        "http://gateway.test",
        auth=Person("t-ada"),
        http=httpx.AsyncClient(transport=httpx.MockTransport(gateway)),
    )
    request = CommandRequest(producer=ProducerRef.parse("person:u-ada"), command="ls", timeout_s=5)
    return CommandRun(fleet, request, "t-ada")


async def test_a_line_the_gateway_garbled_is_passed_over_and_the_run_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    run = _run(
        "{not json",
        "",
        '{"stream": "stdout", "data_b64": "b2sK"}',
        '{"progress": 0.5}',
        '{"done": true, "exit_code": 0}',
    )

    with caplog.at_level(logging.WARNING, logger="igni_client.commands.run"):
        finished = await run.wait()

    assert finished.ok and run.stdout == "ok\n"
    assert len(caplog.records) == 1, "only the garbled line is worth a warning"


async def test_a_run_the_gateway_ends_without_a_result_says_so() -> None:
    run = _run('{"stream": "stderr", "data_b64": "b29wcw=="}')

    finished = await run.wait()

    assert not finished.ok and run.stderr == "oops"
    assert finished.error == "the gateway ended the output without a result"


async def test_a_run_is_read_once() -> None:
    run = _run('{"done": true, "exit_code": 0}')
    await run.wait()

    with pytest.raises(RuntimeError, match="read once"):
        await run.wait()


async def test_a_refused_run_raises_the_gateway_s_reason() -> None:
    run = _run('{"detail": "not your VM"}', status=403)

    with pytest.raises(NotAllowed, match="not your VM"):
        await run.wait()

"""The gateway's `/v1/commands` lines and refusals, parsed into their models."""

from __future__ import annotations

import binascii
import json
import logging
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from igni_client import AuthError, Fleet, NotAllowed, Person, Unavailable, commands
from igni_client.commands import (
    CommandFinished,
    CommandOutput,
    CommandRecord,
    CommandRun,
    Commands,
    Me,
    Wake,
    wire,
)
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


def test_the_commands_package_names_its_models_and_its_wire() -> None:
    assert sorted(commands.__all__) == [
        "CommandFinished",
        "CommandOutput",
        "CommandRecord",
        "CommandRun",
        "Commands",
        "Me",
        "Wake",
    ]
    assert sorted(wire.__all__) == [
        "CommandAccepted",
        "CommandDone",
        "CommandRequest",
        "GatewayErrorBody",
        "GatewayRefusal",
        "OutputLine",
        "ProducerRef",
        "STREAM_LINE",
        "StreamLine",
        "UnknownLine",
        "VmWoken",
    ]


def test_a_record_and_a_wake_keep_what_the_gateway_adds() -> None:
    record = CommandRecord.model_validate({"command_id": "c-1", "asked_by": "person:u-ada"})
    wake = Wake.model_validate({"how": "cold", "ms": 30, "region": "eu"})

    assert (record.command_id, record.command, record.state) == ("c-1", "", "")
    assert record.model_extra == {"asked_by": "person:u-ada"}
    assert (wake.how, wake.node, wake.ms) == ("cold", "", 30.0) and isinstance(wake.ms, float)
    assert wake.model_extra == {"region": "eu"}
    assert Wake().ms is None


def test_who_the_gateway_says_this_is_and_how_a_command_ended() -> None:
    me = Me.model_validate({"producer": "space:sp-1", "plan": "team"})

    assert (me.kind, me.id, me.org, me.group, me.expires_at) == ("space", "sp-1", "", None, 0)
    assert me.model_extra == {"plan": "team"}
    assert not CommandFinished(exit_code=0, error="cancelled").ok
    assert CommandFinished().streamed
    assert CommandOutput(stream="stdout", data=b"caf\xe9").text == "caf\ufffd"


def test_a_request_outside_the_gateway_s_limits_is_refused_before_it_is_sent() -> None:
    with pytest.raises(ValueError, match="16 KiB"):
        CommandRequest.check("", 10)
    with pytest.raises(ValueError, match="1 byte to 16 KiB"):
        CommandRequest.check("x" * (16 * 1024 + 1), 10)
    with pytest.raises(ValueError, match="timeout_s"):
        CommandRequest.check("ls", 0)
    with pytest.raises(ValueError, match="timeout_s is 1 to 3600"):
        CommandRequest.check("ls", 3601)
    with pytest.raises(ValueError, match="'person:<id>'"):
        ProducerRef.parse("robot:r-1")
    with pytest.raises(ValueError, match="'person:<id>'"):
        ProducerRef.parse("person:")
    CommandRequest.check("x" * 16 * 1024, 3600)
    CommandRequest.check("x", 1)


def test_a_done_line_s_result_holds_only_what_the_gateway_sent() -> None:
    done = STREAM_LINE.validate_json('{"done": true, "exit_code": 0, "node": "n1"}')

    assert isinstance(done, CommandDone)
    assert done.finished().model_dump(exclude_unset=True) == {"exit_code": 0, "node": "n1"}


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


@pytest.mark.parametrize(
    ("status", "content", "message"),
    [
        (404, '{"detail": "no such VM"}', "the gateway refused: no such VM"),
        (422, '{"detail": [{"msg": "bad"}]}', "the gateway refused: [{'msg': 'bad'}]"),
        (403, '{"error": {"message": "m"}}', "the gateway refused: {'message': 'm'}"),
        (401, '{"error_description": 5}', "the gateway refused the credential: 5"),
        (403, '{"detail": "", "error": "denied"}', "the gateway refused: denied"),
        (400, "[1, 2]", "the gateway refused: [1, 2]"),
        (502, "", "the gateway answered 502: "),
    ],
)
def test_a_refusal_s_message_is_the_gateway_s_reason_as_it_sent_it(
    status: int, content: str, message: str
) -> None:
    assert str(GatewayRefusal.of(httpx.Response(status, text=content)).error()) == message


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


async def test_a_line_that_is_json_but_not_an_object_is_passed_over_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    run = _run("[1]", "5", '"x"', "null", '{"done": true, "exit_code": 0}')

    with caplog.at_level(logging.WARNING, logger="igni_client.commands.run"):
        finished = await run.wait()

    assert finished.ok and len(caplog.records) == 4


async def test_a_record_and_a_wake_are_none_until_their_lines_arrive() -> None:
    bare = _run('{"done": true, "exit_code": 0}')
    told = _run(
        '{"command": {"command_id": "c-1", "command": "ls", "state": "running"}}',
        '{"woken": {"how": "paused", "node": "n1", "ms": 12.345}}',
        '{"done": true, "exit_code": 0}',
    )

    assert bare.record is None and bare.woken is None
    await bare.wait()
    await told.wait()

    assert bare.record is None and bare.woken is None
    assert told.record == CommandRecord(command_id="c-1", command="ls", state="running")
    assert told.woken == Wake(how="paused", node="n1", ms=12.345)


async def test_a_record_or_a_wake_that_does_not_fit_its_model_is_kept_as_sent() -> None:
    run = _run(
        '{"command": {"command_id": 5, "command": "ls"}}',
        '{"woken": {"how": "paused", "node": null, "ms": "fast"}}',
        '{"done": true, "exit_code": 0}',
    )

    await run.wait()

    assert run.record is not None and run.woken is not None
    assert dict(run.record) == {"command_id": 5, "command": "ls", "state": ""}
    assert dict(run.woken) == {"how": "paused", "node": None, "ms": "fast"}


async def test_a_line_is_taken_by_the_first_key_it_carries() -> None:
    run = _run(
        '{"command": {"command_id": "c-1"}, "woken": {"how": "cold"}, "done": true}',
        '{"woken": {"how": "cold"}, "done": true, "exit_code": 9}',
        '{"done": true, "exit_code": 0, "stream": "stdout", "data_b64": "b2sK"}',
    )

    finished = await run.wait()

    assert run.record is not None and run.record.command_id == "c-1"
    assert run.woken is not None and run.woken.how == "cold"
    assert finished.exit_code == 0 and run.stdout == ""


@pytest.mark.parametrize("done", ["1", '"yes"', "true"])
async def test_any_true_done_ends_the_run(done: str) -> None:
    run = _run(f'{{"done": {done}, "exit_code": 0}}')

    finished = await run.wait()

    assert finished.ok and finished.model_dump(exclude_unset=True) == {"exit_code": 0}


@pytest.mark.parametrize(
    "line", ['{"done": true, "exit_code": "x"}', '{"done": true, "duration_ms": 1.5}']
)
async def test_a_done_line_that_does_not_fit_is_raised_not_passed_over(line: str) -> None:
    run = _run(line)

    with pytest.raises(ValidationError, match="1 validation error for CommandFinished"):
        await run.wait()


async def test_an_output_line_with_no_data_is_an_empty_piece_of_output() -> None:
    run = _run(
        '{"stream": "stdout", "data_b64": null}',
        '{"stream": "stderr"}',
        '{"done": true, "exit_code": 0}',
    )

    outputs = [output async for output in run]

    assert outputs == [
        CommandOutput(stream="stdout", data=b""),
        CommandOutput(stream="stderr", data=b""),
    ]


@pytest.mark.parametrize("data", ['"b2s"', "5"])
async def test_output_that_is_not_base64_is_raised(data: str) -> None:
    run = _run(f'{{"stream": "stdout", "data_b64": {data}}}', '{"done": true, "exit_code": 0}')

    with pytest.raises(binascii.Error):
        await run.wait()


async def test_a_gateway_that_does_not_answer_is_unavailable() -> None:
    def gateway(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    fleet = Fleet(
        "http://gateway.test",
        auth=Person("t-ada"),
        http=httpx.AsyncClient(transport=httpx.MockTransport(gateway)),
    )
    request = CommandRequest(producer=ProducerRef.parse("person:u-ada"), command="ls", timeout_s=5)

    with pytest.raises(Unavailable, match="the gateway at http://gateway.test did not answer"):
        await CommandRun(fleet, request, "t-ada").wait()


class Gateway:
    """The gateway's `/v1/me` and `/v1/commands`, answering `me` and a run that exits 0."""

    def __init__(self, me: httpx.Response | None = None) -> None:
        self.me = me or httpx.Response(200, json={"producer": "person:u-ada", "org": "org-acme"})
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/v1/me":
            return self.me
        return httpx.Response(200, content='{"done": true, "exit_code": 0}\n')

    def commands(self) -> Commands:
        transport = httpx.MockTransport(self)
        http = httpx.AsyncClient(transport=transport)
        return Commands(Fleet("http://gateway.test", auth=Person("t-ada"), http=http))

    def bodies(self) -> list[Any]:
        return [json.loads(r.content) for r in self.requests if r.url.path == "/v1/commands"]


async def test_a_run_asks_who_it_is_once_and_sends_the_gateway_s_body() -> None:
    gateway = Gateway()
    commands = gateway.commands()

    await (await commands.run("ls", timeout_s=5)).wait()
    await (await commands.run("id")).wait()
    await (await commands.run("pwd", producer="app:app-bot")).wait()

    assert [r.url.path for r in gateway.requests].count("/v1/me") == 1
    assert gateway.bodies() == [
        {"producer": {"kind": "person", "id": "u-ada"}, "command": "ls", "timeout_s": 5},
        {"producer": {"kind": "person", "id": "u-ada"}, "command": "id", "timeout_s": 600},
        {"producer": {"kind": "app", "id": "app-bot"}, "command": "pwd", "timeout_s": 600},
    ]
    assert gateway.requests[-1].headers["Authorization"] == "Bearer t-ada"


async def test_a_timeout_is_sent_as_it_was_given() -> None:
    gateway = Gateway()
    commands = gateway.commands()
    fractional: Any = 5.5
    whole: Any = 5.0

    await (await commands.run("ls", timeout_s=fractional)).wait()
    await (await commands.run("ls", timeout_s=whole)).wait()

    sent = [body["timeout_s"] for body in gateway.bodies()]
    assert sent == [5.5, 5.0] and all(isinstance(timeout, float) for timeout in sent)


@pytest.mark.parametrize(
    ("command", "timeout_s", "producer", "message"),
    [
        ("", 600, None, "1 byte to 16 KiB"),
        ("ls", 0, None, "timeout_s is 1 to 3600"),
        ("ls", 600, "person:", "'person:<id>'"),
        ("ls", 600, "robot:r-1", "'person:<id>'"),
    ],
)
async def test_a_run_outside_the_gateway_s_limits_is_refused_before_it_is_asked(
    command: str, timeout_s: int, producer: str | None, message: str
) -> None:
    gateway = Gateway()

    with pytest.raises(ValueError, match=message):
        await gateway.commands().run(command, timeout_s=timeout_s, producer=producer)

    assert gateway.requests == []


@pytest.mark.parametrize(
    ("answer", "error", "message"),
    [
        (httpx.Response(401, json={"error": "invalid_token"}), AuthError, "credential"),
        (httpx.Response(403, json={"detail": "suspended"}), NotAllowed, "suspended"),
        (httpx.Response(503, text="busy"), Unavailable, "answered 503: busy"),
    ],
)
async def test_who_this_is_is_refused_in_the_gateway_s_words(
    answer: httpx.Response, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        await Gateway(answer).commands().me()


async def test_who_this_is_answered_in_something_other_than_json_is_a_json_error() -> None:
    with pytest.raises(json.JSONDecodeError, match="Expecting value"):
        await Gateway(httpx.Response(200, text="<html>")).commands().me()

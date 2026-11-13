"""The gateway's `/v1/commands` lines and refusals, parsed into their models."""

from __future__ import annotations

import binascii
import json
import logging
from collections.abc import AsyncIterator
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
    assert Wake.model_validate({"ms": "12"}).ms == 12.0


def test_who_the_gateway_says_this_is_and_how_a_command_ended() -> None:
    me = Me.model_validate({"producer": "space:sp-1", "plan": "team"})

    assert (me.kind, me.id, me.org, me.group, me.expires_at) == ("space", "sp-1", "", None, 0)
    assert me.model_extra == {"plan": "team"}
    assert (Me(producer="person").kind, Me(producer="person").id) == ("person", "")
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


def test_a_command_s_limit_is_counted_in_bytes() -> None:
    CommandRequest.check("\u00e9" * 8 * 1024, 10)
    with pytest.raises(ValueError, match="1 byte to 16 KiB"):
        CommandRequest.check("\u00e9" * (8 * 1024 + 1), 10)


def test_a_command_that_has_not_ended_with_an_exit_code_is_not_ok() -> None:
    assert not CommandFinished().ok
    assert not CommandFinished(exit_code=1).ok
    assert CommandFinished(exit_code=0).ok
    with pytest.raises(ValidationError):
        CommandOutput.model_validate({"stream": "stdin", "data": b""})


def test_an_output_line_carries_its_output_there_and_back() -> None:
    output = CommandOutput(stream="stderr", data=b"\x00caf\xe9\n")

    line = OutputLine.of(output)

    assert line.model_dump() == {"stream": "stderr", "data_b64": "AGNhZukK"}
    assert STREAM_LINE.validate_json(line.model_dump_json()) == line
    assert line.output() == output


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
        (
            403,
            '{"detail": "", "error": null}',
            'the gateway refused: {"detail": "", "error": null}',
        ),
        (418, '{"detail": "teapot"}', "the gateway answered 418: teapot"),
    ],
)
def test_a_refusal_s_message_is_the_gateway_s_reason_as_it_sent_it(
    status: int, content: str, message: str
) -> None:
    assert str(GatewayRefusal.of(httpx.Response(status, text=content)).error()) == message


@pytest.mark.parametrize(
    ("content", "headers", "reason"),
    [
        ('{"detail": "not your VM"}'.encode("utf-16"), {}, "not your VM"),
        (b'\xef\xbb\xbf{"detail": "not your VM"}', {}, "not your VM"),
        (
            '{"detail": "caf\u00e9"}'.encode(),
            {"content-type": "application/json; charset=latin-1"},
            "caf\u00e9",
        ),
    ],
)
def test_a_refusal_is_read_from_its_bytes_whatever_their_encoding(
    content: bytes, headers: dict[str, str], reason: str
) -> None:
    refused = GatewayRefusal.of(httpx.Response(403, content=content, headers=headers))

    assert str(refused.error()) == f"the gateway refused: {reason}"


def test_a_producer_s_id_is_everything_after_its_first_colon() -> None:
    assert ProducerRef.parse("space:sp:eu:1") == ProducerRef(kind="space", id="sp:eu:1")


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
        " \t ",
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
    # igni-client 0.1.0 raised AttributeError or TypeError here; passing over is on purpose.
    run = _run(
        "[1]",
        "5",
        '"x"',
        "null",
        '{"stream": "stdout", "data_b64": "b2sK"}',
        '{"done": true, "exit_code": 0}',
    )

    with caplog.at_level(logging.WARNING, logger="igni_client.commands.run"):
        finished = await run.wait()

    assert finished.ok and run.stdout == "ok\n"
    assert [record.getMessage() for record in caplog.records] == [
        f"igni-client: passing over a line the gateway sent: {text}"
        for text in ("[1]", "5", '"x"', "null")
    ]


async def test_a_long_line_that_is_not_an_object_is_cut_to_200_characters_in_the_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    long = json.dumps(["x" * 300])
    run = _run(long, '{"done": true, "exit_code": 0}')

    with caplog.at_level(logging.WARNING, logger="igni_client.commands.run"):
        await run.wait()

    assert [record.getMessage() for record in caplog.records] == [
        f"igni-client: passing over a line the gateway sent: {long[:200]}"
    ]


async def test_output_on_a_stream_other_than_stdout_or_stderr_is_passed_over_quietly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    run = _run(
        '{"stream": "stdin", "data_b64": "b2sK"}',
        '{"stream": "stdout", "data_b64": "b2sK"}',
        '{"done": true, "exit_code": 0}',
    )

    with caplog.at_level(logging.WARNING, logger="igni_client.commands.run"):
        outputs = [output async for output in run]

    assert outputs == [CommandOutput(stream="stdout", data=b"ok\n")]
    assert run.stdout == "ok\n" and run.stderr == "" and caplog.records == []


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
    with pytest.raises(TypeError, match="not subscriptable"):
        told.record["command"]  # type: ignore[index]


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


async def test_a_refused_credential_on_a_run_is_an_auth_error() -> None:
    run = _run('{"error": "invalid_token"}', status=401)

    with pytest.raises(AuthError, match="the gateway refused the credential: invalid_token"):
        await run.wait()


async def test_output_read_piece_by_piece_is_kept_as_it_is_read() -> None:
    run = _run(
        '{"stream": "stdout", "data_b64": "b25lCg=="}',
        '{"stream": "stderr", "data_b64": "b29wcw=="}',
        '{"stream": "stdout", "data_b64": "dHdvCg=="}',
        '{"done": true, "exit_code": 0}',
    )
    seen = []

    async for output in run:
        seen.append((output.stream, output.text, run.stdout, run.stderr))

    assert seen == [
        ("stdout", "one\n", "one\n", ""),
        ("stderr", "oops", "one\n", "oops"),
        ("stdout", "two\n", "one\ntwo\n", "oops"),
    ]
    assert run.finished is not None and run.finished.ok


async def test_output_that_is_not_utf_8_is_kept_with_replacement_characters() -> None:
    run = _run(
        '{"stream": "stdout", "data_b64": "Y2Fm6Qo="}',
        '{"stream": "stderr", "data_b64": "/w=="}',
        '{"done": true, "exit_code": 0}',
    )

    outputs = [output async for output in run]

    assert [output.data for output in outputs] == [b"caf\xe9\n", b"\xff"]
    assert (run.stdout, run.stderr) == ("caf\ufffd\n", "\ufffd")


async def test_the_last_done_line_says_how_the_run_ended() -> None:
    run = _run(
        '{"done": true, "exit_code": 1}',
        '{"stream": "stdout", "data_b64": "b2sK"}',
        '{"done": true, "exit_code": 0}',
    )

    finished = await run.wait()

    assert finished.exit_code == 0 and run.stdout == "ok\n"


async def test_a_run_left_partway_has_not_finished() -> None:
    run = _run('{"stream": "stdout", "data_b64": "b2sK"}', '{"done": true, "exit_code": 0}')

    async for _ in run:
        break

    assert run.finished is None and run.stdout == "ok\n"


class _Cut(httpx.AsyncByteStream):
    """A body that sends one line and then loses the connection."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'{"stream": "stdout", "data_b64": "b2sK"}\n'
        raise httpx.ReadError("connection reset")


async def test_a_gateway_that_goes_quiet_partway_is_unavailable_after_what_it_sent() -> None:
    fleet = Fleet(
        "http://gateway.test",
        auth=Person("t-ada"),
        http=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=_Cut()))
        ),
    )
    request = CommandRequest(producer=ProducerRef.parse("person:u-ada"), command="ls", timeout_s=5)
    run = CommandRun(fleet, request, "t-ada")
    seen = []

    with pytest.raises(Unavailable, match="did not answer: connection reset"):
        async for output in run:
            seen.append(output.text)

    assert seen == ["ok\n"] and run.stdout == "ok\n" and run.finished is None


async def test_a_run_is_made_from_a_request_model_not_a_dict() -> None:
    fleet = Fleet("http://gateway.test", auth=Person("t-ada"))
    body: Any = {"producer": {"kind": "person", "id": "u-ada"}, "command": "ls", "timeout_s": 5}

    with pytest.raises(AttributeError, match="model_dump"):
        await CommandRun(fleet, body, "t-ada").wait()


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
    await (await commands.run("ls", timeout_s=True)).wait()

    sent = [body["timeout_s"] for body in gateway.bodies()]
    assert sent == [5.5, 5.0, True]
    assert [type(timeout) for timeout in sent] == [float, float, bool]


@pytest.mark.parametrize(
    ("command", "timeout_s", "producer", "message"),
    [
        ("", 600, None, "1 byte to 16 KiB"),
        ("ls", 0, None, "timeout_s is 1 to 3600"),
        ("ls", 3601, None, "timeout_s is 1 to 3600"),
        ("", 0, "robot:r-1", "1 byte to 16 KiB"),
        ("ls", 0, "robot:r-1", "timeout_s is 1 to 3600"),
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
        (httpx.Response(400, json={"detail": "bad"}), NotAllowed, "the gateway refused: bad"),
        (httpx.Response(404, json={"detail": "gone"}), NotAllowed, "the gateway refused: gone"),
        (httpx.Response(422, json={"detail": "odd"}), NotAllowed, "the gateway refused: odd"),
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


async def test_who_this_is_answered_without_a_producer_is_a_validation_error() -> None:
    with pytest.raises(ValidationError, match="producer"):
        await Gateway(httpx.Response(200, json={"org": "org-acme"})).commands().me()


async def test_a_run_in_a_named_producer_s_vm_does_not_ask_who_this_is() -> None:
    gateway = Gateway(httpx.Response(503, text="busy"))

    finished = await (await gateway.commands().run("ls", producer="space:sp-1")).wait()

    assert finished.ok
    assert [r.url.path for r in gateway.requests] == ["/v1/commands"]
    assert gateway.bodies()[0]["producer"] == {"kind": "space", "id": "sp-1"}


async def test_who_this_is_asked_for_by_hand_is_not_asked_again_by_a_run() -> None:
    gateway = Gateway()
    commands = gateway.commands()

    me = await commands.me()
    await (await commands.run("ls")).wait()

    assert me.producer == "person:u-ada"
    assert [r.url.path for r in gateway.requests].count("/v1/me") == 1


async def test_asking_who_this_is_again_replaces_what_a_run_takes_as_its_producer() -> None:
    gateway = Gateway()
    commands = gateway.commands()
    await (await commands.run("ls")).wait()

    gateway.me = httpx.Response(200, json={"producer": "app:app-bot"})
    assert (await commands.me()).producer == "app:app-bot"
    await (await commands.run("id")).wait()

    assert [r.url.path for r in gateway.requests].count("/v1/me") == 2
    assert [body["producer"] for body in gateway.bodies()] == [
        {"kind": "person", "id": "u-ada"},
        {"kind": "app", "id": "app-bot"},
    ]


class _NoToken:
    async def token(self) -> str:
        raise AuthError("the session ended")


async def test_a_run_whose_credential_cannot_be_had_raises_why_before_it_is_started() -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(Gateway()))
    commands = Commands(Fleet("http://gateway.test", auth=_NoToken(), http=http))

    with pytest.raises(AuthError, match="the session ended"):
        await commands.run("ls", producer="person:u-ada")


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_a_gateway_in_trouble_is_unavailable_with_its_status_and_reason(
    status: int,
) -> None:
    with pytest.raises(Unavailable, match=f"the gateway answered {status}: try later"):
        await Gateway(httpx.Response(status, json={"detail": "try later"})).commands().me()
    with pytest.raises(Unavailable, match=f"the gateway answered {status}: try later"):
        await _run('{"detail": "try later"}', status=status).wait()


@pytest.mark.parametrize("status", [400, 403, 404, 422])
async def test_a_run_the_gateway_refuses_is_not_allowed_with_its_reason(status: int) -> None:
    run = _run('{"detail": "no"}', status=status)

    with pytest.raises(NotAllowed, match="the gateway refused: no"):
        await run.wait()

    assert run.finished is None


async def test_a_run_that_raises_while_it_is_waited_for_has_not_finished() -> None:
    fleet = Fleet(
        "http://gateway.test",
        auth=Person("t-ada"),
        http=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=_Cut()))
        ),
    )
    request = CommandRequest(producer=ProducerRef.parse("person:u-ada"), command="ls", timeout_s=5)
    run = CommandRun(fleet, request, "t-ada")

    with pytest.raises(Unavailable, match="did not answer"):
        await run.wait()

    assert run.finished is None and run.stdout == "ok\n"


async def test_a_run_read_by_two_tasks_at_once_is_read_by_the_first_only() -> None:
    run = _run('{"stream": "stdout", "data_b64": "b2sK"}', '{"done": true, "exit_code": 0}')

    first = run.__aiter__()
    second = run.__aiter__()
    assert (await first.__anext__()).text == "ok\n"

    with pytest.raises(RuntimeError, match="can be read once"):
        await second.__anext__()
    assert [output async for output in first] == []
    assert run.finished is not None and run.finished.ok


@pytest.mark.parametrize(
    "line",
    [
        '{"command": "ls", "stream": "stdout", "data_b64": "b2sK"}',
        '{"woken": 5, "stream": "stdout", "data_b64": "b2sK"}',
        '{"command": [], "woken": "x", "stream": "stdout", "data_b64": "b2sK"}',
    ],
)
async def test_a_command_or_woken_that_is_not_an_object_leaves_the_line_to_its_other_keys(
    line: str,
) -> None:
    run = _run(line, '{"done": true, "exit_code": 0}')

    outputs = [output async for output in run]

    assert [output.text for output in outputs] == ["ok\n"]
    assert run.record is None and run.woken is None


@pytest.mark.parametrize("done", ["false", "0", '""', "null"])
async def test_a_done_that_is_not_true_does_not_end_the_run(done: str) -> None:
    run = _run(f'{{"done": {done}, "exit_code": 3}}')

    finished = await run.wait()

    assert finished.exit_code is None
    assert finished.error == "the gateway ended the output without a result"


def test_a_record_or_a_wake_that_is_not_an_object_is_raised_not_kept() -> None:
    with pytest.raises(ValidationError, match="CommandAccepted"):
        CommandAccepted.model_validate({"command": "ls"})
    with pytest.raises(ValidationError, match="VmWoken"):
        VmWoken.model_validate({"woken": [1]})


class _Body(httpx.AsyncByteStream):
    """A refusal whose body arrives as a stream, unread until someone reads it."""

    def __init__(self, content: bytes) -> None:
        self.content = content

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.content[:5]
        yield self.content[5:]


async def test_a_refusal_that_arrives_as_a_stream_is_read_whole_for_its_reason() -> None:
    body = _Body(b'{"detail": "not your VM"}')
    fleet = Fleet(
        "http://gateway.test",
        auth=Person("t-ada"),
        http=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(403, stream=body))
        ),
    )
    request = CommandRequest(producer=ProducerRef.parse("person:u-ada"), command="ls", timeout_s=5)

    with pytest.raises(NotAllowed, match="the gateway refused: not your VM"):
        await CommandRun(fleet, request, "t-ada").wait()


def test_an_output_piece_is_only_ever_stdout_or_stderr_and_empty_data_reads_as_empty_text() -> None:
    for stream in ("stdin", "", "STDOUT"):
        with pytest.raises(ValidationError):
            CommandOutput(stream=stream, data=b"x")  # type: ignore[arg-type]
    assert CommandOutput(stream="stderr", data=b"").text == ""
    assert CommandOutput(stream="stdout", data=b"ok").text == "ok"

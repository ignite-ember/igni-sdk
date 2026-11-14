"""The fake's parts: its socket, gateway, methods, runs and how `FakeIgni` puts them together."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.typing import Subprotocol

from igni_client import IgniClient, Local, Person
from igni_client.commands.wire import CommandRequest, OutputLine, ProducerRef
from igni_client.models import (
    Cancel,
    CommandResult,
    ContentDelta,
    HitlDecision,
    HitlResponseBatch,
    InfoMessage,
    QueueMessage,
    RpcRequest,
    RpcResponse,
    RunPaused,
    SessionListResult,
    StatusUpdate,
    StreamEnd,
    UserMessage,
    UserMessageReceived,
)
from igni_client.targets import TOKEN_PROTOCOL_PREFIX
from igni_client.testing import (
    Delay,
    FakeGateway,
    FakeIgni,
    FakeMethods,
    FakeRuns,
    FakeSocket,
    LocalHandshake,
    PlayedCommand,
    Steps,
    UnknownFrame,
)
from igni_client.testing.gateway import CONNECT_PATH
from igni_client.testing.server import SUBPROTOCOL
from igni_client.wire import Event

TOKENS = {"t-ada": "person:u-ada"}


async def _noop(frame: object, reply: Any) -> None:
    return None


async def _open(url: str, *protocols: str, **kwargs: Any) -> ClientConnection:
    return await connect(
        url, subprotocols=[Subprotocol(p) for p in (SUBPROTOCOL, *protocols)], **kwargs
    )


async def _next(socket: ClientConnection) -> dict[str, Any]:
    decoded: dict[str, Any] = json.loads(await asyncio.wait_for(socket.recv(), 5))
    return decoded


async def _until(condition: Any) -> None:
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("it did not happen")


# ── FakeSocket ──


class TestFakeSocket:
    async def test_it_listens_on_a_free_loopback_port_until_stopped(self) -> None:
        fake = FakeSocket(LocalHandshake(None), _noop)
        await fake.start()
        assert fake.port > 0 and fake.url == f"ws://127.0.0.1:{fake.port}"
        client = await _open(fake.url)
        await client.close()
        await fake.stop()

        with pytest.raises(OSError):
            await _open(fake.url)

    async def test_its_url_carries_the_path_it_was_given(self) -> None:
        fake = FakeSocket(LocalHandshake(None), _noop, path="/v1/connect")
        await fake.start()
        try:
            assert fake.url == f"ws://127.0.0.1:{fake.port}/v1/connect"
        finally:
            await fake.stop()

    async def test_each_client_is_welcomed_with_an_id_of_its_own(self) -> None:
        fake = FakeSocket(LocalHandshake(None), _noop)
        await fake.start()
        try:
            a, b = await _open(fake.url), await _open(fake.url)
            welcomes = [await _next(a), await _next(b)]

            assert [w["type"] for w in welcomes] == ["welcome", "welcome"]
            assert [w["client_id"] for w in welcomes] == ["ws-1", "ws-2"]
            assert fake.connections == 2
            await a.close()
            await b.close()
        finally:
            await fake.stop()

    async def test_a_broadcast_and_a_push_reach_every_client(self) -> None:
        fake = FakeSocket(LocalHandshake(None), _noop)
        await fake.start()
        try:
            a, b = await _open(fake.url), await _open(fake.url)
            await _next(a)
            await _next(b)
            await _until(lambda: len(fake._clients) == 2)

            await fake.broadcast(InfoMessage(text="hello"))
            await fake.push("chan", {"n": 1}, session_id="s-1")

            for client in (a, b):
                info = await _next(client)
                pushed = await _next(client)
                assert (info["type"], info["text"]) == ("info", "hello")
                assert (pushed["type"], pushed["channel"], pushed["payload"]) == (
                    "push_notification",
                    "chan",
                    {"n": 1},
                )
                assert pushed["session_id"] == "s-1"
        finally:
            await fake.stop()

    async def test_what_a_client_sends_is_kept_with_its_id_and_handled_with_a_reply(self) -> None:
        handled: list[object] = []

        async def handler(frame: object, reply: Any) -> None:
            handled.append(frame)
            await reply(InfoMessage(text="for you alone"))

        fake = FakeSocket(LocalHandshake(None), handler)
        await fake.start()
        try:
            a, b = await _open(fake.url), await _open(fake.url)
            await _next(a)
            await _next(b)
            await b.send(UserMessage(id="m-1", text="hi").model_dump_json())
            await b.send("not json at all")  # passed over, as igni passes it over
            await b.send(json.dumps({"type": "strange", "x": 1}))

            answer = await _next(b)
            await _until(lambda: len(fake.received) == 2)

            assert answer["text"] == "for you alone"
            first, second = fake.received
            assert first.client_id == "ws-2" and isinstance(first.frame, UserMessage)
            assert isinstance(second.frame, UnknownFrame) and second.frame.type == "strange"
            assert len(handled) == 2
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(a.recv(), 0.1)  # the other client heard nothing
        finally:
            await fake.stop()

    async def test_a_move_welcomes_every_client_again_under_a_new_id(self) -> None:
        fake = FakeSocket(LocalHandshake(None), _noop)
        await fake.start()
        try:
            a = await _open(fake.url)
            assert (await _next(a))["client_id"] == "ws-1"
            await _until(lambda: len(fake._clients) == 1)

            await fake.move()

            again = await _next(a)
            assert (again["type"], again["client_id"]) == ("welcome", "ws-2")
            await a.send(UserMessage(id="m", text="x").model_dump_json())
            await _until(lambda: len(fake.received) == 1)
            assert fake.received[0].client_id == "ws-2"
        finally:
            await fake.stop()

    async def test_a_drop_closes_every_connection_with_the_code(self) -> None:
        fake = FakeSocket(LocalHandshake(None), _noop)
        await fake.start()
        try:
            a = await _open(fake.url)
            await _next(a)
            await _until(lambda: len(fake._clients) == 1)

            await fake.drop(1012, "restarting")

            with pytest.raises(ConnectionClosed):
                await asyncio.wait_for(a.recv(), 5)
            assert a.close_code == 1012 and a.close_reason == "restarting"
            await _until(lambda: not fake._clients)
        finally:
            await fake.stop()

    async def test_busy_next_turns_that_many_connections_away_with_1013(self) -> None:
        fake = FakeSocket(LocalHandshake(None), _noop)
        await fake.start()
        try:
            fake.busy_next(2)
            for _ in range(2):
                turned = await _open(fake.url)
                with pytest.raises(ConnectionClosed):
                    await asyncio.wait_for(turned.recv(), 5)
                assert turned.close_code == 1013
            welcomed = await _open(fake.url)

            assert (await _next(welcomed))["type"] == "welcome"
            assert fake.connections == 3
            await welcomed.close()
        finally:
            await fake.stop()

    async def test_it_selects_the_igni_subprotocol_and_none_otherwise(self) -> None:
        fake = FakeSocket(LocalHandshake(None), _noop)
        await fake.start()
        try:
            ok = await connect(fake.url, subprotocols=[Subprotocol(SUBPROTOCOL)])
            assert ok.subprotocol == SUBPROTOCOL == "igni.v1"
            await ok.close()
            other = await connect(fake.url, subprotocols=[Subprotocol("other.v9")])
            assert other.subprotocol is None
            await other.close()
        finally:
            await fake.stop()


class TestLocalHandshake:
    async def test_with_no_token_everyone_gets_in(self) -> None:
        fake = FakeSocket(LocalHandshake(None), _noop)
        await fake.start()
        try:
            client = await _open(fake.url)
            assert (await _next(client))["type"] == "welcome"
            await client.close()
        finally:
            await fake.stop()

    async def test_with_a_token_only_the_subprotocol_that_carries_it_gets_in(self) -> None:
        fake = FakeSocket(LocalHandshake("launch-secret"), _noop)
        await fake.start()
        try:
            for protocols in ((), (f"{TOKEN_PROTOCOL_PREFIX}wrong",)):
                with pytest.raises(InvalidStatus) as refused:
                    await _open(fake.url, *protocols)
                assert refused.value.response.status_code == 403
            client = await _open(fake.url, f"{TOKEN_PROTOCOL_PREFIX}launch-secret")
            assert (await _next(client))["type"] == "welcome"
            await client.close()
        finally:
            await fake.stop()


# ── FakeGateway ──


class TestFakeGateway:
    async def _http(self, gateway: FakeGateway) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=gateway.transport(), base_url="http://gw")

    async def test_me_names_the_producer_the_token_belongs_to(self) -> None:
        gateway = FakeGateway(TOKENS, org="org-x")
        async with await self._http(gateway) as http:
            response = await http.get("/v1/me", headers={"Authorization": "Bearer t-ada"})

        assert response.status_code == 200
        body = response.json()
        assert (body["producer"], body["org"]) == ("person:u-ada", "org-x")

    async def test_the_default_org_is_org_acme_and_tokens_are_copied(self) -> None:
        tokens = dict(TOKENS)
        gateway = FakeGateway(tokens)
        tokens["t-late"] = "person:u-late"

        assert gateway.org == "org-acme" and gateway.tokens == TOKENS
        assert FakeGateway().tokens == {}

    @pytest.mark.parametrize("header", [None, "Bearer nope", "t-ada-without-scheme-x"])
    async def test_a_token_the_gateway_does_not_know_is_a_401(self, header: str | None) -> None:
        gateway = FakeGateway(TOKENS)
        headers = {} if header is None else {"Authorization": header}
        async with await self._http(gateway) as http:
            response = await http.get("/v1/me", headers=headers)

        assert response.status_code == 401
        assert response.json() == {"error": "invalid_token"}

    async def test_a_path_or_method_it_does_not_serve_is_a_404(self) -> None:
        gateway = FakeGateway(TOKENS)
        auth = {"Authorization": "Bearer t-ada"}
        async with await self._http(gateway) as http:
            assert (await http.get("/v1/elsewhere", headers=auth)).status_code == 404
            assert (await http.post("/v1/me", headers=auth)).status_code == 404

    async def test_a_command_streams_its_lines_as_ndjson_and_is_remembered(self) -> None:
        gateway = FakeGateway(TOKENS)
        gateway.commands["make"] = PlayedCommand(stdout="built\n", stderr="warn\n", exit_code=2)
        body = CommandRequest(
            producer=ProducerRef(kind="person", id="u-ada"), command="make", timeout_s=9
        )
        async with await self._http(gateway) as http:
            response = await http.post(
                "/v1/commands",
                headers={"Authorization": "Bearer t-ada"},
                content=body.model_dump_json(),
            )

        assert response.headers["content-type"] == "application/x-ndjson"
        lines = [json.loads(line) for line in response.text.splitlines()]
        assert lines[0]["command"]["command"] == "make"
        assert lines[0]["command"]["command_id"] == "c-1"
        assert lines[1]["woken"]["how"] == "paused"
        assert [ln["stream"] for ln in lines[2:-1]] == ["stdout", "stderr"]
        assert lines[-1]["done"] is True and lines[-1]["exit_code"] == 2
        assert gateway.commands_run == [body]

    async def test_an_unplayed_command_prints_that_it_ran(self) -> None:
        gateway = FakeGateway(TOKENS)
        body = CommandRequest(
            producer=ProducerRef(kind="person", id="u-ada"), command="ls", timeout_s=1
        )
        async with await self._http(gateway) as http:
            first = await http.post(
                "/v1/commands",
                headers={"Authorization": "Bearer t-ada"},
                content=body.model_dump_json(),
            )
            second = await http.post(
                "/v1/commands",
                headers={"Authorization": "Bearer t-ada"},
                content=body.model_dump_json(),
            )

        out = [json.loads(line) for line in first.text.splitlines()][2]
        assert OutputLine.model_validate(out).output().text == "ran ls\n"
        assert [
            json.loads(line)["command"]["command_id"]
            for line in (first.text.splitlines()[0], second.text.splitlines()[0])
        ] == ["c-1", "c-2"]

    async def test_a_command_for_someone_else_s_vm_is_a_403_but_is_still_recorded(self) -> None:
        gateway = FakeGateway(TOKENS)
        body = CommandRequest(
            producer=ProducerRef(kind="person", id="u-bob"), command="ls", timeout_s=1
        )
        async with await self._http(gateway) as http:
            response = await http.post(
                "/v1/commands",
                headers={"Authorization": "Bearer t-ada"},
                content=body.model_dump_json(),
            )

        assert response.status_code == 403 and response.json() == {"detail": "not your VM"}
        assert gateway.commands_run == [body]

    async def test_a_body_that_is_not_a_command_request_is_a_422(self) -> None:
        gateway = FakeGateway(TOKENS)
        async with await self._http(gateway) as http:
            response = await http.post(
                "/v1/commands", headers={"Authorization": "Bearer t-ada"}, content=b'{"command": 1}'
            )

        assert response.status_code == 422 and "detail" in response.json()
        assert gateway.commands_run == []

    def test_a_played_command_writes_stdout_first_and_leaves_empty_streams_out(self) -> None:
        assert PlayedCommand().outputs() == []
        both = PlayedCommand(stdout="a", stderr="b").outputs()
        assert [(o.stream, o.data) for o in both] == [("stdout", b"a"), ("stderr", b"b")]
        only = PlayedCommand(stderr="e").outputs()
        assert [(o.stream, o.data) for o in only] == [("stderr", b"e")]

    async def test_the_socket_handshake_wants_the_connect_path_and_a_known_bearer(self) -> None:
        gateway = FakeGateway(TOKENS)
        fake = FakeSocket(gateway, _noop, path=CONNECT_PATH)
        await fake.start()
        try:
            base = f"ws://127.0.0.1:{fake.port}"
            for url, headers, status in (
                (fake.url, {}, 401),
                (fake.url, {"Authorization": "Bearer nope"}, 401),
                (f"{base}/v1/elsewhere", {"Authorization": "Bearer t-ada"}, 404),
            ):
                with pytest.raises(InvalidStatus) as refused:
                    await _open(url, additional_headers=headers)
                assert refused.value.response.status_code == status
            client = await _open(
                f"{fake.url}?x=1", additional_headers={"Authorization": "Bearer t-ada"}
            )
            assert (await _next(client))["type"] == "welcome"
            await client.close()
        finally:
            await fake.stop()

    async def test_the_refusal_of_a_bad_token_says_invalid_token(self) -> None:
        fake = FakeSocket(FakeGateway(TOKENS), _noop, path=CONNECT_PATH)
        await fake.start()
        try:
            with pytest.raises(InvalidStatus) as refused:
                await _open(fake.url, additional_headers={"Authorization": "Bearer nope"})
            body = json.loads(refused.value.response.body or b"{}")
            assert body["error"] == "invalid_token"
        finally:
            await fake.stop()


# ── FakeMethods ──


def _result(reply: Event) -> Any:
    assert isinstance(reply, RpcResponse)
    return reply.result


def _call(method: str, **args: Any) -> RpcRequest:
    return RpcRequest.model_validate(
        {"id": "call-1", "method": method, "args": args, "session_id": "s-9"}
    )


class TestFakeMethods:
    async def test_every_call_is_kept_and_a_set_answer_is_a_value_or_a_function_of_the_args(
        self,
    ) -> None:
        methods = FakeMethods()
        methods.answers["a"] = {"fixed": 1}
        methods.answers["b"] = lambda args: {"seen": args}

        async def later(args: dict[str, Any]) -> dict[str, Any]:
            return {"later": args["n"]}

        methods.answers["c"] = later
        first = await methods.answer(_call("a"))
        second = await methods.answer(_call("b", x=1))
        third = await methods.answer(_call("c", n=3))

        assert isinstance(first, RpcResponse) and first.result == {"fixed": 1}
        assert isinstance(second, RpcResponse) and second.result == {"seen": {"x": 1}}
        assert isinstance(third, RpcResponse) and third.result == {"later": 3}
        assert (first.id, first.session_id) == ("call-1", "s-9")
        assert [c.method for c in methods.calls] == ["a", "b", "c"]

    async def test_a_model_answer_goes_as_its_json_and_a_list_of_them_too(self) -> None:
        methods = FakeMethods()
        update = StatusUpdate(model="m")
        methods.answers["one"] = update
        methods.answers["many"] = [update, {"raw": 1}]
        one = await methods.answer(_call("one"))
        many = await methods.answer(_call("many"))

        # `StatusUpdate` is itself an event: igni sends it as the message it is.
        assert isinstance(one, StatusUpdate) and (one.id, one.session_id) == ("call-1", "s-9")
        assert isinstance(many, RpcResponse) and isinstance(many.result, list)
        assert _result(many)[0]["model"] == "m" and _result(many)[1] == {"raw": 1}

    async def test_an_answer_that_is_an_event_is_sent_as_that_message_tied_to_the_call(
        self,
    ) -> None:
        methods = FakeMethods()
        methods.answers["x"] = InfoMessage(text="hi")

        answer = await methods.answer(_call("x"))

        assert isinstance(answer, InfoMessage) and answer.text == "hi"
        assert (answer.id, answer.session_id) == ("call-1", "s-9")

    async def test_attach_session_makes_ids_and_remembers_the_project(self) -> None:
        methods = FakeMethods()
        made = await methods.answer(_call("attach_session"))
        named = await methods.answer(_call("attach_session", session_id="mine", project_dir="/p"))
        again = await methods.answer(_call("attach_session", session_id="mine"))
        second = await methods.answer(_call("attach_session"))

        assert isinstance(made, RpcResponse) and isinstance(named, RpcResponse)
        assert isinstance(again, RpcResponse)
        assert _result(made)["session_id"] == "s-1"
        assert _result(made)["project_dir"] == "/workspace"
        assert _result(named)["session_id"] == "mine" and _result(named)["project_dir"] == "/p"
        assert _result(again)["project_dir"] == "/p"
        assert _result(second)["session_id"] == "s-2"
        assert methods.sessions == {"s-1": "/workspace", "mine": "/p", "s-2": "/workspace"}

    async def test_the_sessions_attached_are_listed_and_a_default_id_is_given(self) -> None:
        methods = FakeMethods()
        await methods.answer(_call("attach_session", session_id="s-a"))
        listed = await methods.answer(_call("list_sessions"))
        default = await methods.answer(_call("get_session_id"))

        assert isinstance(listed, SessionListResult) and isinstance(default, RpcResponse)
        assert [s.session_id for s in listed.sessions] == ["s-a"]
        assert default.result == "s-default"

    async def test_the_registry_lists_the_models_and_the_first_is_the_default(self) -> None:
        methods = FakeMethods()
        registry = await methods.answer(_call("get_model_registry"))
        switched = await methods.answer(_call("switch_model", model_name="igni-2"))
        status = await methods.answer(_call("get_status"))

        assert isinstance(registry, RpcResponse)
        assert _result(registry)["default"] == "igni-1"
        assert _result(registry)["max_context_window"] == 200_000
        assert list(_result(registry)["registry"]) == ["igni-1"]
        assert isinstance(switched, InfoMessage) and switched.text == "Switched to igni-2"
        assert isinstance(status, StatusUpdate) and status.model == "igni-1"

    async def test_history_is_by_session_and_empty_when_there_is_none(self) -> None:
        methods = FakeMethods()
        empty = await methods.answer(_call("get_chat_history", session_id="s-1"))

        assert isinstance(empty, RpcResponse) and empty.result == []

    async def test_unbound_for_answers_the_next_n_calls_as_a_vm_not_yet_bound(self) -> None:
        from igni_client.connection import UNBOUND

        methods = FakeMethods()
        methods.unbound_for(2)
        replies = [await methods.answer(_call("get_status")) for _ in range(3)]

        errors = [r.error for r in replies if isinstance(r, RpcResponse)]
        assert errors == [UNBOUND, UNBOUND]
        assert isinstance(replies[2], StatusUpdate)

    async def test_a_method_nobody_answers_is_an_error_in_words(self) -> None:
        methods = FakeMethods()
        known = await methods.answer(_call("list_background_processes"))
        unknown = await methods.answer(_call("no_such_method"))

        assert isinstance(known, RpcResponse) and known.error == "the fake has no answer for it"
        assert isinstance(unknown, RpcResponse)
        assert unknown.error == "Unknown RPC method: no_such_method"

    def test_a_reply_ties_an_event_or_a_result_to_its_call(self) -> None:
        event = FakeMethods.reply(_call("x"), Steps.answer("t")[1])
        result = FakeMethods.reply(_call("x"), [1, 2])

        assert isinstance(event, ContentDelta) and event.id == "call-1"
        assert isinstance(result, RpcResponse) and result.result == [1, 2]


# ── FakeRuns ──


class RecordingSocket(FakeSocket):
    """A socket that records what is broadcast instead of sending it."""

    def __init__(self) -> None:
        super().__init__(LocalHandshake(None), _noop)
        self.sent: list[Event] = []

    async def broadcast(self, event: Event) -> None:
        self.sent.append(event)


def _kinds(socket: RecordingSocket) -> list[str]:
    return [type(e).__name__ for e in socket.sent]


class TestFakeRuns:
    async def test_a_prompt_echoes_it_runs_the_script_and_ends_the_stream(self) -> None:
        socket = RecordingSocket()
        runs = FakeRuns(socket)

        await runs.prompt(UserMessage(id="m-1", session_id="s-1", text="hi", client_id="ws-1"))

        assert _kinds(socket) == [
            "UserMessageReceived",
            "RunStarted",
            "ContentDelta",
            "RunCompleted",
            "StreamEnd",
        ]
        received = socket.sent[0]
        assert isinstance(received, UserMessageReceived)
        assert (received.text, received.client_id, received.session_id) == ("hi", "ws-1", "s-1")
        assert all(e.id == "m-1" and e.session_id == "s-1" for e in socket.sent[1:])
        delta = socket.sent[2]
        assert isinstance(delta, ContentDelta) and delta.text == "echo: hi"
        assert not runs.running("s-1")

    async def test_the_script_is_a_function_of_the_prompt_s_text(self) -> None:
        socket = RecordingSocket()
        runs = FakeRuns(socket)
        runs.script = lambda text: Steps.answer(text.upper())

        await runs.prompt(UserMessage(id="m", session_id="s", text="quiet"))

        assert [e.text for e in socket.sent if isinstance(e, ContentDelta)] == ["QUIET"]

    async def test_a_delay_waits_and_a_run_in_it_is_running(self) -> None:
        socket = RecordingSocket()
        runs = FakeRuns(socket)
        runs.script = lambda text: [Delay(seconds=0.2), *Steps.answer("late")]

        task = asyncio.ensure_future(runs.prompt(UserMessage(id="m", session_id="s", text="x")))
        await asyncio.sleep(0.05)
        assert runs.running("s") and not runs.running("other")
        assert _kinds(socket) == ["UserMessageReceived"]
        await task

        assert _kinds(socket)[-1] == "StreamEnd" and not runs.running("s")

    async def test_an_approval_pauses_the_run_and_a_confirm_resumes_where_it_stopped(self) -> None:
        socket = RecordingSocket()
        runs = FakeRuns(socket)
        runs.script = lambda text: [
            *Steps.answer("before")[:2],
            Steps.approval("write_file", path="/a"),
            Steps.answer("after")[1],
            Steps.answer("after")[2],
        ]
        await runs.prompt(UserMessage(id="m-1", session_id="s-1", text="go"))

        assert _kinds(socket)[-2:] == ["RunPaused", "StreamEnd"]
        paused = next(e for e in socket.sent if isinstance(e, RunPaused))
        assert paused.requirements[0].requirement_id == "req-write_file"
        assert runs.running("s-1")  # a paused run is still the session's turn
        socket.sent.clear()

        decision = HitlDecision(requirement_id="req-write_file", action="confirm")
        await runs.resume(HitlResponseBatch(id="b-1", session_id="s-1", decisions=[decision]))

        assert _kinds(socket) == [
            "RequirementResolved",
            "ContentDelta",
            "RunCompleted",
            "StreamEnd",
        ]
        assert all(e.id == "b-1" for e in socket.sent[1:])
        assert runs.decisions == [[decision]]
        assert not runs.running("s-1")

    async def test_a_reject_resumes_as_rejected_and_then_answers(self) -> None:
        socket = RecordingSocket()
        runs = FakeRuns(socket)
        runs.script = lambda text: [Steps.approval("rm"), *Steps.answer("never")]
        await runs.prompt(UserMessage(id="m", session_id="s", text="go"))
        socket.sent.clear()

        reject = HitlDecision(requirement_id="req-rm", action="reject")
        await runs.resume(HitlResponseBatch(id="b", session_id="s", decisions=[reject]))

        texts = [e.text for e in socket.sent if isinstance(e, ContentDelta)]
        assert texts == ["I did not run it."]
        assert "ToolCompleted" in _kinds(socket)

    async def test_an_answer_no_run_is_waiting_for_plays_nothing_but_the_end(self) -> None:
        socket = RecordingSocket()
        runs = FakeRuns(socket)

        await runs.resume(
            HitlResponseBatch(
                id="b", session_id="s", decisions=[HitlDecision(requirement_id="ghost")]
            )
        )

        assert _kinds(socket) == ["RequirementResolved", "StreamEnd"]

    async def test_a_cancel_says_so_and_ends_the_stream_once(self) -> None:
        socket = RecordingSocket()
        runs = FakeRuns(socket)
        runs.script = lambda text: [Steps.approval("t")]
        await runs.prompt(UserMessage(id="m-1", session_id="s-1", text="go"))
        socket.sent.clear()

        await runs.cancel(Cancel(session_id="s-1"))
        await runs.cancel(Cancel(session_id="s-1"))  # nothing is running now: nothing is said

        info, end = socket.sent
        assert isinstance(info, InfoMessage) and info.text == "Run cancelled by user."
        assert isinstance(end, StreamEnd) and end.id == "m-1"
        assert not runs.running("s-1")

    async def test_a_cancel_with_nothing_running_says_nothing(self) -> None:
        socket = RecordingSocket()

        await FakeRuns(socket).cancel(Cancel(session_id="s"))

        assert socket.sent == []

    async def test_a_queued_message_is_announced_as_queued(self) -> None:
        socket = RecordingSocket()

        await FakeRuns(socket).queue(QueueMessage(session_id="s", text="later"))

        (received,) = socket.sent
        assert isinstance(received, UserMessageReceived)
        assert (received.text, received.queued, received.session_id) == ("later", True, "s")

    def test_a_run_is_not_running_until_a_prompt_starts_it(self) -> None:
        assert not FakeRuns(RecordingSocket()).running("s")


# ── FakeIgni ──


class TestFakeIgni:
    async def test_it_is_a_context_manager_and_stop_closes_the_socket(self) -> None:
        async with FakeIgni() as fake:
            port = fake.socket.port
            assert port > 0
        with pytest.raises(OSError):
            await _open(f"ws://127.0.0.1:{port}")

    async def test_local_points_at_the_socket_with_the_token(self) -> None:
        async with FakeIgni(local_token="tok") as fake:
            target = fake.local()

            assert isinstance(target, Local)
            assert target._resolve() == (f"ws://127.0.0.1:{fake.socket.port}", "tok")
            assert fake.socket.url == f"ws://127.0.0.1:{fake.socket.port}"

    async def test_a_gateway_puts_the_connect_path_on_the_socket_and_fleet_needs_one(self) -> None:
        async with FakeIgni() as plain:
            with pytest.raises(RuntimeError, match="FakeGateway"):
                plain.fleet(Person("t-ada"))
        gateway = FakeGateway(TOKENS)
        async with FakeIgni(gateway=gateway) as fake:
            assert fake.gateway is gateway
            assert fake.socket.url.endswith(CONNECT_PATH)
            fleet = fake.fleet(Person("t-ada"))
            assert (
                fleet.describe().startswith("http://127.0.0.1:") or "127.0.0.1" in fleet.describe()
            )

    async def _client(self, fake: FakeIgni) -> ClientConnection:
        client = await _open(fake.socket.url)
        await _next(client)
        await _until(lambda: bool(fake.socket._clients))
        return client

    async def test_a_call_is_answered_to_its_caller_alone(self) -> None:
        async with FakeIgni() as fake:
            a, b = await self._client(fake), await self._client(fake)
            await _until(lambda: len(fake.socket._clients) == 2)
            await a.send(_call("get_session_id").model_dump_json())

            answer = await _next(a)

            assert (answer["type"], answer["result"], answer["id"]) == (
                "rpc_response",
                "s-default",
                "call-1",
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(b.recv(), 0.1)

    async def test_a_prompt_runs_the_script_for_every_client_attached(self) -> None:
        async with FakeIgni() as fake:
            fake.runs.script = lambda text: Steps.answer(f"you said {text}")
            a, b = await self._client(fake), await self._client(fake)
            await _until(lambda: len(fake.socket._clients) == 2)
            await a.send(UserMessage(id="m-1", session_id="s", text="hi").model_dump_json())

            for client in (a, b):
                types = []
                while "stream_end" not in types:
                    types.append((await _next(client))["type"])
                assert types == [
                    "user_message_received",
                    "run_started",
                    "content_delta",
                    "run_completed",
                    "stream_end",
                ]

    async def test_cancel_run_is_answered_with_whether_a_turn_was_running_and_cancels_it(
        self,
    ) -> None:
        async with FakeIgni() as fake:
            fake.runs.script = lambda text: [Steps.approval("t")]
            client = await self._client(fake)
            await client.send(UserMessage(id="m", session_id="s-9", text="x").model_dump_json())
            while (await _next(client))["type"] != "stream_end":
                pass
            await client.send(_call("cancel_run").model_dump_json())

            seen = {}
            while "rpc_response" not in seen or "stream_end" not in seen:
                message = await _next(client)
                seen[message["type"]] = message

            assert seen["rpc_response"]["result"] == {"cancelled": True}
            assert seen["info"]["text"] == "Run cancelled by user."

    async def test_a_set_answer_for_cancel_run_takes_the_place_of_the_fake_s_own(self) -> None:
        async with FakeIgni() as fake:
            fake.methods.answers["cancel_run"] = {"cancelled": True, "mine": 1}
            client = await self._client(fake)
            await client.send(_call("cancel_run").model_dump_json())

            assert (await _next(client))["result"] == {"cancelled": True, "mine": 1}

    async def test_cancel_run_with_nothing_running_says_nothing_was_cancelled(self) -> None:
        async with FakeIgni() as fake:
            client = await self._client(fake)
            await client.send(_call("cancel_run").model_dump_json())

            assert (await _next(client))["result"] == {"cancelled": False}

    async def test_an_approval_answer_resumes_the_run(self) -> None:
        async with FakeIgni() as fake:
            fake.runs.script = lambda text: [Steps.approval("t"), *Steps.answer("done")[1:]]
            client = await self._client(fake)
            await client.send(UserMessage(id="m", session_id="s", text="x").model_dump_json())
            while (await _next(client))["type"] != "stream_end":
                pass
            batch = HitlResponseBatch(
                id="b",
                session_id="s",
                decisions=[HitlDecision(requirement_id="req-t", action="confirm")],
            )
            await client.send(batch.model_dump_json())

            types = []
            while "stream_end" not in types:
                types.append((await _next(client))["type"])

            assert types == ["requirement_resolved", "content_delta", "run_completed", "stream_end"]
            assert len(fake.runs.decisions) == 1

    async def test_a_queued_message_is_announced(self) -> None:
        async with FakeIgni() as fake:
            client = await self._client(fake)
            await client.send(QueueMessage(session_id="s", text="later").model_dump_json())

            message = await _next(client)

            assert (message["type"], message["queued"]) == ("user_message_received", True)

    async def test_a_cancel_frame_cancels_the_running_turn(self) -> None:
        async with FakeIgni() as fake:
            fake.runs.script = lambda text: [Steps.approval("t")]
            client = await self._client(fake)
            await client.send(UserMessage(id="m", session_id="s", text="x").model_dump_json())
            while (await _next(client))["type"] != "stream_end":
                pass
            await client.send(Cancel(session_id="s").model_dump_json())

            assert (await _next(client))["text"] == "Run cancelled by user."

    async def test_a_slash_command_is_answered_to_everyone_by_the_function_set(self) -> None:
        from igni_client.models import Command

        async with FakeIgni() as fake:
            client = await self._client(fake)
            await client.send(Command(id="c-1", session_id="s", text="/help").model_dump_json())
            default = await _next(client)
            fake.commands = lambda text: CommandResult(kind="error", content=f"no {text}")
            await client.send(Command(id="c-2", session_id="s", text="/x").model_dump_json())
            custom = await _next(client)

            assert (default["id"], default["session_id"]) == ("c-1", "s")
            assert (default["kind"], default["content"]) == ("info", "ran /help")
            assert (custom["id"], custom["kind"], custom["content"]) == ("c-2", "error", "no /x")

    async def test_typing_is_echoed_to_everyone(self) -> None:
        from igni_client.models import Typing

        async with FakeIgni() as fake:
            a, b = await self._client(fake), await self._client(fake)
            await _until(lambda: len(fake.socket._clients) == 2)
            await a.send(Typing(session_id="s", text="dra").model_dump_json())

            assert (await _next(b))["text"] == "dra"
            assert (await _next(a))["text"] == "dra"

    async def test_a_cancelled_sign_in_is_counted(self) -> None:
        from igni_client.models import CancelLogin

        async with FakeIgni() as fake:
            client = await self._client(fake)
            assert fake.logins_cancelled == 0
            await client.send(CancelLogin().model_dump_json())
            await _until(lambda: fake.logins_cancelled == 1)

    async def test_a_gateway_makes_the_socket_check_bearers(self) -> None:
        async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
            with pytest.raises(InvalidStatus):
                await _open(fake.socket.url)
            client = await _open(
                fake.socket.url, additional_headers={"Authorization": "Bearer t-ada"}
            )
            assert (await _next(client))["type"] == "welcome"
            await client.close()

    async def test_the_fleet_target_reaches_the_gateway_over_its_own_transport(self) -> None:
        async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
            fake.runs.script = lambda text: Steps.answer(f"you said {text}")
            async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
                session = await igni.sessions.create()

                assert str(await session.ask("hi")) == "you said hi"
                me = await igni.me()
            assert me.producer == "person:u-ada"

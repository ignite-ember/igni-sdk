"""Connecting, and what happens when the connection changes under the client."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from websockets.asyncio.server import ServerConnection, serve
from websockets.typing import Subprotocol

import igni_client
from igni_client import (
    AuthError,
    Backoff,
    IgniClient,
    Local,
    MethodFailed,
    NotAllowed,
    NotSupported,
    Person,
    RunInterrupted,
    Unavailable,
)
from igni_client import backoff as backoff_module
from igni_client import connection as connection_module
from igni_client.api import NOT_FOR_CLIENTS
from igni_client.connection import REFUSED_METHODS, Connection
from igni_client.events import ContentDelta, PushNotification, RpcResponse, parse_event
from igni_client.frames import RpcRequest, Typing
from igni_client.lifecycle import Lifecycle, Link, Phase
from igni_client.routing import Interruption, Router
from igni_client.testing import Delay, FakeGateway, FakeIgni, Steps

TOKENS = {"t-ada": "person:u-ada"}
FAST = Backoff(first=0.01)


async def test_a_local_igni_is_found_from_its_lockfile(tmp_path: Path) -> None:
    async with FakeIgni(local_token="launch-secret") as fake:
        (tmp_path / ".igni").mkdir()
        (tmp_path / ".igni" / "backend.lock").write_text(
            json.dumps(
                {
                    "pid": 1,
                    "port": fake.socket.port,
                    "wire_version": "1.0.3",
                    "created_at": 0,
                    "ws_token": "launch-secret",
                }
            )
        )
        async with IgniClient(Local(project_dir=tmp_path)) as igni:
            assert igni.client_id.startswith("ws-")


async def test_no_running_igni_says_so(tmp_path: Path) -> None:
    with pytest.raises(Unavailable, match="no igni is running"):
        await IgniClient(Local(project_dir=tmp_path)).connect()


async def test_a_wrong_launch_token_is_an_auth_error() -> None:
    async with FakeIgni(local_token="right") as fake:
        with pytest.raises(AuthError, match="token was missing or wrong"):
            await IgniClient(
                Local(url=f"ws://127.0.0.1:{fake.socket.port}", token="wrong")
            ).connect()


def _lockfile(project: Path, port: int, token: str) -> None:
    (project / ".igni").mkdir()
    (project / ".igni" / "backend.lock").write_text(
        json.dumps(
            {"pid": 1, "port": port, "wire_version": "1.0.3", "created_at": 0, "ws_token": token}
        )
    )


async def test_an_approver_token_is_offered_instead_of_the_lockfile_s(tmp_path: Path) -> None:
    async with FakeIgni(local_token="approver") as fake:
        _lockfile(tmp_path, fake.socket.port, "program")
        local = Local(project_dir=tmp_path, approver_token="approver")
        assert local.approves
        async with IgniClient(local) as igni:
            assert igni.client_id.startswith("ws-")


async def test_an_approver_token_is_taken_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IGNI_APPROVER_TOKEN", "approver")
    async with FakeIgni(local_token="approver") as fake:
        _lockfile(tmp_path, fake.socket.port, "program")
        async with IgniClient(Local(project_dir=tmp_path)) as igni:
            assert igni.client_id.startswith("ws-")


async def test_a_refused_approver_token_says_to_make_a_new_one(tmp_path: Path) -> None:
    async with FakeIgni(local_token="current") as fake:
        _lockfile(tmp_path, fake.socket.port, "program")
        with pytest.raises(AuthError, match="/programs"):
            await IgniClient(Local(project_dir=tmp_path, approver_token="revoked")).connect()


async def test_the_gateway_refuses_a_token_it_does_not_know() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        with pytest.raises(AuthError, match="the token was refused"):
            await IgniClient(fake.fleet(Person("t-stranger"))).connect()


async def test_busy_is_tried_again() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.socket.busy_next(2)
        client = IgniClient(fake.fleet(Person("t-ada")), backoff=FAST)
        async with client:
            assert fake.socket.connections == 3


async def test_busy_for_too_long_is_unavailable() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.socket.busy_next(10)
        client = IgniClient(fake.fleet(Person("t-ada")), backoff=Backoff(attempts=2, first=0.01))
        with pytest.raises(Unavailable, match="busy"):
            await client.connect()


async def test_when_igni_moves_a_run_in_flight_is_interrupted_and_sessions_reattach() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.runs.script = lambda text: [Delay(seconds=30)]
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            session = await igni.sessions.create()
            run = asyncio.ensure_future(session.ask("long"))
            await _until(lambda: _sent(fake, "user_message") == 1)
            await fake.socket.move()
            with pytest.raises(RunInterrupted):
                await asyncio.wait_for(run, 5)
            await _until(lambda: _attached(fake, session.id) == 2)
            fake.runs.script = lambda text: Steps.answer("after the move")
            assert str(await session.ask("again")) == "after the move"


async def test_a_dropped_connection_is_opened_again_with_a_fresh_token() -> None:
    issued: list[int] = []

    class Counting:
        async def token(self) -> str:
            issued.append(1)
            return "t-ada"

    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        client = IgniClient(fake.fleet(Counting()), backoff=FAST)
        async with client as igni:
            session = await igni.sessions.create()
            await fake.socket.drop(1011)
            await _until(lambda: fake.socket.connections == 2 and _attached(fake, session.id) == 2)
            assert str(await session.ask("still there?")) == "echo: still there?"

    # One token for the socket and one for each open; the fake's HTTP is not used here.
    assert len(issued) == 2


async def test_a_producer_no_longer_active_is_final() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        client = IgniClient(fake.fleet(Person("t-ada")), backoff=FAST)
        async with client as igni:
            await fake.socket.drop(1008, "not an active producer")
            await _until(lambda: igni._conn._lifecycle.phase is Phase.FAILED)
            with pytest.raises(NotAllowed, match="not an active producer"):
                await igni.processes.list()
        assert fake.socket.connections == 1


async def test_a_local_igni_that_closed_is_not_reopened() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        await fake.socket.drop(1001, "going away")
        await _until(lambda: igni._conn._lifecycle.phase is Phase.FAILED)
        with pytest.raises(Unavailable):
            await igni.processes.list()
        assert fake.socket.connections == 1


async def test_events_yields_every_broadcast() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        seen = []

        async def watch() -> None:
            async for event in igni.events():
                seen.append(event)
                if event.type == "push_notification":
                    return

        watcher = asyncio.ensure_future(watch())
        await asyncio.sleep(0.05)
        await fake.socket.broadcast(
            PushNotification(channel="session_named", payload={"name": "x"})
        )
        await asyncio.wait_for(watcher, 5)

    assert seen[-1].type == "push_notification"


def test_backoff_doubles_up_to_its_ceiling() -> None:
    assert list(Backoff().delays()) == [0.5, 1.0, 2.0, 4.0, 8.0], "0.1.0's five attempts"
    assert list(Backoff(attempts=6, first=0.5, most=3.0).delays()) == [
        0.5,
        1.0,
        2.0,
        3.0,
        3.0,
        3.0,
    ]
    assert list(Backoff(attempts=0).delays()) == []


async def test_a_reply_settles_its_call_and_a_stream_collects_its_run() -> None:
    router = Router()
    listener = router.listen()
    answer = router.expect("rpc-1")
    stream = router.open_stream("run-1")

    router.deliver(parse_event({"type": "rpc_request", "id": "rpc-1", "method": "echoed"}))
    assert not answer.done(), "igni echoing a request is not its answer"
    router.deliver(parse_event({"type": "rpc_response", "id": "rpc-1", "result": 3}))
    router.deliver(parse_event({"type": "content_delta", "id": "run-1", "text": "hi"}))
    router.deliver(parse_event({"type": "content_delta", "id": "run-2", "text": "theirs"}))

    replied = answer.result()
    assert isinstance(replied, RpcResponse) and replied.result == 3
    collected = stream.get_nowait()
    assert isinstance(collected, ContentDelta) and collected.id == "run-1"
    assert stream.empty(), "another run's message is not this stream's"
    assert listener.qsize() == 4, "a listener hears everything igni sends"


def test_no_two_clients_number_their_requests_alike() -> None:
    mine, theirs = Router(), Router()

    ids = [mine.new_id("run"), mine.new_id("run"), theirs.new_id("run")]

    assert len(set(ids)) == 3, "igni sends every client's messages to every client"
    assert all(i.startswith("run-") for i in ids)


async def test_an_interruption_ends_every_call_and_run_in_flight() -> None:
    router = Router()
    answer = router.expect("rpc-1")
    stream = router.open_stream("run-1")
    moved = RunInterrupted("igni moved")

    router.interrupt(moved)

    with pytest.raises(RunInterrupted):
        answer.result()
    interruption = stream.get_nowait()
    assert isinstance(interruption, Interruption) and interruption.error is moved


async def test_a_closed_stream_and_a_forgotten_call_hear_nothing_more() -> None:
    router = Router()
    stream = router.open_stream("run-1")
    router.close_stream("run-1")
    router.expect("rpc-1")
    router.forget("rpc-1")
    listener = router.listen()
    router.unlisten(listener)

    router.deliver(parse_event({"type": "content_delta", "id": "run-1", "text": "late"}))
    router.deliver(parse_event({"type": "rpc_response", "id": "rpc-1", "result": 1}))

    assert stream.empty() and listener.empty()


async def test_a_socket_replaced_or_closed_by_the_client_is_not_lost() -> None:
    lifecycle = Lifecycle()
    first, second = Link(_StubSocket()), Link(_StubSocket())  # type: ignore[arg-type]
    lifecycle.opening(first)
    lifecycle.opening(second)

    assert not lifecycle.lost(first), "a socket replaced by a newer one"
    lifecycle.opened()
    assert lifecycle.phase is Phase.OPEN
    lifecycle.close()
    assert not lifecycle.lost(second), "a socket the client closed itself"


async def test_a_failed_connection_says_why_to_whoever_sends_next() -> None:
    lifecycle = Lifecycle()
    lifecycle.failed(NotAllowed("not an active producer"))

    with pytest.raises(NotAllowed, match="not an active producer"):
        await lifecycle.socket(5.0, "igni")


async def test_a_connection_not_open_in_time_is_unavailable() -> None:
    with pytest.raises(Unavailable, match="igni is not connected"):
        await Lifecycle().socket(0.01, "igni")


async def test_a_message_igni_cannot_mean_is_passed_over_and_the_connection_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with FakeIgni() as fake:
        fake.methods.answers["list_background_processes"] = []
        async with IgniClient(fake.local()) as igni:
            with caplog.at_level(logging.WARNING, logger="igni_client.connection"):
                for socket in list(fake.socket._clients):
                    await socket.send("not json")
                    await socket.send(json.dumps(["not", "an", "object"]))
                assert await igni.processes.list() == []

    said = [record.getMessage() for record in caplog.records]
    assert any("not JSON" in line for line in said)
    assert any("not an object" in line for line in said)


async def test_a_negative_backoff_tries_once_and_gives_up() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.socket.busy_next(5)
        client = IgniClient(fake.fleet(Person("t-ada")), backoff=Backoff(attempts=-1, first=0.01))
        with pytest.raises(Unavailable, match="busy"):
            await client.connect()
        # 0.1.0 tried no times at all and returned as if connected.
        assert fake.socket.connections == 1


def test_a_backoff_is_fixed_once_made_and_counts_whole_attempts() -> None:
    backoff = Backoff()

    with pytest.raises(ValidationError):
        backoff.attempts = 9
    with pytest.raises(ValidationError):
        Backoff(attempts="many")  # type: ignore[arg-type]
    assert igni_client.Backoff is backoff_module.Backoff and "Backoff" in igni_client.__all__


def test_reply_is_a_public_name_of_the_package() -> None:
    from igni_client.replies import Reply

    assert igni_client.Reply is Reply and "Reply" in igni_client.__all__


def test_a_client_is_paced_by_a_backoff_not_a_count_of_attempts() -> None:
    with pytest.raises(TypeError):
        IgniClient(Local(url="ws://127.0.0.1:1"), reconnect_attempts=5)  # type: ignore[call-arg]
    assert list(inspect.signature(IgniClient).parameters) == ["target", "backoff"]


async def test_events_stop_listening_when_left_and_never_yield_a_welcome() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        events = igni.events()
        first = asyncio.ensure_future(anext(events))
        await asyncio.sleep(0.05)
        await fake.socket.move()
        await fake.socket.broadcast(PushNotification(channel="moved", payload={}))
        seen = await asyncio.wait_for(first, 5)
        await events.aclose()  # type: ignore[attr-defined]

        assert seen.type == "push_notification", "igni moving is the client's own business"
        assert igni._conn.router._listeners == [], "a watcher that left hears nothing more"


async def test_the_connection_module_keeps_only_the_socket() -> None:
    assert connection_module.__all__ == ["REFUSED_METHODS", "Connection"]
    assert frozenset(NOT_FOR_CLIENTS) == REFUSED_METHODS, (
        "igni-core's protocol test reads it: the methods no client sends"
    )
    assert not hasattr(connection_module, "Interruption"), "now igni_client.routing.Interruption"
    for moved in ("new_id", "open_stream", "close_stream", "listen", "unlisten"):
        assert not hasattr(Connection, moved) and hasattr(Router, moved), moved
    assert list(inspect.signature(Connection).parameters) == ["target", "backoff", "router"]

    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        with pytest.raises(AttributeError):
            await igni._conn.send({"type": "cancel", "session_id": "s-1"})  # type: ignore[arg-type]


async def test_closing_passes_over_a_socket_that_fails_to_close_and_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with FakeIgni() as fake:
        igni = await IgniClient(fake.local()).connect()
        socket = _live_socket(igni)
        real_close = socket.close
        socket.close = _raising(OSError("the line is gone"))
        with caplog.at_level(logging.INFO, logger="igni_client.connection"):
            await igni.close()
        await real_close()

    assert any("closing the socket" in r.getMessage() for r in caplog.records)
    assert igni._conn._lifecycle.phase is Phase.CLOSED


async def test_closing_raises_what_is_not_a_socket_error() -> None:
    async with FakeIgni() as fake:
        igni = await IgniClient(fake.local()).connect()
        socket = _live_socket(igni)
        real_close = socket.close
        socket.close = _raising(RuntimeError("a bug, not the line"))
        with pytest.raises(RuntimeError, match="a bug"):
            await igni.close()
        await real_close()


async def test_a_line_that_stops_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        with caplog.at_level(logging.INFO, logger="igni_client.connection"):
            await fake.socket.drop(1011)
            await _until(lambda: igni._conn._lifecycle.phase is Phase.FAILED)

    assert any("stopped" in r.getMessage() for r in caplog.records)


async def test_a_client_opened_again_after_closing_reconnects_when_its_line_drops() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        client = IgniClient(fake.fleet(Person("t-ada")), backoff=FAST)
        await client.connect()
        await client.close()
        await client.connect()
        await fake.socket.drop(1011)
        # 0.1.0 stayed "closing" for good, and never opened a dropped line again.
        await _until(lambda: fake.socket.connections == 3)
        await _until(lambda: client._conn._lifecycle.phase is Phase.OPEN)
        await client.close()


async def test_a_dropped_connection_that_stays_busy_gives_up() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        client = IgniClient(fake.fleet(Person("t-ada")), backoff=Backoff(attempts=2, first=0.01))
        async with client as igni:
            fake.socket.busy_next(10)
            await fake.socket.drop(1011)
            await _until(lambda: igni._conn._lifecycle.phase is Phase.FAILED)
            with pytest.raises(
                Unavailable, match=r"could not be reached again after it closed \(1011\)"
            ):
                await igni.processes.list()
        assert fake.socket.connections == 3


async def test_an_igni_that_never_says_welcome_is_unavailable() -> None:
    async with _igni_that(welcomes=False) as target:
        client = IgniClient(target)
        client._conn.WELCOME_TIMEOUT = 0.05
        with pytest.raises(Unavailable, match="did not say welcome"):
            await client.connect()


async def test_a_call_igni_never_answers_is_unavailable() -> None:
    async with _igni_that(welcomes=True) as target, IgniClient(target) as igni:
        igni._conn.RPC_TIMEOUT = 0.05
        with pytest.raises(
            Unavailable, match="list_background_processes got no answer from igni at"
        ):
            await igni.processes.list()


async def test_a_call_with_no_timeout_given_waits_the_connection_s_own_timeout() -> None:
    async def slowly(args: dict[str, Any]) -> list[Any]:
        await asyncio.sleep(0.15)
        return []

    async with FakeIgni() as fake:
        fake.methods.answers["list_background_processes"] = slowly
        async with IgniClient(fake.local()) as igni:
            igni._conn.RPC_TIMEOUT = 5.0
            # Left out, the timeout is RPC_TIMEOUT (not the -1 sentinel itself).
            assert await igni._conn.ask("list_background_processes") is not None
            # `None` waits as long as it takes; a number is that many seconds.
            assert await igni._conn.ask("list_background_processes", timeout=None) is not None
            with pytest.raises(Unavailable, match="got no answer"):
                await igni._conn.ask("list_background_processes", timeout=0.01)


async def test_closing_ends_every_call_in_flight() -> None:
    async with _igni_that(welcomes=True) as target:
        igni = await IgniClient(target).connect()
        call = asyncio.ensure_future(igni.processes.list())
        await asyncio.sleep(0.05)
        await igni.close()
        with pytest.raises(Unavailable, match="the client was closed"):
            await asyncio.wait_for(call, 5)


async def test_a_connection_opened_again_forgets_why_it_failed() -> None:
    lifecycle = Lifecycle()
    lifecycle.failed(NotAllowed("not an active producer"))
    link = Link(_StubSocket())  # type: ignore[arg-type]
    lifecycle.opening(link)
    assert lifecycle.pending_welcome() is link.welcomed

    lifecycle.opened()
    assert lifecycle.failure is None
    lifecycle.lost(link)
    with pytest.raises(Unavailable, match="igni is not connected"):
        await lifecycle.socket(0.01, "igni")


async def test_a_send_while_opening_waits_for_the_welcome() -> None:
    lifecycle = Lifecycle()
    link = Link(_StubSocket())  # type: ignore[arg-type]
    lifecycle.opening(link)
    sending = asyncio.ensure_future(lifecycle.socket(5.0, "igni"))
    await asyncio.sleep(0.01)
    assert not sending.done()

    link.welcomed.set_result(parse_event({"type": "welcome", "client_id": "ws-1"}))  # type: ignore[arg-type]
    assert lifecycle.pending_welcome() is None
    lifecycle.opened()

    assert await asyncio.wait_for(sending, 1) is link.socket


async def test_an_open_socket_is_given_even_when_there_is_no_time_to_wait() -> None:
    lifecycle = Lifecycle()
    link = Link(_StubSocket())  # type: ignore[arg-type]
    lifecycle.opening(link)
    lifecycle.opened()

    assert await lifecycle.socket(0, "igni") is link.socket


async def test_a_second_reply_and_a_message_without_an_id_go_no_further() -> None:
    router = Router()
    listener = router.listen()
    answer = router.expect("rpc-1")
    stream = router.open_stream("rpc-1")

    router.deliver(parse_event({"type": "rpc_response", "id": "rpc-1", "result": 1}))
    router.deliver(parse_event({"type": "rpc_response", "id": "rpc-1", "result": 2}))
    router.deliver(parse_event({"type": "content_delta", "text": "no id"}))

    replied = answer.result()
    assert isinstance(replied, RpcResponse) and replied.result == 1
    assert stream.empty(), "a reply belongs to its call, never to a stream"
    assert listener.qsize() == 3


async def test_one_queue_collects_a_run_and_its_approvals() -> None:
    router = Router()
    queue = router.open_stream("run-1")
    assert router.open_stream("hitl-1", queue) is queue

    router.deliver(parse_event({"type": "content_delta", "id": "run-1", "text": "a"}))
    router.deliver(parse_event({"type": "content_delta", "id": "hitl-1", "text": "b"}))

    assert queue.qsize() == 2


class _StubSocket:
    """Stands in for a socket where only its identity matters."""


def _sent(fake: FakeIgni, kind: str) -> int:
    return sum(1 for r in fake.socket.received if r.frame.type == kind)


def _attached(fake: FakeIgni, session_id: str) -> int:
    """Attaches naming `session_id`, and attaches of a new session (naming none)."""
    return sum(
        1
        for r in fake.socket.received
        if isinstance(r.frame, RpcRequest)
        and r.frame.method == "attach_session"
        and r.frame.args.get("session_id") in (session_id, None, "")
    )


async def _until(condition: object, timeout: float = 5.0) -> None:
    async def wait() -> None:
        while not condition():  # type: ignore[operator]
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait(), timeout)


def _live_socket(igni: IgniClient) -> Any:
    link = igni._conn._lifecycle.link
    assert link is not None
    return link.socket


def _raising(error: Exception) -> Callable[[], Awaitable[None]]:
    async def close() -> None:
        raise error

    return close


@asynccontextmanager
async def _igni_that(*, welcomes: bool) -> AsyncIterator[Local]:
    """A local igni that says welcome or not, and answers nothing."""

    async def serve_one(socket: ServerConnection) -> None:
        if welcomes:
            await socket.send(json.dumps({"type": "welcome", "client_id": "ws-1"}))
        async for _ in socket:
            pass

    async with serve(serve_one, "127.0.0.1", 0, subprotocols=[Subprotocol("igni.v1")]) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        yield Local(url=f"ws://127.0.0.1:{port}")


async def test_the_fake_answers_a_call_to_the_client_that_made_it_alone() -> None:
    async with FakeIgni() as fake:
        fake.methods.answers["list_background_processes"] = []
        async with IgniClient(fake.local()) as caller, IgniClient(fake.local()) as other:
            seen = other._conn.router.listen()
            assert await caller.processes.list() == []
            await fake.socket.push("session_named", {"session_id": "s", "name": "n"})
            await _until(lambda: not seen.empty())
            assert [seen.get_nowait().type] == ["push_notification"], (
                "igni answers a call to its caller; only a broadcast reaches the rest"
            )


async def test_a_vm_that_stays_unbound_is_unavailable_after_its_retries() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        igni._conn.UNBOUND_RETRY_SECONDS = 0.001
        igni._conn.UNBOUND_RETRIES = 4
        fake.methods.unbound_for(100)

        with pytest.raises(Unavailable, match="was not bound to its producer in time"):
            await igni.processes.list()

    asked = [c for c in fake.methods.calls if c.method == "list_background_processes"]
    assert len(asked) == 4, "one ask per retry, then it gives up"
    assert len({c.id for c in asked}) == 4, "each ask has an id of its own"


async def test_a_vm_is_asked_thirty_times_a_second_apart_before_it_is_given_up_on() -> None:
    assert Connection.UNBOUND_RETRIES == 30
    assert Connection.UNBOUND_RETRY_SECONDS == 1.0
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        igni._conn.UNBOUND_RETRY_SECONDS = 0.0
        fake.methods.answers["list_background_processes"] = lambda args: []
        fake.methods.unbound_for(29)
        assert await igni.processes.list() == [], "the thirtieth ask is answered"
        fake.methods.calls.clear()
        fake.methods.unbound_for(100)
        with pytest.raises(Unavailable, match="was not bound to its producer in time"):
            await igni.processes.list()

    asked = [c for c in fake.methods.calls if c.method == "list_background_processes"]
    assert len(asked) == 30


async def test_a_vm_unbound_and_then_failing_raises_the_failure_not_the_wait() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        igni._conn.UNBOUND_RETRY_SECONDS = 0.001
        fake.methods.answers["list_background_processes"] = lambda args: RpcResponse(
            error="the disk is full"
        )
        fake.methods.unbound_for(2)

        with pytest.raises(MethodFailed, match="the disk is full"):
            await igni.processes.list()


def test_a_backoff_that_starts_above_its_ceiling_or_at_nothing() -> None:
    assert list(Backoff(attempts=3, first=10.0, most=4.0).delays()) == [10.0, 4.0, 4.0]
    assert list(Backoff(attempts=3, first=0.0).delays()) == [0.0, 0.0, 0.0]
    with pytest.raises(ValidationError):
        Backoff(attempts=2.5)  # type: ignore[arg-type]


async def test_a_client_not_yet_open_has_no_name_and_closing_twice_is_harmless() -> None:
    async with FakeIgni() as fake:
        igni = IgniClient(fake.local())
        assert igni.client_id == ""
        with pytest.raises(Unavailable, match="not connected"):
            igni._conn.WELCOME_TIMEOUT = 0.01
            await igni._conn.send(Typing(text="x", client_id=""))
        await igni.connect()
        assert igni.client_id != ""
        await igni.close()
        await igni.close()


async def test_a_call_on_a_closed_client_fails_at_once_not_after_the_welcome_wait() -> None:
    async with FakeIgni() as fake:
        igni = await IgniClient(fake.local()).connect()
        session = await igni.sessions.create()
        await igni.close()
        igni._conn.WELCOME_TIMEOUT = 30  # a wait would outlast the test's own limit
        with pytest.raises(Unavailable, match="was closed"):
            await asyncio.wait_for(session.status(), 2)


async def test_me_on_a_local_igni_names_itself_not_commands() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        with pytest.raises(NotSupported, match=r"^me needs Fleet"):
            await igni.me()


async def test_a_local_igni_has_neither_commands_nor_an_identity_and_gateway_ones_are_cached() -> (
    None
):
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        with pytest.raises(NotSupported):
            _ = igni.commands
        with pytest.raises(NotSupported):
            await igni.me()

    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        client = IgniClient(fake.fleet(Person("t-ada")))
        assert client.commands is client.commands

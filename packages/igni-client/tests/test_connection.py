"""Connecting, and what happens when the connection changes under the client."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest

from igni_client import (
    AuthError,
    Backoff,
    IgniClient,
    Local,
    NotAllowed,
    Person,
    RunInterrupted,
    Unavailable,
)
from igni_client.events import PushNotification, RpcResponse, parse_event
from igni_client.frames import RpcRequest
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
                await igni.rpc("get_todos")
        assert fake.socket.connections == 1


async def test_a_local_igni_that_closed_is_not_reopened() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        await fake.socket.drop(1001, "going away")
        await _until(lambda: igni._conn._lifecycle.phase is Phase.FAILED)
        with pytest.raises(Unavailable):
            await igni.rpc("get_todos")
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

    assert isinstance(answer.result(), RpcResponse) and answer.result().result == 3
    assert stream.qsize() == 1 and stream.get_nowait().id == "run-1"
    assert listener.qsize() == 4, "a listener hears everything igni sends"


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
        fake.methods.answers["get_todos"] = []
        async with IgniClient(fake.local()) as igni:
            with caplog.at_level(logging.WARNING, logger="igni_client.connection"):
                for socket in list(fake.socket._clients):
                    await socket.send("not json")
                    await socket.send(json.dumps(["not", "an", "object"]))
                assert await igni.rpc("get_todos") == []

    said = [record.getMessage() for record in caplog.records]
    assert any("not JSON" in line for line in said)
    assert any("not an object" in line for line in said)


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

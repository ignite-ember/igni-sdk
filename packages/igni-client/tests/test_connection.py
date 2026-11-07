"""Connecting, and what happens when the connection changes under the client."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from igni_client import (
    AuthError,
    IgniClient,
    Local,
    NotAllowed,
    Person,
    RunInterrupted,
    Unavailable,
)
from igni_client.testing import Delay, FakeIgni

TOKENS = {"t-ada": "person:u-ada"}


async def test_a_local_igni_is_found_from_its_lockfile(tmp_path: Path) -> None:
    async with FakeIgni(local_token="launch-secret") as fake:
        (tmp_path / ".igni").mkdir()
        (tmp_path / ".igni" / "backend.lock").write_text(
            json.dumps(
                {
                    "pid": 1,
                    "port": fake.port,
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
            await IgniClient(Local(url=f"ws://127.0.0.1:{fake.port}", token="wrong")).connect()


def _lockfile(project: Path, port: int, token: str) -> None:
    (project / ".igni").mkdir()
    (project / ".igni" / "backend.lock").write_text(
        json.dumps(
            {"pid": 1, "port": port, "wire_version": "1.0.3", "created_at": 0, "ws_token": token}
        )
    )


async def test_an_approver_token_is_offered_instead_of_the_lockfile_s(tmp_path: Path) -> None:
    async with FakeIgni(local_token="approver") as fake:
        _lockfile(tmp_path, fake.port, "program")
        local = Local(project_dir=tmp_path, approver_token="approver")
        assert local.approves
        async with IgniClient(local) as igni:
            assert igni.client_id.startswith("ws-")


async def test_an_approver_token_is_taken_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IGNI_APPROVER_TOKEN", "approver")
    async with FakeIgni(local_token="approver") as fake:
        _lockfile(tmp_path, fake.port, "program")
        async with IgniClient(Local(project_dir=tmp_path)) as igni:
            assert igni.client_id.startswith("ws-")


async def test_a_refused_approver_token_says_to_make_a_new_one(tmp_path: Path) -> None:
    async with FakeIgni(local_token="current") as fake:
        _lockfile(tmp_path, fake.port, "program")
        with pytest.raises(AuthError, match="/programs"):
            await IgniClient(Local(project_dir=tmp_path, approver_token="revoked")).connect()


async def test_the_gateway_refuses_a_token_it_does_not_know() -> None:
    async with FakeIgni(gateway=True, tokens=TOKENS) as fake:
        with pytest.raises(AuthError, match="the token was refused"):
            await IgniClient(fake.fleet(Person("t-stranger"))).connect()


async def test_busy_is_tried_again() -> None:
    async with FakeIgni(gateway=True, tokens=TOKENS) as fake:
        fake.busy_next(2)
        client = IgniClient(fake.fleet(Person("t-ada")))
        client._conn._backoff = 0.01
        async with client:
            assert fake.connections == 3


async def test_busy_for_too_long_is_unavailable() -> None:
    async with FakeIgni(gateway=True, tokens=TOKENS) as fake:
        fake.busy_next(10)
        client = IgniClient(fake.fleet(Person("t-ada")), reconnect_attempts=2)
        client._conn._backoff = 0.01
        with pytest.raises(Unavailable, match="busy"):
            await client.connect()


async def test_when_igni_moves_a_run_in_flight_is_interrupted_and_sessions_reattach() -> None:
    async with FakeIgni(gateway=True, tokens=TOKENS) as fake:
        fake.script = lambda text: [Delay(seconds=30)]
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            session = await igni.sessions.create()
            run = asyncio.ensure_future(session.ask("long"))
            await _until(lambda: _sent(fake, "user_message") == 1)
            await fake.move()
            with pytest.raises(RunInterrupted):
                await asyncio.wait_for(run, 5)
            await _until(lambda: _attached(fake, session.id) == 2)
            fake.script = lambda text: FakeIgni.answer("after the move")
            assert str(await session.ask("again")) == "after the move"


async def test_a_dropped_connection_is_opened_again_with_a_fresh_token() -> None:
    issued: list[int] = []

    class Counting:
        async def token(self) -> str:
            issued.append(1)
            return "t-ada"

    async with FakeIgni(gateway=True, tokens=TOKENS) as fake:
        client = IgniClient(fake.fleet(Counting()))
        client._conn._backoff = 0.01
        async with client as igni:
            session = await igni.sessions.create()
            await fake.drop(1011)
            await _until(lambda: fake.connections == 2 and _attached(fake, session.id) == 2)
            assert str(await session.ask("still there?")) == "echo: still there?"

    # One token for the socket and one for each open; the fake's HTTP is not used here.
    assert len(issued) == 2


async def test_a_producer_no_longer_active_is_final() -> None:
    async with FakeIgni(gateway=True, tokens=TOKENS) as fake:
        client = IgniClient(fake.fleet(Person("t-ada")))
        client._conn._backoff = 0.01
        async with client as igni:
            await fake.drop(1008, "not an active producer")
            await _until(lambda: igni._conn._failure is not None)
            with pytest.raises(NotAllowed, match="not an active producer"):
                await igni.rpc("get_todos")
        assert fake.connections == 1


async def test_a_local_igni_that_closed_is_not_reopened() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        await fake.drop(1001, "going away")
        await _until(lambda: igni._conn._failure is not None)
        with pytest.raises(Unavailable):
            await igni.rpc("get_todos")
        assert fake.connections == 1


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
        await fake.emit(
            {"type": "push_notification", "channel": "session_named", "payload": {"name": "x"}}
        )
        await asyncio.wait_for(watcher, 5)

    assert seen[-1].type == "push_notification"


def _sent(fake: FakeIgni, kind: str) -> int:
    return sum(1 for r in fake.received if r.frame.get("type") == kind)


def _attached(fake: FakeIgni, session_id: str) -> int:
    return sum(
        1
        for r in fake.received
        if r.frame.get("method") == "attach_session"
        and (r.frame.get("args") or {}).get("session_id") == session_id
    ) + sum(
        1
        for r in fake.received
        if r.frame.get("method") == "attach_session"
        and not (r.frame.get("args") or {}).get("session_id")
    )


async def _until(condition: object, timeout: float = 5.0) -> None:
    async def wait() -> None:
        while not condition():  # type: ignore[operator]
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait(), timeout)

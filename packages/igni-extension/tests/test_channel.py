"""`HostConnection`: the socket to igni, through its failures.

test_host.py covers the protocol against `FakeHost`. These are about the
connection itself: a host that is not there, that never says hello, that
goes away mid-request or never answers, and what the connection does
about each. A host that misbehaves is a few lines of `websockets`, a
`Script`; a well-behaved one is `FakeHost`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.datastructures import Headers

from igni_extension import (
    Allow,
    Caller,
    CallerKind,
    Hooks,
    HostError,
    HostUnavailable,
    IgniExtension,
    NotConfigured,
    Reject,
)
from igni_extension.hooks import PlanSubmit
from igni_extension.host_model import Run
from igni_extension.testing import FakeHost
from igni_extension.wire import Hello, Reply, Request

SECRET = "s3cret"
PLAN = {"session_id": "s-1", "plan": "Refactor it.", "tasks": [], "attempt": 0}
HELLO = Hello(op="hello", schema_version="1", granted=["chat.read"], extension_id="acme.example")


class Script:
    """A host that does what a test says: `handler` gets each socket that connects."""

    def __init__(self, handler: Callable[[ServerConnection], Awaitable[None]]) -> None:
        self._handler = handler
        self._server: Server | None = None
        self.url = ""
        self.headers: list[Headers] = []
        """The headers each connection came with."""
        self.opened = 0
        """How many sockets were opened."""

    async def _serve(self, socket: ServerConnection) -> None:
        self.opened += 1
        if socket.request is not None:
            self.headers.append(socket.request.headers)
        await self._handler(socket)

    async def __aenter__(self) -> Script:
        self._server = await serve(self._serve, "127.0.0.1", 0, compression=None)
        port = int(next(iter(self._server.sockets)).getsockname()[1])
        self.url = f"ws://127.0.0.1:{port}/v1/host"
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    def environment(self) -> dict[str, str]:
        return {"IGNI_HOST_URL": self.url, "IGNI_HOST_SECRET": SECRET}


async def say_hello(socket: ServerConnection) -> None:
    await socket.send(HELLO.model_dump_json())


async def answer_nothing(socket: ServerConnection) -> None:
    """Hello, then silence to every request."""
    await say_hello(socket)
    async for _ in socket:
        pass


@pytest.fixture
async def fake() -> AsyncIterator[FakeHost]:
    async with FakeHost(granted=("chat.read",), values={"chat.processing": False}) as host:
        yield host


async def _until(condition: Callable[[], bool], seconds: float = 5.0) -> None:
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(0.01)


async def test_a_host_nobody_listens_for_is_unavailable() -> None:
    async with Script(say_hello) as script:
        environment = script.environment()
    ext = IgniExtension("acme.example", environ=environment)

    with pytest.raises(HostUnavailable, match="did not answer"):
        await ext.connect()

    assert not ext.connection.connected
    await ext.aclose()


async def test_only_one_of_the_two_variables_is_no_host() -> None:
    ext = IgniExtension("acme.example", environ={"IGNI_HOST_URL": "ws://127.0.0.1:1/v1/host"})

    assert not ext.connection.configured
    with pytest.raises(NotConfigured):
        await ext.connection.request("get", "chat.processing")


async def test_a_host_that_never_says_hello_is_given_up_on(monkeypatch: pytest.MonkeyPatch) -> None:
    async with Script(answer_nothing_without_hello) as script:
        ext = IgniExtension("acme.example", environ=script.environment())
        monkeypatch.setattr(ext.connection, "TIMEOUT", 0.2)

        with pytest.raises(HostUnavailable, match="did not say hello"):
            await ext.connect()

        assert not ext.connection.connected
        assert ext.connection.granted == []
        await ext.aclose()


async def answer_nothing_without_hello(socket: ServerConnection) -> None:
    async for _ in socket:
        pass


async def test_a_host_that_hangs_up_before_hello_fails_at_once() -> None:
    async def hang_up(socket: ServerConnection) -> None:
        await socket.close()

    async with Script(hang_up) as script:
        ext = IgniExtension("acme.example", environ=script.environment())

        with pytest.raises(HostUnavailable):
            await asyncio.wait_for(ext.connect(), 3)

        assert not ext.connection.connected
        await ext.aclose()


async def test_a_request_the_host_never_answers_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    async with Script(answer_nothing) as script:
        ext = IgniExtension("acme.example", environ=script.environment())
        monkeypatch.setattr(ext.connection, "TIMEOUT", 0.2)

        with pytest.raises(HostUnavailable, match=r"host\.chat\.processing got no answer"):
            await ext.host.chat.processing

        await ext.aclose()


async def test_a_dialog_waits_on_the_person_for_as_long_as_they_take(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def answer_late(socket: ServerConnection) -> None:
        await say_hello(socket)
        async for raw in socket:
            request = Request.model_validate_json(raw)
            await asyncio.sleep(0.4)
            await socket.send(
                Reply(op="reply", id=request.id, ok=True, result="picked").model_dump_json()
            )

    async with Script(answer_late) as script:
        ext = IgniExtension("acme.example", environ=script.environment())
        monkeypatch.setattr(ext.connection, "TIMEOUT", 0.1)

        assert await ext.connection.request("call", "ui.show_dialog") == "picked"
        with pytest.raises(HostUnavailable, match="got no answer"):
            await ext.connection.request("call", "chat.post")

        await ext.aclose()


async def test_a_host_that_drops_the_socket_mid_request_fails_the_waiting_request() -> None:
    async def drop_on_request(socket: ServerConnection) -> None:
        await say_hello(socket)
        async for _ in socket:
            await socket.close()

    async with Script(drop_on_request) as script:
        ext = IgniExtension("acme.example", environ=script.environment())

        with pytest.raises(HostUnavailable):
            await asyncio.wait_for(ext.host.chat.processing.get(), 3)

        await _until(lambda: not ext.connection.connected)
        await ext.aclose()


async def test_a_reply_for_nothing_asked_is_ignored() -> None:
    async def stray_then_answer(socket: ServerConnection) -> None:
        await say_hello(socket)
        async for raw in socket:
            request = Request.model_validate_json(raw)
            for stray in (None, 9999, "x"):
                await socket.send(
                    Reply(op="reply", id=stray, ok=True, result="stray").model_dump_json()
                )
            await socket.send(
                Reply(op="reply", id=request.id, ok=True, result="mine").model_dump_json()
            )

    async with Script(stray_then_answer) as script:
        ext = IgniExtension("acme.example", environ=script.environment())

        assert await asyncio.wait_for(ext.connection.request("get", "chat.processing"), 3) == "mine"
        assert ext.connection.connected
        await ext.aclose()


async def test_a_frame_over_the_limit_closes_the_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def send_a_big_one(socket: ServerConnection) -> None:
        await say_hello(socket)
        async for _ in socket:
            await socket.send(Reply(op="reply", id=1, ok=True, result="x" * 4096).model_dump_json())

    async with Script(send_a_big_one) as script:
        ext = IgniExtension("acme.example", environ=script.environment())
        monkeypatch.setattr(ext.connection, "MAX_FRAME", 1024)

        with pytest.raises(HostUnavailable):
            await asyncio.wait_for(ext.connection.request("get", "chat.processing"), 3)

        await _until(lambda: not ext.connection.connected)
        await ext.aclose()


async def test_the_secret_and_the_process_group_go_with_the_connection() -> None:
    async with Script(say_hello) as script:
        ext = IgniExtension("acme.example", environ=script.environment())
        await ext.connect()

        [headers] = script.headers
        assert headers.get("Authorization") == f"Bearer {SECRET}"
        assert headers.get("X-Igni-Process-Group") == str(os.getpgid(0))
        await ext.aclose()


async def test_without_process_groups_only_the_secret_goes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(os, "getpgid")
    async with Script(say_hello) as script:
        ext = IgniExtension("acme.example", environ=script.environment())
        await ext.connect()

        [headers] = script.headers
        assert headers.get("Authorization") == f"Bearer {SECRET}"
        assert headers.get("X-Igni-Process-Group") is None
        await ext.aclose()


async def test_calls_that_connect_at_once_share_one_socket(fake: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())

    async with asyncio.timeout(5):
        await asyncio.gather(*(ext.connection.connect() for _ in range(5)))
        await asyncio.gather(*(ext.host.chat.processing.get() for _ in range(5)))

    assert len(fake._sockets) == 1
    await ext.aclose()


async def test_connecting_again_changes_nothing(fake: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())

    await ext.connect()
    await ext.connect()

    assert ext.connection.connected and len(fake._sockets) == 1
    assert ext.connection.granted == ["chat.read"]
    await ext.aclose()


async def test_closing_before_connecting_or_twice_is_harmless(fake: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())

    await ext.connection.close()
    await ext.connect()
    await ext.connection.close()
    await ext.connection.close()

    assert not ext.connection.connected
    await ext.aclose()


async def test_a_request_after_the_host_dropped_us_reconnects(fake: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())
    assert await ext.host.chat.processing is False

    for socket in list(fake._sockets):
        await socket.close()
    await _until(lambda: not ext.connection.connected)

    assert await ext.host.chat.processing is False
    assert ext.connection.connected
    await ext.aclose()


async def test_serving_without_a_host_returns_at_once() -> None:
    ext = IgniExtension("acme.example", environ={})

    await asyncio.wait_for(ext.connection.serve_forever(), 1)

    assert not ext.connection.connected


async def test_serving_waits_for_a_host_that_is_not_there_yet_and_keeps_signals_subscribed(
    fake: FakeHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())
    monkeypatch.setattr(ext.connection, "RETRY_SECONDS", 0.05)

    @ext.on(ext.host.chat.run_completed)
    async def completed(run: Run) -> None: ...

    serving = asyncio.create_task(ext.connection.serve_forever())
    try:
        await fake.wait_subscribed("chat.run_completed")
        assert ext.connection.granted == ["chat.read"]

        fake.subscribed.clear()
        fake.granted = ["chat.read", "chat.post"]
        for socket in list(fake._sockets):
            await socket.close()

        await fake.wait_subscribed("chat.run_completed")
        assert ext.connection.connected
        assert ext.connection.granted == ["chat.read", "chat.post"], "refreshed on reconnecting"
    finally:
        serving.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await serving
        await ext.aclose()


async def test_serving_connects_once_the_host_appears(monkeypatch: pytest.MonkeyPatch) -> None:
    async with FakeHost() as host:
        environment = host.environment()
        url = host.url
    ext = IgniExtension("acme.example", environ=environment)
    monkeypatch.setattr(ext.connection, "RETRY_SECONDS", 0.05)
    serving = asyncio.create_task(ext.connection.serve_forever())
    try:
        await asyncio.sleep(0.2)
        assert not ext.connection.connected, f"nothing listens at {url}"
        assert not serving.done()
    finally:
        serving.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await serving
        await ext.aclose()


async def test_closing_cancels_the_work_a_signal_started(fake: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())
    started = asyncio.Event()
    cancelled = asyncio.Event()

    @ext.on(ext.host.chat.run_completed)
    async def slow(run: Run) -> None:
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    await ext.connect()
    await fake.wait_subscribed("chat.run_completed")
    await fake.emit(
        "chat.run_completed",
        {
            "session_id": "s",
            "run_id": "r",
            "parent_run_id": "",
            "input_tokens": 1,
            "output_tokens": 1,
            "reasoning_tokens": 0,
            "duration": 0.2,
            "changed_files": [],
        },
    )
    await asyncio.wait_for(started.wait(), 3)

    await ext.connection.close()

    await asyncio.wait_for(cancelled.wait(), 3)
    assert not ext.connection.connected
    await ext.aclose()


async def test_a_deciding_hook_answered_too_late_is_warned_not_raised(
    fake: FakeHost, caplog: pytest.LogCaptureFixture
) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())

    @ext.hook(Hooks.PLAN_SUBMIT)
    async def slow(plan: PlanSubmit) -> Allow:
        await asyncio.sleep(0.3)
        return Allow()

    await ext.connect()
    with caplog.at_level(logging.WARNING, logger="igni_extension.channel"):
        with pytest.raises(TimeoutError):
            await fake.hook("PlanSubmit", PLAN, timeout=0.05)
        await _until(lambda: "did not count" in caplog.text)

    assert "the answer to PlanSubmit did not count" in caplog.text
    assert ext.connection.connected
    await ext.aclose()


async def test_a_reader_that_fails_is_logged_not_lost(
    fake: FakeHost, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())

    def boom(message: object) -> None:
        raise RuntimeError("cannot take this")

    await ext.connect()
    monkeypatch.setattr(ext.connection, "_receive", boom)
    with caplog.at_level(logging.ERROR, logger="igni_extension.channel"):
        await fake.tell("SessionStart", {})
        await _until(lambda: not ext.connection.connected)
        await ext.connection.close()

    assert "reading the host's socket failed" in caplog.text
    assert "cannot take this" in caplog.text
    await ext.aclose()


async def test_a_refusal_comes_back_as_the_hosts_error(fake: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())

    with pytest.raises(HostError) as caught:
        await ext.connection.request("get", "nothing.here")

    assert caught.value.code == "not_found"
    await ext.aclose()


async def test_a_deciding_hook_over_the_socket_is_decided_for_the_caller_igni_named(
    fake: FakeHost,
) -> None:
    ext = IgniExtension("acme.example", environ=fake.environment())
    ada = Caller(kind=CallerKind.PERSON, id="u-ada", org="org-acme", group="g-legal")

    @ext.hook(Hooks.PLAN_SUBMIT)
    async def only_for(plan: PlanSubmit, caller: Caller | None) -> Allow | Reject:
        return Allow() if caller == ada else Reject(f"not for {caller and caller.ref}")

    await ext.connect()

    assert (await fake.hook("PlanSubmit", PLAN, caller=ada))["outcome"] == "allow"
    nobody = await fake.hook("PlanSubmit", PLAN)
    assert (nobody["outcome"], nobody["reason"]) == ("reject", "not for None")
    await ext.aclose()


async def test_a_socket_that_fails_sending_says_the_host_went_away(fake: FakeHost) -> None:
    class Broken:
        async def send(self, frame: object) -> None:
            raise OSError("broken pipe")

    ext = IgniExtension("acme.example", environ=fake.environment())
    await ext.connection.connect()
    real = ext.connection._socket
    ext.connection._socket = Broken()  # type: ignore[assignment]
    try:
        with pytest.raises(HostUnavailable, match="went away: broken pipe"):
            await ext.host.chat.processing.get()
    finally:
        ext.connection._socket = real
        await ext.aclose()

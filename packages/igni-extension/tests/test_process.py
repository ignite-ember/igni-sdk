"""`ext.process`: what `ext.run()` and `ext.serve()` do before, while and after they serve."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading

import anyio
import pytest
from mcp.shared.message import SessionMessage

from igni_extension import IgniExtension, ToolHints, ToolHintsMissing
from igni_extension.testing import HostHarness

READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)
HOST = {"IGNI_HOST_URL": "ws://127.0.0.1:9", "IGNI_HOST_SECRET": "s3cret"}


class Stdin:
    def __init__(self, interactive: bool | Exception) -> None:
        self.interactive = interactive

    def isatty(self) -> bool:
        if isinstance(self.interactive, Exception):
            raise self.interactive
        return self.interactive


def run_without_serving(monkeypatch: pytest.MonkeyPatch, ext: IgniExtension) -> list[str]:
    served: list[str] = []
    monkeypatch.setattr("anyio.run", lambda *args, **kwargs: served.append("served"))
    ext.run()
    return served


def test_a_terminal_with_no_host_gets_the_hint_and_the_process_still_serves(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", Stdin(True))

    served = run_without_serving(monkeypatch, IgniExtension("acme.example", environ={}))

    assert served == ["served"]
    said = capsys.readouterr()
    assert said.out == ""
    assert said.err.startswith("acme.example: this is an igni extension's process")
    assert "Waiting for MCP messages on stdin (Ctrl-C to stop)." in said.err


def test_a_terminal_with_the_host_socket_configured_gets_no_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", Stdin(True))

    served = run_without_serving(monkeypatch, IgniExtension("acme.example", environ=HOST))

    assert served == ["served"]
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("failure", [AttributeError("no isatty"), ValueError("closed file")])
def test_a_stdin_that_cannot_say_whether_it_is_a_terminal_gets_no_hint_and_still_serves(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], failure: Exception
) -> None:
    monkeypatch.setattr(sys, "stdin", Stdin(failure))

    served = run_without_serving(monkeypatch, IgniExtension("acme.example", environ={}))

    assert served == ["served"]
    assert capsys.readouterr().err == ""


def test_a_stdin_with_no_isatty_at_all_gets_no_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", object())

    served = run_without_serving(monkeypatch, IgniExtension("acme.example", environ={}))

    assert served == ["served"]
    assert capsys.readouterr().err == ""


def with_a_tool_that_states_no_hints() -> IgniExtension:
    ext = IgniExtension("acme.example", environ={})

    @ext.mcp.tool()
    def unstated() -> str:
        return "x"

    return ext


async def test_a_tool_with_a_hint_unstated_stops_serve_before_any_message_is_read() -> None:
    ext = with_a_tool_that_states_no_hints()
    _, reads = anyio.create_memory_object_stream[SessionMessage | Exception](1)
    writes, _ = anyio.create_memory_object_stream[SessionMessage](1)

    with anyio.fail_after(5), pytest.raises(ToolHintsMissing, match="unstated"):
        await ext.process.serve(reads, writes)


def test_a_tool_with_a_hint_unstated_stops_run_before_it_serves() -> None:
    with pytest.raises(ToolHintsMissing, match="unstated"):
        with_a_tool_that_states_no_hints().run()


class Serving:
    """An extension whose stdio server is replaced by one the test releases."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, environ: dict[str, str] | None = None):
        self.ext = IgniExtension("acme.example", environ=environ or {})
        self.release = asyncio.Event()
        self.closed = 0
        self.events: list[str] = []

        async def run_stdio_async() -> None:
            await self.release.wait()

        async def closing() -> None:
            self.closed += 1
            self.events.append("closed")

        monkeypatch.setattr(self.ext.mcp, "run_stdio_async", run_stdio_async)
        monkeypatch.setattr(self.ext.process, "_close", closing)

    async def serve_until_released(self) -> None:
        task = asyncio.create_task(self.ext.process._run_stdio())
        await asyncio.sleep(0.05)
        self.release.set()
        await asyncio.wait_for(task, 5)


async def test_every_on_start_function_runs_beside_the_server_and_is_cancelled_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serving = Serving(monkeypatch)
    started: list[str] = []
    cancelled: list[str] = []

    for name in ("first", "second"):

        async def background(name: str = name) -> None:
            started.append(name)
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.append(name)
                raise

        serving.ext.on_start(background)

    await serving.serve_until_released()

    assert started == ["first", "second"]
    assert cancelled == ["first", "second"]
    assert serving.closed == 1


async def test_a_plain_function_runs_off_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    serving = Serving(monkeypatch)
    ran_in: list[int] = []
    done = threading.Event()

    def sync_work() -> None:
        ran_in.append(threading.get_ident())
        done.set()

    serving.ext.on_start(sync_work)
    await serving.serve_until_released()

    assert done.is_set()
    assert ran_in != [threading.get_ident()]


async def test_background_work_that_fails_is_logged_and_does_not_stop_the_rest_or_the_close(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    serving = Serving(monkeypatch)
    survivor_cancelled = asyncio.Event()

    async def fails() -> None:
        raise RuntimeError("the sync broke")

    async def survives() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            survivor_cancelled.set()
            raise

    serving.ext.on_start(fails)
    serving.ext.on_start(survives)

    with caplog.at_level(logging.DEBUG, logger="igni_extension.process"):
        await serving.serve_until_released()

    assert survivor_cancelled.is_set()
    assert serving.closed == 1
    [failure] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert failure.getMessage() == "igni: background work ended in failure"
    assert failure.exc_info is not None and "the sync broke" in str(failure.exc_info[1])


async def test_work_that_fails_while_being_cancelled_is_logged_and_the_close_still_runs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    serving = Serving(monkeypatch)

    async def tidy_up_badly() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            raise RuntimeError("could not clean up")

    serving.ext.on_start(tidy_up_badly)

    with caplog.at_level(logging.ERROR, logger="igni_extension.process"):
        await serving.serve_until_released()

    assert serving.closed == 1
    assert any("could not clean up" in str(r.exc_info[1]) for r in caplog.records if r.exc_info)


async def test_the_server_failing_still_cancels_the_work_and_closes_the_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serving = Serving(monkeypatch)
    stopped = asyncio.Event()

    async def broken_stdio() -> None:
        await asyncio.sleep(0.02)
        raise RuntimeError("stdio failed")

    async def background() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            stopped.set()

    monkeypatch.setattr(serving.ext.mcp, "run_stdio_async", broken_stdio)
    serving.ext.on_start(background)

    with pytest.raises(RuntimeError, match="stdio failed"):
        await serving.ext.process._run_stdio()

    assert stopped.is_set() and serving.closed == 1


async def test_a_second_cancellation_during_teardown_still_closes_the_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serving = Serving(monkeypatch)
    in_cleanup = asyncio.Event()

    async def slow_cleanup() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            in_cleanup.set()
            await asyncio.sleep(60)  # cleanup that takes long enough to be cancelled again

    serving.ext.on_start(slow_cleanup)
    task = asyncio.create_task(serving.ext.process._run_stdio())
    await asyncio.sleep(0.05)
    serving.release.set()
    await asyncio.wait_for(in_cleanup.wait(), 5)
    task.cancel()
    await asyncio.wait({task}, timeout=5)

    assert task.done() and serving.closed == 1


async def test_serve_over_streams_starts_no_on_start_work() -> None:
    ext = IgniExtension("acme.example", environ={})
    ran: list[str] = []

    @ext.on_start
    async def background() -> None:
        ran.append("ran")

    @ext.tool(hints=READS)
    def ping() -> str:
        return "pong"

    async with HostHarness(ext) as host:
        result = await host.call("ping")
        await asyncio.sleep(0.05)

    assert not result.is_error
    assert ran == []

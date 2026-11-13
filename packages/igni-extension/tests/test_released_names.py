"""`IgniExtension`'s 0.1.0 names, kept for the code written to them, each doing what the new place does."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import anyio
import pytest
from mcp import ClientSession
from mcp.shared.message import SessionMessage

from igni_extension import IgniExtension, ToolHints, ToolHintsMissing
from igni_extension.released import ReleasedNames
from igni_extension.testing import FakeHost, HostHarness

READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)
LEASE = {
    "id": "busy-1",
    "kind": "extension",
    "holder": "acme.example",
    "reason": "indexing",
    "since": "2026-10-26T12:00:00Z",
    "expires_at": "2026-10-26T12:02:00Z",
}


def an_extension(environ: dict[str, str] | None = None) -> IgniExtension:
    ext = IgniExtension("acme.example", environ=environ or {})

    @ext.tool(hints=READS)
    def ping() -> str:
        return "pong"

    return ext


def test_a_class_that_does_not_override_process_says_it_has_none() -> None:
    class Bare(ReleasedNames):
        pass

    with pytest.raises(NotImplementedError):
        _ = Bare().process


async def test_the_released_serve_serves_a_session_over_the_streams() -> None:
    ext = an_extension()
    to_server, server_reads = anyio.create_memory_object_stream[SessionMessage | Exception](16)
    server_writes, from_server = anyio.create_memory_object_stream[SessionMessage](16)
    answered: list[str] = []

    async def igni() -> None:
        async with ClientSession(from_server, to_server) as client:
            await client.initialize()
            result = await client.call_tool("ping", {})
            answered.append(result.content[0].text)  # type: ignore[union-attr]
        await to_server.aclose()

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(igni)
            await ext.serve(server_reads, server_writes)

    assert answered == ["pong"]


async def test_the_released_serve_checks_the_hints_first() -> None:
    ext = an_extension()

    @ext.mcp.tool()
    def unstated() -> str:
        return "x"

    _, server_reads = anyio.create_memory_object_stream[SessionMessage | Exception](1)
    server_writes, _ = anyio.create_memory_object_stream[SessionMessage](1)

    with anyio.fail_after(5), pytest.raises(ToolHintsMissing, match="unstated"):
        await ext.serve(server_reads, server_writes)


async def test_check_tools_refuses_a_tool_with_a_hint_unstated_and_passes_the_rest() -> None:
    ext = an_extension()
    await ext.check_tools()

    @ext.mcp.tool()
    def unstated() -> str:
        return "x"

    with pytest.raises(ToolHintsMissing, match="unstated"):
        await ext.check_tools()


async def test_observing_tells_the_observer_of_each_call_for_as_long_as_the_block_runs() -> None:
    ext = an_extension()
    seen: list[str] = []

    @contextlib.contextmanager
    def observer(tool: str) -> Iterator[None]:
        seen.append(f"enter {tool}")
        yield
        seen.append(f"exit {tool}")

    async with HostHarness(ext) as host:
        with ext.observing(observer):
            await host.call("ping")
        await host.call("ping")

    assert seen == ["enter ping", "exit ping"]


async def test_busy_while_leases_for_120_seconds_by_default_and_done_lets_go() -> None:
    async with FakeHost(answers={"self.busy": LEASE}) as fake:
        ext = an_extension(fake.environment())

        async with ext.busy_while("indexing"):
            pass
        async with ext.busy_while("syncing", 60):
            pass
        await ext.done("last")
        await ext.aclose()

    calls = [(c.path, c.params) for c in fake.calls]
    assert calls == [
        ("self.busy", {"reason": "indexing", "ttl_seconds": 120.0}),
        ("self.done", {"reason": "indexing"}),
        ("self.busy", {"reason": "syncing", "ttl_seconds": 60}),
        ("self.done", {"reason": "syncing"}),
        ("self.done", {"reason": "last"}),
    ]

"""`ext.mcp.serve`: one MCP session over whatever streams a caller holds."""

from __future__ import annotations

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession
from mcp.shared.message import SessionMessage

from igni_extension import IgniExtension, ToolHints

READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)


def an_extension() -> IgniExtension:
    ext = IgniExtension("acme.example", environ={})

    @ext.tool(hints=READS)
    def shout(word: str) -> str:
        return word.upper()

    return ext


def streams() -> tuple[
    MemoryObjectSendStream[SessionMessage | Exception],
    MemoryObjectReceiveStream[SessionMessage | Exception],
    MemoryObjectSendStream[SessionMessage],
    MemoryObjectReceiveStream[SessionMessage],
]:
    to_server, server_reads = anyio.create_memory_object_stream[SessionMessage | Exception](16)
    server_writes, from_server = anyio.create_memory_object_stream[SessionMessage](16)
    return to_server, server_reads, server_writes, from_server


async def test_serve_returns_when_the_streams_close_before_igni_says_anything() -> None:
    ext = an_extension()
    to_server, server_reads, server_writes, from_server = streams()

    await to_server.aclose()
    with anyio.fail_after(5):
        await ext.mcp.serve(server_reads, server_writes)

    await from_server.aclose()


async def test_serve_answers_a_session_and_returns_when_igni_closes_its_end() -> None:
    ext = an_extension()
    to_server, server_reads, server_writes, from_server = streams()
    answered: list[str] = []

    async def igni() -> None:
        async with ClientSession(from_server, to_server) as client:
            await client.initialize()
            result = await client.call_tool("shout", {"word": "hello"})
            answered.append(result.content[0].text)  # type: ignore[union-attr]
        await to_server.aclose()

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(igni)
            await ext.mcp.serve(server_reads, server_writes)

    assert answered == ["HELLO"]


async def test_serve_goes_on_serving_after_an_error_arrives_on_the_stream() -> None:
    ext = an_extension()
    to_server, server_reads, server_writes, from_server = streams()
    answered: list[str] = []

    async def igni() -> None:
        async with ClientSession(from_server, to_server) as client:
            await client.initialize()
            await to_server.send(ValueError("the pipe hiccuped"))
            result = await client.call_tool("shout", {"word": "still"})
            answered.append(result.content[0].text)  # type: ignore[union-attr]
        await to_server.aclose()

    with anyio.fail_after(5):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(igni)
            await ext.mcp.serve(server_reads, server_writes)

    assert answered == ["STILL"]

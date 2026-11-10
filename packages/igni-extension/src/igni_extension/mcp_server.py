"""`ext.mcp`: the MCP server igni talks to, servable over any pair of streams."""

from __future__ import annotations

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.server.mcpserver import MCPServer
from mcp.shared.message import SessionMessage


class ExtensionMcpServer(MCPServer):
    """An `MCPServer` that serves one session over the streams it is given.

    `run_stdio_async` serves stdio; `serve` serves whatever streams a caller
    holds — the in-memory pair `testing.HostHarness` connects over.
    """

    async def serve(
        self,
        read_stream: MemoryObjectReceiveStream[SessionMessage | Exception],
        write_stream: MemoryObjectSendStream[SessionMessage],
    ) -> None:
        server = self._lowlevel_server
        await server.run(read_stream, write_stream, server.create_initialization_options())

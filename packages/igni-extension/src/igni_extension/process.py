"""`ext.run()`: the extension as igni starts it, an MCP server over stdio beside its background work."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.shared.message import SessionMessage

from igni_extension.channel import HostConnection
from igni_extension.mcp_server import ExtensionMcpServer
from igni_extension.threads import OffTheLoop
from igni_extension.tools import ToolRegistry

logger = logging.getLogger(__name__)


class ExtensionProcess:
    """Serves the extension's MCP server, the host's socket and its `on_start` work."""

    def __init__(
        self,
        extension_id: str,
        mcp: ExtensionMcpServer,
        tools: ToolRegistry,
        connection: HostConnection,
        close: Callable[[], Awaitable[None]],
    ) -> None:
        self._extension_id = extension_id
        self._mcp = mcp
        self._tools = tools
        self._connection = connection
        self._close = close
        self._background: list[Callable[[], Any]] = []

    def on_start(self, fn: Callable[[], Any]) -> None:
        """Run `fn` in the background while the process serves igni (`IgniExtension.on_start`)."""
        self._background.append(fn)

    def run(self) -> None:
        """Serve igni over stdio until it closes the pipe."""
        self._hint_when_outside_igni()
        anyio.run(self._run_stdio)

    async def serve(
        self,
        read_stream: MemoryObjectReceiveStream[SessionMessage | Exception],
        write_stream: MemoryObjectSendStream[SessionMessage],
    ) -> None:
        """Serve one MCP session over the given streams (what `run` does over stdio)."""
        await self._tools.check()
        await self._mcp.serve(read_stream, write_stream)

    def _hint_when_outside_igni(self) -> None:
        """Say what this is when somebody starts it from a terminal, rather than seem to hang.

        igni starts the process with a pipe on stdin; a terminal there
        means a person ran the console script. It still serves — an MCP
        inspector would — but says so first, on stderr.
        """
        try:
            interactive = sys.stdin.isatty()
        except (AttributeError, ValueError):
            return
        if not interactive or self._connection.configured:
            return
        print(
            f"{self._extension_id}: this is an igni extension's process, an MCP server igni "
            "starts over stdio. Run inside igni: a development install (IGNI_DEV_EXTENSIONS=1 "
            "igni ext install <dir>), or its service's bundle. To try a tool without igni, "
            "test it: igni_extension.testing.HostHarness(ext).call(...). Waiting for MCP "
            "messages on stdin (Ctrl-C to stop).",
            file=sys.stderr,
        )

    async def _run_stdio(self) -> None:
        await self._tools.check()
        # The host's socket alongside MCP, so signals arrive whether or not
        # igni is calling a tool.
        host = asyncio.create_task(self._connection.serve_forever())
        background = [asyncio.create_task(OffTheLoop.call(fn)) for fn in self._background]
        try:
            await self._mcp.run_stdio_async()
        finally:
            for task in [*background, host]:
                task.cancel()
                # Awaited one by one, and nothing they raise escapes, so a
                # second cancellation during teardown still reaches `_close`.
                try:
                    await task
                except Exception:
                    logger.exception("igni: background work ended in failure")
                except BaseException:  # its cancellation, or ours again
                    logger.debug("igni: background work cancelled", exc_info=True)
            await self._close()

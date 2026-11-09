"""`IgniExtension`'s names as igni-extension 0.1.0 published them, kept for the code written to them.

Each delegates to where the work now lives: `ext.tools` (names, manifest
lines, the four-hint check, observers), `ext.busy` (leases) and
`ext.process` (serving). `await ext.busy(reason, ttl)` keeps working too:
`BusyLeases` is callable, as `take`.
"""

from __future__ import annotations

import contextlib
from typing import Any

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.shared.message import SessionMessage

from igni_extension.busy import BusyLeases
from igni_extension.process import ExtensionProcess
from igni_extension.tools import ToolNames, ToolObserver, ToolRegistry


class ReleasedNames:
    """The 0.1.0 spellings, on `IgniExtension`."""

    tools: ToolRegistry
    busy: BusyLeases

    @property
    def process(self) -> ExtensionProcess:
        """What `run()` serves; `IgniExtension.process` is the one."""
        raise NotImplementedError

    def tool_names(self, tool: str) -> ToolNames:
        """`ext.tools.names(tool)`."""
        return self.tools.names(tool)

    def manifest_tools(self) -> list[dict[str, Any]]:
        """`ext.tools.manifest()`, each line as the manifest's JSON spells it."""
        return [line.wire() for line in self.tools.manifest()]

    async def check_tools(self) -> None:
        """`ext.tools.check()`."""
        await self.tools.check()

    def observing(self, observer: ToolObserver) -> contextlib.AbstractContextManager[None]:
        """`ext.tools.observing(observer)`."""
        return self.tools.observing(observer)

    async def done(self, reason: str) -> None:
        """`ext.busy.release(reason)`."""
        await self.busy.release(reason)

    def busy_while(
        self, reason: str, ttl: float = 120.0
    ) -> contextlib.AbstractAsyncContextManager[None]:
        """`ext.busy.during(reason, ttl)`."""
        return self.busy.during(reason, ttl)

    async def serve(
        self,
        read_stream: MemoryObjectReceiveStream[SessionMessage | Exception],
        write_stream: MemoryObjectSendStream[SessionMessage],
    ) -> None:
        """`ext.process.serve(read_stream, write_stream)`."""
        await self.process.serve(read_stream, write_stream)


__all__ = ["ReleasedNames"]

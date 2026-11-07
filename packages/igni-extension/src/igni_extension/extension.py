"""`IgniExtension`: an extension's process, as its author writes it.

ext = IgniExtension("acme.example")

@ext.tool(hints=ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False))
async def summarise(slug: str) -> str:
    response = await ext.service.get(f"/v1/things/{slug}")
    ...

ext.run()
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
from pydantic import BaseModel

from igni_extension.busy import BusyLeases
from igni_extension.caller import RequestMeta
from igni_extension.channel import HostConnection
from igni_extension.clock import Clock
from igni_extension.environment import Assets, ExtensionEnvironment
from igni_extension.handlers import ExtensionHandlers
from igni_extension.hints import ToolHints
from igni_extension.hooks import HookEvent, HookHandler
from igni_extension.host import Host
from igni_extension.mcp_server import ExtensionMcpServer
from igni_extension.members import Signal
from igni_extension.offline import OfflineHost
from igni_extension.process import ExtensionProcess
from igni_extension.prompt import PromptConditions
from igni_extension.released import ReleasedNames
from igni_extension.service import ServiceAccess, ServiceClient
from igni_extension.service_events import ServiceEventHandler
from igni_extension.session import HostSession
from igni_extension.signals import SignalHandlers
from igni_extension.tokens import HostTokens
from igni_extension.tools import AnyFunction, ToolNames, ToolRegistry


class IgniExtension(ReleasedNames):
    """One extension's process: its tools, its service, and the host.

    It composes them: `ext.tools`, the handlers igni's socket reads,
    `ext.host` and its leases, the service and its tokens, and the
    process `run()` serves. 0.1.0's spellings (`ext.check_tools()`,
    `ext.busy_while(...)`, ...) delegate to them (`igni_extension.released`).
    """

    def __init__(
        self,
        extension_id: str,
        *,
        instructions: str | None = None,
        environ: Mapping[str, str] | None = None,
        token_transport: httpx.AsyncBaseTransport | None = None,
        service_transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock | None = None,
    ) -> None:
        if not extension_id:
            raise ValueError("an extension is named by its manifest id")
        self.id = extension_id
        self.environment = ExtensionEnvironment.read(environ)
        session = HostSession()
        #: The MCP server igni talks to. Every message igni sends passes the
        #: two middlewares: the request's `_meta` is current while it is
        #: served (`Caller.current()`), and its session is kept so the
        #: process can speak first (`igni_extension.session`).
        self.mcp = ExtensionMcpServer(
            extension_id,
            instructions=instructions,
            middleware=[RequestMeta.middleware, session.middleware],
        )
        #: The tools `ext.tool` registered: their names and manifest lines.
        self.tools = ToolRegistry(extension_id, self.mcp)
        self._handlers = ExtensionHandlers()
        #: The socket to the igni host that `ext.host` travels on.
        self.connection = HostConnection(
            self.environment.host,
            self._handlers.signals,
            self._handlers.hooks,
            self._handlers.service_events,
        )
        #: igni, as this extension sees it: `ext.host.chat`, `ext.host.ui`, …
        #: Without the socket, only `notifications.notify` reaches it (`igni_extension.offline`).
        self.host = Host(self.connection if self.connection.configured else OfflineHost(session))
        #: Which of the conditions its prompt contributions wait on hold.
        self.prompt = PromptConditions(session)
        #: Leases that keep igni awake while the extension works on its own.
        self.busy = BusyLeases(self.host.self)
        self._service = ServiceAccess(
            extension_id,
            self.environment.service,
            token_transport=token_transport,
            transport=service_transport,
            clock=clock,
        )
        #: What `run()` serves: MCP over stdio, the host's socket, `on_start` work.
        self.process = ExtensionProcess(
            extension_id, self.mcp, self.tools, self.connection, self.aclose
        )

    # ── What the extension offers ───────────────────────────────────

    def tool(
        self,
        *,
        hints: ToolHints,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[[AnyFunction], AnyFunction]:
        """Register a tool igni can call: `@ext.tool(hints=ToolHints(...))`.

        `hints` is required: igni's permission modes decide on what a
        tool says it is (`igni_extension.hints`). The same four go in
        the manifest's `permissions.tools` for a tool the agent calls.
        A plain `def` runs in a worker thread, so it never holds the
        other calls (`mcp` does this, as `igni_extension.threads` does for
        the SDK's other callbacks). A parameter typed
        `Caller` receives whom the call is for, and is not part of the
        tool's input (`igni_extension.caller`). An exception the tool
        raises reaches igni, and the model, as its message.
        """
        return self.tools.tool(hints=hints, name=name, description=description)

    def on[T](
        self, signal: Signal[T]
    ) -> Callable[[Callable[[T], Awaitable[None] | None]], Callable[[T], Awaitable[None] | None]]:
        """Handle a host signal: `@ext.on(ext.host.<object>.<signal>)`.

        A reaction: igni never waits on it. A plain `def` runs in a
        worker thread.
        """
        return self._handlers.signals.on(signal)

    def hook[T: BaseModel](self, event: HookEvent[T]) -> Callable[[HookHandler[T]], HookHandler[T]]:
        """Answer one of igni's hook events: `@ext.hook(Hooks.PRE_TOOL_USE)`.

        On an event that decides (`event.decides`) the handler returns
        `Allow()`, `Reject(reason)` or `Modify(value)` (`igni_extension.hooks`);
        on any other it is only told. igni asks only about the events the
        manifest lists in `permissions.hooks`; one handler per event.
        """
        return self._handlers.hooks.on(event)

    def on_service_event(
        self, event_type: str | None = None
    ) -> Callable[[ServiceEventHandler], ServiceEventHandler]:
        """Handle the events this extension's service sends (`igni_extension.service_events`).

        igni posts nothing for an event: the handler acts through its host
        calls (`ext.host.sessions.chat(id).post(...)`), and the agent runs
        only if it posts. An event with no handler for its type is reported
        to the service as not handled. Without `event_type` it handles every
        type no other handler names.
        """
        return self._handlers.service_events.on(event_type)

    def on_start[F: Callable[[], Any]](self, fn: F) -> F:
        """Run `fn` in the background for as long as the process serves igni.

        It starts with `run()`, beside the MCP server, and is cancelled
        when igni closes the pipe — so work the extension owns for its
        whole life (a sync loop, a process it started) cleans up in its
        own `finally`. An exception it raises does not stop the extension;
        it is logged when the process stops. A plain `def` runs in a worker thread, and cannot
        be cancelled: it ends with the process.
        """
        self.process.on_start(fn)
        return fn

    @property
    def signals(self) -> SignalHandlers:
        return self._handlers.signals

    @property
    def assets(self) -> Assets:
        """What it ships for this platform: `ext.assets.path("neo4j")`."""
        return self.environment.assets

    # ── Its service and the host ────────────────────────────────────

    @property
    def service(self) -> ServiceClient:
        """An HTTP client for this extension's own service, as the signed-in person.

        Paths are relative to the service. The person's token is attached
        and renewed; `NotSignedIn` is raised when nobody is signed in to
        igni. `ext.service.anonymous` reaches the same service with no
        token, and `ext.service.websocket(path)` opens a WebSocket to it
        as the person. `ext.service.for_(caller)` is the same service as
        the caller a tool was handed — what a tool acting for someone uses.
        """
        return self._service.client

    @property
    def tokens(self) -> HostTokens:
        """The signed-in person's tokens for this extension's service."""
        return self._service.tokens

    async def connect(self) -> None:
        """Connect to the igni host now rather than on the first `ext.host` call.

        `ext.run()` does this itself, and stays connected so that signals
        arrive; a test or a script that drives the extension without
        `run()` calls it.
        """
        await self.connection.connect()

    async def aclose(self) -> None:
        await self.connection.close()
        await self._service.aclose()

    def run(self) -> None:
        """Serve igni over stdio until it closes the pipe. The console script calls this."""
        self.process.run()


__all__ = ["IgniExtension", "ToolNames"]

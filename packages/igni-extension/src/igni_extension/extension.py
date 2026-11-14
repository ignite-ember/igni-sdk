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

    Args:
        extension_id: The extension's manifest id, as its manifest writes it: `acme.example`.
        instructions: The instructions the extension gives the model, as its author writes
            them; `None` when it has none.
        environ: The environment variables igni set for the process; `os.environ` when `None`.
        token_transport: The HTTP transport the host's token endpoint is reached through, so a
            test can answer it.
        service_transport: The HTTP transport the extension's own service is reached through, so
            a test can answer it.
        clock: The clock a token's age is measured on, so a test can move it.
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
        """The extension's manifest id."""
        self.environment = ExtensionEnvironment.read(environ)
        """What igni granted the process, read once from its environment."""
        session = HostSession()
        self.mcp = ExtensionMcpServer(
            extension_id,
            instructions=instructions,
            middleware=[RequestMeta.middleware, session.middleware],
        )
        """The MCP server igni talks to. Every message igni sends passes the
        two middlewares: the request's `_meta` is current while it is
        served (`Caller.current()`), and its session is kept so the
        process can speak first (`igni_extension.session`).
        """
        self.tools = ToolRegistry(extension_id, self.mcp)
        """The tools `ext.tool` registered: their names and manifest lines."""
        self._handlers = ExtensionHandlers()
        self._connection = HostConnection(
            self.environment.host,
            self._handlers.signals,
            self._handlers.hooks,
            self._handlers.service_events,
        )
        self.host = Host(self._connection if self._connection.configured else OfflineHost(session))
        """igni, as this extension sees it: `ext.host.chat`, `ext.host.ui`, …
        Without the socket, only `notifications.notify` reaches it (`igni_extension.offline`).
        """
        self.prompt = PromptConditions(session)
        """Which of the conditions its prompt contributions wait on hold."""
        self.busy = BusyLeases(self.host.self)
        """Leases that keep igni awake while the extension works on its own."""
        self._service = ServiceAccess(
            extension_id,
            self.environment.service,
            token_transport=token_transport,
            transport=service_transport,
            clock=clock,
        )
        self._process = ExtensionProcess(
            extension_id, self.mcp, self.tools, self._connection, self.aclose
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

        Args:
            hints: What the tool says it is: the four igni's permission modes read
                (`igni_extension.hints`).
            name: The name the tool is registered under; the function's own name when `None`.
            description: What the model is told the tool does; the function's own docstring when
                `None`.
        """
        return self.tools.tool(hints=hints, name=name, description=description)

    def on[T](
        self, signal: Signal[T]
    ) -> Callable[[Callable[[T], Awaitable[None] | None]], Callable[[T], Awaitable[None] | None]]:
        """Handle a host signal: `@ext.on(ext.host.<object>.<signal>)`.

        A reaction: igni never waits on it. A plain `def` runs in a
        worker thread.

        Args:
            signal: The signal to handle: `ext.host.sessions.current_changed`.
        """
        return self._handlers.signals.on(signal)

    def hook[T: BaseModel](self, event: HookEvent[T]) -> Callable[[HookHandler[T]], HookHandler[T]]:
        """Answer one of igni's hook events: `@ext.hook(Hooks.PRE_TOOL_USE)`.

        On an event that decides (`event.decides`) the handler returns
        `Allow()`, `Reject(reason)` or `Modify(value)` (`igni_extension.hooks`);
        on any other it is only told. igni asks only about the events the
        manifest lists in `permissions.hooks`; one handler per event.

        Args:
            event: The hook event to answer: `Hooks.PRE_TOOL_USE`.
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

        Args:
            event_type: The type of service event to handle: `claim.created`; every type no
                other handler names when `None`.
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

        Args:
            fn: The function to run in the background for as long as the process serves igni.
        """
        self._process.on_start(fn)
        return fn

    @property
    def signals(self) -> SignalHandlers:
        """The handlers `@ext.on` registered, by signal (`SignalHandlers`).

        `@ext.on(signal)` is how an extension handles a signal; this is
        what it registers into, and the host's socket delivers into. Use
        it to see what is handled, or — in a test, with no host — to run
        the handlers as if the host had sent the signal:

        - `ext.signals.wires()` — every handled signal, by wire name
          (`["session.switched"]`): what the socket subscribes to.
        - `ext.signals.handlers(signal)` — one signal's handlers, in
          registration order.
        - `await ext.signals.emit(signal, value)` — run them with a typed
          `value`, as the host's delivery does. A handler that raises is
          logged and the others still run.
        - `await ext.signals.deliver(wire, raw)` — the same from the wire
          name and the JSON value the host sends, parsed first; a signal
          nobody handles, or a value of the wrong shape, is skipped.

        Example::

            from igni_extension.host_model import SessionChange

            @ext.on(ext.host.sessions.current_changed)
            async def follow(change: SessionChange) -> None: ...

            assert ext.signals.wires() == ["session.switched"]
            await ext.signals.emit(
                ext.host.sessions.current_changed, SessionChange(session_id="s-2")
            )
        """
        return self._handlers.signals

    @property
    def connection(self) -> HostConnection:
        """The socket to the igni host: what `ext.host`, signals, hooks and service events travel on.

        igni starts the process with `IGNI_HOST_URL` and `IGNI_HOST_SECRET`,
        a WebSocket on the device's loopback interface and the secret that
        says which process this is. `ext.run()` keeps it open, and the first
        `ext.host` call opens it, so an extension rarely needs it. Use it to:

        - tell whether there is a host at all: `ext.connection.configured`
          is `False` outside igni, when `ext.host` reaches igni only through
          `notifications.notify`;
        - see what the host granted: once connected, `ext.connection.granted`
          is the `permissions.host` grants it said this extension holds
          (`["chat.read", "chat.post", "sessions"]`), and
          `ext.connection.schema_version` the host model's version;
        - drive the extension without `run()`, in a test or a script:
          `await ext.connect()` connects once (it is
          `ext.connection.connect()`); `ext.connection.serve_forever()`, as
          a task, stays connected and reconnects every two seconds as
          `run()` does; `ext.connection.connected` says whether it is
          connected now. `await ext.aclose()` closes it.

        Its other methods are the SDK's wire to the host, not an API.

        Example::

            await ext.connect()
            if "chat.post" not in ext.connection.granted:
                print("permissions.host does not grant chat.post")
            await ext.aclose()
        """
        return self._connection

    @property
    def process(self) -> ExtensionProcess:
        """What `ext.run()` serves: the MCP server, the host's socket beside it, the `on_start` work.

        `ext.run()` is `ext.process.run()`: MCP over stdio until igni closes
        the pipe, the host's socket kept open, every `@ext.on_start`
        function in the background. Use the process itself to serve one
        MCP session over streams you hold rather than stdio — an in-memory
        client in a test, or a program that embeds the extension:

        - `await ext.process.serve(read_stream, write_stream)` checks every
          tool's hints (raising `ToolHintsMissing`) and serves the session
          until its streams close. It neither connects to the host nor
          starts the `on_start` work: call `await ext.connect()` for the
          one, and start the other yourself.
        - `ext.process.run()` — what `ext.run()` does.
        - `ext.process.on_start(fn)` — what `@ext.on_start` does.

        `igni_extension.testing.HostHarness` serves this way, and is the
        usual way to call a tool in a test.

        Example::

            import anyio
            from mcp import ClientSession

            to_server, server_reads = anyio.create_memory_object_stream(16)
            server_writes, to_client = anyio.create_memory_object_stream(16)
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(ext.process.serve, server_reads, server_writes)
                async with ClientSession(to_client, to_server) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                tasks.cancel_scope.cancel()
        """
        return self._process

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
        `run()` calls it. Raises `NotConfigured` outside igni, where there is
        no host to connect to, and `HostUnavailable` if the host does not answer.
        """
        await self._connection.connect()

    async def aclose(self) -> None:
        """Close the host's socket and the HTTP clients. `run()` calls it on the way out; a test
        that called `connect()` calls it itself.
        """
        await self._connection.close()
        await self._service.aclose()

    def run(self) -> None:
        """Serve igni over stdio until it closes the pipe. The console script calls this."""
        self._process.run()


__all__ = ["IgniExtension", "ToolNames"]

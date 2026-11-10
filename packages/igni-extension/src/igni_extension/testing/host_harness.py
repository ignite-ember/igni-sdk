"""The igni host's MCP client, connected to an extension over memory streams.

The same session `ext.run()` serves over stdio; it records what the
extension tells the host:

    async with HostHarness(ext) as host:
        await host.session.call_tool("do_thing", {})
        [notification] = await host.received(1)
"""

from __future__ import annotations

import contextlib
from types import TracebackType
from typing import Any, ClassVar, cast

import anyio
from anyio.abc import TaskGroup
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession, types
from mcp.client.extension import NotificationBinding
from mcp.shared.message import SessionMessage

from igni_extension.caller import Caller
from igni_extension.extension import IgniExtension
from igni_extension.notifications import (
    CONDITIONS_METHOD,
    NOTIFY_METHOD,
    ConditionsParams,
    LocalNotification,
    NotifyNotification,
    NotifyParams,
)


class HostHarness:
    """The igni host's MCP session with one extension, in this process."""

    IGNI_METHODS: ClassVar[frozenset[str]] = frozenset({NOTIFY_METHOD, CONDITIONS_METHOD})
    """igni's own notifications, which the harness keeps as they crossed the wire."""

    def __init__(self, ext: IgniExtension, *, timeout: float = 5.0) -> None:
        self._ext = ext
        self._timeout = timeout
        self._stack = contextlib.AsyncExitStack()
        self._tasks: TaskGroup | None = None
        self._session: ClientSession | None = None
        self._changed = anyio.Event()
        self.notifications: list[LocalNotification] = []
        """What the extension told the host, parsed as the host parses it."""
        self.raw: list[dict[str, Any]] = []
        """The same messages exactly as they crossed the wire."""
        self.conditions: list[dict[str, bool]] = []
        """What the extension said about its conditions, in order."""

    @property
    def session(self) -> ClientSession:
        """The MCP client session talking to the extension, for what `call` does not cover. Raises
        `RuntimeError` outside `async with`.
        """
        if self._session is None:
            raise RuntimeError("enter the harness first: async with HostHarness(ext) as host")
        return self._session

    async def __aenter__(self) -> HostHarness:
        to_server_send, to_server_receive = anyio.create_memory_object_stream[
            SessionMessage | Exception
        ](16)
        from_server_send, from_server_receive = anyio.create_memory_object_stream[SessionMessage](
            16
        )
        to_client_send, to_client_receive = anyio.create_memory_object_stream[
            SessionMessage | Exception
        ](16)
        for stream in (
            to_server_send,
            to_server_receive,
            from_server_send,
            from_server_receive,
            to_client_send,
            to_client_receive,
        ):
            await self._stack.enter_async_context(stream)
        self._tasks = await self._stack.enter_async_context(anyio.create_task_group())
        self._tasks.start_soon(self._ext.process.serve, to_server_receive, from_server_send)
        self._tasks.start_soon(self._tap, from_server_receive, to_client_send)
        self._session = await self._stack.enter_async_context(
            ClientSession(
                to_client_receive,
                to_server_send,
                read_timeout_seconds=self._timeout,
                # igni's own notifications, which `mcp` has no type for.
                notification_bindings=[
                    NotificationBinding(
                        method=NOTIFY_METHOD, params_type=NotifyParams, handler=self._on_notify
                    ),
                    NotificationBinding(
                        method=CONDITIONS_METHOD,
                        params_type=ConditionsParams,
                        handler=self._on_conditions,
                    ),
                ],
            )
        )
        await self._session.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._tasks is not None:
            self._tasks.cancel_scope.cancel()
        await self._stack.__aexit__(exc_type, exc, traceback)

    async def call(
        self, tool: str, arguments: dict[str, Any] | None = None, *, caller: Caller | None = None
    ) -> types.CallToolResult:
        """Call a tool as igni does: for `caller`, named in the request's `_meta`."""
        meta = (
            self.request_meta({Caller.META_KEY: caller.model_dump(mode="json")})
            if caller is not None
            else None
        )
        return await self.session.call_tool(tool, arguments or {}, meta=meta)

    @staticmethod
    def request_meta(values: dict[str, Any]) -> types.RequestParamsMeta:
        """`values` as a request's `_meta`.

        `RequestParamsMeta` is an open TypedDict (PEP 728 `extra_items`),
        which mypy cannot yet check for keys it does not name, so the
        dict is declared what it is here, once.
        """
        return cast(types.RequestParamsMeta, values)

    async def received(self, count: int) -> list[LocalNotification]:
        """Wait until the host has `count` notifications from the extension."""
        with anyio.fail_after(self._timeout):
            while len(self.notifications) < count:
                await self._changed.wait()
                self._changed = anyio.Event()
        return list(self.notifications)

    async def conditions_said(self, count: int) -> list[dict[str, bool]]:
        """Wait until the extension has said `count` things about its conditions."""
        with anyio.fail_after(self._timeout):
            while len(self.conditions) < count:
                await self._changed.wait()
                self._changed = anyio.Event()
        return list(self.conditions)

    async def _tap(
        self,
        source: MemoryObjectReceiveStream[SessionMessage],
        sink: MemoryObjectSendStream[SessionMessage | Exception],
    ) -> None:
        async for message in source:
            wire = message.message
            if isinstance(wire, types.JSONRPCNotification) and wire.method in self.IGNI_METHODS:
                self.raw.append(wire.model_dump(by_alias=True, mode="json", exclude_none=True))
            await sink.send(message)

    async def _on_notify(self, params: NotifyParams) -> None:
        self.notifications.append(NotifyNotification(params=params).local())
        self._changed.set()

    async def _on_conditions(self, params: ConditionsParams) -> None:
        self.conditions.append(dict(params.conditions))
        self._changed.set()

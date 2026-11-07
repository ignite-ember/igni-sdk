"""`IgniClient`: one connection to one igni, and everything done through it."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from igni_client.commands import Commands, Me
from igni_client.connection import Connection
from igni_client.events import Event
from igni_client.sessions import Models, Sessions, _result
from igni_client.targets import Target, require_fleet


class IgniClient:
    """A connection to one igni — a producer's in Fleet, or one on this machine.

        async with IgniClient(Fleet("https://gw.acme.internal", auth=Person.from_cli())) as igni:
            session = await igni.sessions.create()
            print(await session.ask("What changed since yesterday?"))

    It stays connected for as long as it is open. When Fleet moves the VM
    to another node, the client re-attaches its sessions on its own; a run
    that was going when it moved ends with `RunInterrupted`.
    """

    def __init__(self, target: Target, *, reconnect_attempts: int = 5) -> None:
        self.target = target
        self._conn = Connection(target, reconnect_attempts=reconnect_attempts)
        self.sessions = Sessions(self._conn)
        self.models = Models(self._conn)
        self._commands: Commands | None = None
        self._conn.on_resync(self.sessions.reattach)

    async def connect(self) -> IgniClient:
        """Open the connection. `async with` does this for you."""
        await self._conn.open()
        return self

    async def close(self) -> None:
        await self._conn.close()

    async def __aenter__(self) -> IgniClient:
        return await self.connect()

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    @property
    def client_id(self) -> str:
        """igni's name for this connection; its own messages carry it."""
        return self._conn.client_id

    @property
    def commands(self) -> Commands:
        """Shell commands in the VM, through Fleet's gateway. Not available for a local igni."""
        if self._commands is None:
            self._commands = Commands(require_fleet(self.target, "commands"))
        return self._commands

    async def me(self) -> Me:
        """Who the gateway says this client is: the producer, organisation and group."""
        return await self.commands.me()

    async def rpc(self, method: str, **args: Any) -> Any:
        """Call any of igni's methods by name, as igni's own app does.

        Returns the call's result, or — for the methods that answer with a
        message of their own, such as `list_sessions` — that message.
        Raises `RpcError` when igni answers with an error. Methods that act
        on one session take `session_id`, or use `Session.rpc`.
        """
        return _result(await self._conn.rpc(method, args))

    async def events(self) -> AsyncIterator[Event]:
        """Every message igni sends from now on, from every session and every client attached.

        igni broadcasts: a person's open window sees this client's runs, and
        this sees theirs. Use it to watch an igni, not to follow your own run
        — `Session.send()` does that.
        """
        queue = self._conn.listen()
        try:
            while True:
                yield await queue.get()
        finally:
            self._conn.unlisten(queue)

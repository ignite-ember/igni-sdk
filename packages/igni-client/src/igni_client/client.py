"""`IgniClient`: one connection to one igni, and everything done through it."""

from __future__ import annotations

from collections.abc import AsyncIterator

from igni_client.api import IgniApi
from igni_client.backoff import Backoff
from igni_client.calls import Caller
from igni_client.commands import Commands, Me
from igni_client.connection import Connection
from igni_client.models import VmCredentialState
from igni_client.routing import Router
from igni_client.sessions import Sessions
from igni_client.sign_in import SignedIn, sign_in
from igni_client.targets import Target, require_fleet
from igni_client.wire import Event


class IgniClient(IgniApi):
    """A connection to one igni — a producer's in Fleet, or one on this machine.

        async with IgniClient(Fleet("https://gw.acme.internal", auth=Person.from_cli())) as igni:
            session = await igni.sessions.create()
            print(await session.ask("What changed since yesterday?"))

    It stays connected for as long as it is open. When Fleet moves the VM
    to another node, the client re-attaches its sessions on its own; a run
    that was going when it moved ends with `RunInterrupted`.

    Every method igni answers for igni as a whole is here, grouped as igni
    groups them — `igni.processes`, `igni.notifications`, `igni.auth` and
    the rest (`igni_client.api.IgniApi`); a session's are on its `Session`.
    """

    sessions: Sessions
    """igni's sessions: create, open, list — and `attach`, igni's own call."""

    def __init__(self, target: Target, *, backoff: Backoff | None = None) -> None:
        """`backoff` paces opening the socket again after Fleet said busy or it dropped."""
        self.target = target
        self._conn = Connection(target, backoff or Backoff(), Router())
        super().__init__(Caller(self._conn))
        self.sessions = Sessions(self._conn)
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

    @property
    def vm_credential(self) -> VmCredentialState | None:
        """What igni on a Fleet VM last said of its own credential, or `None` before it said anything.

        igni says it with a `vm_credential` push when the state changes, and
        sends a client that connects later the state last pushed as it
        attaches: a `needs_sign_in` (or an app's `needs_reissue`) makes
        `Session.ask()` raise `SignInRequired` (`ReissueRequired`) instead
        of `RunFailed`. The client never signs in by itself; the gateway's
        `POST /v1/sign-in` does.
        """
        return self._conn.vm_credential

    async def me(self) -> Me:
        """Who the gateway says this client is — producer, organisation, group — and its VM's state.

        It is the gateway's HTTP API, not igni's socket: it works before the
        client is opened, and never wakes the VM (`Me.vm`).
        """
        require_fleet(self.target, "me")
        return await self.commands.me()

    async def sign_in(self) -> SignedIn:
        """Sign the person in to the igni in their Fleet VM again: the gateway's `POST /v1/sign-in`.

        Do it when `SignInRequired` says the VM's own credential was refused.
        The gateway wakes the VM and hands igni the person's session; igni
        then pushes `ready` on `vm_credential`, and the next run works. Like
        `me()`, it needs no open socket. Not available for a local igni.
        """
        return await sign_in(require_fleet(self.target, "sign_in"))

    async def events(self) -> AsyncIterator[Event]:
        """Every message igni sends from now on, from every session and every client attached.

        igni broadcasts: a person's open window sees this client's runs, and
        this sees theirs. Use it to watch an igni — every push notification
        among them — not to follow your own run (`Session.send()`) or call
        (a `Call`'s `async with`).
        """
        queue = self._conn.router.listen()
        try:
            while True:
                yield await queue.get()
        finally:
            self._conn.router.unlisten(queue)


__all__ = ["IgniClient"]

"""`FakeIgni`: igni's socket, methods and runs — and Fleet's gateway when given one — put together."""

from __future__ import annotations

import httpx

from igni_client.auth.tokens import TokenSource
from igni_client.frames import Cancel, HitlResponseBatch, QueueMessage, RpcRequest, UserMessage
from igni_client.targets import Fleet, Local
from igni_client.testing.gateway import CONNECT_PATH, FakeGateway
from igni_client.testing.inbound import ClientFrame
from igni_client.testing.methods import FakeMethods
from igni_client.testing.runs import FakeRuns
from igni_client.testing.server import FakeSocket, LocalHandshake


class FakeIgni:
    """igni's socket on loopback, scripted — with Fleet's gateway in front when given `gateway`."""

    def __init__(
        self, *, gateway: FakeGateway | None = None, local_token: str | None = None
    ) -> None:
        #: Fleet's gateway in front, or `None` for an igni reached on this machine.
        self.gateway = gateway
        #: Local mode: the per-launch token a client must offer, or `None` for none.
        self.local_token = local_token
        self.socket = FakeSocket(
            gateway or LocalHandshake(local_token),
            self._handle,
            path=CONNECT_PATH if gateway is not None else "",
        )
        self.methods = FakeMethods()
        self.runs = FakeRuns(self.socket)

    async def start(self) -> FakeIgni:
        await self.socket.start()
        return self

    async def stop(self) -> None:
        await self.socket.stop()

    async def __aenter__(self) -> FakeIgni:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    def local(self) -> Local:
        """A `Local` target pointed at this fake."""
        return Local(url=f"ws://127.0.0.1:{self.socket.port}", token=self.local_token)

    def fleet(self, auth: TokenSource) -> Fleet:
        """A `Fleet` target pointed at this fake as the gateway, its HTTP calls served by the gateway's transport."""
        if self.gateway is None:
            raise RuntimeError("FakeIgni(gateway=FakeGateway(...)) plays the gateway")
        http = httpx.AsyncClient(transport=self.gateway.transport())
        return Fleet(f"http://127.0.0.1:{self.socket.port}", auth=auth, http=http)

    async def _handle(self, frame: ClientFrame) -> None:
        match frame:
            case RpcRequest():
                await self.socket.broadcast(await self.methods.answer(frame))
            case UserMessage():
                await self.runs.prompt(frame)
            case HitlResponseBatch():
                await self.runs.resume(frame)
            case QueueMessage():
                await self.runs.queue(frame)
            case Cancel():
                await self.runs.cancel(frame)


__all__ = ["FakeIgni"]

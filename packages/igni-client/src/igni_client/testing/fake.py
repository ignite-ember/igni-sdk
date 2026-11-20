"""`FakeIgni`: igni's socket, methods and runs — and Fleet's gateway when given one — put together."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from igni_client.auth.tokens import TokenSource
from igni_client.cloud import Mode
from igni_client.models import (
    Cancel,
    CancelLogin,
    CancelRunResult,
    Command,
    CommandResult,
    HitlResponseBatch,
    QueueMessage,
    RpcRequest,
    Typing,
    UserMessage,
)
from igni_client.targets import Fleet, Local
from igni_client.testing.cloud import FakeServer
from igni_client.testing.gateway import CONNECT_PATH, LOCAL_ONLY_REASON, FakeGateway
from igni_client.testing.inbound import ClientFrame
from igni_client.testing.methods import FakeMethods
from igni_client.testing.runs import FakeRuns
from igni_client.testing.server import FakeSocket, LocalHandshake, Reply


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
        #: How a slash command is answered: a function of its text.
        self.commands: Callable[[str], CommandResult] = lambda text: CommandResult(
            kind="info", content=f"ran {text}"
        )
        #: How many times a sign-in was cancelled (`cancel_login`).
        self.logins_cancelled = 0
        #: igni server's discovery in front of the gateway (`/v1/me/cloud`), when there is a gateway.
        self.server: FakeServer | None = None
        if gateway is not None:
            self.server = FakeServer(gateway.tokens, gateway_url=self._gateway_url)
            gateway.on_sign_in = self._signed_in

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
        return Fleet(self._gateway_url(), auth=auth, http=http)

    @property
    def server_url(self) -> str:
        """igni server's address, for `discover()` and `Fleet.from_server()` with `server_http()`."""
        return self._server().url

    def server_http(self) -> httpx.AsyncClient:
        """An HTTP client that reaches igni server's discovery and, at the gateway's address, the gateway."""
        server, gateway = self._server(), self.gateway
        assert gateway is not None  # `_server()` says there is one

        async def route(request: httpx.Request) -> httpx.Response:
            if f"{request.url.scheme}://{request.url.host}" == server.url:
                return server.handle(request)
            return await gateway.handle(request)

        return httpx.AsyncClient(transport=httpx.MockTransport(route))

    async def set_mode(self, mode: Mode) -> None:
        """An admin sets the group's mode: igni server says it, and the gateway enforces it.

        `local` refuses every person at the gateway and closes their open
        connections with `1008 group_local_only`, as its kick does; any
        other mode lets them through again.
        """
        server, gateway = self._server(), self.gateway
        assert gateway is not None
        server.mode = mode
        if mode == "local":
            gateway.local_only = {p for p in gateway.tokens.values() if p.startswith("person:")}
            await self.socket.drop(1008, LOCAL_ONLY_REASON)
        else:
            gateway.local_only = set()

    def _server(self) -> FakeServer:
        if self.server is None:
            raise RuntimeError("FakeIgni(gateway=FakeGateway(...)) plays igni server's discovery")
        return self.server

    def _gateway_url(self) -> str:
        return f"http://127.0.0.1:{self.socket.port}"

    async def _signed_in(self, state: str) -> None:
        """igni took the session a sign-in handed it, and says so on `vm_credential`."""
        await self.socket.push("vm_credential", {"state": state, "message": ""})

    async def _handle(self, frame: ClientFrame, reply: Reply) -> None:
        """Play `frame`. A call is answered to the client that made it alone, as igni
        answers it; everything else is broadcast."""
        match frame:
            case RpcRequest(method="cancel_run") if "cancel_run" not in self.methods.answers:
                await reply(
                    FakeMethods.reply(
                        frame, CancelRunResult(cancelled=self.runs.running(frame.session_id))
                    )
                )
                await self.runs.cancel(Cancel(session_id=frame.session_id))
            case RpcRequest():
                await reply(await self.methods.answer(frame))
            case Command():
                answer = self.commands(frame.text)
                await self.socket.broadcast(
                    answer.model_copy(update={"id": frame.id, "session_id": frame.session_id})
                )
            case Typing():
                await self.socket.broadcast(frame)
            case CancelLogin():
                self.logins_cancelled += 1
            case UserMessage():
                await self.runs.prompt(frame)
            case HitlResponseBatch():
                await self.runs.resume(frame)
            case QueueMessage():
                await self.runs.queue(frame)
            case Cancel():
                await self.runs.cancel(frame)


__all__ = ["FakeIgni"]

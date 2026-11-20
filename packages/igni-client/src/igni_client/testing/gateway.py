"""Fleet's gateway in front of the fake: bearer tokens on `/v1/connect`, `/v1/me`, `/v1/commands` and `/v1/sign-in`.

A person whose group runs igni only on the desktop (`local_only`) is
refused as the gateway refuses them: a connection is closed with `1008
group_local_only`, a sign-in or a command answered `403`.
"""

from __future__ import annotations

import itertools
from collections.abc import Awaitable, Callable
from http import HTTPStatus

import httpx
from pydantic import BaseModel, ValidationError
from websockets.asyncio.server import ServerConnection
from websockets.http11 import Request, Response

from igni_client.commands.models import CommandOutput, CommandRecord, Me, VmState, Wake
from igni_client.commands.wire import (
    CommandAccepted,
    CommandDone,
    CommandRequest,
    GatewayErrorBody,
    OutputLine,
    VmWoken,
)

CONNECT_PATH = "/v1/connect"
#: What the gateway says, after its stable word, when a person's group runs igni only on the desktop.
LOCAL_ONLY_REASON = "group_local_only: your organisation runs igni on your computer"


class PlayedCommand(BaseModel):
    """What a command played by the fake prints and exits with."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0

    def outputs(self) -> list[CommandOutput]:
        """What it writes, stdout first; a stream it leaves empty is not written."""
        written = [
            CommandOutput(stream="stdout", data=self.stdout.encode()),
            CommandOutput(stream="stderr", data=self.stderr.encode()),
        ]
        return [output for output in written if output.data]


class FakeGateway:
    """The gateway's checks and HTTP API. `tokens` maps each accepted bearer token to its producer (`kind:id`)."""

    def __init__(self, tokens: dict[str, str] | None = None, *, org: str = "org-acme") -> None:
        self.tokens = dict(tokens or {})
        self.org = org
        #: What a command run through the gateway prints, by command.
        self.commands: dict[str, PlayedCommand] = {}
        #: Every command run through the gateway, as it was asked.
        self.commands_run: list[CommandRequest] = []
        #: People (`person:<id>`) whose group runs igni only on the desktop.
        self.local_only: set[str] = set()
        #: Each producer's VM as `/v1/me` reports it; one not here is running and signed in.
        self.vm_states: dict[str, VmState] = {}
        #: The credential state a sign-in leaves igni in.
        self.sign_in_state = "ready"
        #: Every producer signed in through `/v1/sign-in`, in order.
        self.signed_in: list[str] = []
        #: Run after each sign-in with the credential state: `FakeIgni` pushes it on `vm_credential`.
        self.on_sign_in: Callable[[str], Awaitable[None]] | None = None
        self._ids = itertools.count(1)
        self._routes: dict[
            tuple[str, str], Callable[[httpx.Request, str], Awaitable[httpx.Response]]
        ] = {
            ("GET", "/v1/me"): self._me,
            ("POST", "/v1/commands"): self._run,
            ("POST", "/v1/sign-in"): self._sign_in,
        }

    def refuse(self, connection: ServerConnection, request: Request) -> Response | None:
        """The socket's handshake: only `/v1/connect`, only with a token the gateway accepts."""
        if request.path.split("?")[0] != CONNECT_PATH:
            return connection.respond(HTTPStatus.NOT_FOUND, "not found\n")
        if self._bearer(request.headers.get("Authorization", "")) in self.tokens:
            return None
        body = GatewayErrorBody(error="invalid_token", error_description="the token was refused")
        return connection.respond(HTTPStatus.UNAUTHORIZED, body.model_dump_json(exclude_none=True))

    def close_on_open(self, request: Request) -> tuple[int, str] | None:
        """How the gateway ends a connection it upgraded: `1008 group_local_only` for a local-only person."""
        if (
            self.tokens.get(self._bearer(request.headers.get("Authorization", "")))
            in self.local_only
        ):
            return 1008, LOCAL_ONLY_REASON
        return None

    def transport(self) -> httpx.MockTransport:
        """The gateway's `/v1/me`, `/v1/commands` and `/v1/sign-in`, for an `httpx.AsyncClient`."""
        return httpx.MockTransport(self.handle)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        producer = self.tokens.get(self._bearer(request.headers.get("Authorization", "")))
        if producer is None:
            return self._refusal(HTTPStatus.UNAUTHORIZED, GatewayErrorBody(error="invalid_token"))
        route = self._routes.get((request.method, request.url.path))
        if route is None:
            return self._refusal(HTTPStatus.NOT_FOUND, GatewayErrorBody(error="not_found"))
        return await route(request, producer)

    def vm_state(self, producer: str) -> VmState:
        """`producer`'s VM as `/v1/me` reports it."""
        return self.vm_states.get(producer, VmState(state="running", signed_in=True))

    async def _me(self, request: httpx.Request, producer: str) -> httpx.Response:
        me = Me(
            producer=producer, org=self.org, group=None, expires_at=0, vm=self.vm_state(producer)
        )
        return httpx.Response(HTTPStatus.OK, json=me.model_dump(mode="json"))

    async def _sign_in(self, request: httpx.Request, producer: str) -> httpx.Response:
        if not producer.startswith("person:"):
            body = GatewayErrorBody(
                error="not_a_person", error_description="an app does not sign in"
            )
            return self._refusal(HTTPStatus.BAD_REQUEST, body)
        if producer in self.local_only:
            body = GatewayErrorBody(error="refused", error_description=LOCAL_ONLY_REASON)
            return self._refusal(HTTPStatus.FORBIDDEN, body)
        self.signed_in.append(producer)
        if self.sign_in_state == "ready":
            self.vm_states[producer] = VmState(state="running", signed_in=True)
        if self.on_sign_in is not None:
            await self.on_sign_in(self.sign_in_state)
        answer = {
            "producer": producer,
            "node": "n1",
            "how": "paused",
            "credential": {"state": self.sign_in_state, "message": ""},
        }
        return httpx.Response(HTTPStatus.OK, json=answer)

    async def _run(self, request: httpx.Request, producer: str) -> httpx.Response:
        try:
            asked = CommandRequest.model_validate_json(request.content or b"{}")
        except ValidationError as refused:
            body = GatewayErrorBody(detail=str(refused))
            return self._refusal(HTTPStatus.UNPROCESSABLE_ENTITY, body)
        self.commands_run.append(asked)
        if producer in self.local_only:
            body = GatewayErrorBody(error="refused", error_description=LOCAL_ONLY_REASON)
            return self._refusal(HTTPStatus.FORBIDDEN, body)
        if f"{asked.producer.kind}:{asked.producer.id}" != producer:
            return self._refusal(HTTPStatus.FORBIDDEN, GatewayErrorBody(detail="not your VM"))
        played = self.commands.get(asked.command, PlayedCommand(stdout=f"ran {asked.command}\n"))
        lines: list[BaseModel] = [
            CommandAccepted(
                command=CommandRecord(
                    command_id=f"c-{next(self._ids)}", command=asked.command, state="running"
                )
            ),
            VmWoken(woken=Wake(how="paused", node="n1", ms=12.345)),
            *(OutputLine.of(output) for output in played.outputs()),
            CommandDone(done=True, exit_code=played.exit_code, duration_ms=5),
        ]
        content = "".join(line.model_dump_json(exclude_none=True) + "\n" for line in lines)
        return httpx.Response(
            HTTPStatus.OK, content=content, headers={"content-type": "application/x-ndjson"}
        )

    @staticmethod
    def _bearer(header: str) -> str:
        return header.removeprefix("Bearer ").strip()

    @staticmethod
    def _refusal(status: HTTPStatus, body: GatewayErrorBody) -> httpx.Response:
        return httpx.Response(status, json=body.model_dump(mode="json", exclude_none=True))


__all__ = ["CONNECT_PATH", "LOCAL_ONLY_REASON", "FakeGateway", "PlayedCommand"]

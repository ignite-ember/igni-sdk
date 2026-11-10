"""Fleet's gateway in front of the fake: bearer tokens on `/v1/connect`, `/v1/me` and `/v1/commands`."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from http import HTTPStatus

import httpx
from pydantic import BaseModel, ValidationError
from websockets.asyncio.server import ServerConnection
from websockets.http11 import Request, Response

from igni_client.commands.models import CommandOutput, CommandRecord, Me, Wake
from igni_client.commands.wire import (
    CommandAccepted,
    CommandDone,
    CommandRequest,
    GatewayErrorBody,
    OutputLine,
    VmWoken,
)

CONNECT_PATH = "/v1/connect"


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
        self._ids = itertools.count(1)
        self._routes: dict[tuple[str, str], Callable[[httpx.Request, str], httpx.Response]] = {
            ("GET", "/v1/me"): self._me,
            ("POST", "/v1/commands"): self._run,
        }

    def refuse(self, connection: ServerConnection, request: Request) -> Response | None:
        """The socket's handshake: only `/v1/connect`, only with a token the gateway accepts."""
        if request.path.split("?")[0] != CONNECT_PATH:
            return connection.respond(HTTPStatus.NOT_FOUND, "not found\n")
        if self._bearer(request.headers.get("Authorization", "")) in self.tokens:
            return None
        body = GatewayErrorBody(error="invalid_token", error_description="the token was refused")
        return connection.respond(HTTPStatus.UNAUTHORIZED, body.model_dump_json(exclude_none=True))

    def transport(self) -> httpx.MockTransport:
        """The gateway's `/v1/me` and `/v1/commands`, for an `httpx.AsyncClient`."""
        return httpx.MockTransport(self._http)

    def _http(self, request: httpx.Request) -> httpx.Response:
        producer = self.tokens.get(self._bearer(request.headers.get("Authorization", "")))
        if producer is None:
            return self._refusal(HTTPStatus.UNAUTHORIZED, GatewayErrorBody(error="invalid_token"))
        route = self._routes.get((request.method, request.url.path))
        if route is None:
            return self._refusal(HTTPStatus.NOT_FOUND, GatewayErrorBody(error="not_found"))
        return route(request, producer)

    def _me(self, request: httpx.Request, producer: str) -> httpx.Response:
        me = Me(producer=producer, org=self.org, group=None, expires_at=0)
        return httpx.Response(HTTPStatus.OK, json=me.model_dump(mode="json"))

    def _run(self, request: httpx.Request, producer: str) -> httpx.Response:
        try:
            asked = CommandRequest.model_validate_json(request.content or b"{}")
        except ValidationError as refused:
            body = GatewayErrorBody(detail=str(refused))
            return self._refusal(HTTPStatus.UNPROCESSABLE_ENTITY, body)
        self.commands_run.append(asked)
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


__all__ = ["CONNECT_PATH", "FakeGateway", "PlayedCommand"]

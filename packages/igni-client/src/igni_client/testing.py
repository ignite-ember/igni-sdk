"""igni, played in-process — and Fleet's gateway in front of it — for testing code built on igni-client.

`FakeIgni` speaks igni's protocol on a real loopback socket: it says
welcome, answers calls, plays a scripted run for every prompt, pauses for
approvals and resumes on the answer, and broadcasts every message to every
client attached, as igni does. In gateway mode it also checks bearer
tokens on `/v1/connect` and serves `/v1/me` and `/v1/commands` through an
`httpx.MockTransport`.

    async with FakeIgni(gateway=True, tokens={"t-ada": "person:u-ada"}) as fake:
        fake.script = lambda text: [*FakeIgni.answer(f"you said {text}")]
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            session = await igni.sessions.create()
            assert str(await session.ask("hi")) == "you said hi"

It also plays what the real thing does under you: `move()` sends a new
`welcome` (Fleet moved the VM), `drop(code)` closes every connection,
`busy_next(n)` answers the next connections "busy, retry", and
`unbound_for(n)` answers calls as a VM not yet bound to its producer.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import itertools
import json
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

import httpx
from pydantic import BaseModel, Field
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.http11 import Request, Response

from igni_client.auth.tokens import TokenSource
from igni_client.connection import UNBOUND
from igni_client.events import Event, Requirement
from igni_client.targets import TOKEN_PROTOCOL_PREFIX, Fleet, Local


class Pause(BaseModel):
    """A step of a script: the run stops here until every call is answered."""

    requirements: list[Requirement]


class Delay(BaseModel):
    """A step of a script: wait this long before the next step."""

    seconds: float


Step = Event | dict[str, Any] | Pause | Delay
Script = Callable[[str], list[Step]]


class CommandResult(BaseModel):
    """What a command played by the fake prints and exits with."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class Received(BaseModel):
    """One message a client sent the fake."""

    client_id: str
    frame: dict[str, Any] = Field(default_factory=dict)


class _Continuation(BaseModel):
    session_id: str
    steps: list[Any]


class FakeIgni:
    """igni's socket on loopback, scripted — with Fleet's gateway in front when `gateway=True`."""

    def __init__(
        self,
        *,
        gateway: bool = False,
        tokens: dict[str, str] | None = None,
        org: str = "org-acme",
        local_token: str | None = None,
    ) -> None:
        #: Gateway mode: `tokens` maps each accepted bearer token to its producer (`kind:id`).
        self.gateway = gateway
        self.tokens = dict(tokens or {})
        self.org = org
        #: Local mode: the per-launch token a client must offer, or `None` for none.
        self.local_token = local_token
        #: What a prompt runs. Return the steps of the run for the prompt's text.
        self.script: Script = lambda text: FakeIgni.answer(f"echo: {text}")
        #: Answers to calls the fake does not play itself: a value, or a function of the args.
        self.rpc_answers: dict[str, Any] = {}
        #: The models `get_model_registry` lists.
        self.models: dict[str, dict[str, Any]] = {"igni-1": {"provider": "igni"}}
        #: A session's history, as `get_chat_history` returns it.
        self.history: dict[str, list[dict[str, Any]]] = {}
        #: What a command run through the gateway prints, by command.
        self.commands: dict[str, CommandResult] = {}
        #: Everything clients sent, in order.
        self.received: list[Received] = []
        #: Every approval answer, in order: the `hitl_decision`s of each batch.
        self.decisions: list[list[dict[str, Any]]] = []
        #: Every command run through the gateway: its body.
        self.commands_run: list[dict[str, Any]] = []
        #: The sessions attached, by id, with their project.
        self.sessions: dict[str, str] = {}
        #: How many connections were accepted.
        self.connections = 0
        self.url = ""
        self.port = 0
        self._server: Server | None = None
        self._clients: dict[ServerConnection, str] = {}
        self._ids = itertools.count(1)
        self._paused: dict[str, _Continuation] = {}
        self._active: dict[str, str] = {}
        self._busy = 0
        self._unbound = 0
        self._tasks: set[asyncio.Task[Any]] = set()

    # ── Scripts ──

    @staticmethod
    def answer(text: str, *, model: str = "igni-1", agent: str = "igni") -> list[Step]:
        """The steps of a run that answers `text` and completes."""
        return [
            {"type": "run_started", "run_id": "r-1", "agent_name": agent, "model": model},
            {"type": "content_delta", "text": text},
            {
                "type": "run_completed",
                "run_id": "r-1",
                "input_tokens": 10,
                "output_tokens": len(text.split()),
            },
        ]

    @staticmethod
    def approval(tool_name: str, *, requirement_id: str = "", **tool_args: Any) -> Pause:
        """A step that pauses the run until a call to `tool_name` is answered."""
        return Pause(
            requirements=[
                Requirement(
                    requirement_id=requirement_id or f"req-{tool_name}",
                    tool_name=tool_name,
                    friendly_name=tool_name.replace("_", " "),
                    tool_args=tool_args,
                )
            ]
        )

    # ── Lifecycle ──

    async def start(self) -> FakeIgni:
        self._server = await serve(
            self._serve,
            "127.0.0.1",
            0,
            compression=None,
            process_request=self._check,
            select_subprotocol=lambda _conn, offered: next(
                (p for p in offered if p == "igni.v1"), None
            ),
        )
        self.port = int(next(iter(self._server.sockets)).getsockname()[1])
        path = "/v1/connect" if self.gateway else ""
        self.url = f"ws://127.0.0.1:{self.port}{path}"
        return self

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> FakeIgni:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    def local(self) -> Local:
        """A `Local` target pointed at this fake."""
        return Local(url=f"ws://127.0.0.1:{self.port}", token=self.local_token)

    def fleet(self, auth: TokenSource) -> Fleet:
        """A `Fleet` target pointed at this fake as the gateway, its HTTP calls served by `transport()`."""
        if not self.gateway:
            raise RuntimeError("FakeIgni(gateway=True) plays the gateway")
        http = httpx.AsyncClient(transport=self.transport())
        return Fleet(f"http://127.0.0.1:{self.port}", auth=auth, http=http)

    # ── What happens to a connection ──

    async def move(self) -> None:
        """Fleet moved the VM: every client gets a new `welcome` on the socket it has."""
        for socket in list(self._clients):
            client_id = self._new_client_id()
            self._clients[socket] = client_id
            await self._send_to(socket, {"type": "welcome", "client_id": client_id})

    async def drop(self, code: int = 1011, reason: str = "igni keeps going away") -> None:
        """Close every connection with `code`."""
        for socket in list(self._clients):
            await socket.close(code, reason)

    def busy_next(self, count: int = 1) -> None:
        """Answer the next `count` connections "busy, retry" (`1013`), as the gateway does with no room."""
        self._busy = count

    def unbound_for(self, count: int) -> None:
        """Answer the next `count` calls as a VM not yet bound to its producer."""
        self._unbound = count

    async def emit(self, event: Step, *, session_id: str = "") -> None:
        """Send a message to every client, as a broadcast."""
        frame = self._frame(event)
        frame.setdefault("session_id", session_id)
        await self._broadcast(frame)

    # ── The socket ──

    def _check(self, connection: ServerConnection, request: Request) -> Response | None:
        if self.gateway:
            if request.path.split("?")[0] != "/v1/connect":
                return connection.respond(HTTPStatus.NOT_FOUND, "not found\n")
            header = request.headers.get("Authorization", "")
            token = header.removeprefix("Bearer ").strip()
            if token not in self.tokens:
                return connection.respond(
                    HTTPStatus.UNAUTHORIZED,
                    json.dumps(
                        {"error": "invalid_token", "error_description": "the token was refused"}
                    ),
                )
            return None
        if self.local_token is not None:
            offered = [
                p.strip()
                for value in request.headers.get_all("Sec-WebSocket-Protocol")
                for p in value.split(",")
            ]
            if f"{TOKEN_PROTOCOL_PREFIX}{self.local_token}" not in offered:
                return connection.respond(HTTPStatus.FORBIDDEN, "Forbidden\n")
        return None

    async def _serve(self, socket: ServerConnection) -> None:
        self.connections += 1
        if self._busy > 0:
            self._busy -= 1
            await socket.close(1013, "busy, retry")
            return
        client_id = self._new_client_id()
        self._clients[socket] = client_id
        try:
            await self._send_to(socket, {"type": "welcome", "client_id": client_id})
            async for raw in socket:
                try:
                    frame = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(frame, dict):
                    self.received.append(
                        Received(client_id=self._clients.get(socket, ""), frame=frame)
                    )
                    self._spawn(self._handle(socket, frame))
        except Exception:  # noqa: S110 — a client going away is not the fake's failure
            pass
        finally:
            self._clients.pop(socket, None)

    async def _handle(self, socket: ServerConnection, frame: dict[str, Any]) -> None:
        kind = frame.get("type")
        request_id = str(frame.get("id") or "")
        session_id = str(frame.get("session_id") or "")
        if kind == "rpc_request":
            await self._rpc(
                socket,
                request_id,
                session_id,
                str(frame.get("method")),
                dict(frame.get("args") or {}),
            )
        elif kind == "user_message":
            text = str(frame.get("text") or "")
            await self._broadcast(
                {
                    "type": "user_message_received",
                    "session_id": session_id,
                    "text": text,
                    "client_id": str(frame.get("client_id") or ""),
                }
            )
            self._active[session_id] = request_id
            await self._play(request_id, session_id, list(self.script(text)))
        elif kind == "hitl_response_batch":
            await self._resume(request_id, session_id, list(frame.get("decisions") or []))
        elif kind == "queue_message":
            await self._broadcast(
                {
                    "type": "user_message_received",
                    "session_id": session_id,
                    "text": str(frame.get("text") or ""),
                    "queued": True,
                }
            )
        elif kind == "cancel":
            active = self._active.pop(session_id, "")
            if active:
                await self._broadcast(
                    {
                        "type": "info",
                        "id": active,
                        "session_id": session_id,
                        "text": "Run cancelled by user.",
                    }
                )
                await self._broadcast(
                    {"type": "stream_end", "id": active, "session_id": session_id}
                )

    async def _rpc(
        self,
        socket: ServerConnection,
        request_id: str,
        session_id: str,
        method: str,
        args: dict[str, Any],
    ) -> None:
        def reply(result: Any = None, error: str | None = None) -> dict[str, Any]:
            return {
                "type": "rpc_response",
                "id": request_id,
                "session_id": session_id,
                "result": result,
                "error": error,
            }

        if self._unbound > 0:
            self._unbound -= 1
            await self._broadcast(reply(error=UNBOUND))
            return
        if method == "attach_session":
            sid = str(args.get("session_id") or f"s-{next(self._ids)}")
            project = str(args.get("project_dir") or self.sessions.get(sid) or "/workspace")
            self.sessions[sid] = project
            await self._broadcast(reply({"session_id": sid, "project_dir": project}))
        elif method == "get_session_id":
            await self._broadcast(reply("s-default"))
        elif method == "list_sessions":
            sessions = [{"session_id": sid, "name": sid} for sid in self.sessions]
            await self._broadcast(
                {
                    "type": "session_list_result",
                    "id": request_id,
                    "session_id": session_id,
                    "sessions": sessions,
                }
            )
        elif method == "get_model_registry":
            await self._broadcast(
                reply(
                    {
                        "default": next(iter(self.models), ""),
                        "max_context_window": 200_000,
                        "registry": self.models,
                    }
                )
            )
        elif method == "switch_model":
            await self._broadcast(
                {
                    "type": "info",
                    "id": request_id,
                    "session_id": session_id,
                    "text": f"Switched to {args.get('model_name')}",
                }
            )
        elif method == "get_status":
            await self._broadcast(
                {
                    "type": "status_update",
                    "id": request_id,
                    "session_id": session_id,
                    "model": next(iter(self.models), ""),
                }
            )
        elif method == "get_chat_history":
            await self._broadcast(
                reply(self.history.get(str(args.get("session_id") or session_id), []))
            )
        elif method in self.rpc_answers:
            answer = self.rpc_answers[method]
            result = answer(args) if callable(answer) else answer
            if isinstance(result, Awaitable):
                result = await result
            await self._broadcast(reply(result))
        else:
            await self._broadcast(reply(error=f"Unknown RPC method: {method}"))

    async def _play(self, request_id: str, session_id: str, steps: list[Step]) -> None:
        for index, step in enumerate(steps):
            if isinstance(step, Delay):
                await asyncio.sleep(step.seconds)
                continue
            if isinstance(step, Pause):
                for requirement in step.requirements:
                    self._paused[requirement.requirement_id] = _Continuation(
                        session_id=session_id, steps=steps[index + 1 :]
                    )
                await self._broadcast(
                    {
                        "type": "run_paused",
                        "id": request_id,
                        "session_id": session_id,
                        "run_id": "r-1",
                        "requirements": [r.model_dump() for r in step.requirements],
                    }
                )
                await self._broadcast(
                    {"type": "stream_end", "id": request_id, "session_id": session_id}
                )
                return
            frame = self._frame(step)
            frame["id"] = request_id
            frame["session_id"] = session_id
            await self._broadcast(frame)
        await self._broadcast({"type": "stream_end", "id": request_id, "session_id": session_id})
        if self._active.get(session_id) == request_id:
            self._active.pop(session_id, None)

    async def _resume(
        self, request_id: str, session_id: str, decisions: list[dict[str, Any]]
    ) -> None:
        self.decisions.append(decisions)
        continuation: _Continuation | None = None
        for decision in decisions:
            rid = str(decision.get("requirement_id"))
            await self._broadcast(
                {"type": "requirement_resolved", "session_id": session_id, "requirement_id": rid}
            )
            continuation = self._paused.pop(rid, None) or continuation
        rejected = any(d.get("action") == "reject" for d in decisions)
        steps: list[Step] = []
        if continuation is not None:
            steps = (
                [
                    {
                        "type": "tool_completed",
                        "run_id": "r-1",
                        "summary": "rejected",
                        "is_rejected": True,
                    },
                    *FakeIgni.answer("I did not run it."),
                ]
                if rejected
                else list(continuation.steps)
            )
        self._active[session_id] = request_id
        await self._play(request_id, session_id, steps)

    # ── The gateway's HTTP API ──

    def transport(self) -> httpx.MockTransport:
        """The gateway's `/v1/me` and `/v1/commands`, for an `httpx.AsyncClient`."""
        return httpx.MockTransport(self._http)

    def _http(self, request: httpx.Request) -> httpx.Response:
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        producer = self.tokens.get(token)
        if producer is None:
            return httpx.Response(401, json={"error": "invalid_token"})
        if request.url.path == "/v1/me" and request.method == "GET":
            return httpx.Response(
                200, json={"producer": producer, "org": self.org, "group": None, "expires_at": 0}
            )
        if request.url.path == "/v1/commands" and request.method == "POST":
            body = json.loads(request.content or b"{}")
            self.commands_run.append(body)
            target = body.get("producer") or {}
            if f"{target.get('kind')}:{target.get('id')}" != producer:
                return httpx.Response(403, json={"detail": "not your VM"})
            played = self.commands.get(
                str(body.get("command")), CommandResult(stdout=f"ran {body.get('command')}\n")
            )
            lines: list[dict[str, Any]] = [
                {
                    "command": {
                        "command_id": f"c-{next(self._ids)}",
                        "command": body.get("command"),
                        "state": "running",
                    }
                },
                {"woken": {"how": "paused", "node": "n1", "ms": 12.345}},
            ]
            if played.stdout:
                lines.append(
                    {
                        "stream": "stdout",
                        "data_b64": base64.b64encode(played.stdout.encode()).decode(),
                    }
                )
            if played.stderr:
                lines.append(
                    {
                        "stream": "stderr",
                        "data_b64": base64.b64encode(played.stderr.encode()).decode(),
                    }
                )
            lines.append({"done": True, "exit_code": played.exit_code, "duration_ms": 5})
            content = "".join(json.dumps(line) + "\n" for line in lines)
            return httpx.Response(
                200, content=content, headers={"content-type": "application/x-ndjson"}
            )
        return httpx.Response(404, json={"error": "not_found"})

    # ── Helpers ──

    def _frame(self, step: Step) -> dict[str, Any]:
        if isinstance(step, BaseModel):
            return step.model_dump(exclude_none=True)
        return dict(step)

    def _new_client_id(self) -> str:
        return f"ws-{next(self._ids)}"

    async def _broadcast(self, frame: dict[str, Any]) -> None:
        for socket in list(self._clients):
            await self._send_to(socket, frame)

    @staticmethod
    async def _send_to(socket: ServerConnection, frame: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await socket.send(json.dumps(frame))

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


__all__ = ["CommandResult", "Delay", "FakeIgni", "Pause", "Received", "Script", "Step"]

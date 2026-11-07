"""Sessions: igni's conversations, each with its own history, model and project."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from igni_client.approvals import ApprovalRequested, Approver, Policy
from igni_client.connection import Connection
from igni_client.errors import RpcError
from igni_client.events import (
    Event,
    InfoMessage,
    RpcResponse,
    SessionListEntry,
    SessionListResult,
    StatusUpdate,
)
from igni_client.frames import Cancel, QueueMessage, UserMessage
from igni_client.replies import Reply
from igni_client.runs import Run


class Session:
    """One of igni's sessions, attached to this client."""

    def __init__(self, conn: Connection, session_id: str, project_dir: str = "") -> None:
        self._conn = conn
        self.id = session_id
        self.project_dir = project_dir

    def send(
        self, text: str, *, files: dict[str, str] | None = None, force: bool = False
    ) -> AsyncIterator[Event | ApprovalRequested]:
        """Send a prompt and follow the run it starts, event by event.

        `files` maps a path to its content, attached to the prompt as the
        app attaches a file. `force` discards a run left interrupted in this
        session before starting. A run that pauses for approval yields an
        `ApprovalRequested`; answer it in the loop and the loop continues.
        """
        frame = UserMessage(
            id=self._conn.router.new_id("run"),
            session_id=self.id,
            text=text,
            file_contents=dict(files or {}),
            client_id=self._conn.client_id,
            force=force,
        )
        return Run(self._conn, self.id).stream(frame)

    async def ask(
        self, text: str, *, files: dict[str, str] | None = None, approve: Policy | None = None
    ) -> Reply:
        """Send a prompt and return the whole answer once the run ends.

        `approve` answers any approval the run asks for: `True` allows every
        call, `False` refuses every call, or a function of the `Requirement`
        returns a `bool` or a `Decision`, and may be async. Without it, a
        pause raises `ApprovalRequired`. A failed run raises `RunFailed`.
        """
        return await Reply.collect(self.send(text, files=files), Approver(approve))

    async def queue(self, text: str) -> None:
        """Add a prompt for after the run that is going; it starts nothing now."""
        await self._conn.send(
            QueueMessage(session_id=self.id, text=text, client_id=self._conn.client_id)
        )

    async def cancel(self) -> None:
        """Stop the run that is going. Its stream ends with "Run cancelled by user."."""
        await self._conn.send(Cancel(session_id=self.id))

    async def history(self) -> list[dict[str, Any]]:
        """The session's messages so far, as igni stores them."""
        result = await self.rpc("get_chat_history", session_id=self.id)
        return list(result) if isinstance(result, list) else []

    async def status(self) -> StatusUpdate:
        """The model, the context used and the permission mode of this session."""
        reply = await self._conn.rpc("get_status", session_id=self.id)
        if isinstance(reply, StatusUpdate):
            return reply
        raise RpcError("get_status", f"igni answered with {reply.type}")

    async def use_model(self, name: str) -> str:
        """Switch this session to the model `name` (a key of `Models.list()`). Returns igni's notice."""
        reply = await self._conn.rpc("switch_model", {"model_name": name}, session_id=self.id)
        if isinstance(reply, InfoMessage):
            return reply.text
        if isinstance(reply, RpcResponse):
            return str(reply.result or "")
        return ""

    async def rpc(self, method: str, **args: Any) -> Any:
        """Call any of igni's methods in this session. See `IgniClient.rpc`."""
        return _result(await self._conn.rpc(method, args, session_id=self.id))

    def __repr__(self) -> str:
        return f"Session({self.id!r})"


class Sessions:
    """Create, open and list sessions."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn
        self._attached: dict[str, Session] = {}

    async def create(self, project_dir: str | None = None) -> Session:
        """A new session, working in `project_dir` (igni's own project when left out)."""
        return await self._attach(None, project_dir)

    async def open(self, session_id: str, project_dir: str | None = None) -> Session:
        """An existing session. Approvals it was waiting for are offered again."""
        return await self._attach(session_id, project_dir)

    async def default(self) -> Session:
        """The session igni opened at start."""
        reply = await self._conn.rpc("get_session_id")
        session_id = str(_result(reply) or "")
        return await self._attach(session_id or None, None)

    async def list(self) -> list[SessionListEntry]:
        """Every session igni keeps, newest first."""
        reply = await self._conn.rpc("list_sessions")
        if isinstance(reply, SessionListResult):
            return reply.sessions
        result = _result(reply)
        return [SessionListEntry.model_validate(s) for s in result or []]

    async def _attach(self, session_id: str | None, project_dir: str | None) -> Session:
        args: dict[str, Any] = {}
        if session_id:
            args["session_id"] = session_id
        if project_dir:
            args["project_dir"] = project_dir
        result = _result(await self._conn.rpc("attach_session", args))
        attached = result if isinstance(result, dict) else {}
        sid = str(attached.get("session_id") or session_id or "")
        session = self._attached.get(sid) or Session(self._conn, sid)
        session.project_dir = str(attached.get("project_dir") or project_dir or "")
        self._attached[sid] = session
        return session

    async def reattach(self) -> None:
        """Attach every session again — after igni moved, or the socket was opened again."""
        for session in list(self._attached.values()):
            await self._attach(session.id, session.project_dir or None)


class ModelCatalogue(BaseModel):
    """The models igni can use, by the name a session switches to."""

    model_config = ConfigDict(extra="allow")

    default: str = ""
    max_context_window: int = 0
    models: dict[str, dict[str, Any]] = Field(default_factory=dict)


class Models:
    """The models this igni serves."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def list(self) -> ModelCatalogue:
        result = _result(await self._conn.rpc("get_model_registry"))
        body = result if isinstance(result, dict) else {}
        return ModelCatalogue(
            default=str(body.get("default") or ""),
            max_context_window=int(body.get("max_context_window") or 0),
            models=dict(body.get("registry") or {}),
        )


def _result(reply: Event) -> Any:
    """An `RpcResponse`'s result, or the typed message a method answered with instead."""
    return reply.result if isinstance(reply, RpcResponse) else reply

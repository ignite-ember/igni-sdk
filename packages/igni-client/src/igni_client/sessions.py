"""Sessions: igni's conversations, each with its own history, model and project."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from igni_client.approvals import ApprovalRequested, Approver, Policy
from igni_client.connection import Connection
from igni_client.events import (
    Event,
    InfoMessage,
    SessionListEntry,
    SessionListResult,
    StatusUpdate,
)
from igni_client.frames import Cancel, QueueMessage, UserMessage
from igni_client.methods import (
    ATTACHED_SESSION,
    HISTORY,
    SESSION_ID,
    AttachSession,
    HistoryTurn,
    SessionRef,
    SwitchModel,
)
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

    async def history(self) -> list[HistoryTurn]:
        """The session's turns so far, as igni stores them."""
        return await self._conn.rpc(
            "get_chat_history", HISTORY, SessionRef(session_id=self.id), session_id=self.id
        )

    async def status(self) -> StatusUpdate:
        """The model, the context used and the permission mode of this session."""
        return await self._conn.rpc("get_status", StatusUpdate, session_id=self.id)

    async def use_model(self, name: str) -> str:
        """Switch this session to the model `name` (a key of `Models.list()`). Returns igni's notice."""
        notice = await self._conn.rpc(
            "switch_model", InfoMessage, SwitchModel(model_name=name), session_id=self.id
        )
        return notice.text

    async def rpc(self, method: str, **args: Any) -> Any:
        """Call any of igni's methods in this session. See `IgniClient.rpc`."""
        return self._conn.result(await self._conn.ask(method, args, session_id=self.id))

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
        session_id = await self._conn.rpc("get_session_id", SESSION_ID)
        return await self._attach(session_id or None, None)

    async def list(self) -> list[SessionListEntry]:
        """Every session igni keeps, newest first."""
        listed = await self._conn.rpc("list_sessions", SessionListResult)
        return listed.sessions

    async def _attach(self, session_id: str | None, project_dir: str | None) -> Session:
        attached = await self._conn.rpc(
            "attach_session",
            ATTACHED_SESSION,
            AttachSession(session_id=session_id or None, project_dir=project_dir or None),
        )
        session = self._attached.get(attached.session_id) or Session(
            self._conn, attached.session_id
        )
        session.project_dir = attached.project_dir
        self._attached[attached.session_id] = session
        return session

    async def reattach(self) -> None:
        """Attach every session again — after igni moved, or the socket was opened again."""
        for session in list(self._attached.values()):
            await self._attach(session.id, session.project_dir or None)

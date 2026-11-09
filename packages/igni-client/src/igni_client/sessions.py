"""Sessions: igni's conversations, each with its own history, model and project."""

from __future__ import annotations

from collections.abc import AsyncIterator

from igni_client.api import IgniSessions, SessionApi
from igni_client.approvals import ApprovalRequested, Approver, Policy
from igni_client.calls import Caller
from igni_client.connection import Connection
from igni_client.models import QueueMessage, RunPaused, SessionListEntry, UserMessage
from igni_client.replies import Reply
from igni_client.runs import Run, answer_elsewhere
from igni_client.wire import Event


class Session(SessionApi):
    """One of igni's sessions, attached to this client.

    `send()`, `ask()` and `queue()` prompt it; every method igni answers for
    one session is here too, grouped as igni groups them — `session.plan`,
    `session.history`, `session.mcp` and the rest (`igni_client.api.SessionApi`).
    """

    def __init__(self, conn: Connection, session_id: str, project_dir: str = "") -> None:
        super().__init__(Caller(conn, session_id))
        self._conn = conn
        #: The folder this session works in, as igni bound it.
        self.project_dir = project_dir

    @property
    def id(self) -> str:
        """The session's id."""
        return self._caller.session_id

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

    async def events(self) -> AsyncIterator[Event | ApprovalRequested]:
        """Every message igni sends about this session from now on, from every client's runs.

        igni broadcasts, so this sees the runs a person starts in igni's
        window as much as this client's own. A run that pauses for approval
        is offered as an `ApprovalRequested` — among them the approvals igni
        shows again when a session is attached — and answering it resumes
        the run, whose events follow here. Use `send()` to follow a run of
        your own.
        """
        queue = self._conn.router.listen()
        try:
            while True:
                event = await queue.get()
                if event.session_id != self.id:
                    continue
                if isinstance(event, RunPaused):
                    yield ApprovalRequested(event, answer_elsewhere(self._conn, self.id))
                    continue
                yield event
        finally:
            self._conn.router.unlisten(queue)

    def __repr__(self) -> str:
        return f"Session({self.id!r})"


class Sessions(IgniSessions):
    """Create, open and list sessions; `attach()` is igni's own call underneath."""

    def __init__(self, conn: Connection) -> None:
        super().__init__(Caller(conn))
        self._conn = conn
        self._attached: dict[str, Session] = {}

    async def create(self, project_dir: str | None = None) -> Session:
        """A new session, working in `project_dir` (igni's own project when left out)."""
        return await self._attach(None, project_dir)

    async def open(self, session_id: str, project_dir: str | None = None) -> Session:
        """An existing session. Approvals it was waiting for are shown again (`Session.events()`)."""
        return await self._attach(session_id, project_dir)

    async def default(self) -> Session:
        """The session igni opened at start."""
        session_id = await SessionApi(Caller(self._conn)).current_id()
        return await self._attach(session_id or None, None)

    async def list(self) -> list[SessionListEntry]:
        """Every session kept in igni's own project, newest first.

        For another project's, call `list_sessions()` on a session of it.
        """
        listed = await SessionApi(Caller(self._conn)).list_sessions()
        return listed.sessions

    async def _attach(self, session_id: str | None, project_dir: str | None) -> Session:
        attached = await self.attach(session_id=session_id or "", project_dir=project_dir or "")
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


__all__ = ["Session", "Sessions"]

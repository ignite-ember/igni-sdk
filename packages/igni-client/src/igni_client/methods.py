"""The arguments and answers of the igni methods this client calls itself."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, TypeAdapter


class SessionRef(BaseModel):
    """Arguments naming one session, for the methods that read one."""

    session_id: str


class SwitchModel(BaseModel):
    """Arguments of `switch_model`."""

    model_name: str


class AttachSession(BaseModel):
    """Arguments of `attach_session`: a session to attach, or none for a new one."""

    session_id: str | None = None
    project_dir: str | None = None


class AttachedSession(BaseModel):
    """`attach_session`'s answer: the session igni bound, and the project it works in."""

    session_id: str
    project_dir: str


class HistoryTurn(BaseModel):
    """One turn of a session's history, as igni stores it.

    `role` says which kind it is (`user`, `assistant`, `thinking`, `tool`,
    `plan`, `stats`, `visualization`); the fields of each kind are kept.
    """

    model_config = ConfigDict(extra="allow")

    role: str
    run_id: str = ""
    created_at: int = 0
    content: str = ""


ATTACHED_SESSION = TypeAdapter(AttachedSession)
HISTORY = TypeAdapter(list[HistoryTurn])
SESSION_ID = TypeAdapter(str | None)

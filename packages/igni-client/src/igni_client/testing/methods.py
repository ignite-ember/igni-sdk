"""igni's methods, as the fake answers them: the ones it plays itself, and the ones a test sets."""

from __future__ import annotations

import inspect
import itertools
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from igni_client.catalogue import ModelCatalogue, ModelEntry
from igni_client.connection import UNBOUND
from igni_client.events import (
    Event,
    InfoMessage,
    RpcResponse,
    SessionListEntry,
    SessionListResult,
    StatusUpdate,
)
from igni_client.frames import RpcRequest
from igni_client.methods import AttachedSession, AttachSession, HistoryTurn, SwitchModel

#: A method's answer: the value itself, or a function of the call's args (sync or async).
RpcAnswer = Any | Callable[[dict[str, Any]], Any]

DEFAULT_SESSION = "s-default"
DEFAULT_PROJECT = "/workspace"
MAX_CONTEXT_WINDOW = 200_000


class HistoryArgs(BaseModel):
    """`get_chat_history`'s args: the session to read, or the call's own when none is named."""

    session_id: str | None = None


class FakeMethods:
    """Answers every call a client makes, as one message to broadcast."""

    def __init__(self) -> None:
        #: Answers to calls the fake does not play itself, by method.
        self.answers: dict[str, RpcAnswer] = {}
        #: The models `get_model_registry` lists.
        self.models: dict[str, ModelEntry] = {"igni-1": ModelEntry(provider="igni")}
        #: A session's history, as `get_chat_history` returns it.
        self.history: dict[str, list[HistoryTurn]] = {}
        #: The sessions attached, by id, with their project.
        self.sessions: dict[str, str] = {}
        self._unbound = 0
        self._ids = itertools.count(1)
        self._played: dict[str, Callable[[RpcRequest], Event]] = {
            "attach_session": self._attach_session,
            "get_session_id": self._get_session_id,
            "list_sessions": self._list_sessions,
            "get_model_registry": self._get_model_registry,
            "switch_model": self._switch_model,
            "get_status": self._get_status,
            "get_chat_history": self._get_chat_history,
        }

    def unbound_for(self, count: int) -> None:
        """Answer the next `count` calls as a VM not yet bound to its producer."""
        self._unbound = count

    async def answer(self, call: RpcRequest) -> Event:
        """What igni sends back for `call`."""
        if self._unbound > 0:
            self._unbound -= 1
            return self._reply(call, error=UNBOUND)
        played = self._played.get(call.method)
        if played is not None:
            return played(call)
        if call.method in self.answers:
            answer = self.answers[call.method]
            result = answer(call.args) if callable(answer) else answer
            if inspect.isawaitable(result):
                result = await result
            return self._reply(call, result)
        return self._reply(call, error=f"Unknown RPC method: {call.method}")

    # ── The methods the fake plays ──

    def _attach_session(self, call: RpcRequest) -> Event:
        args = AttachSession.model_validate(call.args)
        session_id = args.session_id or f"s-{next(self._ids)}"
        project = args.project_dir or self.sessions.get(session_id) or DEFAULT_PROJECT
        self.sessions[session_id] = project
        attached = AttachedSession(session_id=session_id, project_dir=project)
        return self._reply(call, attached.model_dump())

    def _get_session_id(self, call: RpcRequest) -> Event:
        return self._reply(call, DEFAULT_SESSION)

    def _list_sessions(self, call: RpcRequest) -> Event:
        return SessionListResult(
            id=call.id,
            session_id=call.session_id or "",
            sessions=[SessionListEntry(session_id=sid, name=sid) for sid in self.sessions],
        )

    def _get_model_registry(self, call: RpcRequest) -> Event:
        catalogue = ModelCatalogue(
            default=next(iter(self.models), ""),
            max_context_window=MAX_CONTEXT_WINDOW,
            registry=self.models,
        )
        return self._reply(call, catalogue.model_dump(by_alias=True))

    def _switch_model(self, call: RpcRequest) -> Event:
        args = SwitchModel.model_validate(call.args)
        return InfoMessage(
            id=call.id, session_id=call.session_id or "", text=f"Switched to {args.model_name}"
        )

    def _get_status(self, call: RpcRequest) -> Event:
        return StatusUpdate(
            id=call.id, session_id=call.session_id or "", model=next(iter(self.models), "")
        )

    def _get_chat_history(self, call: RpcRequest) -> Event:
        session_id = HistoryArgs.model_validate(call.args).session_id or call.session_id or ""
        turns = self.history.get(session_id, [])
        return self._reply(call, [turn.model_dump() for turn in turns])

    @staticmethod
    def _reply(call: RpcRequest, result: Any = None, error: str | None = None) -> RpcResponse:
        return RpcResponse(id=call.id, session_id=call.session_id or "", result=result, error=error)


__all__ = ["FakeMethods", "HistoryArgs", "RpcAnswer"]

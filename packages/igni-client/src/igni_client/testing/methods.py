"""igni's methods, as the fake answers them: the ones it plays itself, and the ones a test sets."""

from __future__ import annotations

import inspect
import itertools
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from igni_client.api import METHODS
from igni_client.connection import UNBOUND
from igni_client.models import (
    AttachSessionParams,
    AttachSessionResult,
    ChatTurn,
    InfoMessage,
    ModelRegistryEntryView,
    ModelRegistryResult,
    RpcRequest,
    RpcResponse,
    SessionIdArgs,
    SessionListEntry,
    SessionListResult,
    StatusUpdate,
    SwitchModelArgs,
)
from igni_client.wire import Event

#: A method's answer: the value itself, or a function of the call's args (sync or async).
#: A value may be a model (sent as its JSON), an `Event` (sent as igni sends a method
#: answered by a message), or anything JSON holds.
RpcAnswer = Any | Callable[[dict[str, Any]], Any]

DEFAULT_SESSION = "s-default"
DEFAULT_PROJECT = "/workspace"
MAX_CONTEXT_WINDOW = 200_000


class FakeMethods:
    """Answers every call a client makes, as one message to broadcast."""

    def __init__(self) -> None:
        #: Answers to calls the fake does not play itself, by method.
        self.answers: dict[str, RpcAnswer] = {}
        #: The models `get_model_registry` lists.
        self.models: dict[str, ModelRegistryEntryView] = {
            "igni-1": ModelRegistryEntryView(
                model_id="igni-1",
                provider="igni",
                has_api_key=True,
                prompt_caching=True,
                timeout=60,
                vision=False,
            )
        }
        #: A session's history, as `get_chat_history` returns it.
        self.history: dict[str, list[ChatTurn]] = {}
        #: The sessions attached, by id, with their project.
        self.sessions: dict[str, str] = {}
        #: Every call answered, in order.
        self.calls: list[RpcRequest] = []
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
        self.calls.append(call)
        if self._unbound > 0:
            self._unbound -= 1
            return self._reply(call, error=UNBOUND)
        if call.method in self.answers:
            answer = self.answers[call.method]
            result = answer(dict(call.args)) if callable(answer) else answer
            if inspect.isawaitable(result):
                result = await result
            return self.reply(call, result)
        played = self._played.get(call.method)
        if played is not None:
            return played(call)
        if call.method in METHODS:
            return self._reply(call, error="the fake has no answer for it")
        return self._reply(call, error=f"Unknown RPC method: {call.method}")

    @classmethod
    def reply(cls, call: RpcRequest, result: Any) -> Event:
        """igni's answer to `call` carrying `result`: the message itself, or an `rpc_response`."""
        if isinstance(result, Event):
            return result.model_copy(update={"id": call.id, "session_id": call.session_id})
        if isinstance(result, BaseModel):
            result = result.model_dump(mode="json", by_alias=True)
        elif isinstance(result, list):
            result = [
                r.model_dump(mode="json", by_alias=True) if isinstance(r, BaseModel) else r
                for r in result
            ]
        return cls._reply(call, result)

    # ── The methods the fake plays ──

    def _attach_session(self, call: RpcRequest) -> Event:
        args = AttachSessionParams.model_validate(call.args)
        session_id = args.session_id or f"s-{next(self._ids)}"
        project = args.project_dir or self.sessions.get(session_id) or DEFAULT_PROJECT
        self.sessions[session_id] = project
        return self.reply(call, AttachSessionResult(session_id=session_id, project_dir=project))

    def _get_session_id(self, call: RpcRequest) -> Event:
        return self._reply(call, DEFAULT_SESSION)

    def _list_sessions(self, call: RpcRequest) -> Event:
        entries = [
            SessionListEntry(
                session_id=sid,
                name=sid,
                created_at=0,
                updated_at=0,
                run_count=0,
                summary="",
                agent_name="igni",
            )
            for sid in self.sessions
        ]
        return self.reply(call, SessionListResult(sessions=entries))

    def _get_model_registry(self, call: RpcRequest) -> Event:
        registry = ModelRegistryResult(
            default=next(iter(self.models), ""),
            max_context_window=MAX_CONTEXT_WINDOW,
            registry=self.models,
        )
        return self.reply(call, registry)

    def _switch_model(self, call: RpcRequest) -> Event:
        args = SwitchModelArgs.model_validate(call.args)
        return self.reply(call, InfoMessage(text=f"Switched to {args.model_name}"))

    def _get_status(self, call: RpcRequest) -> Event:
        return self.reply(call, StatusUpdate(model=next(iter(self.models), "")))

    def _get_chat_history(self, call: RpcRequest) -> Event:
        session_id = SessionIdArgs.model_validate(call.args).session_id
        return self.reply(call, list(self.history.get(session_id, [])))

    @staticmethod
    def _reply(call: RpcRequest, result: Any = None, error: str | None = None) -> RpcResponse:
        return RpcResponse(id=call.id, session_id=call.session_id, result=result, error=error)


__all__ = ["FakeMethods", "RpcAnswer"]

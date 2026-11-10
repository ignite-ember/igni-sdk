"""Events your service sends: `@ext.on_service_event`.

Your service sends an event for a producer (igni server's
`docs/service-identity.md` §15, igni's `docs/CLOUD.md` §6.1) — "the index
is ready", "the build failed". igni hands it to that producer's igni (on
their desktop, or in their Fleet VM, woken for it), which hands it to the
handler this extension registered for the event's `type` (or for every
type). **igni posts nothing for an event.** The handler does what it
wants through its host calls, and the agent runs only if it posts:

    @ext.on_service_event("index.ready")
    async def index_ready(event: ServiceEvent) -> None:
        created = await ext.host.sessions.create(title=f"Index: {event.payload['repo']}")
        await ext.host.sessions.chat(created.session_id).post("The index is ready; review it.")

`sessions.create` opens the chat without moving the person's window.

An event with no handler for its type, or that reaches no running
extension, or whose handler raises, is *not handled*: the service reads
`not_handled` when it polls the event. A handler returns nothing: what
it wants posted, it posts through `ext.host.sessions`.

A handler should be quick — igni waits on it (10 s at most) — and may be
handed the same event twice (delivery is at least once; igni drops the
repeat afterwards, by `event_id`).

Messages your service sends the agent (`agent.send_message` in
`igni-service`) never reach a handler: igni posts them as sent.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from igni_extension.caller import Caller, CallerScope
from igni_extension.threads import OffTheLoop
from igni_extension.wire import HookAnswer, Outcome

logger = logging.getLogger(__name__)

SERVICE_EVENT = "ServiceEvent"
"""The frame's event name on the host socket."""


class ServiceEvent(BaseModel):
    """One event from this extension's service."""

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)

    event_id: str
    """igni's id for it; a repeat has the same one."""
    extension_id: str = ""
    """The extension it is for: this one."""
    client_id: str = ""
    """The service that sent it (its client id)."""
    type: str
    """The service's own word for what happened: `claim.created`."""
    payload: dict[str, Any] = Field(default_factory=dict)
    """What the service sent with it."""
    event_key: str | None = None
    """The key the service sent it with, if any: one event per key."""
    created_at: str | None = None
    """When igni stored it, ISO 8601."""
    expires_at: str | None = None
    """When igni stops trying to deliver it, ISO 8601."""


ServiceEventHandler = Callable[[ServiceEvent], Awaitable[None] | None]


class ServiceEventHandlers:
    """One handler per event type, and one for any type."""

    ANY = "*"
    """Registered for every type the others do not name."""

    def __init__(self) -> None:
        self._handlers: dict[str, ServiceEventHandler] = {}

    def on(
        self, event_type: str | None = None
    ) -> Callable[[ServiceEventHandler], ServiceEventHandler]:
        key = event_type or self.ANY

        def register(handler: ServiceEventHandler) -> ServiceEventHandler:
            if key in self._handlers:
                raise ValueError(f"service event {key!r} has a handler already")
            self._handlers[key] = handler
            return handler

        return register

    async def answer(self, hook_id: str, raw: object, caller: Caller | None = None) -> HookAnswer:
        """The `answer` request's parameters: handled (`allow`), no handler (`reject`), or `failed`."""
        try:
            event = ServiceEvent.model_validate(raw)
        except ValidationError as exc:
            return HookAnswer(hook=hook_id, outcome=Outcome.FAILED, reason=f"not an event: {exc}")
        handler = self._handlers.get(event.type) or self._handlers.get(self.ANY)
        if handler is None:
            return HookAnswer(
                hook=hook_id, outcome=Outcome.REJECT, reason=f"no handler for {event.type}"
            )
        try:
            with CallerScope.of(caller):
                await OffTheLoop.call(handler, event)
        except Exception as exc:
            logger.exception("igni: the handler of service event %s failed", event.type)
            return HookAnswer(hook=hook_id, outcome=Outcome.FAILED, reason=str(exc))
        return HookAnswer(hook=hook_id, outcome=Outcome.ALLOW)


__all__ = ["SERVICE_EVENT", "ServiceEvent", "ServiceEventHandler", "ServiceEventHandlers"]

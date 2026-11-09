"""How a followed call's events are told from every other call's.

igni broadcasts: every client attached sees every session's messages. A
method that streams (the contract's `streams`) causes messages that carry
no request id, so a `Call` (`igni_client.calls`) picks out its own by what
they carry — a workflow run's id, a process's pid, a plan's run id — and
knows when there are no more. One rule per followed method, here; the
generated `METHODS` table says which methods are followed, and a test
holds the two together.

A method igni gives nothing to correlate is not followed at all: it is in
`igni_client.api.UNFOLLOWED`, with the reason.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from igni_client.models import PushNotification
from igni_client.wire import Event


@dataclass
class Context:
    """What a rule reads: the call's arguments, its session, and — once it came — its result."""

    args: BaseModel
    session_id: str
    result: Any = None
    has_result: bool = False


Test = Callable[[Context, Event], bool]


def _never(context: Context, event: Event) -> bool:
    return False


def _no_end(context: Context) -> bool:
    return False


@dataclass(frozen=True)
class Rule:
    """Which events are this call's, and when there are no more."""

    #: Whether `event` is one of this call's.
    match: Test
    #: Whether this call's `event` is its last.
    last: Test = _never
    #: Whether the result says nothing more will come.
    ends_with: Callable[[Context], bool] = _no_end
    #: Events are kept until the result says which to match.
    needs_result: bool = False
    #: Only the events that arrive while the call waits for its answer.
    while_waiting: bool = False
    #: Channels and message types the rule yields, for the docs.
    yields: tuple[str, ...] = field(default=())


def channel(event: Event, *names: str) -> bool:
    """Whether `event` is a push on one of `names`."""
    return isinstance(event, PushNotification) and event.channel in names


def payload(event: Event, key: str) -> Any:
    """A field of a push's payload, typed or not."""
    data = getattr(event, "payload", None)
    if isinstance(data, BaseModel):
        return getattr(data, key, None)
    if isinstance(data, dict):
        return data.get(key)
    return None


def arg(context: Context, key: str) -> Any:
    return getattr(context.args, key, None)


def result(context: Context, key: str) -> Any:
    return getattr(context.result, key, None)


def _same_session(context: Context, event: Event) -> bool:
    return bool(context.session_id) and event.session_id == context.session_id


# ── Plans ──


def _plan_decided(context: Context, event: Event) -> bool:
    return channel(event, "plan_decided") and payload(event, "run_id") == arg(context, "run_id")


PLAN = Rule(
    match=_plan_decided,
    last=_plan_decided,
    ends_with=lambda c: result(c, "ok") is False,
    yields=("plan_decided",),
)


# ── Workflows ──

WORKFLOW_ENDS = ("workflow_completed", "workflow_failed")


def _workflow(run_id: Callable[[Context], Any]) -> Test:
    def match(context: Context, event: Event) -> bool:
        return channel(event, "workflow_event") and payload(event, "workflow_run_id") == run_id(
            context
        )

    return match


def _workflow_last(run_id: Callable[[Context], Any]) -> Test:
    match = _workflow(run_id)

    def last(context: Context, event: Event) -> bool:
        return match(context, event) and payload(event, "type") in WORKFLOW_ENDS

    return last


def _run_workflow_id(context: Context) -> Any:
    return result(context, "workflow_run_id")


def _cancel_workflow_id(context: Context) -> Any:
    return arg(context, "workflow_run_id")


RUN_WORKFLOW = Rule(
    match=_workflow(_run_workflow_id),
    last=_workflow_last(_run_workflow_id),
    needs_result=True,
    yields=("workflow_event",),
)
CANCEL_WORKFLOW = Rule(
    match=_workflow(_cancel_workflow_id),
    last=_workflow_last(_cancel_workflow_id),
    ends_with=lambda c: result(c, "cancelled") is False,
    yields=("workflow_event",),
)


# ── Processes ──


def _process(context: Context, event: Event) -> bool:
    return channel(event, "process_line", "process_exited", "background_process_done") and payload(
        event, "pid"
    ) == arg(context, "pid")


STOP_PROCESS = Rule(
    match=_process,
    last=lambda c, e: _process(c, e) and channel(e, "background_process_done"),
    ends_with=lambda c: result(c, "killed") is False,
    yields=("process_line", "process_exited", "background_process_done"),
)

SHUTDOWN = Rule(
    match=lambda c, e: channel(e, "process_exited", "background_process_done"),
    while_waiting=True,
    yields=("process_exited", "background_process_done"),
)


# ── This session ──


def _visualization(context: Context, event: Event) -> bool:
    return (
        channel(event, "visualization_action_dispatched")
        and _same_session(context, event)
        and payload(event, "action") == arg(context, "action")
        and (payload(event, "params") or {}) == (arg(context, "params") or {})
    )


VISUALIZATION = Rule(
    match=_visualization, last=_visualization, yields=("visualization_action_dispatched",)
)

SCHEDULER = Rule(
    match=lambda c, e: (
        channel(e, "scheduler_started", "scheduler_completed") and _same_session(c, e)
    ),
    yields=("scheduler_started", "scheduler_completed"),
)


# ── Signing in ──

LOGIN = Rule(
    match=lambda c, e: channel(e, "login_status", "login_result"),
    last=lambda c, e: channel(e, "login_result"),
    yields=("login_status", "login_result"),
)


#: The rule of every followed method, by wire name.
RULES: dict[str, Rule] = {
    "approve_plan": PLAN,
    "dismiss_plan": PLAN,
    "run_workflow": RUN_WORKFLOW,
    "cancel_workflow": CANCEL_WORKFLOW,
    "stop_background_process": STOP_PROCESS,
    "shutdown": SHUTDOWN,
    "dispatch_visualization_action": VISUALIZATION,
    "start_scheduler": SCHEDULER,
    "login": LOGIN,
}

__all__ = ["RULES", "Context", "Rule", "channel", "payload"]

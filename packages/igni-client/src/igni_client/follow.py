"""How a followed call's events are told from every other call's.

igni broadcasts: every client attached sees every session's messages. A
`Call` (`igni_client.calls`) picks out its own by what they carry — a
workflow run's id, a process's pid, a plan's run id — and knows when
there are no more. One rule per followed method, here; the generated
`METHODS` table says which methods are followed, and a test holds the two
together.

What the events carry is igni's contract's business: it says, per method,
which place in a streamed message holds the value found in the call
(`correlation`), and which messages and pushes the call causes at all.
This module reads that and applies it; what the contract cannot say —
when a call's stream has no more to come — is what each rule adds.

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

#: The prefix a push channel's name carries in igni's contract.
PUSH_PREFIX = "push_notification:"


@dataclass
class Context:
    """What a rule reads: the call's arguments, its session, its request's id,
    and — once it came — its result."""

    args: BaseModel
    session_id: str
    #: The id of the request this call was sent as.
    request_id: str = ""
    result: Any = None
    has_result: bool = False
    #: Whether the call's last event has been seen.
    ended: bool = False


@dataclass(frozen=True)
class Correlation:
    """How a client tells which of the messages igni streams are a call's own.

    igni's contract says this for the calls it says it for: `by` is the
    place in the streamed message that holds the value found at `source`
    — a place in the call — or at `equals`, a fixed value. The places
    are the contract's: `id`, `session_id`, `run_id`, `payload.<field>`
    and `channel` in a message; `request.id`, `request.session_id`,
    `args.<field>` and `result.<field>` in the call.
    """

    #: Where in the streamed message the value is.
    by: str
    #: Where in the call the value comes from.
    source: str = ""
    #: A fixed value the message must carry.
    equals: str = ""


Test = Callable[[Context, Event], bool]


def _never(context: Context, event: Event) -> bool:
    return False


def _always(context: Context, event: Event) -> bool:
    return True


def _no_end(context: Context) -> bool:
    return False


@dataclass(frozen=True)
class Rule:
    """Which events are this call's, and when there are no more."""

    #: What the rule adds to the contract's correlation: whether `event` is
    #: one of this call's. `True` when it adds nothing.
    match: Test = _always
    #: Whether this call's `event` is its last.
    last: Test = _never
    #: Whether the result says nothing more will come.
    ends_with: Callable[[Context], bool] = _no_end
    #: Events are kept until the result says which to match.
    needs_result: bool = False
    #: Channels and message types the rule yields, for the docs.
    yields: tuple[str, ...] = field(default=())

    def is_ours(self, context: Context, event: Event, method: str) -> bool:
        """Whether `event` is this call's own.

        The contract's correlation says which of the messages igni streams
        are the call's own, and what the call causes says which of them
        it causes; the rule's `match` says anything more.
        """
        if event.type == "rpc_response":
            return False  # the answer is the answer, not one of the call's events
        correlation = correlation_of(method)
        if correlation is not None:
            causes = causes_of(method)
            if causes and not _caused_by(causes, event):
                return False
            if not correlated(correlation, context, event):
                return False
        return self.match(context, event)


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


def place(event: Event, where: str) -> Any:
    """The value at `where` in a message igni sent.

    `where` is the contract's: `id`, `session_id`, `run_id`, `channel`
    or `payload.<field>`. A place the message does not carry has no
    value, and so matches nothing.
    """
    if where.startswith("payload."):
        return payload(event, where.split(".", 1)[1])
    if where == "channel":
        return getattr(event, "channel", None)
    return getattr(event, where, None)


def call_place(context: Context, where: str) -> Any:
    """The value at `where` in the call: `request.id`, `request.session_id`,
    `args.<field>` or `result.<field>`.

    A `result.<field>` the answer has not brought yet is looked for in the
    argument of the same name: igni uses the argument it is given, so the
    value is known before the answer says it.
    """
    if where == "request.id":
        return context.request_id
    if where == "request.session_id":
        return context.session_id
    if where.startswith("args."):
        return arg(context, where.split(".", 1)[1])
    if where.startswith("result."):
        field = where.split(".", 1)[1]
        if not context.has_result:
            return arg(context, field)
        return result(context, field)
    return None


def correlated(correlation: Correlation, context: Context, event: Event) -> bool:
    """Whether `event` is this call's own, as the contract's correlation says.

    The message must carry, at the place the contract names, the value the
    call holds at the place it names — or, where the contract fixes the
    value, exactly that value. A correlation that names neither a value
    nor a fixed one says only that the call's effects are its own: what
    it causes decides.
    """
    if correlation.equals:
        return bool(place(event, correlation.by) == correlation.equals)
    if not correlation.source:
        return True
    wanted = call_place(context, correlation.source)
    if wanted is None:
        return False
    return bool(place(event, correlation.by) == wanted)


def _caused_by(causes: tuple[str, ...], event: Event) -> bool:
    """Whether `event` is one of the messages or pushes the call causes."""
    channel = getattr(event, "channel", "")
    for cause in causes:
        if cause.startswith(PUSH_PREFIX):
            if channel == cause[len(PUSH_PREFIX) :]:
                return True
        elif getattr(event, "type", "") == cause:
            return True
    return False


def correlation_of(method: str) -> Correlation | None:
    """The contract's rule for telling `method`'s events from every other call's."""
    from igni_client.calls import spec

    try:
        return spec(method).correlate
    except KeyError:
        return None


def causes_of(method: str) -> tuple[str, ...]:
    """The messages and pushes `method` causes, as the contract names them."""
    from igni_client.calls import spec

    try:
        described = spec(method)
    except KeyError:
        return ()
    return (*described.streams, *described.may_stream)


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
    needs_result=True,
    yields=("login_status", "login_result"),
)


# ── What the contract itself says ──
#
# For these the contract says which of the messages igni streams are the
# call's own — by the request's id, the session's, the run's, a path, a
# token or a cause. The rule says only what the contract cannot: when the
# stream has no more to come.


def _stream_end(context: Context, event: Event) -> bool:
    """Whether the message ends the stream it belongs to."""
    return getattr(event, "type", "") == "stream_end"


#: Attaching a session: the approvals it shows again, and the runs it
#: continues, carry the attach's own request id; a `stream_end` of that id
#: ends them.
ATTACH_SESSION = Rule(
    last=_stream_end,
    ends_with=lambda c: c.ended,
    yields=("run_paused", "requirement_details", "stream_end"),
)

#: Stopping the turn: the `info` and `stream_end` of the turn it stops are
#: the session's own, and the `stream_end` ends them. With no turn running
#: nothing is streamed, and the answer says so.
CANCEL_RUN = Rule(
    last=_stream_end,
    ends_with=lambda c: result(c, "cancelled") is False,
    yields=("info", "stream_end"),
)

#: A scheduled task's run: what its tools push carries the run's id, which
#: the call gives (igni-client makes one when the caller does not) and the
#: answer confirms. The run is over when the answer comes.
SCHEDULED_TASK = Rule(
    ends_with=lambda c: c.has_result,
    yields=(
        "orchestrate_event",
        "file_edited",
        "todos_updated",
        "process_started",
        "permission_mode_changed",
        "plan_submitted",
    ),
)

#: Notifications: the push says what caused it — listed, marked read, or
#: the sign-in that was cleared — and the answer ends it.
NOTIFICATIONS = Rule(
    ends_with=lambda c: c.has_result,
    yields=("notifications_changed",),
)

#: A folder's trust: the push carries the path, which the answer gives;
#: the push comes before the answer, so it waits for it.
WORKSPACE_TRUST = Rule(
    needs_result=True,
    ends_with=lambda c: c.has_result,
    yields=("workspace_trust_required",),
)

#: A window's model: the push carries the writer's own token, which the
#: call gives (igni-client makes one when the caller does not).
WINDOW_MODEL = Rule(
    ends_with=lambda c: c.has_result,
    yields=("window_model_changed",),
)

#: A shell command: a command that finishes inside the wait pushes
#: nothing, and the answer is its output. A command that outlives the
#: wait moves to the background: the answer names the pid, and the
#: process's pushes carry it — the last of them, `background_process_done`,
#: ends the call.
RUN_SHELL = Rule(
    needs_result=True,
    last=lambda c, e: channel(e, "background_process_done"),
    ends_with=lambda c: c.has_result and result(c, "backgrounded") is not True,
    yields=("process_started", "process_line", "process_exited", "background_process_done"),
)


#: The rule of every followed method, by wire name.
RULES: dict[str, Rule] = {
    "approve_plan": PLAN,
    "dismiss_plan": PLAN,
    "run_workflow": RUN_WORKFLOW,
    "cancel_workflow": CANCEL_WORKFLOW,
    "stop_background_process": STOP_PROCESS,
    "dispatch_visualization_action": VISUALIZATION,
    "start_scheduler": SCHEDULER,
    "login": LOGIN,
    "attach_session": ATTACH_SESSION,
    "cancel_run": CANCEL_RUN,
    "execute_scheduled_task": SCHEDULED_TASK,
    "notifications_list": NOTIFICATIONS,
    "notifications_mark_read": NOTIFICATIONS,
    "clear_cloud_credentials": NOTIFICATIONS,
    "set_workspace_trust": WORKSPACE_TRUST,
    "window_model": WINDOW_MODEL,
    "run_shell": RUN_SHELL,
}

__all__ = [
    "RULES",
    "Context",
    "Correlation",
    "Rule",
    "call_place",
    "causes_of",
    "channel",
    "correlated",
    "correlation_of",
    "payload",
    "place",
]

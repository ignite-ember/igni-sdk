"""The helpers a followed call is told its events by, one at a time.

`test_following.py` plays whole streams through the client; these hold
the small pieces of `igni_client.follow` to what they say — where a
value is read from a message and from a call, when a message is the
call's, and what ends it — including the edges a stream does not reach.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

import igni_client.frames as frames
from igni_client import NotAllowed, Unavailable
from igni_client.events import parse_event
from igni_client.follow import (
    ATTACH_SESSION,
    CANCEL_RUN,
    CANCEL_WORKFLOW,
    PLAN,
    RULES,
    RUN_SHELL,
    SCHEDULED_TASK,
    STOP_PROCESS,
    VISUALIZATION,
    WORKFLOW_ENDS,
    Context,
    Correlation,
    call_place,
    causes_of,
    channel,
    correlated,
    correlation_of,
    payload,
    place,
)
from igni_client.lifecycle import Lifecycle, Link, Phase
from igni_client.wire import Event, Frame


class _Args(BaseModel):
    run_id: str | None = None
    pid: int | None = None
    action: str | None = None
    params: dict[str, Any] | None = None


def _push(channel_name: str, data: Any, session_id: str = "s-1") -> Event:
    return parse_event(
        {
            "type": "push_notification",
            "channel": channel_name,
            "payload": data,
            "session_id": session_id,
        }
    )


def _context(**args: Any) -> Context:
    return Context(args=_Args(**args), session_id="s-1", request_id="rpc-1")


class _StubSocket:
    """Stands in for a socket where only its identity matters."""


def _link() -> Link:
    return Link(_StubSocket())  # type: ignore[arg-type]


# ── what a message carries ──


def test_a_payload_field_is_read_from_a_typed_or_an_untyped_push() -> None:
    typed = _push("plan_decided", {"run_id": "r-1", "decision": "approved"})
    untyped = _push("no_such_channel", {"run_id": "r-2"})

    assert payload(typed, "run_id") == "r-1"
    assert payload(untyped, "run_id") == "r-2"
    assert type(untyped).__name__ == "PushNotification", "an unknown channel is a plain push"
    assert place(untyped, "payload.run_id") == "r-2"


def test_a_message_without_a_payload_or_with_a_plain_one_has_no_payload_field() -> None:
    assert payload(parse_event({"type": "info", "id": "x"}), "run_id") is None
    assert payload(_push("no_such_channel", "text"), "run_id") is None
    assert place(_push("no_such_channel", {"a": 1}), "payload.missing") is None


def test_the_places_of_a_message_are_its_own_fields() -> None:
    push = _push("scheduler_started", {}, session_id="s-9")
    answer = parse_event({"type": "info", "id": "rpc-4", "session_id": "s-2"})

    assert place(push, "channel") == "scheduler_started"
    assert place(push, "session_id") == "s-9"
    assert place(answer, "id") == "rpc-4"
    assert place(answer, "channel") is None
    assert place(answer, "nowhere") is None


def test_channel_is_true_only_for_a_push_on_a_named_channel() -> None:
    push = _push("plan_decided", {"run_id": "r"})

    assert channel(push, "plan_decided", "other")
    assert not channel(push, "other")
    assert not channel(parse_event({"type": "info", "id": "x"}), "plan_decided")


# ── what the call holds ──


def test_the_places_of_a_call_are_its_request_session_arguments_and_result() -> None:
    context = Context(
        args=_Args(pid=7),
        session_id="s-1",
        request_id="rpc-1",
        result=_Args(pid=8),
        has_result=True,
    )

    assert call_place(context, "request.id") == "rpc-1"
    assert call_place(context, "request.session_id") == "s-1"
    assert call_place(context, "args.pid") == 7
    assert call_place(context, "result.pid") == 8
    assert call_place(context, "somewhere.else") is None


def test_a_result_place_is_the_argument_of_that_name_until_the_answer_comes() -> None:
    waiting = Context(args=_Args(pid=7), session_id="s-1")
    answered = Context(args=_Args(pid=7), session_id="s-1", result=_Args(), has_result=True)

    assert call_place(waiting, "result.pid") == 7
    assert call_place(answered, "result.pid") is None, "the answer's own value, even when empty"


# ── whether a message is the call's ──


def test_a_fixed_value_wins_over_a_place_in_the_call() -> None:
    event = _push("notifications_changed", {"cause": "listed"})
    context = _context(action="signed_out")

    assert correlated(Correlation(by="payload.cause", equals="listed"), context, event)
    assert not correlated(Correlation(by="payload.cause", equals="marked_read"), context, event)
    both = Correlation(by="payload.cause", source="args.action", equals="listed")
    assert correlated(both, context, event), "equals is used, the source is not looked at"


def test_a_value_the_call_does_not_hold_yet_matches_nothing() -> None:
    event = _push("process_line", {"pid": None})

    assert not correlated(Correlation(by="payload.pid", source="args.pid"), _context(), event)
    assert correlated(
        Correlation(by="payload.pid", source="args.pid"),
        _context(pid=3),
        _push("process_line", {"pid": 3}),
    )
    assert not correlated(
        Correlation(by="payload.pid", source="args.pid"),
        _context(pid=3),
        _push("process_line", {"pid": 4}),
    )


def test_a_correlation_naming_no_value_leaves_it_to_what_the_call_causes() -> None:
    assert correlated(Correlation(by="channel"), _context(), _push("anything", {}))


def test_a_method_the_contract_does_not_know_has_no_correlation_and_causes_nothing() -> None:
    assert correlation_of("no_such_method") is None
    assert causes_of("no_such_method") == ()
    assert correlation_of("approve_plan") == Correlation(by="payload.run_id", source="args.run_id")
    assert "push_notification:plan_decided" in causes_of("approve_plan")


def test_an_answer_is_never_one_of_a_calls_events() -> None:
    answer = parse_event({"type": "rpc_response", "id": "rpc-1", "result": {}})

    assert not ATTACH_SESSION.is_ours(_context(), answer, "attach_session")
    assert not SCHEDULED_TASK.is_ours(_context(), answer, "no_such_method"), "whatever it matches"
    assert SCHEDULED_TASK.is_ours(_context(), _push("file_edited", {}), "no_such_method")


def test_a_message_the_call_does_not_cause_is_not_its_own_even_when_it_correlates() -> None:
    context = _context(run_id="r-1")
    decided = _push("plan_decided", {"run_id": "r-1"})
    other_channel = _push("process_line", {"run_id": "r-1"})

    assert PLAN.is_ours(context, decided, "approve_plan")
    assert not PLAN.is_ours(context, other_channel, "approve_plan")


def test_a_message_type_the_call_causes_is_told_by_its_type() -> None:
    # cancel_run causes `info` and `stream_end` of its own session, not `content_delta`.
    context = _context()
    assert CANCEL_RUN.is_ours(
        context, parse_event({"type": "info", "session_id": "s-1"}), "cancel_run"
    )
    assert not CANCEL_RUN.is_ours(
        context, parse_event({"type": "info", "session_id": "s-2"}), "cancel_run"
    )
    assert not CANCEL_RUN.is_ours(
        context, parse_event({"type": "content_delta", "session_id": "s-1"}), "cancel_run"
    )


def test_a_rule_without_a_known_method_applies_only_its_own_match() -> None:
    context = _context(run_id="r-1")

    assert PLAN.is_ours(context, _push("plan_decided", {"run_id": "r-1"}), "no_such_method")
    assert not PLAN.is_ours(context, _push("plan_decided", {"run_id": "r-2"}), "no_such_method")


def test_a_visualization_with_no_params_equals_one_with_empty_params() -> None:
    context = _context(action="zoom", params=None)
    event = _push("visualization_action_dispatched", {"action": "zoom", "params": {}})
    other = _push("visualization_action_dispatched", {"action": "zoom", "params": {"k": 1}})

    assert VISUALIZATION.match(context, event)
    assert not VISUALIZATION.match(context, other)
    assert not VISUALIZATION.match(
        Context(args=_Args(action="zoom"), session_id=""),
        _push("visualization_action_dispatched", {"action": "zoom"}, session_id=""),
    ), "a call with no session matches no session"


# ── when there is no more ──


def test_a_workflow_ends_on_its_completion_or_its_failure_and_on_nothing_else() -> None:
    context = _context()
    context.args = _Args()
    ended = Context(
        args=type("A", (BaseModel,), {"__annotations__": {"workflow_run_id": str}})(
            workflow_run_id="w-1"
        ),
        session_id="s-1",
    )

    def event(kind: str, run: str = "w-1") -> Event:
        return _push(
            "workflow_event",
            {"workflow_run_id": run, "type": kind, "name": "n", "ts": 1, "seq": 1, "payload": {}},
        )

    assert WORKFLOW_ENDS == ("workflow_completed", "workflow_failed")
    assert CANCEL_WORKFLOW.last(ended, event("workflow_completed"))
    assert CANCEL_WORKFLOW.last(ended, event("workflow_failed"))
    assert not CANCEL_WORKFLOW.last(ended, event("step"))
    assert not CANCEL_WORKFLOW.last(ended, event("workflow_failed", run="w-2"))


class _Answer(BaseModel):
    ok: bool | None = None
    cancelled: bool | None = None
    killed: bool | None = None
    backgrounded: bool | None = None


@pytest.mark.parametrize(
    ("rule", "field"),
    [
        (PLAN, "ok"),
        (CANCEL_WORKFLOW, "cancelled"),
        (CANCEL_RUN, "cancelled"),
        (STOP_PROCESS, "killed"),
    ],
)
def test_an_answer_ends_the_call_only_when_it_says_false_not_when_it_says_nothing(
    rule: Any, field: str
) -> None:
    def answered(value: bool | None) -> Context:
        return Context(
            args=_Args(), session_id="s-1", result=_Answer(**{field: value}), has_result=True
        )

    assert rule.ends_with(answered(False))
    assert not rule.ends_with(answered(None))
    assert not rule.ends_with(answered(True))


def test_a_shell_command_ends_with_its_answer_unless_it_went_to_the_background() -> None:
    def answered(backgrounded: bool | None) -> Context:
        return Context(
            args=_Args(),
            session_id="s-1",
            result=_Answer(backgrounded=backgrounded),
            has_result=True,
        )

    assert RUN_SHELL.ends_with(answered(None))
    assert RUN_SHELL.ends_with(answered(False))
    assert not RUN_SHELL.ends_with(answered(True))
    assert not RUN_SHELL.ends_with(_context()), "no answer yet"
    assert RUN_SHELL.last(_context(), _push("background_process_done", {"pid": 1}))
    assert not RUN_SHELL.last(_context(), _push("process_line", {"pid": 1}))


def test_the_calls_that_end_with_their_answer_wait_for_it() -> None:
    assert not SCHEDULED_TASK.ends_with(_context())
    assert SCHEDULED_TASK.ends_with(Context(args=_Args(), session_id="s-1", has_result=True))


def test_an_attach_ends_when_its_stream_does() -> None:
    context = _context()

    assert not ATTACH_SESSION.ends_with(context)
    context.ended = True
    assert ATTACH_SESSION.ends_with(context)
    assert ATTACH_SESSION.last(context, parse_event({"type": "stream_end", "id": "rpc-1"}))
    assert not ATTACH_SESSION.last(context, parse_event({"type": "info", "id": "rpc-1"}))
    assert set(RULES) >= {"attach_session"}


# ── frames ──


def test_every_frame_the_module_names_is_a_frame_that_can_be_imported_from_it() -> None:
    assert frames.__all__ == sorted(frames.__all__)
    for name in frames.__all__:
        assert hasattr(frames, name), name
        # a message that goes both ways, `Typing`, is an event that is also sent
        assert issubclass(getattr(frames, name), (Frame, Event)), name
    assert issubclass(frames.RpcRequest, Frame)
    assert frames.Frame is Frame


# ── the connection's lifecycle ──


async def test_closing_gives_back_the_latest_link_or_none() -> None:
    assert Lifecycle().close() is None

    lifecycle = Lifecycle()
    first, second = _link(), _link()
    lifecycle.opening(first)
    lifecycle.opening(second)
    assert lifecycle.close() is second
    assert lifecycle.phase is Phase.CLOSED


async def test_a_loss_is_nothing_when_the_connection_is_not_open_or_opening() -> None:
    lifecycle = Lifecycle()
    link = _link()

    assert not lifecycle.lost(link), "down, no link"
    lifecycle.opening(link)
    lifecycle.failed(NotAllowed("no"))
    assert not lifecycle.lost(link), "failed for good"
    assert lifecycle.phase is Phase.FAILED
    lifecycle.opening(link)
    assert lifecycle.lost(link)
    assert not lifecycle.lost(link), "already down"
    assert lifecycle.phase.value == Phase.DOWN.value


async def test_an_older_link_is_not_lost_while_a_newer_one_is_open() -> None:
    lifecycle = Lifecycle()
    older, newer = _link(), _link()
    lifecycle.opening(older)
    lifecycle.opening(newer)
    lifecycle.opened()

    assert not lifecycle.lost(older)
    assert lifecycle.phase is Phase.OPEN


async def test_a_welcome_already_delivered_is_not_pending() -> None:
    lifecycle = Lifecycle()
    assert lifecycle.pending_welcome() is None, "no link"
    link = _link()
    lifecycle.opening(link)
    link.welcomed.set_result(parse_event({"type": "welcome", "client_id": "ws-1"}))  # type: ignore[arg-type]

    assert lifecycle.pending_welcome() is None


async def test_a_sender_waiting_is_told_why_when_the_connection_fails_for_good() -> None:
    lifecycle = Lifecycle()
    lifecycle.opening(_link())
    sending = asyncio.ensure_future(lifecycle.socket(0.2, "igni"))
    await asyncio.sleep(0.01)
    lifecycle.failed(NotAllowed("not an active producer"))

    with pytest.raises(NotAllowed, match="not an active producer"):
        await sending


async def test_a_sender_woken_by_an_open_that_is_lost_before_it_runs_is_not_given_the_socket() -> (
    None
):
    lifecycle = Lifecycle()
    link = _link()
    lifecycle.opening(link)
    sending = asyncio.ensure_future(lifecycle.socket(5.0, "igni"))
    await asyncio.sleep(0.01)
    lifecycle.opened()
    lifecycle.close()  # before the waiter runs again

    with pytest.raises(Unavailable, match="igni is not connected"):
        await sending


async def test_a_timeout_of_nothing_or_less_is_unavailable_at_once() -> None:
    for timeout in (0, -1):
        with pytest.raises(Unavailable, match="the shell is not connected"):
            await Lifecycle().socket(timeout, "the shell")


async def test_every_sender_waiting_is_given_the_socket_once_it_opens() -> None:
    lifecycle = Lifecycle()
    link = _link()
    lifecycle.opening(link)
    senders = [asyncio.ensure_future(lifecycle.socket(5.0, "igni")) for _ in range(3)]
    await asyncio.sleep(0.01)
    lifecycle.opened()

    assert [await s for s in senders] == [link.socket] * 3

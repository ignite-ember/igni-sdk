"""A call that streams yields its own events, and no other call's.

igni broadcasts every push to every client, carrying no request id. A
`Call` picks out the ones its call caused by what they carry
(`igni_client.follow`); each test here plays a stream with another call's
events mixed in, and checks that only this call's come out, in order, and
that the stream ends where igni has no more to send.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from igni_client import (
    ApprovalRequested,
    IgniClient,
    MethodFailed,
    RunInterrupted,
    Session,
)
from igni_client.events import Unknown, parse_event
from igni_client.follow import PUSH_PREFIX, RULES, causes_of
from igni_client.models import (
    AttachSessionResult,
    BackgroundProcessDonePush,
    FileEditedPush,
    InfoMessage,
    LoginResultPush,
    LoginStarted,
    LoginStatusPush,
    NotificationCounts,
    NotificationsChangedPush,
    NotificationsListResult,
    NotificationsReadResult,
    PlanDecidedPush,
    PlanDecisionResult,
    ProcessExitedPush,
    ProcessLinePush,
    ProcessStartedPush,
    PushNotification,
    RunPaused,
    RunShellResult,
    ScheduledTaskRunResult,
    StatusUpdate,
    StopProcessResult,
    StreamEnd,
    VisualizationActionResult,
    WindowModelChangedPush,
    WorkflowCancelResponse,
    WorkflowEventPush,
    WorkflowRunResponse,
    WorkspaceTrustRequiredPush,
    WorkspaceTrustStatus,
    Written,
)
from igni_client.testing import FakeIgni, Steps, sample
from igni_client.wire import Event


def _workflow(run_id: str, kind: str, seq: int) -> dict[str, Any]:
    return {
        "workflow_run_id": run_id,
        "name": "nightly",
        "ts": seq,
        "seq": seq,
        "type": kind,
        "payload": {},
    }


async def _follow(call: Any) -> tuple[list[Any], Any]:
    async with call as following:
        events = [event async for event in following]
        return events, await following.result()


async def _drain(stream: Any) -> None:
    """Run a run to its end, answering nothing."""
    async for _ in stream:
        pass


def _later(fake: FakeIgni, *pushes: tuple[str, dict[str, Any], str]) -> asyncio.Task[None]:
    async def push() -> None:
        await asyncio.sleep(0.05)
        for channel, payload, session_id in pushes:
            await fake.socket.push(channel, payload, session_id=session_id)

    return asyncio.ensure_future(push())


Answer = Callable[[dict[str, Any]], Awaitable[Any]]


def _answer(fake: FakeIgni, before: list[tuple[str, dict[str, Any], str]], result: Any) -> Answer:
    """An answer that pushes `before` first, as igni pushes while it handles a call."""

    async def answer(args: dict[str, Any]) -> Any:
        for channel, payload, session_id in before:
            await fake.socket.push(channel, payload, session_id=session_id)
        return result

    return answer


async def test_a_workflow_run_yields_its_own_events_from_before_its_answer_to_its_end() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["run_workflow"] = _answer(
            fake,
            [
                ("workflow_event", _workflow("wf-other", "step", 1), session.id),
                ("workflow_event", _workflow("wf-1", "started", 1), session.id),
            ],
            WorkflowRunResponse(workflow_run_id="wf-1", name="nightly"),
        )
        _later(
            fake,
            ("workflow_event", _workflow("wf-other", "workflow_completed", 2), session.id),
            ("workflow_event", _workflow("wf-1", "step", 2), session.id),
            ("workflow_event", _workflow("wf-1", "workflow_completed", 3), session.id),
            ("workflow_event", _workflow("wf-1", "late", 4), session.id),
        )
        events, result = await _follow(session.workflows.run("nightly"))

    assert result == WorkflowRunResponse(workflow_run_id="wf-1", name="nightly")
    assert all(isinstance(e, WorkflowEventPush) for e in events), "typed by its channel"
    assert [(e.payload.workflow_run_id, e.payload.type) for e in events] == [
        ("wf-1", "started"),
        ("wf-1", "step"),
        ("wf-1", "workflow_completed"),
    ]


async def test_a_workflow_cancelled_ends_with_its_last_event_or_with_an_answer_that_says_none() -> (
    None
):
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["cancel_workflow"] = _answer(
            fake,
            [
                ("workflow_event", _workflow("wf-2", "step", 5), session.id),
                ("workflow_event", _workflow("wf-1", "workflow_failed", 6), session.id),
            ],
            WorkflowCancelResponse(cancelled=True, workflow_run_id="wf-1"),
        )
        cancelled, _ = await _follow(session.workflows.cancel("wf-1"))

        fake.methods.answers["cancel_workflow"] = WorkflowCancelResponse(
            cancelled=False, workflow_run_id="wf-9"
        )
        nothing, answer = await asyncio.wait_for(_follow(session.workflows.cancel("wf-9")), 5)

    assert [e.payload.type for e in cancelled] == ["workflow_failed"]
    assert nothing == [] and answer.cancelled is False


async def test_stopping_a_process_yields_its_lines_and_ends_when_it_is_done() -> None:
    def line(pid: int, text: str) -> tuple[str, dict[str, Any], str]:
        return ("process_line", {"pid": pid, "line": text}, "")

    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["stop_background_process"] = StopProcessResult(
            pid=7, killed=True, message=""
        )
        _later(
            fake,
            line(8, "someone else's"),
            line(7, "stopping"),
            (
                "process_exited",
                {"pid": 7, "cmd": "sleep", "exit_code": -15, "duration_seconds": 1.0},
                "",
            ),
            (
                "background_process_done",
                {"pid": 8, "cmd": "x", "exit_code": 0, "duration_seconds": 1.0},
                "",
            ),
            (
                "background_process_done",
                {"pid": 7, "cmd": "sleep", "exit_code": -15, "duration_seconds": 1.0},
                "",
            ),
        )
        events, result = await _follow(igni.processes.stop(7))

        fake.methods.answers["stop_background_process"] = StopProcessResult(
            pid=9, killed=False, message="not tracked"
        )
        none, refused = await asyncio.wait_for(_follow(igni.processes.stop(9)), 5)

    assert result.killed
    assert [e.channel for e in events] == [
        "process_line",
        "process_exited",
        "background_process_done",
    ]
    assert isinstance(events[0], ProcessLinePush) and events[0].payload.line == "stopping"
    assert none == [] and refused.message == "not tracked"


@pytest.mark.parametrize("method", ["approve", "dismiss"])
async def test_a_plan_decision_yields_its_own_plan_decided(method: str) -> None:
    decision = "approved" if method == "approve" else "dismissed"
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        result = sample(PlanDecisionResult).model_copy(update={"run_id": "r-1", "ok": True})
        fake.methods.answers[f"{method}_plan"] = result
        _later(
            fake,
            ("plan_decided", {"run_id": "r-other", "decision": decision}, session.id),
            ("plan_decided", {"run_id": "r-1", "decision": decision}, session.id),
        )
        events, answer = await _follow(getattr(session.plan, method)("r-1"))

        fake.methods.answers[f"{method}_plan"] = result.model_copy(update={"ok": False})
        none, refused = await asyncio.wait_for(_follow(getattr(session.plan, method)("")), 5)

    assert answer.ok
    assert [type(e) for e in events] == [PlanDecidedPush]
    assert events[0].payload.run_id == "r-1" and events[0].payload.decision == decision
    assert none == [] and refused.ok is False


async def test_a_visualization_action_yields_its_own_dispatch_in_its_session() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        other = await igni.sessions.create()
        dispatched = {"action": "refresh", "params": {"page": 2}}
        fake.methods.answers["dispatch_visualization_action"] = _answer(
            fake,
            [
                ("visualization_action_dispatched", dispatched, other.id),
                (
                    "visualization_action_dispatched",
                    {"action": "refresh", "params": {}},
                    session.id,
                ),
                ("visualization_action_dispatched", dispatched, session.id),
            ],
            VisualizationActionResult(ok=True, action="refresh", params={"page": 2}),
        )
        events, result = await _follow(
            session.visualization_action(action="refresh", params={"page": 2})
        )

    assert result.ok
    assert [(e.session_id, e.payload.params) for e in events] == [(session.id, {"page": 2})]


async def test_a_scheduler_yields_its_session_s_tasks_until_the_block_is_left() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        other = await igni.sessions.create()
        fake.methods.answers["start_scheduler"] = None
        started = {"task_id": "t-1", "description": "nightly review"}
        _later(
            fake,
            ("scheduler_started", {"task_id": "t-9", "description": "theirs"}, other.id),
            ("scheduler_started", started, session.id),
            ("process_line", {"pid": 1, "line": "a tool's"}, session.id),
            ("scheduler_completed", {**started, "result": "done"}, session.id),
        )
        seen: list[Any] = []
        async with session.scheduler.start() as scheduler:
            await scheduler.result()
            async for event in scheduler:
                seen.append(event)
                if event.channel == "scheduler_completed":
                    break

    assert [(e.channel, e.payload.task_id) for e in seen] == [
        ("scheduler_started", "t-1"),
        ("scheduler_completed", "t-1"),
    ]


async def test_signing_in_yields_its_status_until_its_result() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["login"] = LoginStarted(started=True, flow_id="flow-1")
        _later(
            fake,
            ("login_status", {"flow_id": "flow-1", "text": "Opening your browser"}, ""),
            ("login_status", {"flow_id": "flow-other", "text": "another sign-in"}, ""),
            ("login_result", {"flow_id": "flow-1", "success": True, "result": "ada@acme.dev"}, ""),
            ("notifications_changed", {"counts": {"unread": 0, "by_source": {}}}, ""),
        )
        events, started = await _follow(igni.auth.login())

    assert started.started and started.flow_id == "flow-1"
    assert [type(e) for e in events] == [LoginStatusPush, LoginResultPush]
    assert events[0].payload.text == "Opening your browser"
    assert events[-1].payload.result == "ada@acme.dev"


async def test_attaching_a_session_yields_the_approvals_it_shows_again() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        request_id = ""

        async def answer(args: dict[str, Any]) -> Any:
            nonlocal request_id
            request_id = fake.methods.calls[-1].id
            await fake.socket.broadcast(
                RunPaused(id=request_id, session_id=session.id, run_id="r-1", requirements=[])
            )
            await fake.socket.broadcast(
                RunPaused(
                    id="another-request", session_id=session.id, run_id="r-1", requirements=[]
                )
            )
            await fake.socket.broadcast(StreamEnd(id=request_id, session_id=session.id))
            return AttachSessionResult(session_id=session.id, project_dir="/workspace")

        fake.methods.answers["attach_session"] = answer
        events, attached = await _follow(igni.sessions.attach(session_id=session.id))

    assert attached.session_id == session.id
    assert [type(e) for e in events] == [RunPaused, StreamEnd]
    assert events[0].id == request_id


async def test_stopping_a_turn_yields_its_info_and_its_end() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.runs.script = lambda text: [Steps.approval("deploy")]
        await _drain(session.send("a long turn"))
        events, cancelled = await _follow(session.cancel())

    assert cancelled.cancelled is True
    assert [type(e) for e in events] == [InfoMessage, StreamEnd]


async def test_stopping_a_turn_that_is_not_running_ends_with_the_answer() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        events, cancelled = await asyncio.wait_for(_follow(session.cancel()), 5)

    assert events == []
    assert cancelled.cancelled is False


async def test_a_scheduled_task_yields_the_pushes_of_the_run_it_starts() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        sent = ""

        async def answer(args: dict[str, Any]) -> Any:
            nonlocal sent
            sent = args["run_id"]
            await fake.socket.broadcast(
                PushNotification(
                    channel="file_edited",
                    payload={"path": "/workspace/a.py"},
                    run_id=sent,
                    session_id=session.id,
                )
            )
            await fake.socket.broadcast(
                PushNotification(
                    channel="file_edited",
                    payload={"path": "/workspace/other.py"},
                    run_id="another-run",
                    session_id=session.id,
                )
            )
            return ScheduledTaskRunResult(result="done", run_id=sent)

        fake.methods.answers["execute_scheduled_task"] = answer
        events, result = await _follow(session.scheduler.execute("review the payments"))

    assert sent.startswith("run-"), "igni-client makes the run's id"
    assert result.run_id == sent
    assert [type(e) for e in events] == [FileEditedPush]
    assert [e.payload.path for e in events] == ["/workspace/a.py"]


async def test_listing_notifications_yields_the_push_that_says_the_list_was_read() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["notifications_list"] = _answer(
            fake,
            [
                ("notifications_changed", {"cause": "server", "counts": {"unread": 3}}, ""),
                ("notifications_changed", {"cause": "listed", "counts": {"unread": 0}}, ""),
            ],
            NotificationsListResult(counts=NotificationCounts(unread=0)),
        )
        events, listed = await _follow(igni.notifications.list())

    assert [type(e) for e in events] == [NotificationsChangedPush]
    assert [e.payload.cause for e in events] == ["listed"]
    assert listed.counts.unread == 0


async def test_marking_notifications_read_yields_the_push_that_says_so() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["notifications_mark_read"] = _answer(
            fake,
            [
                ("notifications_changed", {"cause": "listed", "counts": {"unread": 1}}, ""),
                ("notifications_changed", {"cause": "marked_read", "counts": {"unread": 0}}, ""),
            ],
            NotificationsReadResult(counts=NotificationCounts(unread=0)),
        )
        events, read = await _follow(igni.notifications.mark_read(ids=["n-1"]))

    assert [e.payload.cause for e in events] == ["marked_read"]
    assert read.counts.unread == 0


async def test_signing_out_yields_the_push_that_says_the_person_signed_out() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["clear_cloud_credentials"] = _answer(
            fake,
            [
                ("notifications_changed", {"cause": "server", "counts": {"unread": 1}}, session.id),
                (
                    "notifications_changed",
                    {"cause": "signed_out", "counts": {"unread": 0}},
                    session.id,
                ),
            ],
            StatusUpdate(session_id=session.id),
        )
        events, status = await _follow(session.auth.sign_out())

    assert [e.payload.cause for e in events] == ["signed_out"]
    assert isinstance(status, StatusUpdate)


async def test_trusting_a_folder_yields_the_push_that_tells_the_windows() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        status = WorkspaceTrustStatus(
            can_trust=True,
            path="/workspace",
            policy_mode="ask",
            reason="trusted for now",
            state="trusted",
        )
        fake.methods.answers["set_workspace_trust"] = _answer(
            fake,
            [
                (
                    "workspace_trust_required",
                    status.model_dump(mode="json"),
                    session.id,
                )
            ],
            status,
        )
        events, trusted = await _follow(session.workspace.set_trust("trust"))

    assert [type(e) for e in events] == [WorkspaceTrustRequiredPush]
    assert events[0].payload.path == "/workspace"
    assert trusted.state == "trusted"


async def test_a_window_model_write_yields_the_push_that_carries_it() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        token = ""

        async def answer(args: dict[str, Any]) -> Any:
            nonlocal token
            token = args["token"]
            await fake.socket.broadcast(
                PushNotification(
                    channel="window_model_changed",
                    payload={
                        "field": "composer",
                        "rev": 2,
                        "token": token,
                        "value": {"text": "hi"},
                        "window": "w-1",
                    },
                )
            )
            await fake.socket.broadcast(
                PushNotification(
                    channel="window_model_changed",
                    payload={
                        "field": "composer",
                        "rev": 3,
                        "token": "another-writer's-token",
                        "value": {"text": "hi"},
                        "window": "w-2",
                    },
                )
            )
            return Written(op="write", rev=2)

        fake.methods.answers["window_model"] = answer
        events, written = await _follow(
            igni.window.model(op="write", window="w-1", field="composer", value={"text": "hi"})
        )

    assert token.startswith("change-"), "igni-client makes the token"
    assert written.rev == 2
    assert [type(e) for e in events] == [WindowModelChangedPush]
    assert [e.payload.window for e in events] == ["w-1"]


async def test_a_shell_command_that_goes_on_yields_its_process_pushes() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["run_shell"] = RunShellResult(
            output="", exit_code=0, backgrounded=True, pid=42
        )
        _later(
            fake,
            ("process_started", {"cmd": "sleep 60", "pid": 42, "started_at": 1.0}, session.id),
            ("process_line", {"line": "still going", "pid": 42}, session.id),
            ("process_started", {"cmd": "other", "pid": 43, "started_at": 1.0}, session.id),
            (
                "process_exited",
                {"cmd": "sleep 60", "duration_seconds": 1.0, "exit_code": 0, "pid": 42},
                session.id,
            ),
            (
                "background_process_done",
                {"cmd": "sleep 60", "duration_seconds": 1.0, "exit_code": 0, "pid": 42},
                session.id,
            ),
        )
        events, result = await _follow(session.run_shell("sleep 60"))

    assert result.backgrounded is True and result.pid == 42
    assert [type(e) for e in events] == [
        ProcessStartedPush,
        ProcessLinePush,
        ProcessExitedPush,
        BackgroundProcessDonePush,
    ]
    assert [e.payload.pid for e in events] == [42, 42, 42, 42]


async def test_a_shell_command_that_finishes_ends_with_its_answer() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["run_shell"] = RunShellResult(
            output="done", exit_code=0, backgrounded=False, pid=42
        )
        events, result = await asyncio.wait_for(_follow(session.run_shell("true")), 5)

    assert events == []
    assert result.output == "done" and result.backgrounded is False


def test_every_rule_yields_only_what_the_contract_says_its_call_causes() -> None:
    for wire, rule in RULES.items():
        causes = {cause.removeprefix(PUSH_PREFIX) for cause in causes_of(wire)}
        assert set(rule.yields) <= causes, wire


async def test_a_call_igni_refuses_raises_from_its_stream() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        with pytest.raises(MethodFailed, match="the fake has no answer"):
            await _follow(session.workflows.run("nightly"))


async def test_a_call_followed_when_igni_moves_is_interrupted() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["run_workflow"] = WorkflowRunResponse(workflow_run_id="wf-1", name="n")

        async def move() -> None:
            await asyncio.sleep(0.05)
            await fake.socket.move()

        asyncio.ensure_future(move())
        with pytest.raises(RunInterrupted):
            await asyncio.wait_for(_follow(session.workflows.run("n")), 5)


async def test_a_call_is_awaited_on_its_own_and_followed_only_inside_async_with() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["run_workflow"] = WorkflowRunResponse(workflow_run_id="wf-1", name="n")
        call = session.workflows.run("n")
        with pytest.raises(RuntimeError, match="async with"):
            call.__aiter__()
        assert (await call).workflow_run_id == "wf-1"
        async with call:
            with pytest.raises(RuntimeError, match="already entered"):
                await call.__aenter__()
        assert repr(call) == "Call(run_workflow)"
        assert igni._conn.router._followers == [], "a call that was left listens no more"


async def test_a_session_s_events_offer_its_waiting_approvals() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        other = await igni.sessions.create()
        approval = Steps.approval("deploy").requirements

        async def pause() -> None:
            await asyncio.sleep(0.05)
            for target in (other, session):
                await fake.socket.broadcast(
                    RunPaused(session_id=target.id, run_id="r-1", requirements=approval)
                )

        asyncio.ensure_future(pause())
        offered = await asyncio.wait_for(_first_approval(session), 5)
        await offered.approve()
        await _until(lambda: len(fake.runs.decisions) == 1)

    assert offered.requirements[0].tool_name == "deploy"
    assert fake.runs.decisions[0][0].requirement_id == "req-deploy"


async def _first_approval(session: Session) -> ApprovalRequested:
    async for event in session.events():
        if isinstance(event, ApprovalRequested):
            return event
    raise AssertionError("no approval")


async def test_a_push_on_a_channel_the_contract_does_not_type_is_a_plain_push() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        events = igni.events()
        first = asyncio.ensure_future(anext(events))
        await asyncio.sleep(0.05)
        await fake.socket.push("brand_new_channel", {"anything": [1, 2]})
        seen: Event = await asyncio.wait_for(first, 5)

    assert type(seen) is PushNotification and seen.payload == {"anything": [1, 2]}


async def _until(condition: Any, timeout: float = 5.0) -> None:
    async def wait() -> None:
        while not condition():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait(), timeout)


def test_a_push_is_its_channel_s_class_and_falls_back_to_a_plain_push(
    caplog: pytest.LogCaptureFixture,
) -> None:
    typed = parse_event(
        {"type": "push_notification", "channel": "process_line", "payload": {"pid": 1, "line": "x"}}
    )
    assert isinstance(typed, ProcessLinePush) and typed.payload.pid == 1
    with caplog.at_level(logging.WARNING, logger="igni_client.events"):
        unreadable = parse_event(
            {"type": "push_notification", "channel": "process_line", "payload": {"pid": "one"}}
        )
    assert type(unreadable) is PushNotification and unreadable.payload == {"pid": "one"}
    assert any("process_line" in r.getMessage() for r in caplog.records)
    newer = parse_event({"type": "something_newer", "id": "x", "more": 1})
    assert isinstance(newer, Unknown) and newer.type == "something_newer"
    assert newer.model_extra == {"more": 1}

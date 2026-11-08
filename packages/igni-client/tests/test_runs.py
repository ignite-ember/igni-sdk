"""Sessions and runs: a prompt followed to its end, approvals answered in the loop."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from pydantic import ValidationError
from websockets.asyncio.client import connect
from websockets.typing import Subprotocol

from igni_client import (
    ApprovalRequested,
    ApprovalRequired,
    ContentDelta,
    Decision,
    IgniClient,
    InfoMessage,
    NotAllowed,
    Requirement,
    RpcError,
    RunCompleted,
    RunFailed,
    RunStarted,
    ToolCompleted,
)
from igni_client.approvals import Approver
from igni_client.events import ErrorMessage, Event, RequirementDetails, RunError, RunPaused
from igni_client.frames import HitlDecision, QueueMessage
from igni_client.methods import ATTACHED_SESSION, HISTORY, HistoryTurn
from igni_client.replies import Reply
from igni_client.testing import Delay, FakeIgni, Pause, Steps


async def test_a_prompt_streams_typed_events_to_its_end() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        events = [event async for event in session.send("hello")]

    kinds = [type(e) for e in events]
    assert RunStarted in kinds and ContentDelta in kinds and RunCompleted in kinds
    text = "".join(e.text for e in events if isinstance(e, ContentDelta))
    assert text == "echo: hello"


async def test_ask_returns_the_whole_answer_and_the_main_runs_completion() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        reply = await session.ask("hi")

    assert str(reply) == "echo: hi"
    assert reply.completed is not None and reply.completed.input_tokens == 10


async def test_another_clients_run_never_reaches_this_one() -> None:
    # igni broadcasts every message to every client; a run is followed by its request id.
    async with (
        FakeIgni() as fake,
        IgniClient(fake.local()) as mine,
        IgniClient(fake.local()) as theirs,
    ):
        fake.runs.script = lambda text: [Delay(seconds=0.05), *Steps.answer(text)]
        ours = await mine.sessions.create()
        other = await theirs.sessions.create()
        # Theirs is asked first, so igni plays it first: both are each client's second request.
        _, mine_reply = await asyncio.gather(other.ask("theirs"), ours.ask("mine"))

    assert str(mine_reply) == "mine"


async def test_an_approval_is_answered_in_the_loop_and_the_run_resumes() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [
            Steps.approval("run_shell_command", command="rm -rf build"),
            *Steps.answer("cleaned"),
        ]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            seen: list[ApprovalRequested] = []
            text = ""
            async for event in session.send("clean"):
                if isinstance(event, ApprovalRequested):
                    seen.append(event)
                    assert event.requirements[0].tool_args == {"command": "rm -rf build"}
                    await event.approve()
                elif isinstance(event, ContentDelta):
                    text += event.text

    assert len(seen) == 1 and seen[0].answered
    assert text == "cleaned"
    assert fake.runs.decisions == [
        [HitlDecision(requirement_id="req-run_shell_command", action="confirm", choice="once")]
    ]


async def test_a_refusal_resumes_the_run_with_the_call_rejected() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [Steps.approval("deploy"), *Steps.answer("deployed")]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            events = []
            async for event in session.send("deploy"):
                if isinstance(event, ApprovalRequested):
                    await event.reject(remember=True)
                events.append(event)

    assert fake.runs.decisions[0][0].action == "reject"
    assert fake.runs.decisions[0][0].choice == "deny"
    assert any(isinstance(e, ToolCompleted) and e.is_rejected for e in events)


async def test_every_call_of_a_pause_must_be_answered() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [Steps.approval("deploy")]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            async for event in session.send("deploy"):
                if isinstance(event, ApprovalRequested):
                    with pytest.raises(ValueError, match="every call needs an answer"):
                        await event.decide({})
                    break


async def test_a_loop_that_does_not_answer_ends_and_leaves_the_run_waiting() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [Steps.approval("deploy"), *Steps.answer("never")]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            events = [event async for event in session.send("deploy")]

    assert isinstance(events[-1], ApprovalRequested) and not events[-1].answered
    assert fake.runs.decisions == []


async def test_ask_without_a_policy_raises_at_an_approval() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [Steps.approval("deploy")]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            with pytest.raises(ApprovalRequired) as raised:
                await session.ask("deploy")

    assert raised.value.requirements[0].tool_name == "deploy"


async def test_ask_answers_approvals_with_an_async_policy() -> None:
    async def policy(requirement: Requirement) -> Decision:
        return Decision.allow("always") if requirement.tool_name == "read_file" else Decision.deny()

    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [
            Steps.approval("read_file", path="a.py"),
            *Steps.answer("read"),
        ]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            reply = await session.ask("read it", approve=policy)

    assert str(reply) == "read"
    assert fake.runs.decisions[0][0].choice == "always"


async def test_a_failed_run_raises() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [RunError(error="model unreachable")]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            with pytest.raises(RunFailed, match="model unreachable"):
                await session.ask("hi")


async def test_cancel_ends_the_run() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [Delay(seconds=30), *Steps.answer("too late")]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            follow = asyncio.ensure_future(_collect(session.send("long")))
            await _until(lambda: _sent(fake, "user_message") == 1)
            await session.cancel()
            followed = await asyncio.wait_for(follow, 5)

    assert any(isinstance(e, InfoMessage) and "cancelled" in e.text for e in followed)


async def test_queue_sends_a_prompt_for_later() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        await session.queue("and then the tests")
        await _until(lambda: _sent(fake, "queue_message") == 1)

    frame = next(r.frame for r in fake.socket.received if isinstance(r.frame, QueueMessage))
    assert frame.text == "and then the tests" and frame.session_id == session.id


async def test_sessions_are_created_opened_listed_and_switched() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        created = await igni.sessions.create(project_dir="/workspace/payments")
        opened = await igni.sessions.open(created.id)
        listed = await igni.sessions.list()
        default = await igni.sessions.default()
        notice = await created.use_model("igni-1")
        status = await created.status()
        catalogue = await igni.models.list()

    assert opened is created and created.project_dir == "/workspace/payments"
    assert created.id in [entry.session_id for entry in listed]
    assert default.id == "s-default"
    assert notice == "Switched to igni-1"
    assert status.model == "igni-1"
    assert catalogue.default == "igni-1" and catalogue.models["igni-1"].provider == "igni"


async def test_a_session_reads_its_history_as_turns() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.history[session.id] = [
            HistoryTurn(role="user", content="hello", created_at=1),
            HistoryTurn.model_validate({"role": "tool", "tool_name": "read_file", "content": "ok"}),
        ]
        history = await session.history()

    assert [turn.role for turn in history] == ["user", "tool"]
    assert history[0].content == "hello" and history[1].model_extra == {"tool_name": "read_file"}


async def test_an_answer_not_shaped_as_the_method_returns_raises() -> None:
    async with FakeIgni() as fake:
        fake.methods.answers["get_turns"] = {"not": "a list"}
        async with IgniClient(fake.local()) as igni:
            with pytest.raises(RpcError, match="get_turns"):
                await igni._conn.rpc("get_turns", HISTORY)


async def test_any_method_is_reachable_and_an_error_raises() -> None:
    async with FakeIgni() as fake:
        fake.methods.answers["get_todos"] = lambda args: [{"text": "write tests", "done": False}]
        async with IgniClient(fake.local()) as igni:
            todos = await igni.rpc("get_todos")
            with pytest.raises(RpcError, match="Unknown RPC method"):
                await igni.rpc("no_such_method")

    assert todos == [{"text": "write tests", "done": False}]


async def test_a_vm_not_yet_bound_is_asked_again() -> None:
    async with FakeIgni() as fake:
        fake.methods.answers["get_todos"] = []
        async with IgniClient(fake.local()) as igni:
            igni._conn.UNBOUND_RETRY_SECONDS = 0.01
            fake.methods.unbound_for(3)
            assert await igni.rpc("get_todos") == []


async def test_a_client_never_sends_what_stops_igni() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        for method in ("shutdown", "vm_sign_in", "deliver_service_events"):
            with pytest.raises(ValueError) as refused:
                await igni.rpc(method)
            assert type(refused.value) is ValueError, "a plain ValueError, as 0.1.0 raised"
            assert str(refused.value) == f"{method} is not a client's to send"

    assert not any(r.frame.type == "rpc_request" for r in fake.socket.received)


def test_an_approval_answer_reaches_only_as_far_as_igni_knows() -> None:
    assert Decision.allow("similar").frame("req-1") == HitlDecision(
        requirement_id="req-1", action="confirm", choice="similar"
    )
    assert Decision.deny(remember=True).frame("req-1").choice == "deny"
    assert Decision.deny().choice == "once"
    with pytest.raises(ValidationError, match="choice"):
        Decision(action="confirm", choice="sometimes")  # type: ignore[arg-type]


async def test_an_attach_answer_without_its_project_is_refused() -> None:
    async with FakeIgni() as fake:
        fake.methods.answers["attach_elsewhere"] = {"session_id": "s-9"}
        async with IgniClient(fake.local()) as igni:
            with pytest.raises(RpcError, match="attach_elsewhere"):
                await igni._conn.rpc("attach_elsewhere", ATTACHED_SESSION)


async def test_an_approval_is_answered_once() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [Steps.approval("deploy"), *Steps.answer("deployed")]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            async for event in session.send("deploy"):
                if isinstance(event, ApprovalRequested):
                    assert event.run_id == Steps.RUN_ID
                    assert repr(event) == "ApprovalRequested(deploy)"
                    await event.approve("similar")
                    with pytest.raises(RuntimeError, match="this approval was already answered"):
                        await event.reject()

    assert fake.runs.decisions == [
        [HitlDecision(requirement_id="req-deploy", action="confirm", choice="similar")]
    ]


async def test_the_calls_of_a_pause_are_answered_in_their_order() -> None:
    pause = Pause(
        requirements=[
            Requirement(requirement_id="req-a", tool_name="read_file"),
            Requirement(requirement_id="req-b", tool_name="write_file", friendly_name="Write"),
        ]
    )
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [pause, *Steps.answer("done")]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            async for event in session.send("both"):
                if isinstance(event, ApprovalRequested):
                    assert repr(event) == "ApprovalRequested(read_file, Write)"
                    with pytest.raises(ValueError) as refused:
                        await event.decide({"req-a": Decision.allow()})
                    assert str(refused.value) == "every call needs an answer; missing ['req-b']"
                    await event.decide(
                        {"req-b": Decision.deny(), "req-a": Decision.allow("always")}
                    )

    assert fake.runs.decisions == [
        [
            HitlDecision(requirement_id="req-a", action="confirm", choice="always"),
            HitlDecision(requirement_id="req-b", action="reject", choice="once"),
        ]
    ]


@pytest.mark.parametrize(
    ("policy", "action", "text"),
    [
        (True, "confirm", "deployed"),
        (False, "reject", "I did not run it."),
        (lambda requirement: requirement.tool_name == "deploy", "confirm", "deployed"),
        (lambda requirement: Decision.deny(remember=True), "reject", "I did not run it."),
    ],
    ids=["true", "false", "a-callable-saying-yes", "a-callable-returning-a-decision"],
)
async def test_ask_answers_approvals_with_a_plain_policy(
    policy: object, action: str, text: str
) -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda _: [Steps.approval("deploy"), *Steps.answer("deployed")]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            reply = await session.ask("deploy", approve=policy)  # type: ignore[arg-type]

    assert str(reply) == text
    assert [d.action for d in fake.runs.decisions[0]] == [action]


async def test_an_approver_on_its_own_answers_each_call_and_refuses_without_a_policy() -> None:
    sent: list[list[HitlDecision]] = []

    async def answer(decisions: list[HitlDecision]) -> None:
        sent.append(decisions)

    paused = RunPaused(
        run_id="r-9",
        requirements=[
            Requirement(requirement_id="req-a", tool_name="read_file"),
            Requirement(requirement_id="req-b", tool_name="deploy"),
        ],
    )
    await Approver(lambda r: r.tool_name == "read_file").answer(ApprovalRequested(paused, answer))
    with pytest.raises(ApprovalRequired) as raised:
        await Approver(None).answer(ApprovalRequested(paused, answer))

    assert sent == [
        [
            HitlDecision(requirement_id="req-a", action="confirm", choice="once"),
            HitlDecision(requirement_id="req-b", action="reject", choice="once"),
        ]
    ]
    assert [r.requirement_id for r in raised.value.requirements] == ["req-a", "req-b"]


async def test_a_reply_gathers_thinking_and_tools_and_keeps_the_main_runs_completion() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [
            ContentDelta(text="let me ", is_thinking=True),
            ContentDelta(text="Hello"),
            ContentDelta(text="see", is_thinking=True),
            ToolCompleted(run_id="r-sub", summary="read a.py"),
            ContentDelta(text=", world"),
            RunCompleted(run_id=Steps.RUN_ID, input_tokens=10),
            RunCompleted(run_id="r-sub", parent_run_id=Steps.RUN_ID, input_tokens=99),
        ]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            reply = await session.ask("hi")

    assert reply.text == "Hello, world" and reply.thinking == "let me see"
    assert [tool.summary for tool in reply.tools] == ["read a.py"]
    assert reply.completed is not None and reply.completed.input_tokens == 10


async def test_a_reply_collected_on_its_own_follows_any_stream_of_events() -> None:
    async def events() -> AsyncIterator[Event | ApprovalRequested]:
        yield ContentDelta(text="hi")
        yield RunCompleted(run_id="r-1", output_tokens=1)

    reply = await Reply.collect(events(), Approver(None))

    assert str(reply) == "hi" and reply.thinking == "" and reply.tools == []
    assert reply.completed is not None and reply.completed.output_tokens == 1


async def test_a_run_failing_without_a_word_raises_in_plain_words() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [RunError()]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            with pytest.raises(RunFailed) as raised:
                await session.ask("hi")

    assert str(raised.value) == "the run failed"


@pytest.mark.parametrize(
    ("text", "message"),
    [("you may not approve", "you may not approve"), ("", "igni refused the approval")],
)
async def test_igni_refusing_an_answer_raises_not_allowed(text: str, message: str) -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda _: [Steps.approval("deploy"), ErrorMessage(text=text)]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            with pytest.raises(NotAllowed) as raised:
                await session.ask("deploy", approve=True)

    assert str(raised.value) == message


async def test_the_details_of_a_waiting_call_fill_in_its_requirement() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [
            Steps.approval("deploy"),
            RequirementDetails(requirement_id="req-deploy", details="ships to prod"),
            *Steps.answer("deployed"),
        ]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            seen: list[ApprovalRequested] = []
            async for event in session.send("deploy"):
                if isinstance(event, ApprovalRequested):
                    event.requirements[0].details_pending = True
                    seen.append(event)
                    await event.approve()

    assert seen[0].requirements[0].details == "ships to prod"
    assert not seen[0].requirements[0].details_pending


def test_an_approval_frame_refuses_a_scope_igni_does_not_know() -> None:
    assert HitlDecision(requirement_id="r", action="reject", choice="deny").choice == "deny"
    with pytest.raises(ValidationError, match="choice"):
        HitlDecision(requirement_id="r", action="confirm", choice="sometimes")  # type: ignore[arg-type]


async def test_the_fake_passes_over_an_answer_with_a_scope_igni_does_not_know() -> None:
    def batch(choice: str) -> str:
        decision = {"requirement_id": "req-x", "action": "confirm", "choice": choice}
        return json.dumps(
            {
                "type": "hitl_response_batch",
                "id": choice,
                "session_id": "s",
                "decisions": [decision],
            }
        )

    async with (
        FakeIgni() as fake,
        connect(fake.socket.url, subprotocols=[Subprotocol("igni.v1")]) as ws,
    ):
        await ws.recv()  # the welcome
        await ws.send(batch("sometimes"))
        await ws.send(batch("once"))
        await _until(lambda: len(fake.runs.decisions) == 1)

    assert fake.runs.decisions == [
        [HitlDecision(requirement_id="req-x", action="confirm", choice="once")]
    ]
    assert [r.frame.type for r in fake.socket.received] == ["hitl_response_batch"]


def test_approvals_and_replies_live_in_their_own_modules() -> None:
    import igni_client
    from igni_client import approvals, replies, runs

    assert igni_client.Decision is approvals.Decision
    assert igni_client.ApprovalRequested is approvals.ApprovalRequested
    assert igni_client.Reply is replies.Reply
    assert Decision.__module__ == ApprovalRequested.__module__ == "igni_client.approvals"
    assert Reply.__module__ == "igni_client.replies"
    for moved in ("Decision", "Policy", "Choice", "Answer", "Reply", "collect"):
        assert not hasattr(runs, moved), f"igni_client.runs.{moved} moved out in 0.2"


# ── helpers ──


async def _collect(run: object) -> list[object]:
    return [event async for event in run]  # type: ignore[attr-defined]


def _sent(fake: FakeIgni, kind: str) -> int:
    return sum(1 for r in fake.socket.received if r.frame.type == kind)


async def _until(condition: object, timeout: float = 5.0) -> None:
    async def wait() -> None:
        while not condition():  # type: ignore[operator]
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait(), timeout)

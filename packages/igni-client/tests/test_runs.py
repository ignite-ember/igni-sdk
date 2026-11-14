"""Sessions and runs: a prompt followed to its end, approvals answered in the loop."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import get_args

import pytest
from pydantic import ValidationError

from igni_client import (
    AccessRefused,
    ApprovalRequested,
    ApprovalRequired,
    ContentDelta,
    Decision,
    IgniClient,
    InfoMessage,
    InvalidArguments,
    MethodFailed,
    NotAllowed,
    Requirement,
    RunCompleted,
    RunFailed,
    RunStarted,
    StatusUpdate,
    ToolCompleted,
    ToolError,
    ToolStarted,
    UnexpectedAnswer,
    UnknownMethod,
)
from igni_client.api import NOT_FOR_CLIENTS
from igni_client.approvals import Approver, Scope
from igni_client.events import ErrorMessage, Event, RequirementDetails, RunError, RunPaused
from igni_client.frames import (
    HitlDecision,
    HitlResponseBatch,
    QueueMessage,
    RpcRequest,
    UserMessage,
)
from igni_client.models import ModelSwitched, RpcResponse, ToolTurn, UserTurn
from igni_client.replies import Reply
from igni_client.testing import Delay, FakeIgni, Pause, Steps


def _refuse(error: str) -> RpcResponse:
    """An answer the fake sends as it is: igni's error, as an `rpc_response`."""
    return RpcResponse(error=error)


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
    # As igni: the refused call started nothing, so no tool event comes for it.
    resumed = events[events.index(next(e for e in events if isinstance(e, ApprovalRequested))) :]
    assert not [e for e in resumed if isinstance(e, (ToolStarted, ToolCompleted, ToolError))]
    assert isinstance(events[-1], RunCompleted)


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
        switched = await created.models.switch("igni-1")
        status = await created.status()
        registry = await created.models.list()

    assert opened is created and created.project_dir == "/workspace/payments"
    assert created.id in [entry.session_id for entry in listed]
    assert default.id == "s-default"
    assert isinstance(switched, ModelSwitched) and switched.text == "Switched to igni-1"
    assert isinstance(status, StatusUpdate) and status.model == "igni-1"
    assert registry.default == "igni-1" and registry.registry["igni-1"].provider == "igni"


async def test_switching_to_an_unknown_model_raises_the_documented_error() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        with pytest.raises(MethodFailed, match="Unknown model: nope") as failed:
            await session.models.switch("nope")

    assert failed.value.method == "switch_model"


async def test_a_session_reads_its_history_as_typed_turns() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.history[session.id] = [
            UserTurn(run_id="r-1", created_at=1, content="hello"),
            ToolTurn(
                run_id="r-1",
                created_at=2,
                tool_name="read_file",
                friendly_name="Read file",
                args="a.py",
                content="ok",
                is_error=False,
                is_rejected=False,
            ),
        ]
        history = await session.history.get()

    assert [turn.role for turn in history] == ["user", "tool"]
    user, tool = history
    assert isinstance(user, UserTurn) and user.content == "hello"
    assert isinstance(tool, ToolTurn) and tool.tool_name == "read_file"
    asked = [c for c in fake.methods.calls if c.method == "get_chat_history"]
    assert asked[0].args == {"session_id": session.id}, "a session names itself"


async def test_an_answer_not_shaped_as_the_method_returns_raises() -> None:
    async with FakeIgni() as fake:
        fake.methods.answers["get_todos"] = {"not": "a list"}
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            with pytest.raises(UnexpectedAnswer, match="get_todos"):
                await session.todos()


async def test_each_kind_of_error_igni_answers_is_its_own_type() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["get_todos"] = lambda args: _refuse("Unknown RPC method: get_todos")
        with pytest.raises(UnknownMethod):
            await session.todos()
        fake.methods.answers["get_todos"] = lambda args: _refuse(
            "get_todos: only igni's window may do this"
        )
        with pytest.raises(AccessRefused) as refused:
            await session.todos()
        assert isinstance(refused.value, NotAllowed), "a refusal is also NotAllowed"
        fake.methods.answers["get_todos"] = lambda args: _refuse("the disk is full")
        with pytest.raises(MethodFailed, match="the disk is full") as failed:
            await session.todos()
        assert failed.value.method == "get_todos" and failed.value.message == "the disk is full"


async def test_arguments_are_checked_before_they_are_sent() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        with pytest.raises(InvalidArguments, match="read_process_tail"):
            await igni.processes.tail("not a pid")  # type: ignore[arg-type]

    assert not any(
        r.frame.type == "rpc_request" and r.frame.method == "read_process_tail"  # type: ignore[union-attr]
        for r in fake.socket.received
    )


async def test_a_vm_not_yet_bound_is_asked_again() -> None:
    async with FakeIgni() as fake:
        fake.methods.answers["list_background_processes"] = []
        async with IgniClient(fake.local()) as igni:
            igni._conn.UNBOUND_RETRY_SECONDS = 0.01
            fake.methods.unbound_for(3)
            assert await igni.processes.list() == []


async def test_a_client_never_sends_a_page_s_or_the_platform_s_call() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        for method in NOT_FOR_CLIENTS:
            assert not hasattr(igni, method)
            with pytest.raises(ValueError) as refused:
                await igni._conn.ask(method)
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
        fake.methods.answers["attach_session"] = {"session_id": "s-9"}
        async with IgniClient(fake.local()) as igni:
            with pytest.raises(UnexpectedAnswer, match="attach_session"):
                await igni.sessions.create()


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
            _requirement("req-a", "read_file"),
            _requirement("req-b", "write_file").model_copy(update={"friendly_name": "Write"}),
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
            _requirement("req-a", "read_file"),
            _requirement("req-b", "deploy"),
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


def test_an_approval_s_scope_is_checked_by_the_decision_and_sent_as_igni_types_it() -> None:
    """igni's contract types `choice` as a string; `Decision` holds the values igni knows."""
    assert get_args(Scope) == ("once", "always", "similar", "deny")
    assert HitlDecision(requirement_id="r", action="reject", choice="deny").choice == "deny"
    with pytest.raises(ValidationError, match="choice"):
        Decision(action="confirm", choice="sometimes")  # type: ignore[arg-type]


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


def test_an_approval_batch_goes_to_igni_field_for_field() -> None:
    batch = HitlResponseBatch(
        id="req-9", session_id="s-1", decisions=[Decision.deny(remember=True).frame("req-a")]
    )

    assert json.loads(batch.wire()) == {
        "type": "hitl_response_batch",
        "id": "req-9",
        "session_id": "s-1",
        "decisions": [{"requirement_id": "req-a", "action": "reject", "choice": "deny"}],
    }, "each row the fields given; igni applies the rest's defaults"


async def test_an_approval_stays_open_when_its_answer_fails_to_send() -> None:
    attempts: list[list[HitlDecision]] = []

    async def answer(decisions: list[HitlDecision]) -> None:
        attempts.append(decisions)
        if len(attempts) == 1:
            raise ConnectionError("the socket closed")

    paused = RunPaused(run_id="r-9", requirements=[_requirement("req-a", "deploy")])
    request = ApprovalRequested(paused, answer)

    assert request.paused is paused and repr(request) == "ApprovalRequested(deploy)"
    with pytest.raises(ConnectionError):
        await request.approve()
    assert not request.answered
    await request.approve()
    assert request.answered and len(attempts) == 2


def test_a_decision_is_fixed_once_made() -> None:
    decision = Decision.allow()

    with pytest.raises(ValidationError):
        decision.choice = "always"


async def test_a_reply_keeps_the_last_main_completion() -> None:
    async def events() -> AsyncIterator[Event | ApprovalRequested]:
        yield RunCompleted(run_id="r-1", output_tokens=1)
        yield RunCompleted(run_id="r-1", output_tokens=2)

    reply = await Reply.collect(events(), Approver(None))

    assert reply.completed is not None and reply.completed.output_tokens == 2


async def test_a_reply_reads_no_further_than_a_failure() -> None:
    read: list[str] = []

    async def events() -> AsyncIterator[Event | ApprovalRequested]:
        read.append("error")
        yield RunError(error="the VM went away")
        read.append("after")
        yield ContentDelta(text="never read")

    with pytest.raises(RunFailed, match="the VM went away"):
        await Reply.collect(events(), Approver(None))
    assert read == ["error"]


async def test_a_reply_answers_each_approval_with_its_approver() -> None:
    sent: list[list[HitlDecision]] = []

    async def answer(decisions: list[HitlDecision]) -> None:
        sent.append(decisions)

    paused = RunPaused(run_id="r-1", requirements=[_requirement("req-a", "deploy")])

    async def events() -> AsyncIterator[Event | ApprovalRequested]:
        yield ApprovalRequested(paused, answer)
        yield ContentDelta(text="deployed")

    reply = await Reply.collect(events(), Approver(lambda r: Decision.allow("always")))

    assert str(reply) == "deployed"
    assert sent == [[HitlDecision(requirement_id="req-a", action="confirm", choice="always")]]


async def test_a_run_closed_early_stops_following_its_streams() -> None:
    async with FakeIgni() as fake:
        fake.runs.script = lambda text: [ContentDelta(text="first"), Delay(seconds=0.05)]
        async with IgniClient(fake.local()) as igni:
            session = await igni.sessions.create()
            run = session.send("hi")
            async for event in run:
                if isinstance(event, ContentDelta):
                    break
            await run.aclose()  # type: ignore[attr-defined]
            assert igni._conn.router._streams == {}, "a run closed early holds no stream open"


async def test_ask_attaches_its_files_to_the_prompt() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        await session.ask("read it", files={"a.py": "print(1)"})

    [prompt] = [r.frame for r in fake.socket.received if r.frame.type == "user_message"]
    assert prompt.file_contents == {"a.py": "print(1)"}  # type: ignore[union-attr]


async def test_a_reply_to_a_stream_with_nothing_in_it_is_empty() -> None:
    async def events() -> AsyncIterator[Event | ApprovalRequested]:
        return
        yield

    reply = await Reply.collect(events(), Approver(None))

    assert reply == Reply(text="", thinking="", tools=[], completed=None)
    assert str(reply) == ""


async def test_an_approval_given_a_scope_igni_does_not_know_sends_nothing() -> None:
    sent: list[list[HitlDecision]] = []

    async def answer(decisions: list[HitlDecision]) -> None:
        sent.append(decisions)

    request = ApprovalRequested(_paused("deploy"), answer)

    with pytest.raises(ValidationError, match="choice"):
        await request.approve("sometimes")  # type: ignore[arg-type]
    assert sent == [] and not request.answered


async def test_rejecting_for_good_refuses_every_call_of_a_pause() -> None:
    sent: list[list[HitlDecision]] = []

    async def answer(decisions: list[HitlDecision]) -> None:
        sent.append(decisions)

    await ApprovalRequested(_paused("read_file", "deploy"), answer).reject(remember=True)

    assert sent == [
        [
            HitlDecision(requirement_id="req-read_file", action="reject", choice="deny"),
            HitlDecision(requirement_id="req-deploy", action="reject", choice="deny"),
        ]
    ]


async def test_an_answer_for_a_call_igni_did_not_ask_about_is_left_out() -> None:
    sent: list[list[HitlDecision]] = []

    async def answer(decisions: list[HitlDecision]) -> None:
        sent.append(decisions)

    await ApprovalRequested(_paused("deploy"), answer).decide(
        {"req-other": Decision.allow(), "req-deploy": Decision.deny()}
    )

    assert sent == [[HitlDecision(requirement_id="req-deploy", action="reject", choice="once")]]


@pytest.mark.parametrize(
    ("said", "action"),
    [("yes", "confirm"), (1, "confirm"), (0, "reject"), (None, "reject"), ("", "reject")],
)
async def test_an_approver_reads_any_other_answer_as_a_yes_or_a_no(
    said: object, action: str
) -> None:
    sent: list[list[HitlDecision]] = []

    async def answer(decisions: list[HitlDecision]) -> None:
        sent.append(decisions)

    approver = Approver(lambda requirement: said)  # type: ignore[arg-type]
    await approver.answer(ApprovalRequested(_paused("deploy"), answer))

    assert [[(d.action, d.choice) for d in batch] for batch in sent] == [[(action, "once")]]


async def test_a_policy_that_fails_leaves_the_approval_unanswered() -> None:
    sent: list[list[HitlDecision]] = []

    async def answer(decisions: list[HitlDecision]) -> None:
        sent.append(decisions)

    def policy(requirement: Requirement) -> bool:
        raise LookupError(f"no rule for {requirement.tool_name}")

    request = ApprovalRequested(_paused("deploy"), answer)
    with pytest.raises(LookupError, match="no rule for deploy"):
        await Approver(policy).answer(request)

    assert sent == [] and not request.answered


async def test_a_reply_collected_on_its_own_raises_at_an_approval_without_a_policy() -> None:
    read: list[str] = []

    async def answer(decisions: list[HitlDecision]) -> None:
        raise AssertionError("nothing is sent without a policy")

    async def events() -> AsyncIterator[Event | ApprovalRequested]:
        yield ContentDelta(text="about to deploy")
        read.append("approval")
        yield ApprovalRequested(_paused("deploy"), answer)
        read.append("after")

    with pytest.raises(ApprovalRequired) as raised:
        await Reply.collect(events(), Approver(None))

    assert [r.tool_name for r in raised.value.requirements] == ["deploy"]
    assert read == ["approval"]


async def test_a_reply_passes_over_what_is_not_part_of_the_answer() -> None:
    async def events() -> AsyncIterator[Event | ApprovalRequested]:
        yield RunStarted(run_id="r-1")
        yield StatusUpdate(model="m", input_tokens=5)
        yield ToolStarted(run_id="r-1", tool_name="read_file")
        yield ContentDelta(text="done")
        yield InfoMessage(text="noted")

    reply = await Reply.collect(events(), Approver(None))

    assert reply == Reply(text="done") and str(reply) == "done"


async def test_what_the_client_sends_is_the_contract_s_messages_field_for_field() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        wire = _wire(igni)
        await _collect(session.send("héllo", files={"a.py": "x"}, force=True))
        await session.queue("then this")
        await session.cancel()
        await _until(lambda: len(wire) == 3)

    [prompt] = [r.frame for r in fake.socket.received if isinstance(r.frame, UserMessage)]
    assert json.loads(wire[0]) == {
        "type": "user_message",
        "id": prompt.id,
        "session_id": session.id,
        "text": "héllo",
        "file_contents": {"a.py": "x"},
        "client_id": igni.client_id,
        "force": True,
    }
    assert json.loads(wire[1]) == {
        "type": "queue_message",
        "session_id": session.id,
        "text": "then this",
        "client_id": igni.client_id,
    }
    cancel = json.loads(wire[2])
    assert cancel == {
        "type": "rpc_request",
        "id": cancel["id"],
        "method": "cancel_run",
        "args": {},
        "session_id": session.id,
    }, "cancel_run answers, so session.cancel() calls it"


async def test_a_call_s_args_go_to_igni_by_the_contract_s_names_with_its_defaults() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["read_process_tail"] = {
            "pid": 7,
            "output": "",
            "is_running": False,
            "exit_code": None,
        }
        session = await igni.sessions.create()
        fake.methods.answers["search_chat"] = []
        wire = _wire(igni)
        await igni.processes.tail(7)
        await session.history.search(query="deploy")

    calls = [json.loads(line) for line in wire]
    assert calls[0] == {
        "type": "rpc_request",
        "id": calls[0]["id"],
        "method": "read_process_tail",
        "args": {"pid": 7, "tail": 200},
    }, "no session_id for igni as a whole; every argument, its default included"
    assert calls[1]["session_id"] == session.id
    assert calls[1]["args"] == {"session_id": session.id, "query": "deploy", "limit": 50}


def test_a_frame_built_from_its_fields_is_checked() -> None:
    with pytest.raises(ValidationError):
        RpcRequest(id="rpc-1", method="get_todos", args="all")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        UserMessage(id="run-1", session_id="s-1", text=5, client_id="")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        UserMessage(id="run-1", session_id="s-1", txt="hi")  # type: ignore[call-arg]


# ── helpers ──


def _requirement(requirement_id: str, tool_name: str) -> Requirement:
    return Requirement(
        requirement_id=requirement_id, tool_name=tool_name, tool_args={}, agent_path=[]
    )


def _paused(*tools: str) -> RunPaused:
    return RunPaused(run_id="r-1", requirements=[_requirement(f"req-{t}", t) for t in tools])


async def _collect(run: object) -> list[object]:
    return [event async for event in run]  # type: ignore[attr-defined]


def _sent(fake: FakeIgni, kind: str) -> int:
    return sum(1 for r in fake.socket.received if r.frame.type == kind)


async def _until(condition: object, timeout: float = 5.0) -> None:
    async def wait() -> None:
        while not condition():  # type: ignore[operator]
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait(), timeout)


def _wire(igni: IgniClient) -> list[str]:
    """Every message the client puts on its socket from now on, as it went."""
    link = igni._conn._lifecycle.link
    assert link is not None
    socket, wire = link.socket, []
    send = socket.send

    async def recording(message: str) -> None:
        wire.append(message)
        await send(message)

    socket.send = recording  # type: ignore[method-assign,assignment]
    return wire

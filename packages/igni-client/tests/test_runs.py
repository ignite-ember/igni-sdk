"""Sessions and runs: a prompt followed to its end, approvals answered in the loop."""

from __future__ import annotations

import asyncio

import pytest

from igni_client import (
    ApprovalRequested,
    ApprovalRequired,
    ContentDelta,
    Decision,
    IgniClient,
    InfoMessage,
    Requirement,
    RpcError,
    RunCompleted,
    RunFailed,
    RunStarted,
    ToolCompleted,
)
from igni_client.events import RunError
from igni_client.frames import HitlDecision, QueueMessage
from igni_client.methods import HISTORY, HistoryTurn
from igni_client.testing import Delay, FakeIgni, Steps


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
        mine_reply, _ = await asyncio.gather(ours.ask("mine"), other.ask("theirs"))

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

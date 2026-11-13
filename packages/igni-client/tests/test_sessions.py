"""Sessions and the runs followed in them: what they hold, ask for and refuse to mix up."""

from __future__ import annotations

import asyncio
from typing import Any

from igni_client import (
    ApprovalRequested,
    ContentDelta,
    IgniClient,
    RunCompleted,
)
from igni_client.events import ErrorMessage, Event, RequirementDetails, RunPaused
from igni_client.frames import HitlResponseBatch
from igni_client.testing import FakeIgni, Steps
from igni_client.testing.methods import DEFAULT_SESSION


async def test_a_session_knows_its_id_and_the_project_igni_bound_it_to() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create("/work/api")

        assert repr(session) == f"Session({session.id!r})"
        assert session.project_dir == "/work/api"
        assert (await igni.sessions.open(session.id)).project_dir == "/work/api"


async def test_the_default_session_is_a_new_one_when_igni_has_none_open() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        opened = await igni.sessions.default()
        fake.methods.answers["get_session_id"] = ""
        fresh = await igni.sessions.default()

    assert opened.id == DEFAULT_SESSION
    assert fresh.id not in ("", DEFAULT_SESSION), "attached with none named: igni made one"
    attaches = [c.args for c in fake.methods.calls if c.method == "attach_session"]
    assert attaches[-1].get("session_id", "") == ""


async def test_a_session_s_events_are_its_own_and_not_another_sessions() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        mine = await igni.sessions.create()
        other = await igni.sessions.create()
        heard: list[Event | ApprovalRequested] = []

        async def listen() -> None:
            async for event in mine.events():
                heard.append(event)
                if isinstance(event, RunCompleted):
                    return

        listening = asyncio.ensure_future(listen())
        await asyncio.sleep(0.05)
        await other.ask("theirs")
        await mine.ask("mine")
        await asyncio.wait_for(listening, 5)

    assert {getattr(e, "session_id", None) for e in heard} == {mine.id}
    assert "".join(e.text for e in heard if isinstance(e, ContentDelta)) == "echo: mine"


async def test_an_approval_answered_from_events_goes_to_igni_in_its_own_session() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        approval = Steps.approval("deploy").requirements

        async def pause() -> None:
            await asyncio.sleep(0.05)
            await fake.socket.broadcast(
                RunPaused(session_id=session.id, run_id="r-1", requirements=approval)
            )

        asyncio.ensure_future(pause())
        async for event in session.events():
            if isinstance(event, ApprovalRequested):
                await event.approve()
                break
        await _until(
            lambda: any(isinstance(r.frame, HitlResponseBatch) for r in fake.socket.received)
        )

    [sent] = [r.frame for r in fake.socket.received if isinstance(r.frame, HitlResponseBatch)]
    assert sent.session_id == session.id
    assert sent.id.startswith("hitl-"), "a request id of the client's own, for an answer"
    assert [d.requirement_id for d in sent.decisions] == ["req-deploy"]


async def test_an_error_on_the_prompt_s_own_stream_is_yielded_and_not_taken_for_a_refusal() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.runs.script = lambda text: [
            ErrorMessage(text="the model hiccuped"),
            *Steps.answer("ok"),
        ]
        session = await igni.sessions.create()

        events = [event async for event in session.send("go")]

    errors = [e for e in events if isinstance(e, ErrorMessage)]
    assert [e.text for e in errors] == ["the model hiccuped"]
    assert isinstance(events[-1], RunCompleted), "the run went on to its end"


async def test_details_for_a_requirement_nobody_waits_on_change_nothing_and_are_still_yielded() -> (
    None
):
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.runs.script = lambda text: [
            RequirementDetails(requirement_id="req-deploy", details="too early"),
            Steps.approval("deploy"),
            RequirementDetails(requirement_id="req-elsewhere", details="not this one"),
            *Steps.answer("deployed"),
        ]
        session = await igni.sessions.create()
        yielded: list[Any] = []
        waiting: ApprovalRequested | None = None
        async for event in session.send("deploy"):
            yielded.append(event)
            if isinstance(event, ApprovalRequested):
                waiting = event
                event.requirements[0].details_pending = True
                await event.approve()

    assert waiting is not None
    assert waiting.requirements[0].details == "", "neither the early nor the other's details"
    assert waiting.requirements[0].details_pending
    assert [e.details for e in yielded if isinstance(e, RequirementDetails)] == [
        "too early",
        "not this one",
    ]


async def test_reattaching_attaches_every_session_again_with_its_project() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        first = await igni.sessions.create("/work/a")
        second = await igni.sessions.create("/work/b")
        third = await igni.sessions.create()
        before = len(fake.methods.calls)

        await igni.sessions.reattach()

    again = [c.args for c in fake.methods.calls[before:] if c.method == "attach_session"]
    assert [(a["session_id"], a.get("project_dir")) for a in again] == [
        (first.id, "/work/a"),
        (second.id, "/work/b"),
        (third.id, third.project_dir),
    ]


async def _until(condition: Any, timeout: float = 5.0) -> None:
    async def wait() -> None:
        while not condition():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait(), timeout)

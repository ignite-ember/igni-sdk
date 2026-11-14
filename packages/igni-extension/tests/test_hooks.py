"""`@ext.hook`: the extension answering igni's hook events.

Against `FakeHost`, which asks as igni asks (`docs/HOST_MODEL_PROTOCOL.md` (https://github.com/ignite-ember/igni-core/blob/main/docs/HOST_MODEL_PROTOCOL.md)).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from collections.abc import AsyncIterator

import pytest
from pydantic import ValidationError

from igni_extension import Allow, Caller, CallerKind, Hooks, IgniExtension, Modify, Reject
from igni_extension.hooks import HookHandlers, PlanSubmit, PostToolUse, PreToolUse, Stop, Told
from igni_extension.testing import FakeHost

PLAN = {"session_id": "s-1", "plan": "Refactor it.", "tasks": [], "attempt": 0}
ADA = Caller(kind=CallerKind.PERSON, id="u-ada", org="org-acme", group="g-legal")


@pytest.fixture
async def host() -> AsyncIterator[FakeHost]:
    async with FakeHost() as fake:
        yield fake


async def _connected(ext: IgniExtension) -> asyncio.Task[None]:
    await ext.connect()
    return asyncio.create_task(ext.connection.serve_forever())


async def test_a_reject_carries_its_reason(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())

    @ext.hook(Hooks.PLAN_SUBMIT)
    async def grounded(plan: PlanSubmit) -> Allow | Reject:
        assert plan.attempt == 0
        return Reject("Name the files the plan changes.")

    task = await _connected(ext)
    try:
        answer = await host.hook("PlanSubmit", PLAN)
    finally:
        task.cancel()
        await ext.aclose()

    assert answer["outcome"] == "reject"
    assert answer["reason"] == "Name the files the plan changes."


async def test_returning_nothing_allows(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())

    @ext.hook(Hooks.POST_TOOL_USE)
    async def watch(call: PostToolUse) -> None:
        assert call.result == "42"

    task = await _connected(ext)
    try:
        answer = await host.hook(
            "PostToolUse",
            {"session_id": "s-1", "tool_name": "sum", "tool_args": {}, "result": "42"},
        )
    finally:
        task.cancel()
        await ext.aclose()

    assert answer["outcome"] == "allow"


async def test_a_change_is_sent_whole(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())

    @ext.hook(Hooks.PRE_TOOL_USE)
    async def narrow(call: PreToolUse) -> Modify:
        return Modify(call.model_copy(update={"tool_args": {**call.tool_args, "limit": 10}}))

    task = await _connected(ext)
    try:
        answer = await host.hook(
            "PreToolUse", {"session_id": "s-1", "tool_name": "search", "tool_args": {"q": "x"}}
        )
    finally:
        task.cancel()
        await ext.aclose()

    assert answer["outcome"] == "modify"
    assert answer["value"]["tool_args"] == {"q": "x", "limit": 10}
    assert answer["value"]["tool_name"] == "search"


async def test_a_handler_that_raises_says_it_failed(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())

    @ext.hook(Hooks.PLAN_SUBMIT)
    async def broken(plan: PlanSubmit) -> Allow:
        raise RuntimeError("index unreachable")

    task = await _connected(ext)
    try:
        answer = await host.hook("PlanSubmit", PLAN)
    finally:
        task.cancel()
        await ext.aclose()

    assert answer == {"hook": answer["hook"], "outcome": "failed", "reason": "index unreachable"}


async def test_an_event_nothing_handles_is_allowed(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    task = await _connected(ext)
    try:
        answer = await host.hook("PlanSubmit", PLAN)
    finally:
        task.cancel()
        await ext.aclose()

    assert answer["outcome"] == "allow"


async def test_a_told_event_reaches_its_handler_and_nothing_goes_back(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    heard: asyncio.Future[Told] = asyncio.get_running_loop().create_future()

    @ext.hook(Hooks.SESSION_START)
    async def started(event: Told) -> None:
        heard.set_result(event)

    task = await _connected(ext)
    try:
        await host.tell("SessionStart", {"session_id": "s-1", "source": "startup"})
        event = await asyncio.wait_for(heard, 5)
    finally:
        task.cancel()
        await ext.aclose()

    assert event.session_id == "s-1"
    assert event.model_extra == {"source": "startup"}


def test_one_handler_answers_for_an_event() -> None:
    ext = IgniExtension("acme.example", environ={})

    @ext.hook(Hooks.PLAN_SUBMIT)
    async def first(plan: PlanSubmit) -> None:
        return None

    with pytest.raises(ValueError, match="hooked twice"):

        @ext.hook(Hooks.PLAN_SUBMIT)
        async def second(plan: PlanSubmit) -> None:
            return None


def test_only_the_deciding_events_can_be_changed() -> None:
    changeable = {event.name: event.modify for event in Hooks.all() if event.modify}
    assert changeable == {
        "PreToolUse": ("tool_args",),
        "PostToolUse": ("result",),
        "UserPromptSubmit": ("message",),
        "PlanSubmit": ("plan",),
    }
    assert {event.name for event in Hooks.all() if event.decides} == {
        "PreToolUse",
        "PostToolUse",
        "UserPromptSubmit",
        "Stop",
        "PlanSubmit",
    }


@pytest.mark.parametrize("value_type", [PreToolUse, PostToolUse])
def test_a_tool_event_names_the_tool_as_igni_registers_it_and_as_the_manifest_does(
    value_type: type[PreToolUse] | type[PostToolUse],
) -> None:
    """`tool_name` is igni's (`mcp_ext:acme.tickets_lookup_ticket`, or `read_file`);
    `tool_manifest_name` the manifest's (`acme.tickets.lookup_ticket`), empty for igni's own."""
    fields = {"tool_name": "mcp_ext:acme.tickets_lookup_ticket", "result": ""}

    told = value_type.model_validate({**fields, "tool_manifest_name": "acme.tickets.lookup_ticket"})
    built_in = value_type.model_validate({**fields, "tool_name": "read_file"})

    assert "tool_manifest_name" in value_type.model_fields
    assert told.tool_manifest_name == "acme.tickets.lookup_ticket"
    assert built_in.tool_manifest_name == ""


async def test_a_told_event_hands_its_handler_the_caller_igni_named(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    heard: asyncio.Future[tuple[Caller, Caller | None]] = asyncio.get_running_loop().create_future()

    @ext.hook(Hooks.SESSION_START)
    async def started(event: Told, caller: Caller) -> None:
        heard.set_result((caller, Caller.current()))

    task = await _connected(ext)
    try:
        await host.tell("SessionStart", {"session_id": "s-1"}, caller=ADA)
        seen = await asyncio.wait_for(heard, 5)
    finally:
        task.cancel()
        await ext.aclose()

    assert seen == (ADA, ADA)


@pytest.mark.parametrize("principal", [None, {"kind": "person"}, {"kind": "robot", "id": "r-1"}])
async def test_a_missing_or_malformed_principal_reaches_a_handler_as_no_caller(
    host: FakeHost, principal: object
) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    heard: asyncio.Future[tuple[Caller | None, Caller | None]] = (
        asyncio.get_running_loop().create_future()
    )

    @ext.hook(Hooks.SESSION_START)
    async def started(event: Told, caller: Caller | None) -> None:
        heard.set_result((caller, Caller.current()))

    task = await _connected(ext)
    frame = {"op": "hook", "event": "SessionStart", "value": {}, "principal": principal}
    try:
        await host.tell("SessionEnd", {})  # nothing hooks it; returns once connected
        for socket in list(host._sockets):
            await socket.send(json.dumps(frame))
        seen = await asyncio.wait_for(heard, 5)
    finally:
        task.cancel()
        await ext.aclose()

    assert seen == (None, None)


@pytest.mark.parametrize("principal", [None, {"kind": "person"}, {"kind": "robot", "id": "r-1"}])
async def test_a_deciding_event_with_a_malformed_principal_reaches_its_handler_as_no_caller(
    host: FakeHost, principal: object
) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    heard: asyncio.Future[tuple[Caller | None, Caller | None]] = (
        asyncio.get_running_loop().create_future()
    )

    @ext.hook(Hooks.PLAN_SUBMIT)
    async def grounded(plan: PlanSubmit, caller: Caller | None) -> None:
        heard.set_result((caller, Caller.current()))

    task = await _connected(ext)
    frame = {
        "op": "hook",
        "id": "h-raw",
        "event": "PlanSubmit",
        "value": PLAN,
        "principal": principal,
    }
    try:
        await host.tell("SessionEnd", {})  # nothing hooks it; returns once connected
        for socket in list(host._sockets):
            await socket.send(json.dumps(frame))
        seen = await asyncio.wait_for(heard, 5)
    finally:
        task.cancel()
        await ext.aclose()

    assert seen == (None, None)


class TestHookHandlers:
    """Called as the host channel calls them, with the caller already read off the wire."""

    async def test_answer_hands_the_handler_the_caller_it_is_given(self) -> None:
        handlers = HookHandlers()
        seen: list[tuple[Caller, Caller | None]] = []

        @handlers.on(Hooks.PLAN_SUBMIT)
        def grounded(plan: PlanSubmit, caller: Caller) -> Reject:
            seen.append((caller, Caller.current()))
            return Reject(caller.id)

        answer = await handlers.answer("h-1", "PlanSubmit", PLAN, caller=ADA)

        assert (answer.outcome, answer.reason) == ("reject", "u-ada")
        assert seen == [(ADA, ADA)] and seen[0][0] is ADA
        assert Caller.current() is None

    async def test_a_deciding_handler_that_raises_is_answered_failed_with_why(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        handlers = HookHandlers()

        @handlers.on(Hooks.PLAN_SUBMIT)
        def broken(plan: PlanSubmit, caller: Caller) -> Allow:
            raise RuntimeError(f"no index for {caller.id}")

        with caplog.at_level(logging.ERROR, logger="igni_extension.hooks"):
            answer = await handlers.answer("h-4", "PlanSubmit", PLAN, caller=ADA)

        assert (answer.hook, answer.outcome, answer.reason) == (
            "h-4",
            "failed",
            "no index for u-ada",
        )
        (record,) = [r for r in caplog.records if r.name == "igni_extension.hooks"]
        assert record.getMessage() == "igni: the handler of PlanSubmit failed"
        assert Caller.current() is None

    async def test_an_event_nothing_handles_is_allowed_or_not_heard(self) -> None:
        handlers = HookHandlers()

        await handlers.tell("SessionEnd", {}, caller=ADA)  # nothing to hear it; does not raise
        answer = await handlers.answer("h-5", "PlanSubmit", PLAN, caller=ADA)

        assert (answer.hook, answer.outcome, answer.reason) == ("h-5", "allow", "")

    async def test_tell_hands_the_handler_the_caller_it_is_given(self) -> None:
        handlers = HookHandlers()
        seen: list[Caller | None] = []

        @handlers.on(Hooks.SESSION_END)
        async def ended(event: Told) -> None:
            seen.append(Caller.current())

        await handlers.tell("SessionEnd", {"session_id": "s-1"}, caller=ADA)
        assert seen == [ADA]

    async def test_without_a_caller_a_handler_that_takes_one_or_none_gets_none(self) -> None:
        handlers = HookHandlers()
        seen: list[Caller | None] = []

        @handlers.on(Hooks.STOP)
        async def stopping(event: Stop, caller: Caller | None) -> None:
            seen.append(caller)

        answer = await handlers.answer("h-2", "Stop", {"session_id": "s-1"})

        assert answer.outcome == "allow"
        assert seen == [None]

    @pytest.mark.parametrize("call", ["tell", "answer"])
    async def test_the_caller_is_no_longer_passed_as_principal(self, call: str) -> None:
        handlers = HookHandlers()
        principal = ADA.model_dump(mode="json")
        with pytest.raises(TypeError, match="principal"):
            if call == "tell":
                await handlers.tell("SessionStart", {}, principal=principal)  # type: ignore[call-arg]
            else:
                await handlers.answer("h-3", "PlanSubmit", PLAN, principal=principal)  # type: ignore[call-arg]

    async def test_a_told_handler_that_raises_is_logged_and_swallowed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        handlers = HookHandlers()

        @handlers.on(Hooks.NOTIFICATION)
        def broken(event: Told) -> None:
            raise RuntimeError("the pager is down")

        with caplog.at_level(logging.ERROR, logger="igni_extension.hooks"):
            await handlers.tell("Notification", {}, caller=ADA)  # does not raise

        (record,) = [r for r in caplog.records if r.name == "igni_extension.hooks"]
        assert record.getMessage() == "igni: the handler of Notification failed"
        assert record.exc_info is not None and isinstance(record.exc_info[1], RuntimeError)


class TestAPlansTasks:
    def test_keep_the_json_the_agent_wrote(self) -> None:
        tasks = [{"title": "Split it", "done": False, "files": ["a.py"]}, "Test it", 3, None]

        plan = PlanSubmit.model_validate_json(json.dumps({**PLAN, "tasks": tasks}))

        assert plan.tasks == tasks

    @pytest.mark.parametrize(
        "task",
        [datetime.date(2026, 11, 8), {1, 2}, object(), {1: "one"}],
        ids=["a date", "a set", "an object", "a dict with an int key"],
    )
    def test_refuse_what_is_not_json(self, task: object) -> None:
        with pytest.raises(ValidationError):
            PlanSubmit(plan="Refactor it.", tasks=[task])  # type: ignore[list-item]

    def test_are_described_as_json_values(self) -> None:
        items = PlanSubmit.model_json_schema()["properties"]["tasks"]["items"]

        assert items == {"$ref": "#/$defs/JsonValue"}


def test_every_hook_event_is_listed_with_igni_s_name_and_whether_it_decides() -> None:
    assert {event.name: event.decides for event in Hooks.all()} == {
        "PreToolUse": True,
        "PostToolUse": True,
        "UserPromptSubmit": True,
        "Stop": True,
        "PlanSubmit": True,
        "PostToolUseFailure": False,
        "SessionStart": False,
        "SessionEnd": False,
        "SubagentStart": False,
        "SubagentStop": False,
        "Notification": False,
        "PreCompact": False,
        "PostCompact": False,
        "InstructionsLoaded": False,
        "TaskCreated": False,
        "TaskCompleted": False,
        "StopFailure": False,
        "PermissionRequest": False,
        "PermissionDenied": False,
    }
    assert repr(Hooks.PRE_TOOL_USE) == "HookEvent('PreToolUse')"


def test_the_handled_events_are_listed_by_name_in_order() -> None:
    handlers = HookHandlers()
    assert handlers.events() == []
    handlers.on(Hooks.STOP)(lambda event: None)
    handlers.on(Hooks.PLAN_SUBMIT)(lambda event: None)
    handlers.on(Hooks.PRE_TOOL_USE)(lambda event: None)
    assert handlers.events() == ["PlanSubmit", "PreToolUse", "Stop"]


def test_an_event_reads_what_igni_sent_and_refuses_what_it_cannot() -> None:
    plan = Hooks.PLAN_SUBMIT.parse({"plan": "Do it.", "tasks": [{"a": [1, None]}, "b"], "x": 1})
    assert plan.session_id == "" and plan.attempt == 0
    assert plan.tasks == [{"a": [1, None]}, "b"]
    assert plan.model_extra == {"x": 1}
    assert Hooks.STOP.parse({}).response == ""
    with pytest.raises(ValidationError):
        Hooks.USER_PROMPT_SUBMIT.parse({"session_id": "s-1"})
    with pytest.raises(ValidationError):
        Hooks.PLAN_SUBMIT.parse({"plan": "x", "attempt": "first"})
    with pytest.raises(ValidationError):
        Hooks.PLAN_SUBMIT.parse("not an object")


def test_each_answer_goes_to_igni_as_its_hook_id_and_outcome() -> None:
    allowed = Allow().for_hook("h-1").model_dump(mode="json")
    rejected = Reject("no").for_hook("h-2").model_dump(mode="json")
    changed = Modify({"plan": "better"}).for_hook("h-3").model_dump(mode="json")
    assert allowed == {"hook": "h-1", "outcome": "allow", "reason": "", "value": None}
    assert rejected == {"hook": "h-2", "outcome": "reject", "reason": "no", "value": None}
    assert changed == {
        "hook": "h-3",
        "outcome": "modify",
        "reason": "",
        "value": {"plan": "better"},
    }


@pytest.mark.parametrize("value", [None, "", 0, [], {"plan": "x"}])
def test_a_modify_sends_whatever_value_it_was_given(value: object) -> None:
    answer = Modify(value).for_hook("h-1")
    assert answer.outcome == "modify" and answer.value == value


def test_a_reject_with_no_reason_is_still_a_reject() -> None:
    answer = Reject("").for_hook("h-1")
    assert (answer.outcome, answer.reason) == ("reject", "")


async def test_an_event_igni_sent_malformed_is_answered_failed_for_a_decision() -> None:
    handlers = HookHandlers()
    ran: list[object] = []
    handlers.on(Hooks.USER_PROMPT_SUBMIT)(lambda event: ran.append(event))

    answer = await handlers.answer("h-1", "UserPromptSubmit", {"session_id": "s-1"})

    assert answer.hook == "h-1" and answer.outcome == "failed"
    assert "message" in answer.reason
    assert ran == []


async def test_an_event_igni_sent_malformed_is_logged_and_swallowed_when_only_told(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handlers = HookHandlers()
    ran: list[object] = []
    handlers.on(Hooks.POST_TOOL_USE)(lambda event: ran.append(event))

    with caplog.at_level(logging.ERROR):
        await handlers.tell("PostToolUse", {"tool_name": "sum"})

    assert ran == []
    assert "the handler of PostToolUse failed" in caplog.text


async def test_an_asked_event_nothing_hooks_is_allowed_and_the_log_says_how_to_fix_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handlers = HookHandlers()
    with caplog.at_level(logging.WARNING):
        answer = await handlers.answer("h-9", "Stop", {"response": "done"})
        await handlers.tell("SessionStart", {})

    assert (answer.hook, answer.outcome) == ("h-9", "allow")
    assert "nothing here hooks" in caplog.text and "permissions.hooks" in caplog.text
    assert caplog.text.count("igni:") == 1


async def test_a_plain_def_handler_runs_off_the_loop_and_a_raising_one_says_why() -> None:
    import threading

    handlers = HookHandlers()
    where: list[int] = []

    def decide(event: PlanSubmit) -> Reject:
        where.append(threading.get_ident())
        return Reject(f"attempt {event.attempt}")

    handlers.on(Hooks.PLAN_SUBMIT)(decide)
    answer = await handlers.answer("h-1", "PlanSubmit", {"plan": "p", "attempt": 2})
    assert (answer.outcome, answer.reason) == ("reject", "attempt 2")
    assert where and where[0] != threading.get_ident()

    def broken(event: Stop) -> None:
        raise ValueError("no reason given")

    handlers.on(Hooks.STOP)(broken)
    failed = await handlers.answer("h-2", "Stop", {})
    assert (failed.outcome, failed.reason) == ("failed", "no reason given")

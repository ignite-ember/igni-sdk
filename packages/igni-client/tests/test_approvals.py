"""Answering a paused run: what `ApprovalRequested` and `Approver` send, and when they refuse."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from igni_client import ApprovalRequested, ApprovalRequired, Decision
from igni_client.approvals import Approver
from igni_client.models import HitlDecision, Requirement, RunPaused


def _requirement(requirement_id: str, tool: str, friendly: str = "") -> Requirement:
    return Requirement(
        requirement_id=requirement_id,
        tool_name=tool,
        friendly_name=friendly,
        tool_args={},
        agent_path=[],
    )


class _Sent:
    """What reached igni, as the answer callback of a request."""

    def __init__(self, *, fail: int = 0, pause: float = 0.0) -> None:
        self.frames: list[list[HitlDecision]] = []
        self._fail = fail
        self._pause = pause

    async def __call__(self, frames: list[HitlDecision]) -> None:
        await asyncio.sleep(self._pause)
        if self._fail:
            self._fail -= 1
            raise ConnectionError("the line dropped")
        self.frames.append(frames)


def _request(sent: _Sent, *requirements: Requirement) -> ApprovalRequested:
    return ApprovalRequested(RunPaused(run_id="r-1", requirements=list(requirements)), sent)


async def test_two_answers_racing_on_one_request_send_only_one() -> None:
    sent = _Sent(pause=0.05)
    request = _request(sent, _requirement("a", "shell"))

    results = await asyncio.gather(request.approve(), request.reject(), return_exceptions=True)

    assert len(sent.frames) == 1, "igni is answered once"
    assert [type(r) for r in results].count(RuntimeError) == 1
    assert request.answered


async def test_a_failed_send_leaves_the_request_open_to_be_answered_again() -> None:
    sent = _Sent(fail=1)
    request = _request(sent, _requirement("a", "shell"))

    with pytest.raises(ConnectionError):
        await request.approve()
    assert not request.answered
    await request.approve()

    assert request.answered and len(sent.frames) == 1
    with pytest.raises(RuntimeError, match="already answered"):
        await request.approve()


async def test_a_policy_that_raises_sends_nothing_and_leaves_the_request_open() -> None:
    def boom(requirement: Requirement) -> bool:
        raise KeyError(requirement.tool_name)

    async def aboom(requirement: Requirement) -> bool:
        raise KeyError(requirement.tool_name)

    for policy in (boom, aboom):
        sent = _Sent()
        request = _request(sent, _requirement("a", "shell"))
        with pytest.raises(KeyError):
            await Approver(policy).answer(request)
        assert sent.frames == [] and not request.answered


async def test_a_policy_may_mix_decisions_and_bools_across_calls() -> None:
    async def policy(requirement: Requirement) -> Decision | bool:
        if requirement.tool_name == "shell":
            return Decision.deny(remember=True)
        if requirement.tool_name == "write":
            return Decision.allow("similar")
        return True

    sent = _Sent()
    request = _request(
        sent, _requirement("1", "shell"), _requirement("2", "write"), _requirement("3", "read")
    )
    await Approver(policy).answer(request)

    assert [(f.requirement_id, f.action, f.choice) for f in sent.frames[0]] == [
        ("1", "reject", "deny"),
        ("2", "confirm", "similar"),
        ("3", "confirm", "once"),
    ]


async def test_no_policy_is_an_approval_required_that_names_the_waiting_tools() -> None:
    sent = _Sent()
    request = _request(sent, _requirement("1", "shell", "Run a command"), _requirement("2", "w"))

    with pytest.raises(ApprovalRequired, match="Run a command, w") as raised:
        await Approver(None).answer(request)

    assert raised.value.requirements == request.requirements and sent.frames == []


async def test_a_request_with_no_calls_is_answered_with_nothing() -> None:
    sent = _Sent()
    request = _request(sent)

    await request.approve()

    assert sent.frames == [[]] and repr(request) == "ApprovalRequested()"


async def test_an_answer_for_calls_the_run_does_not_wait_on_is_ignored_and_a_missing_one_refused() -> (
    None
):
    sent = _Sent()
    request = _request(sent, _requirement("a", "shell"))

    with pytest.raises(ValueError, match=r"missing \['a'\]"):
        await request.decide({"zzz": Decision.allow()})
    assert sent.frames == [] and not request.answered
    await request.decide({"a": Decision.deny(), "zzz": Decision.allow()})

    assert [(f.requirement_id, f.action) for f in sent.frames[0]] == [("a", "reject")]


def test_a_request_is_named_by_what_it_asks_and_a_decision_cannot_be_changed() -> None:
    request = _request(
        _Sent(), _requirement("1", "shell", "Run a command"), _requirement("2", "write")
    )
    decision = Decision.allow()

    assert repr(request) == "ApprovalRequested(Run a command, write)" and request.run_id == "r-1"
    with pytest.raises(ValidationError):
        decision.choice = "always"  # type: ignore[misc]

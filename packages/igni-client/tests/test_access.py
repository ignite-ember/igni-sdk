"""A call a connection cannot make is refused before it is sent; one it may is sent.

igni-core's contract says which access level each method needs, and which a
connection reaches by how it attached (`igni_client.access`). Where the
client knows the standing it refuses for igni, with the same error igni
answers; where it does not, igni decides.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from igni_client import AccessRefused, ApprovalRequested, IgniClient, Local, NotAllowed, Person
from igni_client.access import REACHES, check
from igni_client.api import METHODS
from igni_client.models import ApproverTokenMinted, LoginStarted, PlanDecisionResult, RpcResponse
from igni_client.testing import FakeGateway, FakeIgni, Steps, sample


def _lockfile(project: Path, port: int, token: str | None) -> None:
    (project / ".igni").mkdir()
    body = {"pid": 1, "port": port, "wire_version": "1.0.3", "created_at": 0}
    if token is not None:
        body["ws_token"] = token
    (project / ".igni" / "backend.lock").write_text(json.dumps(body))


def _calls(fake: FakeIgni, method: str) -> int:
    return sum(1 for c in fake.methods.calls if c.method == method)


async def test_a_program_with_the_lockfile_s_token_reaches_client_calls_only(
    tmp_path: Path,
) -> None:
    async with FakeIgni(local_token="program") as fake:
        _lockfile(tmp_path, fake.socket.port, "program")
        fake.methods.answers["list_background_processes"] = []
        async with IgniClient(Local(project_dir=tmp_path)) as igni:
            assert igni.target.standing == "program"
            assert await igni.processes.list() == []
            with pytest.raises(AccessRefused, match="only igni's window may do this"):
                await igni.approvers.mint_token()
            session = await igni.sessions.create()
            with pytest.raises(AccessRefused, match="approver token") as refused:
                await session.plan.approve("r-1")
            assert isinstance(refused.value, NotAllowed)

    assert _calls(fake, "mint_approver_token") == _calls(fake, "approve_plan") == 0, (
        "refused before it was sent"
    )


async def test_an_approver_reaches_approver_calls_but_not_the_window_s(tmp_path: Path) -> None:
    async with FakeIgni(local_token="approver") as fake:
        _lockfile(tmp_path, fake.socket.port, "program")
        fake.methods.answers["approve_plan"] = sample(PlanDecisionResult)
        async with IgniClient(Local(project_dir=tmp_path, approver_token="approver")) as igni:
            assert igni.target.standing == "approver"
            session = await igni.sessions.create()
            await session.plan.approve("r-1")
            with pytest.raises(AccessRefused):
                await igni.auth.login()

    assert _calls(fake, "approve_plan") == 1 and _calls(fake, "login") == 0


async def test_an_igni_without_a_launch_secret_stands_every_connection_as_its_window(
    tmp_path: Path,
) -> None:
    async with FakeIgni() as fake:
        _lockfile(tmp_path, fake.socket.port, None)
        fake.methods.answers["mint_approver_token"] = ApproverTokenMinted(token="t")
        async with IgniClient(Local(project_dir=tmp_path)) as igni:
            assert igni.target.standing == "window"
            assert (await igni.approvers.mint_token()).token == "t"


async def test_through_fleet_every_connection_is_igni_s_window() -> None:
    async with FakeIgni(gateway=FakeGateway({"t-ada": "person:u-ada"})) as fake:
        fake.methods.answers["login"] = LoginStarted(started=True)
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            assert igni.target.standing == "window"
            assert (await igni.auth.login()).started


async def test_a_token_given_by_hand_is_igni_s_to_judge() -> None:
    async with FakeIgni(local_token="whose") as fake:
        fake.methods.answers["login"] = lambda args: RpcResponse(
            error="login: only igni's window may do this"
        )
        async with IgniClient(Local(url=fake.socket.url, token="whose")) as igni:
            assert igni.target.standing == "unknown"
            with pytest.raises(AccessRefused, match="only igni's window"):
                await igni.auth.login()

    assert _calls(fake, "login") == 1, "sent, and igni said no"


def test_every_generated_method_needs_an_access_a_client_can_have() -> None:
    assert {spec.access for spec in METHODS.values()} <= {"client", "approver", "window"}
    assert REACHES["unknown"] is None
    for access in ("client", "approver", "window"):
        check("m", access, "window")
        check("m", access, "unknown")
    check("m", "approver", "approver")
    with pytest.raises(AccessRefused):
        check("m", "approver", "program")


def test_what_each_standing_reaches_is_exactly_this() -> None:
    expected = {
        "program": frozenset({"client"}),
        "approver": frozenset({"client", "approver"}),
        "window": frozenset({"client", "approver", "window"}),
        "unknown": None,
    }
    assert dict(REACHES) == expected


def test_a_refusal_names_the_method_and_says_who_may() -> None:
    with pytest.raises(AccessRefused) as window_only:
        check("login", "window", "approver")
    assert window_only.value.method == "login"
    assert window_only.value.message == "only igni's window may do this"
    assert isinstance(window_only.value, NotAllowed)

    with pytest.raises(AccessRefused) as approver_only:
        check("approve_plan", "approver", "program")
    assert approver_only.value.method == "approve_plan"
    assert "Local(approver_token=...)" in approver_only.value.message

    with pytest.raises(AccessRefused):
        check("login", "window", "program")


def test_an_access_level_with_no_reason_is_refused_with_the_fallback_text() -> None:
    for standing in ("program", "approver", "window"):
        with pytest.raises(AccessRefused) as refused:
            check("open_page", "page", standing)
        assert refused.value.message == "a page call"
        assert refused.value.method == "open_page"
    with pytest.raises(AccessRefused) as empty:
        check("", "platform", "window")
    assert empty.value.message == "a platform call"


def test_an_unknown_standing_never_refuses_even_what_nothing_reaches() -> None:
    check("m", "page", "unknown")
    check("m", "window", "unknown")


def test_a_standing_that_does_not_exist_is_a_programming_error() -> None:
    with pytest.raises(KeyError):
        check("m", "client", "stranger")  # type: ignore[arg-type]


async def test_a_reply_that_carries_a_code_is_classified_by_it_not_by_its_words() -> None:
    async with FakeIgni(local_token="whose") as fake:
        fake.methods.answers["login"] = lambda args: RpcResponse(
            error="login: not for this connection", code="forbidden"
        )
        async with IgniClient(Local(url=fake.socket.url, token="whose")) as igni:
            with pytest.raises(AccessRefused, match="not for this connection"):
                await igni.auth.login()


async def test_a_program_s_approve_is_refused_before_it_is_sent(tmp_path: Path) -> None:
    """`approve()` returned as if it had answered, and igni's refusal came back as
    a bare `NotAllowed` from the next turn of the `send()` loop."""
    async with FakeIgni(local_token="program") as fake:
        _lockfile(tmp_path, fake.socket.port, "program")
        fake.runs.script = lambda text: [Steps.approval("run_shell_command"), *Steps.answer("x")]
        async with IgniClient(Local(project_dir=tmp_path)) as igni:
            session = await igni.sessions.create()
            async for event in session.send("run it"):
                if isinstance(event, ApprovalRequested):
                    with pytest.raises(AccessRefused, match="approver token") as refused:
                        await event.approve()
                    assert isinstance(refused.value, NotAllowed)
                    assert refused.value.method == "hitl_response_batch"
                    assert not event.answered
                    break

    assert fake.runs.decisions == [], "refused before it was sent"


async def test_a_connection_whose_standing_is_unknown_sends_its_answer(tmp_path: Path) -> None:
    async with FakeIgni(local_token="anything") as fake:
        fake.runs.script = lambda text: [Steps.approval("run_shell_command"), *Steps.answer("x")]
        async with IgniClient(fake.local()) as igni:
            assert igni.target.standing == "unknown"
            session = await igni.sessions.create()
            async for event in session.send("run it"):
                if isinstance(event, ApprovalRequested):
                    await event.approve()

    assert len(fake.runs.decisions) == 1

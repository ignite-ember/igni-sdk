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

from igni_client import AccessRefused, IgniClient, Local, NotAllowed, Person
from igni_client.access import REACHES, check
from igni_client.api import METHODS
from igni_client.models import ApproverTokenMinted, LoginStarted, PlanDecisionResult, RpcResponse
from igni_client.testing import FakeGateway, FakeIgni, sample


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

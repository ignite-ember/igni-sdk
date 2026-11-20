"""A Fleet VM's own credential refused: `ask()` says to sign in at the gateway, and does not sign in.

igni on the VM says the credential was refused with a `vm_credential`
push (`needs_sign_in`, or `needs_reissue` for an app), and sends the state
it last pushed to each client as it attaches. The run's own error is only
the model provider's words, so the push is what the client reads.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from igni_client import (
    AuthError,
    CredentialRefused,
    IgniClient,
    Person,
    ReissueRequired,
    RunFailed,
    SignInRequired,
)
from igni_client.models import RunError, RunStarted, VmCredentialState
from igni_client.testing import FakeGateway, FakeIgni, Step, Steps

TOKENS = {"t-ada": "person:u-ada", "t-bot": "app:bot"}
#: What a run carries when the provider refuses the VM's token: its words, no status.
PROVIDER_REFUSAL = "Invalid or expired token"


def _failing(text: str) -> list[Step]:
    return [RunStarted(run_id=Steps.RUN_ID), RunError(error=PROVIDER_REFUSAL)]


async def _told(igni: IgniClient, state: str) -> None:
    """Until igni's `vm_credential` push saying `state` has reached the client."""
    for _ in range(200):
        if igni.vm_credential is not None and igni.vm_credential.state == state:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"the client never heard {state}")


# ── The typed error ──


def test_a_refused_credential_s_state_names_its_error() -> None:
    signed_out = CredentialRefused.of("needs_sign_in", "revoked", where="igni in Fleet via gw")
    reissue = CredentialRefused.of("needs_reissue")

    assert isinstance(signed_out, SignInRequired) and isinstance(signed_out, AuthError)
    # A refused credential is a failed run too: code that catches RunFailed
    # keeps catching it.
    assert isinstance(signed_out, RunFailed) and isinstance(reissue, RunFailed)
    assert (signed_out.state, signed_out.detail) == ("needs_sign_in", "revoked")
    assert str(signed_out).startswith("igni in Fleet via gw: ")
    assert "(revoked)" in str(signed_out)
    assert "gateway" in str(signed_out) and "POST /v1/sign-in" in str(signed_out)
    assert "vm_sign_in" in str(signed_out)
    assert isinstance(reissue, ReissueRequired) and isinstance(reissue, AuthError)
    assert "re-issues" in str(reissue) and "sign-in" not in str(reissue)
    assert CredentialRefused.of("ready") is None
    assert CredentialRefused.of("unreachable") is None


# ── ask() raises it ──


async def test_a_run_failing_after_igni_said_sign_in_raises_sign_in_required() -> None:
    gateway = FakeGateway(TOKENS)
    async with FakeIgni(gateway=gateway) as fake:
        fake.runs.script = _failing
        fleet = fake.fleet(Person("t-ada"))
        async with IgniClient(fleet) as igni:
            session = await igni.sessions.create()
            await fake.socket.push(
                "vm_credential", {"state": "needs_sign_in", "message": "invalid_grant: revoked"}
            )
            await _told(igni, "needs_sign_in")

            with pytest.raises(SignInRequired) as raised:
                await session.ask("hi")

    assert str(raised.value).startswith(f"igni in Fleet via {fleet.base}: ")
    assert "sign the person in again at the gateway (`POST /v1/sign-in`" in str(raised.value)
    assert raised.value.detail == "invalid_grant: revoked"
    assert isinstance(raised.value.__cause__, RunFailed)
    assert str(raised.value.__cause__) == PROVIDER_REFUSAL


async def test_the_client_does_not_sign_in_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = FakeGateway(TOKENS)
    asked: list[tuple[str, str]] = []
    served = gateway.handle

    async def recorded(request: httpx.Request) -> httpx.Response:
        asked.append((request.method, request.url.path))
        return await served(request)

    monkeypatch.setattr(gateway, "handle", recorded)
    async with FakeIgni(gateway=gateway) as fake:
        fake.runs.script = _failing
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            session = await igni.sessions.create()
            await fake.socket.push("vm_credential", {"state": "needs_sign_in", "message": ""})
            await _told(igni, "needs_sign_in")
            for _ in range(2):
                with pytest.raises(SignInRequired):
                    await session.ask("hi")

    # The gateway was only ever asked for the socket: no `POST /v1/sign-in`, no other call.
    assert fake.socket.connections == 1
    assert asked == []
    assert gateway.signed_in == []


async def test_an_app_s_run_failing_after_igni_said_reissue_raises_reissue_required() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.runs.script = _failing
        async with IgniClient(fake.fleet(Person("t-bot"))) as igni:
            session = await igni.sessions.create()
            await fake.socket.push("vm_credential", {"state": "needs_reissue", "message": ""})
            await _told(igni, "needs_reissue")

            with pytest.raises(ReissueRequired):
                await session.ask("hi")


async def test_a_client_connecting_after_the_refusal_is_told_and_its_ask_raises_it() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.runs.script = _failing
        async with IgniClient(fake.fleet(Person("t-ada"))) as first:
            await fake.socket.push(
                "vm_credential", {"state": "needs_sign_in", "message": "invalid_grant: revoked"}
            )
            await _told(first, "needs_sign_in")
        async with IgniClient(fake.fleet(Person("t-ada"))) as later:
            session = await later.sessions.create()
            # No push after it connected: igni sent the state it last pushed as it attached.
            with pytest.raises(SignInRequired) as raised:
                await session.ask("hi")

    assert later.vm_credential == VmCredentialState(
        state="needs_sign_in", message="invalid_grant: revoked"
    )
    assert isinstance(raised.value.__cause__, RunFailed)


async def test_signing_in_elsewhere_clears_it_when_igni_says_ready() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.runs.script = _failing
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            session = await igni.sessions.create()
            await fake.socket.push("vm_credential", {"state": "needs_sign_in", "message": ""})
            await _told(igni, "needs_sign_in")
            with pytest.raises(SignInRequired):
                await session.ask("hi")

            # The person signed in at the gateway; igni pushes the new state.
            await fake.socket.push("vm_credential", {"state": "ready", "message": ""})
            await _told(igni, "ready")
            fake.runs.script = Steps.echo
            assert (await session.ask("again")).text == "echo: again"


# ── Everything else is as it was ──


async def test_a_run_failing_before_igni_said_anything_stays_run_failed() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.runs.script = _failing
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            session = await igni.sessions.create()
            with pytest.raises(RunFailed) as raised:
                await session.ask("hi")
            assert igni.vm_credential is None

    assert type(raised.value) is RunFailed
    assert str(raised.value) == PROVIDER_REFUSAL


@pytest.mark.parametrize("state", ["ready", "unreachable"])
async def test_a_run_failing_while_the_credential_is_not_refused_stays_run_failed(
    state: str,
) -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.runs.script = _failing
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            session = await igni.sessions.create()
            await fake.socket.push("vm_credential", {"state": state, "message": "x"})
            await _told(igni, state)
            with pytest.raises(RunFailed) as raised:
                await session.ask("hi")

    assert type(raised.value) is RunFailed


async def test_a_bearer_token_the_gateway_refuses_is_still_a_plain_auth_error() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        with pytest.raises(AuthError) as raised:
            async with IgniClient(fake.fleet(Person("garbage"))):
                pass

    assert type(raised.value) is AuthError
    assert "gateway" in str(raised.value)

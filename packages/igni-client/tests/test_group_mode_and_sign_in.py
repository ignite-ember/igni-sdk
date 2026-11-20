"""The gateway's side of the group mode, its sign-in, its VM state, and a token that runs out.

* A person whose group runs igni only on the desktop is refused with
  `GroupIsLocalOnly` wherever the gateway says so: `1008 group_local_only`
  on connecting, the same close kicking an open connection, `403` on
  sign-in and on a command, `403` on the socket's handshake.
* `igni.sign_in()` is the gateway's `POST /v1/sign-in`, asked only when
  the program asks.
* `Me.vm` is the VM's state, read without waking it.
* `1008 token_expired` is not final: the socket is opened again with a
  fresh token.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from igni_client import (
    AuthError,
    Backoff,
    Fleet,
    GroupIsLocalOnly,
    IgniClient,
    NotAllowed,
    NotSupported,
    Person,
    SignedIn,
    Unavailable,
    VmState,
)
from igni_client.commands import Commands, Me
from igni_client.commands.models import VM_STATES
from igni_client.commands.wire import GatewayRefusal
from igni_client.errors import GROUP_LOCAL_ONLY, TOKEN_EXPIRED, reason_token
from igni_client.models import VmCredentialState
from igni_client.sign_in import sign_in
from igni_client.targets import RefusalBody, _refusal
from igni_client.testing import FakeGateway, FakeIgni, Steps
from igni_client.testing.gateway import LOCAL_ONLY_REASON

TOKENS = {"t-ada": "person:u-ada", "t-bot": "app:bot"}
FAST = Backoff(attempts=3, first=0.01, most=0.01)


async def _until(check: Any, what: str) -> None:
    for _ in range(200):
        if check():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"never: {what}")


class Counting:
    """A person's token source that counts how often it is asked."""

    def __init__(self, token: str) -> None:
        self._token = token
        self.asked = 0

    async def token(self) -> str:
        self.asked += 1
        return self._token


# ── The gateway's reason words ──


@pytest.mark.parametrize(
    ("reason", "token"),
    [
        ("group_local_only", "group_local_only"),
        ("group_local_only: your organisation runs igni on your computer", "group_local_only"),
        ("  group_local_only text", "group_local_only"),
        ("token_expired", "token_expired"),
        ("licence: the seat is gone", "licence"),
        ("not an active producer", "not"),
        ("group_local_onlyish", "group_local_onlyish"),
        ("group_local_onlyX", ""),
        ("Group_local_only", ""),
        ("", ""),
        (": nothing", ""),
    ],
)
def test_a_reason_leads_with_its_stable_word(reason: str, token: str) -> None:
    assert reason_token(reason) == token


def test_the_words_are_the_gateway_s() -> None:
    assert (GROUP_LOCAL_ONLY, TOKEN_EXPIRED) == ("group_local_only", "token_expired")
    assert reason_token(LOCAL_ONLY_REASON) == GROUP_LOCAL_ONLY


def test_group_is_local_only_is_a_not_allowed() -> None:
    assert issubclass(GroupIsLocalOnly, NotAllowed)


# ── 1008 group_local_only on the socket ──


async def test_connecting_as_a_local_only_person_raises_and_is_not_retried() -> None:
    gateway = FakeGateway(TOKENS)
    gateway.local_only.add("person:u-ada")
    async with FakeIgni(gateway=gateway) as fake:
        with pytest.raises(
            GroupIsLocalOnly, match="runs igni only on their own computer"
        ) as raised:
            await IgniClient(fake.fleet(Person("t-ada")), backoff=FAST).connect()
        assert "group_local_only: your organisation" in str(raised.value)
        assert fake.socket.connections == 1


async def test_another_producer_is_not_refused_for_a_local_only_person() -> None:
    gateway = FakeGateway(TOKENS)
    gateway.local_only.add("person:u-ada")
    async with FakeIgni(gateway=gateway) as fake:
        igni = await IgniClient(fake.fleet(Person("t-bot"))).connect()
        assert igni.client_id
        await igni.close()


async def test_an_open_connection_is_kicked_when_the_group_turns_local() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.runs.script = lambda text: Steps.answer("ok")
        async with IgniClient(fake.fleet(Person("t-ada")), backoff=FAST) as igni:
            session = await igni.sessions.create()
            await fake.set_mode("local")
            with pytest.raises(GroupIsLocalOnly):
                for _ in range(100):
                    await session.ask("still there?")
                    await asyncio.sleep(0.01)
            with pytest.raises(GroupIsLocalOnly):
                await igni.sessions.create()
        assert fake.socket.connections == 1  # final: never opened again


async def test_a_mode_that_allows_the_cloud_lets_the_person_in_again() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        await fake.set_mode("local")
        with pytest.raises(GroupIsLocalOnly):
            await IgniClient(fake.fleet(Person("t-ada"))).connect()
        await fake.set_mode("cloud")
        assert fake.gateway is not None and fake.gateway.local_only == set()
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            assert igni.client_id


async def test_set_mode_local_refuses_every_person_and_no_app() -> None:
    gateway = FakeGateway({**TOKENS, "t-bo": "person:u-bo"})
    async with FakeIgni(gateway=gateway) as fake:
        await fake.set_mode("local")
        assert gateway.local_only == {"person:u-ada", "person:u-bo"}
        assert fake.server is not None and fake.server.mode == "local"


async def test_a_plain_1008_is_still_not_allowed_and_not_local_only() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        igni = await IgniClient(fake.fleet(Person("t-ada")), backoff=FAST).connect()
        await fake.socket.drop(1008, "not an active producer")
        with pytest.raises(NotAllowed, match="not an active producer") as raised:
            for _ in range(100):
                await igni.sessions.create()
                await asyncio.sleep(0.01)
        assert not isinstance(raised.value, GroupIsLocalOnly)
        await igni.close()


async def test_a_local_igni_closing_with_group_local_only_is_not_reopened() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local(), backoff=FAST) as igni:
        await fake.socket.drop(1008, LOCAL_ONLY_REASON)
        with pytest.raises(GroupIsLocalOnly):
            for _ in range(100):
                await igni.sessions.create()
                await asyncio.sleep(0.01)


# ── 403 group_local_only over HTTP and on the handshake ──


def _invalid(status: int, body: str) -> InvalidStatus:
    return InvalidStatus(Response(status, "", Headers(), body.encode()))


@pytest.mark.parametrize(
    "body",
    [
        '{"error": "group_local_only", "error_description": "your organisation runs igni locally"}',
        '{"error": "refused", "error_description": "group_local_only: your organisation runs igni locally"}',
        "group_local_only: your organisation runs igni locally",
    ],
)
def test_a_refused_handshake_naming_group_local_only_is_local_only(body: str) -> None:
    assert RefusalBody.local_only(body)
    error = _refusal(_invalid(403, body), "the gateway")
    assert type(error) is GroupIsLocalOnly
    assert "runs igni only on their own computer" in str(error)


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (403, '{"error": "refused", "error_description": "not an active producer"}', NotAllowed),
        (403, "forbidden", NotAllowed),
        (403, '["group_local_only"]', NotAllowed),
        (401, '{"error": "group_local_only"}', AuthError),
        (500, "group_local_only", Unavailable),
    ],
)
def test_only_a_403_naming_group_local_only_is_local_only(
    status: int, body: str, kind: type[Exception]
) -> None:
    assert type(_refusal(_invalid(status, body), "the gateway")) is kind


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (403, {"error": "refused", "error_description": LOCAL_ONLY_REASON}, GroupIsLocalOnly),
        (403, {"error": "group_local_only", "error_description": "no"}, GroupIsLocalOnly),
        (403, {"detail": "group_local_only"}, GroupIsLocalOnly),
        (403, {"error": "refused", "error_description": "not an active producer"}, NotAllowed),
        (400, {"error": "group_local_only"}, NotAllowed),
        (401, {"error": "group_local_only"}, AuthError),
        (503, {"error": "busy", "error_description": "group_local_only"}, Unavailable),
    ],
)
def test_a_gateway_refusal_over_http_is_local_only_only_as_a_403(
    status: int, body: dict[str, str], kind: type[Exception]
) -> None:
    refusal = GatewayRefusal.of(httpx.Response(status, json=body))
    assert type(refusal.error()) is kind


def test_a_refusal_keeps_the_gateway_s_code() -> None:
    assert GatewayRefusal.of(httpx.Response(403, json={"error": "refused"})).code == "refused"
    assert GatewayRefusal.of(httpx.Response(403, json={"error": 7})).code == ""
    assert GatewayRefusal.of(httpx.Response(403, text="plain")).code == ""


async def test_a_command_for_a_local_only_person_is_refused() -> None:
    gateway = FakeGateway(TOKENS)
    async with FakeIgni(gateway=gateway) as fake:
        commands = Commands(fake.fleet(Person("t-ada")))
        gateway.local_only.add("person:u-ada")
        with pytest.raises(GroupIsLocalOnly):
            await (await commands.run("ls")).wait()


# ── sign_in() ──


async def test_sign_in_signs_the_person_in_and_igni_says_ready() -> None:
    gateway = FakeGateway(TOKENS)
    gateway.vm_states["person:u-ada"] = VmState(state="asleep", signed_in=False)
    fake = await FakeIgni(gateway=gateway).start()
    async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
        await fake.socket.push("vm_credential", {"state": "needs_sign_in", "message": ""})
        signed = await igni.sign_in()
        assert signed == SignedIn(
            producer="person:u-ada",
            node="n1",
            how="paused",
            credential=VmCredentialState(state="ready", message=""),
        )
        assert signed.ready
        await _until(
            lambda: igni.vm_credential is not None and igni.vm_credential.state == "ready",
            "igni said ready",
        )
        assert (await igni.me()).vm == VmState(state="running", signed_in=True)
    await fake.stop()
    assert gateway.signed_in == ["person:u-ada"]


async def test_sign_in_needs_no_open_socket() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        assert (await IgniClient(fake.fleet(Person("t-ada"))).sign_in()).ready
        assert fake.socket.connections == 0


async def test_a_session_igni_could_not_use_is_answered_not_raised() -> None:
    gateway = FakeGateway(TOKENS)
    gateway.sign_in_state = "needs_sign_in"
    gateway.vm_states["person:u-ada"] = VmState(state="running", signed_in=False)
    async with FakeIgni(gateway=gateway) as fake:
        signed = await sign_in(fake.fleet(Person("t-ada")))
        assert not signed.ready
        assert signed.credential is not None and signed.credential.state == "needs_sign_in"
        assert gateway.vm_state("person:u-ada").signed_in is False


async def test_signing_in_a_local_only_person_raises_group_is_local_only() -> None:
    gateway = FakeGateway(TOKENS)
    gateway.local_only.add("person:u-ada")
    async with FakeIgni(gateway=gateway) as fake:
        with pytest.raises(GroupIsLocalOnly, match="group_local_only"):
            await IgniClient(fake.fleet(Person("t-ada"))).sign_in()
    assert gateway.signed_in == []


async def test_an_app_does_not_sign_in() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        with pytest.raises(NotAllowed, match="an app does not sign in") as raised:
            await sign_in(fake.fleet(Person("t-bot")))
        assert not isinstance(raised.value, GroupIsLocalOnly)


async def test_a_refused_session_cannot_sign_in() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        with pytest.raises(AuthError):
            await sign_in(fake.fleet(Person("t-gone")))


async def test_a_local_igni_has_no_gateway_to_sign_in_at() -> None:
    async with FakeIgni() as fake:
        with pytest.raises(NotSupported, match="sign_in needs Fleet's gateway"):
            await IgniClient(fake.local()).sign_in()


def _gateway_answering(response: httpx.Response) -> Fleet:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response))
    return Fleet("https://gw.acme", auth=Person("t-ada"), http=http)


@pytest.mark.parametrize(
    ("response", "kind", "words"),
    [
        (
            httpx.Response(503, json={"error": "busy", "error_description": "retry"}),
            Unavailable,
            "503",
        ),
        (httpx.Response(502, json={"error": "sign_in_failed"}), Unavailable, "502"),
        (httpx.Response(200, text="<html>"), Unavailable, "with something else"),
        (httpx.Response(200, json={"credential": "ready"}), Unavailable, "with something else"),
    ],
)
async def test_a_sign_in_that_did_not_happen_is_unavailable(
    response: httpx.Response, kind: type[Exception], words: str
) -> None:
    with pytest.raises(kind, match=words):
        await sign_in(_gateway_answering(response))


async def test_a_credential_state_this_version_does_not_know_is_kept() -> None:
    answer = {"producer": "person:u-ada", "credential": {"state": "rotating", "message": "soon"}}
    signed = await sign_in(_gateway_answering(httpx.Response(200, json=answer)))
    assert signed.credential is not None
    assert (signed.credential.state, signed.credential.message) == ("rotating", "soon")
    assert not signed.ready


async def test_an_answer_without_a_credential_is_not_ready() -> None:
    signed = await sign_in(_gateway_answering(httpx.Response(200, json={"producer": "person:u"})))
    assert signed.credential is None and not signed.ready


async def test_sign_in_posts_to_the_gateway_with_the_bearer() -> None:
    asked: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return httpx.Response(200, json={"credential": {"state": "ready", "message": ""}})

    fleet = Fleet(
        "https://gw.acme/base",
        auth=Person("t-ada"),
        http=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    await sign_in(fleet)
    [request] = asked
    assert (request.method, str(request.url)) == ("POST", "https://gw.acme/base/v1/sign-in")
    assert request.headers["Authorization"] == "Bearer t-ada"


# ── Me.vm ──


@pytest.mark.parametrize("state", VM_STATES)
async def test_me_says_the_vm_s_state_and_never_opens_the_socket(state: str) -> None:
    gateway = FakeGateway(TOKENS)
    gateway.vm_states["person:u-ada"] = VmState(state=state, signed_in=state == "running")
    async with FakeIgni(gateway=gateway) as fake:
        me = await IgniClient(fake.fleet(Person("t-ada"))).me()
        assert me.vm == VmState(state=state, signed_in=state == "running")
        assert fake.socket.connections == 0


def test_the_states_are_the_gateway_s() -> None:
    assert VM_STATES == ("none", "asleep", "waking", "running")


def test_an_older_gateway_s_me_has_no_vm() -> None:
    assert Me.model_validate({"producer": "person:u"}).vm is None


@pytest.mark.parametrize("vm", ["asleep", 3, {"state": "asleep", "signed_in": "maybe"}, None])
def test_a_vm_that_is_not_the_gateway_s_shape_is_no_state_known(vm: Any) -> None:
    me = Me.model_validate({"producer": "person:u", "vm": vm})
    assert me.vm is None


def test_a_newer_gateway_s_vm_state_is_kept_as_sent() -> None:
    me = Me.model_validate(
        {"producer": "person:u", "vm": {"state": "draining", "signed_in": True, "node": "n2"}}
    )
    assert me.vm is not None
    assert (me.vm.state, me.vm.signed_in, me.vm.model_extra) == ("draining", True, {"node": "n2"})


def test_a_vm_with_no_fields_is_none_and_not_signed_in() -> None:
    assert Me.model_validate({"producer": "person:u", "vm": {}}).vm == VmState(
        state="none", signed_in=False
    )


# ── 1008 token_expired ──


async def test_a_socket_closed_as_its_token_expired_is_opened_again_with_a_fresh_one() -> None:
    auth = Counting("t-ada")
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.runs.script = lambda text: Steps.answer("still here")
        async with IgniClient(fake.fleet(auth), backoff=FAST) as igni:
            session = await igni.sessions.create()
            assert auth.asked == 1
            await fake.socket.drop(1008, "token_expired: the session ran out")
            await _until(lambda: fake.socket.connections == 2, "opened again")
            assert auth.asked == 2
            assert str(await session.ask("hi")) == "still here"


async def test_a_token_that_expired_before_welcome_is_tried_again() -> None:
    gateway = FakeGateway(TOKENS)
    closes = iter([(1008, "token_expired")])

    def close_once(request: Any) -> tuple[int, str] | None:
        return next(closes, None)

    gateway.close_on_open = close_once  # type: ignore[method-assign]
    auth = Counting("t-ada")
    async with FakeIgni(gateway=gateway) as fake:
        async with IgniClient(fake.fleet(auth), backoff=FAST) as igni:
            assert igni.client_id
        assert fake.socket.connections == 2
        assert auth.asked == 2


async def test_a_local_igni_closing_as_its_token_expired_has_stopped() -> None:
    async with FakeIgni() as fake:
        async with IgniClient(fake.local(), backoff=FAST) as igni:
            await fake.socket.drop(1008, "token_expired")
            with pytest.raises(Unavailable, match="token expired"):
                for _ in range(100):
                    await igni.sessions.create()
                    await asyncio.sleep(0.01)
        assert fake.socket.connections == 1

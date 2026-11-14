"""`FakeHost`, `HostHarness` and `FakeHostTokenEndpoint`: what each promises an extension's tests."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import anyio
import httpx
import pytest
from mcp.shared.exceptions import MCPError
from mcp.shared.message import SessionMessage
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from igni_extension import Caller, CallerKind, IgniExtension, LocalNotification, Target, ToolHints
from igni_extension.testing import (
    FakeHost,
    FakeHostTokenEndpoint,
    HostCall,
    HostHarness,
    TokenClaims,
)
from igni_extension.wire import Hello, HookMessage, Op, Reply, Request, SignalMessage

ADA = Caller(kind=CallerKind.PERSON, id="u-ada", org="org-acme")
READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)


async def _client(host: FakeHost, secret: str | None = None) -> ClientConnection:
    return await connect(
        host.url,
        additional_headers={"Authorization": f"Bearer {host.secret if secret is None else secret}"},
    )


async def _ask(client: ClientConnection, request: Request) -> Reply:
    await client.send(request.model_dump_json())
    return Reply.model_validate_json(await asyncio.wait_for(client.recv(), 5))


async def _hello(client: ClientConnection) -> Hello:
    return Hello.model_validate_json(await asyncio.wait_for(client.recv(), 5))


# ── FakeHost ──


class TestFakeHost:
    async def test_it_listens_on_loopback_and_stop_closes_it(self) -> None:
        host = FakeHost()
        assert host.url == ""
        await host.start()
        assert host.url.startswith("ws://127.0.0.1:") and host.url.endswith("/v1/host")
        client = await _client(host)
        await _hello(client)
        await host.stop()
        with pytest.raises(ConnectionClosed):
            await asyncio.wait_for(client.recv(), 5)
        with pytest.raises(OSError):
            await _client(host)

    async def test_stop_before_start_is_harmless(self) -> None:
        await FakeHost().stop()

    async def test_the_environment_is_the_url_the_secret_and_whatever_else_is_given(self) -> None:
        async with FakeHost() as host:
            env = host.environment(IGNI_EXTENSION_DATA="/data/x")

            assert env == {
                "IGNI_HOST_URL": host.url,
                "IGNI_HOST_SECRET": host.secret,
                "IGNI_EXTENSION_DATA": "/data/x",
            }
            assert FakeHost().secret != host.secret

    async def test_a_wrong_secret_is_closed_with_4001_before_any_hello(self) -> None:
        async with FakeHost() as host:
            client = await _client(host, "wrong")

            with pytest.raises(ConnectionClosed):
                await asyncio.wait_for(client.recv(), 5)
            assert client.close_code == 4001 and client.close_reason == "unauthorized"

    async def test_the_hello_names_the_extension_its_grants_and_the_schema(self) -> None:
        from igni_extension.host_model import SCHEMA_VERSION

        async with FakeHost(extension_id="acme.other", granted=("chat.read", "sessions")) as host:
            hello = await _hello(await _client(host))

        assert hello.op == "hello" and hello.extension_id == "acme.other"
        assert hello.granted == ["chat.read", "sessions"]
        assert hello.schema_version == SCHEMA_VERSION

    async def test_the_defaults_grant_nothing_and_serve_acme_example(self) -> None:
        async with FakeHost() as host:
            hello = await _hello(await _client(host))

        assert (hello.extension_id, hello.granted) == ("acme.example", [])

    async def test_a_get_reads_a_value_and_an_unknown_path_is_not_found(self) -> None:
        async with FakeHost(values={"chat.processing": False}) as host:
            client = await _client(host)
            await _hello(client)
            known = await _ask(client, Request(id=1, op=Op.GET, path="chat.processing"))
            unknown = await _ask(client, Request(id=2, op=Op.GET, path="chat.nope"))

        assert (known.id, known.ok, known.result) == (1, True, False)
        assert unknown.ok is False and unknown.id == 2
        assert unknown.error is not None
        assert (unknown.error.code, unknown.error.message) == ("not_found", "chat.nope")

    async def test_a_set_stores_the_value_for_the_next_get(self) -> None:
        async with FakeHost() as host:
            client = await _client(host)
            await _hello(client)
            stored = await _ask(client, Request(id=1, op=Op.SET, path="a.b", value={"x": 1}))
            read = await _ask(client, Request(id=2, op=Op.GET, path="a.b"))

        assert stored.ok and stored.result is None
        assert read.result == {"x": 1} and host.values == {"a.b": {"x": 1}}

    async def test_a_call_answers_a_value_or_a_function_of_its_params_or_nothing(self) -> None:
        async with FakeHost(
            answers={"chat.append": "view-1", "echo": lambda params: {"got": params}}
        ) as host:
            client = await _client(host)
            await _hello(client)
            fixed = await _ask(client, Request(id=1, op=Op.CALL, path="chat.append"))
            echoed = await _ask(
                client, Request(id=2, op=Op.CALL, path="echo", params={"text": "hi"})
            )
            nothing = await _ask(client, Request(id=3, op=Op.CALL, path="unknown.method"))

        assert (fixed.ok, fixed.result) == (True, "view-1")
        assert echoed.result == {"got": {"text": "hi"}}
        assert (nothing.ok, nothing.result) == (True, None)

    async def test_a_refused_member_is_refused_for_every_op_with_its_code(self) -> None:
        refusals = {"mcp.servers": ("not_granted", "not granted 'mcp'")}
        async with FakeHost(values={"mcp.servers": 1}, refusals=refusals) as host:
            client = await _client(host)
            await _hello(client)
            replies = [
                await _ask(client, Request(id=i, op=op, path="mcp.servers"))
                for i, op in enumerate((Op.GET, Op.SET, Op.CALL), start=1)
            ]

        for reply in replies:
            assert reply.ok is False and reply.error is not None
            assert (reply.error.code, reply.error.message) == ("not_granted", "not granted 'mcp'")
        assert host.values == {"mcp.servers": 1}  # the refused set stored nothing
        assert [c.op for c in host.calls] == ["get", "set", "call"]  # refusals are still kept

    async def test_every_get_set_and_call_is_kept_without_its_number(self) -> None:
        async with FakeHost(values={"v": 1}) as host:
            client = await _client(host)
            await _hello(client)
            await _ask(client, Request(id=7, op=Op.GET, path="v", window="w-1"))
            await _ask(client, Request(id=8, op=Op.SET, path="v", value=2, session="s-1"))
            await _ask(client, Request(id=9, op=Op.CALL, path="m", params={"a": 1}))
            await _ask(client, Request(id=10, op=Op.SUBSCRIBE, signals=["chat.x"]))

        assert host.calls == [
            HostCall(op="get", path="v", window="w-1"),
            HostCall(op="set", path="v", value=2, session="s-1"),
            HostCall(op="call", path="m", params={"a": 1}),
        ]

    def test_a_host_call_is_what_the_request_asked_and_nothing_more(self) -> None:
        request = Request(
            id=3, op=Op.CALL, path="p", window="w", session="s", params={"k": 1}, value=5
        )

        assert HostCall.of(request) == HostCall(
            op="call", path="p", window="w", session="s", params={"k": 1}, value=5
        )
        assert "id" not in HostCall.model_fields

    async def test_a_subscribe_is_answered_with_what_was_subscribed_and_kept(self) -> None:
        async with FakeHost() as host:
            client = await _client(host)
            await _hello(client)
            reply = await _ask(client, Request(id=1, op=Op.SUBSCRIBE, signals=["a.one", "b.two"]))
            await _ask(client, Request(id=2, op=Op.SUBSCRIBE, signals=["b.two", "c.three"]))

        assert reply.result == {"subscribed": ["a.one", "b.two"], "not_granted": [], "unknown": []}
        assert host.subscribed == {"a.one", "b.two", "c.three"}

    async def test_a_signal_reaches_only_a_connection_that_subscribed_to_it(self) -> None:
        async with FakeHost() as host:
            client = await _client(host)
            await _hello(client)
            await host.emit("chat.run_completed", {"n": 0})  # nobody subscribed: nothing sent
            await _ask(client, Request(id=1, op=Op.SUBSCRIBE, signals=["chat.run_completed"]))
            await host.emit("chat.other", {"n": 1})
            await host.emit("chat.run_completed", {"n": 2})

            message = SignalMessage.model_validate_json(await asyncio.wait_for(client.recv(), 5))

        assert (message.signal, message.value) == ("chat.run_completed", {"n": 2})

    async def test_wait_subscribed_returns_when_the_extension_subscribes_and_times_out(
        self,
    ) -> None:
        async with FakeHost() as host:
            client = await _client(host)
            await _hello(client)
            waiting = asyncio.ensure_future(host.wait_subscribed("chat.x"))
            await asyncio.sleep(0.05)
            assert not waiting.done()
            await _ask(client, Request(id=1, op=Op.SUBSCRIBE, signals=["chat.x"]))
            await asyncio.wait_for(waiting, 5)
            await host.wait_subscribed("chat.x")  # already so: returns at once
            with pytest.raises(TimeoutError):
                await host.wait_subscribed("never", timeout=0.05)

    async def test_a_hook_is_sent_with_an_id_and_returns_the_params_of_its_answer(self) -> None:
        async with FakeHost() as host:
            client = await _client(host)
            await _hello(client)
            asking = asyncio.ensure_future(host.hook("PreToolUse", {"tool": "t"}, caller=ADA))
            message = HookMessage.model_validate_json(await asyncio.wait_for(client.recv(), 5))
            reply = await _ask(
                client,
                Request(
                    id=1,
                    op=Op.ANSWER,
                    params={"hook": message.id, "outcome": "reject", "reason": "no"},
                ),
            )
            answer = await asyncio.wait_for(asking, 5)

        assert (message.op, message.event, message.value) == ("hook", "PreToolUse", {"tool": "t"})
        assert message.id == "h-1"
        assert message.principal == ADA.model_dump(mode="json")
        assert reply.ok
        assert answer == {"hook": "h-1", "outcome": "reject", "reason": "no"}

    async def test_a_hook_for_nobody_carries_no_principal_and_ids_count_up(self) -> None:
        async with FakeHost() as host:
            client = await _client(host)
            await _hello(client)
            ids = []
            for _ in range(2):
                asking = asyncio.ensure_future(host.hook("Stop", {}, timeout=0.1))
                message = HookMessage.model_validate_json(await asyncio.wait_for(client.recv(), 5))
                ids.append(message.id)
                assert message.principal is None
                with pytest.raises(TimeoutError):
                    await asking

        assert ids == ["h-1", "h-2"]

    async def test_an_answer_nothing_waits_for_is_refused_as_not_found(self) -> None:
        async with FakeHost() as host:
            client = await _client(host)
            await _hello(client)
            reply = await _ask(
                client, Request(id=1, op=Op.ANSWER, params={"hook": "h-9", "outcome": "allow"})
            )

        assert reply.ok is False and reply.error is not None
        assert (reply.error.code, reply.error.message) == ("not_found", "nothing waits on it")

    async def test_tell_sends_a_hook_with_no_id_and_waits_for_a_connection(self) -> None:
        async with FakeHost() as host:
            with pytest.raises(TimeoutError):
                await host.tell("SessionStart", {}, timeout=0.05)  # nobody is connected
            client = await _client(host)
            await _hello(client)
            await host.tell("SessionStart", {"session_id": "s-1"}, caller=ADA)
            message = HookMessage.model_validate_json(await asyncio.wait_for(client.recv(), 5))

        assert (message.id, message.event, message.value) == (
            None,
            "SessionStart",
            {"session_id": "s-1"},
        )
        assert message.principal == ADA.model_dump(mode="json")

    async def test_a_hook_asked_before_the_extension_connects_is_sent_when_it_does(self) -> None:
        async with FakeHost() as host:
            asking = asyncio.ensure_future(host.hook("Stop", {"n": 1}, timeout=5))
            await asyncio.sleep(0.1)
            client = await _client(host)
            await _hello(client)
            message = HookMessage.model_validate_json(await asyncio.wait_for(client.recv(), 5))
            await _ask(
                client, Request(id=1, op=Op.ANSWER, params={"hook": message.id, "outcome": "allow"})
            )

            assert (await asking)["outcome"] == "allow"

    async def test_an_answer_that_comes_after_the_hook_gave_up_is_not_found(self) -> None:
        async with FakeHost() as host:
            client = await _client(host)
            await _hello(client)
            with pytest.raises(TimeoutError):
                await host.hook("Stop", {}, timeout=0.05)
            message = HookMessage.model_validate_json(await asyncio.wait_for(client.recv(), 5))
            late = await _ask(
                client, Request(id=1, op=Op.ANSWER, params={"hook": message.id, "outcome": "allow"})
            )

        assert late.ok is False and late.error is not None and late.error.code == "not_found"
        assert host._hooks == {}  # a hook that gave up is not kept waiting

    async def test_a_hook_waits_for_a_connection_before_it_asks(self) -> None:
        async with FakeHost() as host:
            with pytest.raises(TimeoutError):
                await host.hook("Stop", {}, timeout=0.05)

    async def test_a_signal_and_a_hook_go_to_every_connection(self) -> None:
        async with FakeHost() as host:
            a, b = await _client(host), await _client(host)
            await _hello(a)
            await _hello(b)
            for i, c in enumerate((a, b), start=1):
                await _ask(c, Request(id=i, op=Op.SUBSCRIBE, signals=["s"]))
            await host.emit("s", 1)
            await host.tell("E", 2)

            for c in (a, b):
                assert json.loads(await asyncio.wait_for(c.recv(), 5))["op"] == "signal"
                assert json.loads(await asyncio.wait_for(c.recv(), 5))["op"] == "hook"

    async def test_an_extension_reads_and_writes_the_host_through_it(self) -> None:
        async with FakeHost(values={"chat.processing": False}, granted=("chat.read",)) as host:
            ext = IgniExtension("acme.example", environ=host.environment())
            try:
                assert await ext.host.chat.processing is False
                assert [c.path for c in host.calls] == ["chat.processing"]
            finally:
                await ext.aclose()


# ── HostHarness ──


def _an_extension() -> IgniExtension:
    ext = IgniExtension("acme.example", environ={})

    @ext.tool(hints=READS)
    async def whoami(prefix: str = "") -> str:
        caller = Caller.current()
        return f"{prefix}{caller.id if caller else 'nobody'}"

    return ext


class TestHostHarness:
    async def test_the_session_is_not_there_until_the_harness_is_entered(self) -> None:
        harness = HostHarness(_an_extension())

        with pytest.raises(RuntimeError, match="enter the harness first"):
            _ = harness.session

    async def test_a_tool_is_called_over_the_session_for_a_caller_or_nobody(self) -> None:
        async with HostHarness(_an_extension()) as host:
            for_ada = await host.call("whoami", {"prefix": "it is "}, caller=ADA)
            for_nobody = await host.call("whoami")
            listed = await host.session.list_tools()

        assert "it is u-ada" in str(for_ada.content)
        assert "nobody" in str(for_nobody.content)
        assert [t.name for t in listed.tools] == ["whoami"]

    def test_request_meta_is_the_dict_it_is_given(self) -> None:
        values = {"igni/principal": {"id": "u"}, "other": 1}

        assert HostHarness.request_meta(values) == values

    async def test_notifications_are_kept_parsed_and_as_they_crossed_the_wire(self) -> None:
        ext = _an_extension()
        note = LocalNotification(
            kind="k", title="T", body="B", target=Target(page="acme.example"), event_key="e:1"
        )

        async with HostHarness(ext) as host:
            await ext.host.notifications.notify(note)
            await ext.host.notifications.notify(note.model_copy(update={"kind": "k2"}))
            seen = await host.received(2)

        assert [n.kind for n in seen] == ["k", "k2"]
        assert host.notifications == seen
        assert [m["method"] for m in host.raw] == ["notifications/igni/notify"] * 2
        assert host.raw[0]["params"]["kind"] == "k"
        assert host.conditions == []

    async def test_conditions_are_kept_in_order_and_igni_methods_are_the_two_it_taps(self) -> None:
        ext = _an_extension()

        async with HostHarness(ext) as host:
            await ext.prompt.hold("a", True)
            await ext.prompt.hold("b", False)
            said = await host.conditions_said(2)

        assert said == [{"a": True}, {"b": False}]
        assert host.notifications == []
        assert {
            "notifications/igni/notify",
            "notifications/igni/conditions",
        } == HostHarness.IGNI_METHODS

    async def test_waiting_for_more_than_will_come_times_out_after_the_timeout(self) -> None:
        async with HostHarness(_an_extension(), timeout=0.1) as host:
            with pytest.raises(TimeoutError):
                await host.received(1)
            with pytest.raises(TimeoutError):
                await host.conditions_said(1)

    async def test_what_was_already_said_is_returned_at_once_as_a_copy(self) -> None:
        ext = _an_extension()

        async with HostHarness(ext) as host:
            await ext.prompt.hold("a", True)
            first = await host.conditions_said(1)
            first.append({"junk": True})
            again = await host.conditions_said(1)

        assert again == [{"a": True}]

    async def test_received_hands_back_a_copy(self) -> None:
        ext = _an_extension()
        note = LocalNotification(
            kind="k", title="T", body="B", target=Target(page="acme.example"), event_key="e:1"
        )

        async with HostHarness(ext) as host:
            await ext.host.notifications.notify(note)
            first = await host.received(1)
            first.clear()

            assert await host.received(1) == [note]

    async def test_only_igni_s_own_notifications_are_kept_raw(self) -> None:
        from mcp import types

        harness = HostHarness(_an_extension())
        source_send, source = anyio.create_memory_object_stream[SessionMessage](4)
        sink, sink_receive = anyio.create_memory_object_stream[SessionMessage | Exception](4)
        other = types.JSONRPCNotification(jsonrpc="2.0", method="notifications/other")
        igni = types.JSONRPCNotification(
            jsonrpc="2.0", method="notifications/igni/conditions", params={"conditions": {}}
        )
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(harness._tap, source, sink)
            await source_send.send(SessionMessage(other))
            await source_send.send(SessionMessage(igni))
            for _ in range(2):  # both are passed on to the client either way
                await sink_receive.receive()
            await source_send.aclose()

        assert [m["method"] for m in harness.raw] == ["notifications/igni/conditions"]

    async def test_a_call_that_outlasts_the_timeout_is_an_error(self) -> None:
        ext = IgniExtension("acme.example", environ={})

        @ext.tool(hints=READS)
        async def slow() -> str:
            await asyncio.sleep(2)
            return "late"

        async with HostHarness(ext, timeout=0.2) as host:
            with pytest.raises(MCPError):
                await host.call("slow")

    async def test_it_leaves_nothing_running_when_it_exits(self) -> None:
        harness = HostHarness(_an_extension())
        async with harness:
            await harness.call("whoami")

        assert harness._tasks is not None and harness._tasks.cancel_scope.cancel_called


# ── FakeHostTokenEndpoint ──


def _get(host: FakeHostTokenEndpoint, secret: str | None = None, **headers: str) -> httpx.Response:
    bearer = host.secret if secret is None else secret
    return host.handle(
        httpx.Request(
            "GET", host.TOKEN_URL, headers={"authorization": f"Bearer {bearer}", **headers}
        )
    )


def _claims(token: str) -> dict[str, Any]:
    body = token.split(".")[1]
    decoded: dict[str, Any] = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    return decoded


class TestFakeHostTokenEndpoint:
    def test_the_environment_names_the_service_the_endpoint_and_the_secret(self) -> None:
        host = FakeHostTokenEndpoint(service_url="http://svc.test")

        assert host.environment(EXTRA="1") == {
            "IGNI_SERVICE_URL": "http://svc.test",
            "IGNI_SERVICE_TOKEN_URL": "http://127.0.0.1:47011/igni/service-token",
            "IGNI_SERVICE_TOKEN_SECRET": host.secret,
            "EXTRA": "1",
        }
        assert FakeHostTokenEndpoint().service_url == "http://service.test"
        assert FakeHostTokenEndpoint().secret != host.secret

    def test_a_token_is_an_unsigned_jwt_of_the_person_signed_in(self) -> None:
        host = FakeHostTokenEndpoint(expires_in=42)
        response = _get(host)
        body = response.json()

        assert response.status_code == 200
        assert body["expires_in"] == 42 and body["service_url"] == "http://service.test"
        claims = _claims(body["access_token"])
        assert (claims["sub"], claims["org"], claims["email"], claims["name"]) == (
            "u-ada",
            "org-acme",
            "ada@acme.test",
            "Ada",
        )
        assert (claims["aud"], claims["token_use"]) == ("http://service.test", "user")
        assert body["access_token"].count(".") == 2
        assert host.issued == [body["access_token"]]

    def test_every_token_has_a_jti_of_its_own(self) -> None:
        host = FakeHostTokenEndpoint()
        first, second = (_claims(_get(host).json()["access_token"]) for _ in range(2))

        assert first["jti"] and second["jti"] and first["jti"] != second["jti"]
        assert len(host.issued) == 2 and host.person is not None and host.person.jti == ""

    def test_a_request_is_kept_even_when_it_is_refused(self) -> None:
        host = FakeHostTokenEndpoint()
        _get(host, "wrong")
        _get(host)

        assert len(host.requests) == 2

    def test_a_wrong_or_missing_secret_is_a_401_and_hands_out_nothing(self) -> None:
        host = FakeHostTokenEndpoint()
        bare = host.handle(httpx.Request("GET", host.TOKEN_URL))

        assert _get(host, "wrong").status_code == 401
        assert bare.status_code == 401
        assert host.issued == []

    def test_another_path_or_method_is_a_404(self) -> None:
        host = FakeHostTokenEndpoint()
        auth = {"authorization": f"Bearer {host.secret}"}

        assert (
            host.handle(
                httpx.Request("GET", "http://127.0.0.1:47011/other", headers=auth)
            ).status_code
            == 404
        )
        assert host.handle(httpx.Request("POST", host.TOKEN_URL, headers=auth)).status_code == 404

    def test_sign_out_is_a_503_until_somebody_signs_in_and_tokens_are_theirs(self) -> None:
        host = FakeHostTokenEndpoint()
        host.sign_out()
        assert host.person is None and _get(host).status_code == 503
        host.sign_in(user_id="u-grace", org_id="org-b", email="g@b.test", name="Grace")
        claims = _claims(_get(host).json()["access_token"])

        assert (claims["sub"], claims["org"], claims["email"], claims["name"]) == (
            "u-grace",
            "org-b",
            "g@b.test",
            "Grace",
        )

    def test_a_person_signed_in_without_email_or_name_has_them_empty(self) -> None:
        host = FakeHostTokenEndpoint()
        host.sign_in(user_id="u-x", org_id="o")

        assert host.person == TokenClaims(
            sub="u-x", org="o", email="", name="", aud="http://service.test", jti=""
        )

    def test_a_token_is_handed_out_to_the_person_it_is_asked_for_and_nobody_else(self) -> None:
        host = FakeHostTokenEndpoint()
        header = Caller.TOKEN_HEADER

        assert _get(host, **{header: "person:u-ada"}).status_code == 200
        refused = _get(host, **{header: "person:u-grace"})
        assert refused.status_code == 403 and "person:u-grace" in refused.json()["error"]
        assert _get(host, **{header: "app:u-ada"}).status_code == 403

    def test_a_minter_makes_the_token_from_the_claims(self) -> None:
        seen: list[TokenClaims] = []

        def minter(claims: TokenClaims) -> str:
            seen.append(claims)
            return f"signed-for-{claims.sub}"

        host = FakeHostTokenEndpoint(minter=minter, user_id="u-z")

        assert host.minter is minter
        assert _get(host).json()["access_token"] == "signed-for-u-z"
        assert seen[0].aud == "http://service.test" and seen[0].jti

    def test_unsigned_is_the_default_minter(self) -> None:
        host = FakeHostTokenEndpoint()
        claims = TokenClaims(sub="s", org="o", aud="a", jti="j")
        token = host.unsigned(claims)
        header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))

        assert host.minter == host.unsigned
        assert header == {"alg": "RS256", "typ": "JWT"}
        assert _claims(token) == claims.model_dump()
        assert "=" not in token

    async def test_an_extension_signed_in_through_it_reads_the_person_and_their_token(
        self,
    ) -> None:
        endpoint = FakeHostTokenEndpoint()
        ext = IgniExtension(
            "acme.example", environ=endpoint.environment(), token_transport=endpoint.transport
        )
        try:
            token = await ext.tokens.token()
            signed_in = ext.tokens.signed_in
        finally:
            await ext.aclose()

        assert token == endpoint.issued[0]
        assert signed_in is not None and signed_in.user_id == "u-ada"

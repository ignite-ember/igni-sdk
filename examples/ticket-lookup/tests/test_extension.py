"""The extension's own behaviour: its two tools, its hook and its identity, as igni drives them."""

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "extension" / "src"))

from igni_extension import Caller, CallerKind  # noqa: E402
from igni_extension.service import ServiceAccess  # noqa: E402
from igni_extension.testing import FakeHost, FakeHostTokenEndpoint, HostHarness  # noqa: E402

SOURCE = HERE.parent / "extension" / "src" / "acme_tickets_extension" / "__init__.py"

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


ADA = Caller(kind=CallerKind.PERSON, id="u-ada", org="org-1", group="g-1")


def _fresh(environ: dict[str, str], monkeypatch: pytest.MonkeyPatch):
    """The example's module, read again as a process igni starts: with `environ` as its environment."""
    for key in [k for k in os.environ if k.startswith("IGNI_")]:
        monkeypatch.delenv(key)
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("acme_tickets_fresh", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _service_answering(
    module, token: FakeHostTokenEndpoint, handler, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point the extension at a service that answers with `handler`, behind the token endpoint."""
    access = ServiceAccess(
        "acme.tickets",
        module.ext.environment.service,
        token_transport=token.transport,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(module.ext, "_service", access)


async def test_an_unknown_ticket_is_an_answer_not_an_error() -> None:
    from acme_tickets_extension import ext

    async with HostHarness(ext) as host:
        result = await host.call("lookup_ticket", {"ticket_id": "T-9999"}, caller=ADA)
    assert not result.is_error
    assert json.loads(result.content[0].text) == {
        "error": "no ticket T-9999",
        "known": ["T-1001", "T-1002"],
    }


async def test_a_ticket_id_matches_in_any_case_and_the_error_keeps_the_casing_given() -> None:
    from acme_tickets_extension import ext

    async with HostHarness(ext) as host:
        found = await host.call("lookup_ticket", {"ticket_id": "t-1002"}, caller=ADA)
        missing = await host.call("lookup_ticket", {"ticket_id": "t-5"}, caller=ADA)
    assert json.loads(found.content[0].text) == {
        "id": "T-1002",
        "title": "Printer on 3rd floor offline",
        "status": "closed",
        "owner": "grace",
    }
    assert json.loads(missing.content[0].text)["error"] == "no ticket t-5"


async def test_a_hostile_ticket_id_is_an_unknown_ticket() -> None:
    from acme_tickets_extension import ext

    hostile = 'T-1001", "owner": "root\n\u202e'
    async with HostHarness(ext) as host:
        empty = await host.call("lookup_ticket", {"ticket_id": ""}, caller=ADA)
        bad = await host.call("lookup_ticket", {"ticket_id": hostile}, caller=ADA)
    assert json.loads(empty.content[0].text)["error"] == "no ticket "
    assert json.loads(bad.content[0].text) == {
        "error": f"no ticket {hostile}",
        "known": ["T-1001", "T-1002"],
    }


async def test_the_tools_say_what_they_are_to_igni() -> None:
    from acme_tickets_extension import ext

    async with HostHarness(ext) as host:
        listed = {t.name: t.annotations for t in (await host.session.list_tools()).tools}
    assert set(listed) == {"lookup_ticket", "ticket_from_service"}
    own, service = listed["lookup_ticket"], listed["ticket_from_service"]
    assert own is not None and service is not None
    assert (own.read_only_hint, own.destructive_hint, own.idempotent_hint, own.open_world_hint) == (
        True,
        False,
        True,
        False,
    )
    assert (
        service.read_only_hint,
        service.destructive_hint,
        service.idempotent_hint,
        service.open_world_hint,
    ) == (True, False, True, True)


def test_the_extension_is_the_one_the_manifest_names() -> None:
    from acme_tickets_extension import ext

    manifest = json.loads((HERE.parent / "extension" / "manifest.json").read_text())
    assert ext.id == manifest["id"] == "acme.tickets"


async def test_the_service_tool_fetches_as_the_signed_in_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = FakeHostTokenEndpoint()
    token.sign_in(user_id="u-ada", org_id="org-1")
    module = _fresh(token.environment(), monkeypatch)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text='{"id": "T-1001"}')

    _service_answering(module, token, handler, monkeypatch)
    async with HostHarness(module.ext) as host:
        result = await host.call("ticket_from_service", {"ticket_id": "T-1001"}, caller=ADA)
    assert result.content[0].text == '{"id": "T-1001"}'
    [request] = seen
    assert request.url.path == "/v1/tickets/T-1001"
    assert request.headers["authorization"] == f"Bearer {token.issued[0]}"


async def test_the_service_tool_asks_to_sign_in_when_nobody_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = FakeHostTokenEndpoint()
    token.sign_out()
    module = _fresh(token.environment(), monkeypatch)
    reached: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        reached.append(request)
        return httpx.Response(200)

    _service_answering(module, token, handler, monkeypatch)
    async with HostHarness(module.ext) as host:
        result = await host.call("ticket_from_service", {"ticket_id": "T-1001"}, caller=ADA)
    assert not result.is_error
    assert result.content[0].text == "Sign in to igni to reach the ticket service."
    assert reached == []


async def test_the_service_tool_fails_when_the_service_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = FakeHostTokenEndpoint()
    token.sign_in(user_id="u-ada", org_id="org-1")
    module = _fresh(token.environment(), monkeypatch)
    _service_answering(
        module, token, lambda request: httpx.Response(404, text="no such ticket"), monkeypatch
    )
    async with HostHarness(module.ext) as host:
        result = await host.call("ticket_from_service", {"ticket_id": "T-9"}, caller=ADA)
    assert result.is_error
    assert "404" in result.content[0].text


async def test_the_service_tool_keeps_a_ticket_id_inside_its_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = FakeHostTokenEndpoint()
    token.sign_in(user_id="u-ada", org_id="org-1")
    module = _fresh(token.environment(), monkeypatch)
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, text="ok")

    _service_answering(module, token, handler, monkeypatch)
    async with HostHarness(module.ext) as host:
        for hostile in ("../igni/subjects/u-ada", "T-1001?admin=1", "a b#c"):
            await host.call("ticket_from_service", {"ticket_id": hostile}, caller=ADA)
    assert [(u.raw_path.decode(), u.query) for u in seen] == [
        (b"/v1/tickets/..%2Figni%2Fsubjects%2Fu-ada".decode(), b""),
        ("/v1/tickets/T-1001%3Fadmin%3D1", b""),
        ("/v1/tickets/a%20b%23c", b""),
    ]


async def test_the_hook_records_each_tool_in_the_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with FakeHost(extension_id="acme.tickets") as fake:
        module = _fresh(fake.environment(IGNI_EXTENSION_DATA=str(tmp_path)), monkeypatch)
        await module.ext.connect()
        task = asyncio.create_task(module.ext.connection.serve_forever())
        try:
            for name in ("lookup_ticket", "ticket_from_service", "evil\nforged_line"):
                answer = await fake.hook(
                    "PostToolUse",
                    {"session_id": "s-1", "tool_name": name, "tool_args": {}, "result": "x"},
                )
                assert answer["outcome"] == "allow"
        finally:
            task.cancel()
            await module.ext.aclose()
    assert (tmp_path / "tool-audit.log").read_text().splitlines() == [
        "lookup_ticket",
        "ticket_from_service",
        "evil forged_line",
    ]


async def test_the_hook_writes_nothing_when_igni_did_not_start_the_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    async with FakeHost(extension_id="acme.tickets") as fake:
        module = _fresh(fake.environment(), monkeypatch)
        assert module.ext.environment.data_dir is None
        await module.ext.connect()
        task = asyncio.create_task(module.ext.connection.serve_forever())
        try:
            answer = await fake.hook(
                "PostToolUse",
                {"session_id": "s-1", "tool_name": "lookup_ticket", "tool_args": {}, "result": "x"},
            )
        finally:
            task.cancel()
            await module.ext.aclose()
    assert answer["outcome"] == "allow"
    assert list(tmp_path.iterdir()) == []


def test_main_runs_the_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    import acme_tickets_extension as example

    ran: list[bool] = []
    monkeypatch.setattr(example.ext, "run", lambda: ran.append(True))
    example.main()
    assert ran == [True]

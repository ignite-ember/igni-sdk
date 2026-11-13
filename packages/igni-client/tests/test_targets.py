"""Where an igni is: how a target is found, opened, refused and described."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Request, Response

from igni_client import AuthError, Local, NotAllowed, NotSupported, Unavailable
from igni_client import targets as targets_module
from igni_client.targets import SUBPROTOCOL, Fleet, require_fleet


class _Token:
    async def token(self) -> str:
        return "t-ada"


def _fleet(url: str = "http://gateway.test", **kwargs: Any) -> Fleet:
    return Fleet(url, auth=_Token(), **kwargs)


def _gateway(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@asynccontextmanager
async def _answering(status: int, body: bytes = b"") -> AsyncIterator[str]:
    """A server that refuses every handshake with `status` and `body`; its address."""

    def refuse(connection: ServerConnection, request: Request) -> Response:
        return Response(status, "Refused", Headers(), body)

    async def never(connection: ServerConnection) -> None:
        raise AssertionError("nobody gets in")

    async with serve(never, "127.0.0.1", 0, process_request=refuse) as server:
        yield f"127.0.0.1:{next(iter(server.sockets)).getsockname()[1]}"


# ── Fleet's address ──


@pytest.mark.parametrize(
    ("given", "base", "connect"),
    [
        ("http://gateway.test", "http://gateway.test", "ws://gateway.test/v1/connect"),
        ("https://gateway.test/", "https://gateway.test", "wss://gateway.test/v1/connect"),
        ("ws://gateway.test:8080", "http://gateway.test:8080", "ws://gateway.test:8080/v1/connect"),
        ("wss://gateway.test", "https://gateway.test", "wss://gateway.test/v1/connect"),
        ("HTTPS://gateway.test", "https://gateway.test", "wss://gateway.test/v1/connect"),
        (
            "https://gateway.test/fleet?x=1#top",
            "https://gateway.test/fleet",
            "wss://gateway.test/fleet/v1/connect",
        ),
    ],
)
def test_the_gateways_address_gives_its_http_base_and_its_socket(
    given: str, base: str, connect: str
) -> None:
    fleet = _fleet(given)

    assert (fleet.base, fleet.connect_url) == (base, connect)


@pytest.mark.parametrize("given", ["ftp://gateway.test", "gateway.test", "file:///gateway"])
def test_a_gateway_address_that_is_not_http_or_ws_is_refused(given: str) -> None:
    with pytest.raises(ValueError, match=r"http\(s\):// or ws\(s\)://"):
        _fleet(given)


def test_a_target_describes_itself_and_says_whether_it_is_worth_reopening(tmp_path: Path) -> None:
    fleet = _fleet("https://gateway.test/fleet")

    assert fleet.describe() == "igni in Fleet via https://gateway.test/fleet"
    assert fleet.reconnects and fleet.standing == "window"
    assert Local(url="ws://127.0.0.1:9").describe() == "igni at ws://127.0.0.1:9"
    assert Local(tmp_path).describe() == f"igni at {tmp_path.resolve()}"
    assert not Local(tmp_path).reconnects


def test_require_fleet_gives_the_fleet_and_names_what_needed_it_otherwise(tmp_path: Path) -> None:
    fleet = _fleet()

    assert require_fleet(fleet, "commands") is fleet
    with pytest.raises(NotSupported, match=r"commands needs Fleet's gateway; igni at .* has none"):
        require_fleet(Local(tmp_path), "commands")


def test_a_local_project_is_found_from_a_home_relative_or_a_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    assert Local("~/api").project_dir == tmp_path.resolve() / "api"
    assert Local("work/api").project_dir == tmp_path.resolve() / "work" / "api"
    assert Local().project_dir == tmp_path.resolve()


# ── Fleet's HTTP ──


async def test_a_gateway_call_carries_the_producers_token_and_the_callers_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    fleet = _fleet("https://gateway.test/fleet", http=_gateway(handler))

    await fleet.request("GET", "/v1/me", headers={"X-Trace": "7"})
    await fleet.request("GET", "/v1/me", headers={"Authorization": "Bearer other"})

    assert str(seen[0].url) == "https://gateway.test/fleet/v1/me"
    assert seen[0].headers["Authorization"] == "Bearer t-ada" and seen[0].headers["X-Trace"] == "7"
    assert seen[1].headers["Authorization"] == "Bearer other", "what the caller sets wins"


async def test_a_gateway_that_cannot_be_reached_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    fleet = _fleet(http=_gateway(handler))

    with pytest.raises(Unavailable, match="the gateway at http://gateway.test did not answer"):
        await fleet.request("GET", "/v1/me")


async def test_a_streamed_gateway_call_carries_the_token_it_is_given_and_the_callers_headers() -> (
    None
):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="lines")

    fleet = _fleet(http=_gateway(handler))

    async with fleet.stream("POST", "/v1/commands", "t-given", headers={"X-Trace": "9"}) as reply:
        assert await reply.aread() == b"lines"

    assert seen[0].headers["Authorization"] == "Bearer t-given"
    assert seen[0].headers["X-Trace"] == "9"


async def test_closing_a_fleet_closes_only_the_http_client_it_made() -> None:
    mine = _fleet()
    theirs = _gateway(lambda request: httpx.Response(200))

    await mine.aclose()
    await mine.aclose()  # closing twice is harmless
    await _fleet(http=theirs).aclose()

    assert mine._http.is_closed
    assert not theirs.is_closed
    assert (await theirs.get("http://gateway.test/")).status_code == 200


# ── Local's lockfile ──


def _lock(project: Path, content: str) -> None:
    (project / ".igni").mkdir(exist_ok=True)
    (project / ".igni" / "backend.lock").write_text(content)


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "",
        "{}",
        '{"pid": 1}',
        '{"port": "eighty"}',
        '{"port": null}',
        "[1, 2]",
        '"port"',
    ],
)
async def test_a_lockfile_that_does_not_hold_a_port_is_not_an_igni_lockfile(
    tmp_path: Path, content: str
) -> None:
    _lock(tmp_path, content)

    with pytest.raises(Unavailable, match="backend.lock is not an igni lockfile"):
        await Local(tmp_path).open()


async def test_a_lockfile_with_an_empty_token_means_igni_takes_none(tmp_path: Path) -> None:
    async with _answering(500) as address:
        _lock(tmp_path, json.dumps({"port": int(address.split(":")[1]), "ws_token": ""}))
        local = Local(tmp_path)
        with pytest.raises(Unavailable):
            await local.open()

    assert local.standing == "window"


def test_an_empty_approver_token_is_no_approver_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IGNI_APPROVER_TOKEN", "")

    assert not Local(tmp_path).approves
    assert Local(tmp_path).standing == "unknown"
    monkeypatch.setenv("IGNI_APPROVER_TOKEN", "from-the-environment")
    assert Local(tmp_path).approves


# ── Opening ──


async def test_a_local_igni_is_offered_its_token_as_the_subprotocol_igni_wants() -> None:
    offered: list[str] = []

    async def handler(connection: ServerConnection) -> None:
        assert connection.request is not None
        offered.append(connection.request.headers["Sec-WebSocket-Protocol"])

    async with serve(handler, "127.0.0.1", 0, subprotocols=[SUBPROTOCOL]) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        link = await Local(url=f"ws://127.0.0.1:{port}", token="launch-secret").open()
        await link.wait_closed()

    assert offered == ["igni.v1, igni-token.launch-secret"]


async def test_a_frame_much_larger_than_a_websocket_default_is_received() -> None:
    big = "x" * 3_000_000

    async def handler(connection: ServerConnection) -> None:
        await connection.send(big)

    async with serve(handler, "127.0.0.1", 0, max_size=None, subprotocols=[SUBPROTOCOL]) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        link = await Local(url=f"ws://127.0.0.1:{port}").open()
        received = await link.recv()
        await link.close()

    assert received == big


async def test_an_igni_nobody_listens_for_is_unavailable() -> None:
    with socket.socket() as spare:
        spare.bind(("127.0.0.1", 0))
        port = spare.getsockname()[1]

    with pytest.raises(Unavailable, match=f"igni at ws://127.0.0.1:{port} did not answer"):
        await Local(url=f"ws://127.0.0.1:{port}").open()


async def test_an_igni_that_accepts_and_never_answers_is_unavailable_when_the_wait_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(targets_module, "OPEN_TIMEOUT", 0.2)
    held: list[asyncio.StreamWriter] = []

    async def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        held.append(writer)
        await asyncio.sleep(5)

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        with pytest.raises(Unavailable, match="igni at .* did not answer"):
            await Local(url=f"ws://127.0.0.1:{port}").open()
        with pytest.raises(Unavailable, match="the gateway at .* did not answer"):
            await _fleet(f"ws://127.0.0.1:{port}").open()
    finally:
        for writer in held:
            writer.close()
        server.close()


@pytest.mark.parametrize(("status", "error"), [(401, AuthError), (403, NotAllowed)])
async def test_the_gateway_refuses_a_credential_as_unauthorised_and_a_producer_as_not_allowed(
    status: int, error: type[Exception]
) -> None:
    async with _answering(status, b'{"error_description": "token expired"}') as address:
        with pytest.raises(error, match="the gateway refused .*: token expired"):
            await _fleet(f"ws://{address}").open()


@pytest.mark.parametrize(
    ("body", "said"),
    [
        (b'{"error_description": "token expired", "error": "invalid_token"}', "token expired"),
        (b'{"error": "invalid_token"}', "invalid_token"),
        (b"plain words\n", "plain words"),
        (b'["not", "a", "dict"]', '["not", "a", "dict"]'),
        (b"", "unauthorized"),
        (b"caf\xe9 \xff", "caf� �"),
    ],
)
async def test_a_refusal_is_read_from_its_bytes_whatever_they_hold(body: bytes, said: str) -> None:
    async with _answering(401, body) as address:
        with pytest.raises(AuthError) as refused:
            await _fleet(f"ws://{address}").open()

    assert str(refused.value) == f"the gateway refused the credential: {said}"


async def test_a_status_that_is_not_a_refusal_of_the_credential_is_unavailable_with_what_was_said() -> (
    None
):
    async with _answering(502, b'{"error": "vm asleep"}') as address:
        with pytest.raises(Unavailable) as refused:
            await _fleet(f"ws://{address}").open()
    assert str(refused.value) == "the gateway answered 502: vm asleep"


async def test_a_local_igni_answering_500_is_unavailable_with_what_it_said() -> None:
    async with _answering(500, b"boom") as address:
        with pytest.raises(Unavailable, match=f"igni at ws://{address} answered 500: boom"):
            await Local(url=f"ws://{address}").open()


async def test_a_local_igni_refusing_with_401_is_an_auth_error() -> None:
    async with _answering(401, b"no") as address:
        with pytest.raises(AuthError, match=f"igni at ws://{address} refused the credential: no"):
            await Local(url=f"ws://{address}").open()


def test_a_refusal_that_carries_no_body_still_says_what_was_refused() -> None:
    refused = InvalidStatus(Response(403, "Forbidden", Headers(), None))  # type: ignore[arg-type]

    error = targets_module._refusal(refused, "the gateway")

    assert isinstance(error, NotAllowed)
    assert str(error) == "the gateway refused the connection: forbidden"

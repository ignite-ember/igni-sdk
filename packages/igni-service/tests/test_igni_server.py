"""igni's address as a service holds it: trimmed, discovered once, never closed for the caller."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from igni_service.errors import IgniUnavailable
from igni_service.server import Discovery, IgniServer

DOCUMENT = {
    "issuer": "https://igni.public.test",
    "authorization_endpoint": "https://igni.public.test/portal/sign-in",
}


class Metadata:
    """igni's discovery endpoint: answers what it is told to and counts its calls."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.answer = httpx.Response(200, json=DOCUMENT)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        await asyncio.sleep(0)  # a real answer takes time: callers meet on the lock
        return self.answer


@pytest.fixture
def metadata() -> Metadata:
    return Metadata()


@pytest.fixture
def server(metadata: Metadata) -> IgniServer:
    http = httpx.AsyncClient(transport=httpx.MockTransport(metadata.handle))
    return IgniServer(base_url="http://igni.internal:8080", http=http)


def test_the_address_is_trimmed_and_loses_its_trailing_slashes() -> None:
    assert IgniServer(base_url="  http://igni.test///  ").base_url == "http://igni.test"
    assert IgniServer(base_url="").base_url == ""
    assert IgniServer(base_url=None).base_url == ""  # type: ignore[arg-type]
    assert IgniServer(base_url="   ").base_url == ""


def test_a_path_is_added_to_the_configured_address() -> None:
    server = IgniServer(base_url="http://igni.test/")

    assert server.url("/v1/clients") == "http://igni.test/v1/clients"


def test_an_app_has_no_url_of_its_own_and_a_service_s_is_normalised() -> None:
    assert IgniServer(base_url="http://igni.test").own_url == ""
    assert IgniServer(base_url="http://igni.test", timeout=3).timeout == 3
    service = IgniServer(base_url="http://igni.test", own_url="https://svc.test/")
    assert service.own_url == "https://svc.test"


async def test_discovery_reads_the_issuer_and_asks_the_configured_address(
    server: IgniServer, metadata: Metadata
) -> None:
    assert await server.issuer() == "https://igni.public.test"
    assert await server.authorization_endpoint() == "https://igni.public.test/portal/sign-in"
    assert [str(call.url) for call in metadata.calls] == [
        "http://igni.internal:8080/.well-known/openid-configuration"
    ]


async def test_discovery_is_read_once_even_when_callers_arrive_together(
    server: IgniServer, metadata: Metadata
) -> None:
    found = await asyncio.gather(*(server.discovery() for _ in range(5)))

    assert len(metadata.calls) == 1
    assert all(item is found[0] for item in found)
    await server.issuer()
    assert len(metadata.calls) == 1


async def test_an_issuer_loses_its_trailing_slash(server: IgniServer, metadata: Metadata) -> None:
    metadata.answer = httpx.Response(200, json={"issuer": "https://igni.public.test//"})

    assert await server.issuer() == "https://igni.public.test"


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500, text="down"),
        httpx.Response(404),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"authorization_endpoint": "https://x.test/"}),
        httpx.Response(200, json=["issuer"]),
    ],
    ids=["500", "404", "not-json", "no-issuer", "wrong-shape"],
)
async def test_unusable_metadata_is_igni_unavailable_and_is_asked_for_again(
    server: IgniServer, metadata: Metadata, answer: httpx.Response
) -> None:
    metadata.answer = answer
    with pytest.raises(IgniUnavailable, match="metadata"):
        await server.discovery()

    metadata.answer = httpx.Response(200, json=DOCUMENT)
    assert await server.issuer() == "https://igni.public.test"
    assert len(metadata.calls) == 2


async def test_a_network_failure_is_igni_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))

    with pytest.raises(IgniUnavailable, match="ConnectError"):
        await IgniServer(base_url="http://igni.test", http=http).discovery()


async def test_metadata_without_an_authorization_endpoint_is_igni_unavailable(
    server: IgniServer, metadata: Metadata
) -> None:
    metadata.answer = httpx.Response(200, json={"issuer": "https://igni.public.test"})

    assert Discovery.model_validate({"issuer": "x"}).authorization_endpoint == ""
    assert await server.issuer() == "https://igni.public.test"
    with pytest.raises(IgniUnavailable, match="authorization_endpoint"):
        await server.authorization_endpoint()


async def test_the_client_it_made_has_the_timeout_and_is_closed_and_closing_again_is_fine() -> None:
    server = IgniServer(base_url="http://igni.test", timeout=7.5)
    await server.aclose()  # before any client was made

    first = server.http
    assert server.http is first
    assert first.timeout.read == 7.5
    await server.aclose()
    assert first.is_closed
    await server.aclose()


async def test_a_client_the_caller_gave_is_left_open(server: IgniServer) -> None:
    given = server.http

    await server.aclose()

    assert not given.is_closed
    assert server.http is given
    await given.aclose()

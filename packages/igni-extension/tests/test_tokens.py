"""`igni_extension.tokens`: what the host's token endpoint may answer, and what is made of it."""

from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from igni_extension import (
    Caller,
    CallerKind,
    HostError,
    HostUnavailable,
    NotConfigured,
    NotSignedIn,
)
from igni_extension.environment import ServiceEndpoint
from igni_extension.testing import ManualClock
from igni_extension.tokens import HostTokenAuth, HostTokens, IssuedToken, SignedIn

ENDPOINT = ServiceEndpoint(
    url="http://service.test", token_url="http://host.test/token", token_secret="s3cret"
)


def jwt(claims: object) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"h.{body}.sig"


class Host:
    """A token endpoint that answers what it is told to, and keeps what it was asked."""

    def __init__(self, *replies: httpx.Response) -> None:
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply

    def tokens(self, **kwargs: object) -> HostTokens:
        return HostTokens(
            ENDPOINT,
            transport=httpx.MockTransport(self.handle),
            clock=ManualClock(),
            **kwargs,  # type: ignore[arg-type]
        )


def issued(token: str = "t-1", **more: object) -> httpx.Response:
    return httpx.Response(200, json={"access_token": token, **more})


def test_an_issued_token_defaults_to_ten_minutes_and_no_service_url() -> None:
    token = IssuedToken.model_validate({"access_token": "t"})

    assert (token.expires_in, token.service_url) == (600, "")


def test_a_token_needs_an_access_token() -> None:
    with pytest.raises(ValueError, match="access_token"):
        IssuedToken.model_validate({"expires_in": 5})


def test_signed_in_reads_the_claims_without_padding() -> None:
    claims = {"sub": "u-ada", "org": "org-acme", "email": "ada@acme.test", "name": "Ada"}
    assert SignedIn.of(jwt(claims)) == SignedIn(
        user_id="u-ada", org_id="org-acme", email="ada@acme.test", name="Ada"
    )


def test_a_missing_or_null_claim_is_empty_and_a_number_is_text() -> None:
    assert SignedIn.of(jwt({"sub": 7, "org": None})) == SignedIn(user_id="7")


@pytest.mark.parametrize(
    "token",
    [
        "",
        "opaque",
        "a.b",
        "a.!!!.c",
        "a." + base64.urlsafe_b64encode(b"not json").decode() + ".c",
        jwt([1, 2]),
        jwt("text"),
        jwt(None),
        jwt(7),
    ],
)
def test_a_token_that_is_not_a_jwt_names_nobody(token: str) -> None:
    assert SignedIn.of(token) == SignedIn()


def test_it_is_configured_only_with_both_the_url_and_the_secret() -> None:
    def configured(**fields: str) -> bool:
        return HostTokens(ServiceEndpoint(**fields)).configured

    assert configured(token_url="http://h", token_secret="s")
    assert not configured(token_url="http://h")
    assert not configured(token_secret="s")
    assert not configured()


async def test_an_unconfigured_process_asks_nobody() -> None:
    host = Host(issued())
    tokens = HostTokens(
        ServiceEndpoint(token_url="http://h"), transport=httpx.MockTransport(host.handle)
    )

    with pytest.raises(NotConfigured):
        await tokens.token()
    assert host.requests == []


async def test_the_host_is_asked_with_the_secret_and_no_caller_by_default() -> None:
    host = Host(issued())

    assert await host.tokens().token() == "t-1"

    [request] = host.requests
    assert request.headers["authorization"] == "Bearer s3cret"
    assert Caller.TOKEN_HEADER not in request.headers


async def test_a_refusal_names_whom_the_host_would_not_serve() -> None:
    host = Host(httpx.Response(403))

    with pytest.raises(HostError) as refused:
        await host.tokens().token()
    assert refused.value.code == "refused"
    assert "the signed-in person" in str(refused.value)

    ada = Caller(kind=CallerKind.PERSON, id="u-ada")
    with pytest.raises(HostError, match=r"person:u-ada"):
        await host.tokens().for_(ada).token()


async def test_a_token_is_asked_for_each_caller_and_kept_apart() -> None:
    host = Host(issued("for-ada"), issued("for-bob"))
    tokens = host.tokens()
    ada = Caller(kind=CallerKind.PERSON, id="u-ada")
    bob = Caller(kind=CallerKind.PERSON, id="u-bob")

    assert tokens.for_(ada) is tokens.for_(Caller(kind=CallerKind.PERSON, id="u-ada"))
    assert tokens.for_(ada) is not tokens.for_(bob)
    assert await tokens.for_(ada).token() == "for-ada"
    assert await tokens.for_(bob).token() == "for-bob"
    assert await tokens.for_(ada).token() == "for-ada"

    assert [r.headers[Caller.TOKEN_HEADER] for r in host.requests] == [
        "person:u-ada",
        "person:u-bob",
    ]
    assert all(r.headers["authorization"] == "Bearer s3cret" for r in host.requests)


async def test_a_caller_s_tokens_share_the_clock_and_transport_of_their_parent() -> None:
    host = Host(issued("t", expires_in=100))
    clock = ManualClock()
    tokens = HostTokens(ENDPOINT, transport=httpx.MockTransport(host.handle), clock=clock)
    ada = tokens.for_(Caller(kind=CallerKind.PERSON, id="u-ada"))

    await ada.token()
    clock.advance(71)
    await ada.token()

    assert len(host.requests) == 2


async def test_nobody_signed_in_forgets_the_token_and_who_it_was() -> None:
    host = Host(issued(jwt({"sub": "u-ada"})), httpx.Response(503))
    tokens = host.tokens()
    await tokens.token()
    assert tokens.signed_in is not None and tokens.signed_in.user_id == "u-ada"
    tokens.invalidate()

    with pytest.raises(NotSignedIn):
        await tokens.token()

    assert tokens.signed_in is None


async def test_signed_in_is_unknown_before_the_first_token() -> None:
    assert Host(issued()).tokens().signed_in is None


@pytest.mark.parametrize("status", [401, 404, 500, 502])
async def test_any_other_status_is_an_unavailable_host(status: int) -> None:
    with pytest.raises(HostUnavailable, match=str(status)):
        await Host(httpx.Response(status)).tokens().token()


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"expires_in": 5}),
        httpx.Response(200, json={"access_token": 5}),
        httpx.Response(200, json=["t"]),
    ],
)
async def test_an_answer_that_is_not_a_token_is_an_unavailable_host(reply: httpx.Response) -> None:
    with pytest.raises(HostUnavailable, match="something else"):
        await Host(reply).tokens().token()


async def test_a_host_that_cannot_be_reached_is_unavailable_and_says_why() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    tokens = HostTokens(ENDPOINT, transport=httpx.MockTransport(refuse))

    with pytest.raises(HostUnavailable, match="ConnectError"):
        await tokens.token()


async def test_a_token_expiring_within_the_margin_is_asked_for_every_time() -> None:
    host = Host(issued("short", expires_in=10))
    tokens = host.tokens()

    await tokens.token()
    await tokens.token()

    assert len(host.requests) == 2


async def test_invalidate_makes_the_next_call_ask_again() -> None:
    host = Host(issued("a"), issued("b"))
    tokens = host.tokens()
    assert await tokens.token() == "a"

    tokens.invalidate()

    assert await tokens.token() == "b"


async def test_callers_arriving_together_share_one_fetch() -> None:
    gate = asyncio.Event()
    asked = 0

    async def slow(request: httpx.Request) -> httpx.Response:
        nonlocal asked
        asked += 1
        await gate.wait()
        return issued()

    tokens = HostTokens(ENDPOINT, transport=httpx.MockTransport(slow), clock=ManualClock())
    calls = [asyncio.create_task(tokens.token()) for _ in range(5)]
    await asyncio.sleep(0.05)
    gate.set()

    assert await asyncio.gather(*calls) == ["t-1"] * 5
    assert asked == 1


class Service:
    def __init__(self, *statuses: int) -> None:
        self.statuses = list(statuses)
        self.seen: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request.headers["authorization"])
        return httpx.Response(self.statuses.pop(0))


async def test_a_second_401_is_returned_and_not_retried_again() -> None:
    host = Host(issued("a"), issued("b"), issued("c"))
    service = Service(401, 401, 200)
    auth = HostTokenAuth(host.tokens())

    async with httpx.AsyncClient(transport=httpx.MockTransport(service.handle), auth=auth) as c:
        response = await c.get("http://service.test/x")

    assert response.status_code == 401
    assert service.seen == ["Bearer a", "Bearer b"]
    assert len(host.requests) == 2

"""ServiceTokens' edges: the renewal boundary, concurrent grants, forgetting and the call to igni."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from igni_service import IgniService, IgniUnavailable, MemoryKeyStore
from igni_service.service_tokens import ServiceTokens
from igni_service.testing import FakeIgni, ManualClock
from igni_service.urls import IgniPaths

from .conftest import ORG, OTHER_ORG

DIRECTORY = f"{IgniPaths.DIRECTORY}/organisation"


class Wire(httpx.AsyncBaseTransport):
    """The fake igni, seen and bent: every request kept as sent, some paths answered otherwise."""

    def __init__(self, fake: FakeIgni) -> None:
        self.inner = fake.transport()
        self.sent: list[httpx.Request] = []
        self.answers: list[httpx.Response | Exception] = []
        """What the directory path answers first, one each; the fake answers when none is left."""
        self.always: httpx.Response | Exception | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        if request.url.path == DIRECTORY:
            answer = self.answers.pop(0) if self.answers else self.always
            if isinstance(answer, Exception):
                raise answer
            if answer is not None:
                return answer
        return await self.inner.handle_async_request(request)

    def to_directory(self) -> list[httpx.Request]:
        return [r for r in self.sent if r.url.path == DIRECTORY]


@pytest.fixture
def wire(fake: FakeIgni) -> Wire:
    return Wire(fake)


@pytest.fixture
def service(fake: FakeIgni, wire: Wire) -> IgniService:
    return IgniService(
        fake.settings(),
        key_store=MemoryKeyStore(),
        http=httpx.AsyncClient(transport=wire),
        clock=fake.clock,
        retry_min=0.01,
    )


def unauthorised() -> httpx.Response:
    return httpx.Response(401, json={"detail": "no"})


async def test_a_token_is_replaced_exactly_a_minute_before_it_expires(
    igni: IgniService, fake: FakeIgni, clock: ManualClock
) -> None:
    first = await igni.tokens.token(ORG)
    clock.advance(600 - ServiceTokens.RENEW_BEFORE - 0.5)
    assert await igni.tokens.token(ORG) == first

    clock.advance(0.5)

    assert await igni.tokens.token(ORG) != first
    assert ServiceTokens.RENEW_BEFORE == 60.0


async def test_callers_asking_at_once_for_one_organisation_cause_one_grant(
    igni: IgniService, fake: FakeIgni
) -> None:
    tokens = await asyncio.gather(*(igni.tokens.token(ORG) for _ in range(6)))

    assert len(set(tokens)) == 1
    assert len(fake.traffic.requests_to(IgniPaths.TOKEN)) == 1


async def test_callers_asking_at_once_for_two_organisations_get_a_grant_each(
    igni: IgniService, fake: FakeIgni
) -> None:
    here, there = await asyncio.gather(igni.tokens.token(ORG), igni.tokens.token(OTHER_ORG))

    assert here != there
    assert len(fake.traffic.requests_to(IgniPaths.TOKEN)) == 2


async def test_forgetting_one_organisation_leaves_the_others_kept(
    igni: IgniService, fake: FakeIgni
) -> None:
    here = await igni.tokens.token(ORG)
    there = await igni.tokens.token(OTHER_ORG)

    igni.tokens.forget(ORG)
    igni.tokens.forget("org-never-held")

    assert await igni.tokens.token(OTHER_ORG) == there
    assert await igni.tokens.token(ORG) != here
    assert len(fake.traffic.requests_to(IgniPaths.TOKEN)) == 3


async def test_forgetting_without_an_organisation_forgets_every_one(
    igni: IgniService, fake: FakeIgni
) -> None:
    await igni.tokens.token(ORG)
    await igni.tokens.token(OTHER_ORG)

    igni.tokens.forget()
    await igni.tokens.token(ORG)
    await igni.tokens.token(OTHER_ORG)

    assert len(fake.traffic.requests_to(IgniPaths.TOKEN)) == 4


async def test_a_second_401_in_a_row_is_igni_refusing_this_service(
    service: IgniService, wire: Wire
) -> None:
    wire.always = unauthorised()

    with pytest.raises(IgniUnavailable, match=f"refused this service for organisation {ORG}"):
        await service.tokens.request("GET", DIRECTORY, org_id=ORG)

    assert len(wire.to_directory()) == 2, "one retry with a new token, and no more"
    first, second = (r.headers["authorization"] for r in wire.to_directory())
    assert first != second


async def test_a_401_the_second_time_is_not_asked_a_third_time_but_forgets_the_token(
    service: IgniService, wire: Wire, fake: FakeIgni
) -> None:
    wire.answers = [unauthorised()]

    response = await service.tokens.request("GET", DIRECTORY, org_id=ORG)

    assert response.status_code == 200
    assert len(fake.traffic.requests_to(IgniPaths.TOKEN)) == 2


@pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
async def test_any_other_error_status_is_answered_as_it_came(
    service: IgniService, wire: Wire, status: int
) -> None:
    wire.always = httpx.Response(status, json={"detail": "x"})

    response = await service.tokens.request("GET", DIRECTORY, org_id=ORG)

    assert response.status_code == status
    assert len(wire.to_directory()) == 1


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError("secret-host.internal refused"), httpx.ReadTimeout("slow")],
)
async def test_a_call_that_cannot_reach_igni_names_only_the_kind_of_failure(
    service: IgniService, wire: Wire, error: Exception
) -> None:
    wire.always = error

    with pytest.raises(IgniUnavailable) as raised:
        await service.tokens.request("GET", DIRECTORY, org_id=ORG)

    assert str(raised.value) == f"could not reach igni server: {type(error).__name__}"
    assert "secret-host" not in str(raised.value)


async def test_the_callers_headers_travel_but_never_replace_the_service_token(
    service: IgniService, wire: Wire
) -> None:
    await service.tokens.request(
        "GET",
        DIRECTORY,
        org_id=ORG,
        headers={"X-Request-Id": "r-1", "authorization": "Bearer the-callers-own"},
    )

    [sent] = wire.to_directory()
    assert sent.headers["x-request-id"] == "r-1"
    assert sent.headers.get_list("authorization") == [f"Bearer {await service.tokens.token(ORG)}"]


async def test_a_request_passes_its_other_arguments_on(service: IgniService, wire: Wire) -> None:
    await service.tokens.request(
        "GET", f"{IgniPaths.DIRECTORY}/members", org_id=ORG, params={"query": "ada"}
    )

    [sent] = [r for r in wire.sent if r.url.path == f"{IgniPaths.DIRECTORY}/members"]
    assert sent.url.params["query"] == "ada"
    assert sent.method == "GET"

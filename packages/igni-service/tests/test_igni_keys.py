"""igni's key set as `IgniKeys` keeps it: for `max-age`, refetched for a new `kid`, kept when igni fails."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx
import pytest

from igni_service.crypto import RsaKeyPair
from igni_service.errors import IgniUnavailable
from igni_service.jwks import IgniKeys
from igni_service.server import IgniServer
from igni_service.testing import ManualClock

PAIR = RsaKeyPair.generate()
OTHER = RsaKeyPair.generate()


class Igni:
    """A JWKS endpoint that answers what it is told to and counts its calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.answer: Callable[[], httpx.Response] = lambda: self.keys_response()

    def keys_response(self, *, cache_control: str | None = "max-age=60") -> httpx.Response:
        body = {"keys": [PAIR.public_jwk("k1").model_dump(exclude_none=True)]}
        headers = {"Cache-Control": cache_control} if cache_control is not None else {}
        return httpx.Response(200, json=body, headers=headers)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        await asyncio.sleep(0)  # a real answer takes time: callers meet on the lock
        return self.answer()


@pytest.fixture
def igni_endpoint() -> Igni:
    return Igni()


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def keys(igni_endpoint: Igni, clock: ManualClock) -> IgniKeys:
    http = httpx.AsyncClient(transport=httpx.MockTransport(igni_endpoint.handle))
    return IgniKeys(IgniServer(base_url="http://igni.test", http=http), clock=clock)


async def test_a_key_igni_publishes_is_returned_and_one_it_does_not_is_none(
    keys: IgniKeys,
) -> None:
    found = await keys.key("k1")

    assert found is not None and found.kid == "k1"
    assert await keys.key("not-published") is None
    assert await keys.key("") is None


async def test_without_a_max_age_the_set_is_kept_for_the_default(
    keys: IgniKeys, igni_endpoint: Igni, clock: ManualClock
) -> None:
    igni_endpoint.answer = lambda: igni_endpoint.keys_response(cache_control=None)
    await keys.key("k1")

    clock.advance(299)
    await keys.key("k1")
    assert igni_endpoint.calls == 1

    clock.advance(2)
    await keys.key("k1")
    assert igni_endpoint.calls == 2


async def test_max_age_is_read_from_among_other_directives(
    keys: IgniKeys, igni_endpoint: Igni, clock: ManualClock
) -> None:
    igni_endpoint.answer = lambda: igni_endpoint.keys_response(cache_control="public, max-age=10")
    await keys.key("k1")

    clock.advance(9)
    await keys.key("k1")
    assert igni_endpoint.calls == 1

    clock.advance(2)
    await keys.key("k1")
    assert igni_endpoint.calls == 2


async def test_a_max_age_of_zero_is_not_kept(keys: IgniKeys, igni_endpoint: Igni) -> None:
    igni_endpoint.answer = lambda: igni_endpoint.keys_response(cache_control="max-age=0")

    await keys.key("k1")
    await keys.key("k1")

    assert igni_endpoint.calls == 2


async def test_callers_arriving_together_on_a_cold_cache_make_one_request(
    keys: IgniKeys, igni_endpoint: Igni
) -> None:
    found = await asyncio.gather(*(keys.key("k1") for _ in range(8)))

    assert all(key is not None and key.kid == "k1" for key in found)
    assert igni_endpoint.calls == 1


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(lambda: httpx.Response(500), id="error status"),
        pytest.param(lambda: httpx.Response(200, text="not json"), id="not json"),
        pytest.param(lambda: httpx.Response(200, json=[1, 2]), id="a list"),
        pytest.param(lambda: httpx.Response(200, json={"keys": 5}), id="keys not a list"),
    ],
)
async def test_without_any_key_set_a_failed_fetch_is_igni_unavailable(
    keys: IgniKeys, igni_endpoint: Igni, answer: Callable[[], httpx.Response]
) -> None:
    igni_endpoint.answer = answer

    with pytest.raises(IgniUnavailable, match="could not fetch igni's signing keys"):
        await keys.key("k1")


async def test_without_any_key_set_an_unreachable_igni_is_igni_unavailable(
    clock: ManualClock,
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    keys = IgniKeys(IgniServer(base_url="http://igni.test", http=http), clock=clock)

    with pytest.raises(IgniUnavailable, match="ConnectError"):
        await keys.key("k1")


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(lambda: httpx.Response(503), id="error status"),
        pytest.param(lambda: httpx.Response(200, text="<html>"), id="not json"),
    ],
)
async def test_a_failed_refresh_keeps_the_cached_set_and_tries_again_after_the_wait(
    keys: IgniKeys,
    igni_endpoint: Igni,
    clock: ManualClock,
    answer: Callable[[], httpx.Response],
) -> None:
    await keys.key("k1")
    healthy = igni_endpoint.answer
    igni_endpoint.answer = answer
    clock.advance(61)

    kept = await keys.key("k1")
    assert kept is not None and kept.kid == "k1"
    assert igni_endpoint.calls == 2

    clock.advance(IgniKeys.REFETCH_EVERY - 1)
    await keys.key("k1")
    assert igni_endpoint.calls == 2

    igni_endpoint.answer = healthy
    clock.advance(2)
    await keys.key("k1")
    assert igni_endpoint.calls == 3
    clock.advance(59)
    await keys.key("k1")
    assert igni_endpoint.calls == 3


async def test_a_rotation_replaces_the_set_not_adds_to_it(
    keys: IgniKeys, igni_endpoint: Igni, clock: ManualClock
) -> None:
    await keys.key("k1")

    def rotated() -> httpx.Response:
        body = {"keys": [OTHER.public_jwk("k2").model_dump(exclude_none=True)]}
        return httpx.Response(200, json=body, headers={"Cache-Control": "max-age=60"})

    igni_endpoint.answer = rotated
    clock.advance(61)

    assert await keys.key("k1") is None
    second = await keys.key("k2")
    assert second is not None and second.kid == "k2"

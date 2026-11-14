"""`ext.busy`: a lease is kept for as long as a block runs, and never outlives it.

`BusyLeases` talks to the host through `HostSelf`; these tests give it a
`HostSelf` that records what it was asked and fails when told to, so each
edge of `during` (a failing renewal, a failing release, a block that
raises or is cancelled) is reached deterministically. The wire itself is
covered against `FakeHost` in test_host.py.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import pytest

from igni_extension.busy import BusyLeases
from igni_extension.errors import HostError, HostUnavailable
from igni_extension.host_model import BusyLease, HostSelf

LEASE = BusyLease.model_validate(
    {
        "id": "busy-1",
        "kind": "extension",
        "holder": "acme.example",
        "reason": "indexing",
        "since": "2026-10-26T12:00:00Z",
        "expires_at": "2026-10-26T12:02:00Z",
    }
)


class RecordingHost:
    """What the host is asked, in order, and the failures it is told to give."""

    def __init__(self, *, fail_busy_from: int | None = None, fail_done: bool = False) -> None:
        self.asked: list[tuple[str, str, float | None]] = []
        self._busy_calls = 0
        self._fail_busy_from = fail_busy_from
        self._fail_done = fail_done

    async def busy(self, reason: str, ttl: float | None = None) -> BusyLease:
        self._busy_calls += 1
        self.asked.append(("busy", reason, ttl))
        if self._fail_busy_from is not None and self._busy_calls >= self._fail_busy_from:
            raise HostUnavailable("the igni host went away")
        return LEASE

    async def done(self, reason: str) -> None:
        self.asked.append(("done", reason, None))
        if self._fail_done:
            raise HostError("failed", "no such lease")


def _leases(host: RecordingHost) -> BusyLeases:
    return BusyLeases(cast(HostSelf, host))


def _renewers() -> list[asyncio.Task[Any]]:
    return [t for t in asyncio.all_tasks() if t.get_coro().__qualname__ == "BusyLeases._renew"]  # type: ignore[union-attr]


async def test_a_block_that_raises_still_lets_go_and_its_error_goes_on() -> None:
    host = RecordingHost()

    with pytest.raises(ValueError, match="the block's own"):
        async with _leases(host).during("indexing"):
            raise ValueError("the block's own")

    assert host.asked == [("busy", "indexing", 120.0), ("done", "indexing", None)]
    assert _renewers() == []


async def test_without_a_ttl_the_lease_is_taken_for_two_minutes() -> None:
    host = RecordingHost()

    async with _leases(host).during("indexing"):
        pass

    assert host.asked[0] == ("busy", "indexing", 120.0)


async def test_the_lease_is_renewed_every_half_ttl_with_the_same_ttl() -> None:
    host = RecordingHost()

    async with _leases(host).during("sync", ttl=0.2):
        await asyncio.sleep(0.28)

    renewals = [a for a in host.asked if a[0] == "busy"]
    assert len(renewals) >= 3, "the first take, and a renewal at 0.1s and another at 0.2s"
    assert all(a == ("busy", "sync", 0.2) for a in renewals)


async def test_a_renewal_that_fails_is_logged_and_the_block_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    host = RecordingHost(fail_busy_from=2)
    finished = False

    with caplog.at_level(logging.ERROR, logger="igni_extension.busy"):
        async with _leases(host).during("sync", ttl=0.04):
            await asyncio.sleep(0.1)
            finished = True

    assert finished
    assert host.asked[-1] == ("done", "sync", None), "the release is still tried"
    assert "could not renew the busy lease for 'sync'" in caplog.text


async def test_a_release_that_fails_is_logged_and_does_not_hide_the_blocks_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    host = RecordingHost(fail_done=True)

    with (
        caplog.at_level(logging.ERROR, logger="igni_extension.busy"),
        pytest.raises(ValueError, match="the block's own"),
    ):
        async with _leases(host).during("indexing"):
            raise ValueError("the block's own")

    assert "could not let go of the busy lease for 'indexing'" in caplog.text


async def test_a_release_that_fails_after_a_clean_block_is_logged_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    host = RecordingHost(fail_done=True)

    with caplog.at_level(logging.ERROR, logger="igni_extension.busy"):
        async with _leases(host).during("indexing"):
            pass

    assert "could not let go of the busy lease" in caplog.text


async def test_a_first_take_that_fails_raises_and_starts_nothing() -> None:
    host = RecordingHost(fail_busy_from=1)
    ran = False

    with pytest.raises(HostUnavailable):
        async with _leases(host).during("indexing"):
            ran = True

    assert not ran
    assert host.asked == [("busy", "indexing", 120.0)], "no renewal, no release"
    assert _renewers() == []


async def test_a_cancelled_block_stops_renewing_and_lets_go() -> None:
    host = RecordingHost()
    inside = asyncio.Event()

    async def work() -> None:
        async with _leases(host).during("indexing", ttl=60):
            inside.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(work())
    await inside.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert host.asked[-1] == ("done", "indexing", None)
    assert _renewers() == []


async def test_leases_for_different_reasons_are_independent() -> None:
    host = RecordingHost()
    leases = _leases(host)

    async with leases.during("indexing", ttl=60), leases.during("syncing", ttl=60):
        pass

    assert host.asked == [
        ("busy", "indexing", 60),
        ("busy", "syncing", 60),
        ("done", "syncing", None),
        ("done", "indexing", None),
    ]


async def test_taking_without_a_ttl_leaves_the_default_to_the_host() -> None:
    host = RecordingHost()

    assert await _leases(host).take("indexing") is LEASE
    assert await _leases(host)("indexing") is LEASE

    assert host.asked == [("busy", "indexing", None), ("busy", "indexing", None)]

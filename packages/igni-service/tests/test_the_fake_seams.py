"""The doubles for the SDK's own seams: a clock a test moves, a key already held, a sleep that waits for nothing."""

from __future__ import annotations

import time

from igni_service.keystore import StoredKey
from igni_service.testing_seams import HeldKeyStore, ManualClock, no_sleep


def test_a_manual_clock_starts_where_told_and_by_default_in_2027() -> None:
    assert ManualClock().wall() == 1_800_000_000.0
    assert ManualClock(start=5.5).wall() == 5.5


def test_a_manual_clock_stands_still_until_advanced() -> None:
    clock = ManualClock(start=100.0)

    first = (clock.wall(), clock.monotonic())
    time.sleep(0.01)

    assert (clock.wall(), clock.monotonic()) == first == (100.0, 100.0)


def test_advancing_moves_the_wall_and_the_monotonic_reading_together() -> None:
    clock = ManualClock(start=100.0)

    clock.advance(2.5)
    clock.advance(0)
    clock.advance(10_000_000_000)

    assert clock.wall() == clock.monotonic() == 100.0 + 2.5 + 10_000_000_000


async def test_a_held_key_store_answers_its_key_and_claims_never_replace_it() -> None:
    held = StoredKey(kid="kid-held", private_pem="held-pem")
    other = StoredKey(kid="kid-other", private_pem="other-pem")
    store = HeldKeyStore(held)

    assert await store.get() is held
    assert await store.claim(other) is held
    assert await store.claim(held) is held
    assert await store.get() is held


async def test_no_sleep_answers_at_once_whatever_it_is_asked_to_wait() -> None:
    started = time.monotonic()

    await no_sleep(3600.0)

    assert time.monotonic() - started < 1.0

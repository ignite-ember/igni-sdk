"""`Clock`: the real monotonic clock a token's age is measured on."""

from __future__ import annotations

import time

from igni_extension.clock import Clock


def test_it_reads_the_systems_monotonic_clock() -> None:
    before = time.monotonic()
    now = Clock().monotonic()
    after = time.monotonic()

    assert isinstance(now, float)
    assert before <= now <= after


def test_it_never_goes_backwards() -> None:
    clock = Clock()
    readings = [clock.monotonic() for _ in range(1000)]

    assert readings == sorted(readings)


def test_it_moves_with_real_time() -> None:
    clock = Clock()
    start = clock.monotonic()
    time.sleep(0.02)

    assert clock.monotonic() - start >= 0.015

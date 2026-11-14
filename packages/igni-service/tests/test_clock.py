"""`Clock`: the real wall and monotonic clocks, the two a token and a cache are read on."""

from __future__ import annotations

import time

import pytest

from igni_service.clock import Clock


def test_the_wall_clock_is_the_systems_time_since_the_epoch() -> None:
    before = time.time()
    now = Clock().wall()
    after = time.time()

    assert isinstance(now, float)
    assert before <= now <= after


def test_the_monotonic_clock_is_the_systems_monotonic_clock() -> None:
    before = time.monotonic()
    now = Clock().monotonic()
    after = time.monotonic()

    assert isinstance(now, float)
    assert before <= now <= after


def test_the_monotonic_clock_never_goes_backwards() -> None:
    clock = Clock()
    readings = [clock.monotonic() for _ in range(1000)]

    assert readings == sorted(readings)


def test_the_monotonic_clock_ignores_the_wall_clock_being_set_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    before = clock.monotonic()
    monkeypatch.setattr(time, "time", lambda: 0.0)

    assert clock.wall() == 0.0
    assert clock.monotonic() >= before

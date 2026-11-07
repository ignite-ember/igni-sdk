"""A clock a test moves by hand."""

from __future__ import annotations

from igni_extension.clock import Clock


class ManualClock(Clock):
    """A clock that moves only when told to."""

    def __init__(self, start: float = 1_000.0) -> None:
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

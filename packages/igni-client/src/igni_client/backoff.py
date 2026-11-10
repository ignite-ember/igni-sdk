"""How long to wait between attempts to open igni's socket."""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict


class Backoff(BaseModel):
    """`attempts` waits, starting at `first` seconds and doubling up to `most`."""

    model_config = ConfigDict(frozen=True)

    attempts: int = 5
    first: float = 0.5
    most: float = 8.0

    def delays(self) -> Iterator[float]:
        delay = self.first
        for _ in range(self.attempts):
            yield delay
            delay = min(delay * 2, self.most)

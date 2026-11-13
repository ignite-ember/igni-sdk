"""Have igni answer one path in a way a test chooses, and everything else as the fake does."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from igni_service.testing_router import FakeRouter


def answer(
    monkeypatch: pytest.MonkeyPatch, path: str, reply: Callable[[], httpx.Response | None]
) -> None:
    """Have igni answer what is asked at `path` with `reply()`, and everything else as the fake.

    A `reply` that returns `None` leaves that one request to the fake; one that raises
    plays the connection failing.
    """
    real = FakeRouter.handle

    def handle(router: FakeRouter, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith(path):
            router.traffic.record(request)
            replied = reply()
            if replied is not None:
                return replied
            router.traffic.seen.pop()
        return real(router, request)

    monkeypatch.setattr(FakeRouter, "handle", handle)

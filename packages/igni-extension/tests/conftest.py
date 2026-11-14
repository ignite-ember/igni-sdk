"""Shared fixtures for igni-extension tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from igni_extension.testing import FakeHost


@pytest.fixture
async def host() -> AsyncIterator[FakeHost]:
    """A FakeHost instance that serves the protocol igni serves on its loopback socket."""
    fake = FakeHost(
        granted=("chat.read", "chat.post", "sessions"),
        values={
            "chat.processing": False,
            "sessions.current": "s-1",
            "chat.status": {
                "session_id": "s-1",
                "model": "small",
                "model_configured": True,
                "permission_mode": "default",
                "input_tokens": 1,
                "output_tokens": 2,
                "context_tokens": 3,
                "max_context": 100,
            },
        },
        answers={"chat.append": "view-1"},
        refusals={"mcp.servers": ("not_granted", "acme.example is not granted 'mcp'")},
    )
    async with fake:
        yield fake

"""`OfflineHost`: with no socket to igni, only `notifications.notify` works, over MCP."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from igni_extension import IgniExtension, LocalNotification, NotConfigured, Target
from igni_extension.offline import OfflineHost
from igni_extension.session import HostSession

NOTE = LocalNotification(
    kind="export_ready", title="Runbook.pdf", target=Target(page="acme.example"), event_key="e1"
)


def offline() -> tuple[OfflineHost, HostSession]:
    session = HostSession()
    return OfflineHost(session), session


async def test_notify_is_held_for_igni_and_answers_nothing() -> None:
    host, session = offline()

    answer = await host.request(
        "call", "notifications.notify", params={"notification": NOTE.model_dump()}
    )

    assert answer is None
    assert len(session._pending) == 1


@pytest.mark.parametrize(
    ("op", "path"),
    [
        ("get", "chat.processing"),
        ("set", "sessions.current"),
        ("call", "chat.post"),
        ("get", "notifications.notify"),
        ("set", "notifications.notify"),
    ],
)
async def test_everything_else_says_it_is_not_running_inside_igni(op: str, path: str) -> None:
    host, session = offline()

    with pytest.raises(NotConfigured) as refused:
        await host.request(op, path, params={"notification": NOTE.model_dump()}, value="x")

    message = str(refused.value)
    assert f"host.{path}" in message
    assert "IGNI_HOST_URL" in message and "IGNI_HOST_SECRET" in message
    assert not session._pending


@pytest.mark.parametrize("params", [None, {}, {"notification": None}, {"other": 1}])
async def test_a_notify_without_a_notification_is_refused_as_invalid_not_as_a_key_error(
    params: dict[str, Any] | None,
) -> None:
    host, session = offline()

    with pytest.raises(ValidationError):
        await host.request("call", "notifications.notify", params=params)

    assert not session._pending


async def test_a_notification_that_breaks_igni_s_limits_is_refused_before_it_is_sent() -> None:
    host, session = offline()
    broken = {**NOTE.model_dump(), "title": ""}

    with pytest.raises(ValidationError):
        await host.request("call", "notifications.notify", params={"notification": broken})

    assert not session._pending


async def test_through_an_extension_without_a_socket_other_members_say_so() -> None:
    ext = IgniExtension("acme.example", environ={})

    await ext.host.notifications.notify(NOTE)
    with pytest.raises(NotConfigured, match=r"host\.chat\.processing"):
        await ext.host.chat.processing

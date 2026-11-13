"""`HostSession`: what the process says to igni, held until igni is there to hear it."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from igni_extension.notifications import ConditionsNotification, ConditionsParams
from igni_extension.session import HostSession


class Listening:
    """Stands where the `mcp` package's `ServerSession` does: keeps what is sent to it."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.heard: list[str] = []
        self.fail_on = fail_on

    async def send_notification(self, notification: ConditionsNotification) -> None:
        name = next(iter(notification.params.conditions), "")
        if name == self.fail_on:
            self.fail_on = None
            raise ConnectionError("the pipe is gone")
        self.heard.append(name)


def said(name: str) -> ConditionsNotification:
    return ConditionsNotification(params=ConditionsParams(conditions={name: True}))


def session_of(listening: Listening) -> Any:
    return listening


async def test_nothing_is_connected_until_a_session_is_attached() -> None:
    held = HostSession()
    assert not held.connected

    await held.attach(session_of(Listening()))

    assert held.connected


async def test_what_was_said_before_the_host_connected_is_delivered_in_order() -> None:
    held = HostSession()
    for name in ("a", "b", "c"):
        await held.send(said(name))
    listening = Listening()

    await held.attach(session_of(listening))
    await held.send(said("d"))

    assert listening.heard == ["a", "b", "c", "d"]


async def test_the_oldest_are_dropped_with_a_warning_beyond_what_is_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    held = HostSession()
    with caplog.at_level(logging.WARNING, logger="igni_extension.session"):
        for number in range(HostSession.MAX_PENDING + 1):
            await held.send(said(f"c{number}"))

    assert HostSession.MAX_PENDING == 100
    [warning] = [r for r in caplog.records if r.name == "igni_extension.session"]
    assert "notifications/igni/conditions" in warning.getMessage()
    listening = Listening()
    await held.attach(session_of(listening))
    assert len(listening.heard) == HostSession.MAX_PENDING
    assert listening.heard[0] == "c1" and listening.heard[-1] == "c100"


async def test_exactly_what_is_kept_is_dropped_without_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    held = HostSession()
    with caplog.at_level(logging.WARNING, logger="igni_extension.session"):
        for number in range(HostSession.MAX_PENDING):
            await held.send(said(f"c{number}"))

    assert [r for r in caplog.records if r.name == "igni_extension.session"] == []


async def test_a_new_connection_replaces_the_old_one() -> None:
    held = HostSession()
    first, second = Listening(), Listening()
    await held.attach(session_of(first))
    await held.send(said("a"))

    await held.attach(session_of(second))
    await held.send(said("b"))

    assert first.heard == ["a"] and second.heard == ["b"]


async def test_a_failed_send_reaches_the_caller_when_connected() -> None:
    held = HostSession()
    await held.attach(session_of(Listening(fail_on="a")))

    with pytest.raises(ConnectionError):
        await held.send(said("a"))


async def test_a_failure_while_flushing_loses_nothing_and_the_next_message_finishes_it() -> None:
    held = HostSession()
    for name in ("a", "b", "c"):
        await held.send(said(name))
    listening = Listening(fail_on="b")

    with pytest.raises(ConnectionError):
        await held.attach(session_of(listening))
    assert listening.heard == ["a"]

    await held.attach(session_of(listening))  # igni's next message

    assert listening.heard == ["a", "b", "c"]


async def test_the_middleware_attaches_the_session_of_each_message_and_passes_it_on() -> None:
    held = HostSession()
    listening = Listening()
    await held.send(said("a"))

    class Context:
        session = listening

    async def next_handler(ctx: Any) -> Any:
        return "answered"

    answer: Any = await held.middleware(Context(), next_handler)  # type: ignore[arg-type]

    assert answer == "answered"
    assert held.connected and listening.heard == ["a"]

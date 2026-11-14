"""`igni_extension.signals`: who handles a signal, and what runs when it arrives."""

from __future__ import annotations

import logging
import threading

import pytest

from igni_extension import Signal
from igni_extension.signals import SignalHandlers

DONE = Signal[int]("chat.run_completed", int)
SWITCHED = Signal[str]("session.switched", str)


def test_on_returns_the_handler_unchanged() -> None:
    handlers = SignalHandlers()

    async def react(value: int) -> None: ...

    assert handlers.on(DONE)(react) is react


def test_a_signal_nobody_handles_has_no_handlers_and_no_wire() -> None:
    handlers = SignalHandlers()

    assert handlers.handlers(DONE) == []
    assert handlers.wires() == []


def test_the_wires_are_every_handled_signal_sorted_and_once() -> None:
    handlers = SignalHandlers()
    for signal in (SWITCHED, DONE, DONE):
        handlers.on(signal)(lambda value: None)

    assert handlers.wires() == ["chat.run_completed", "session.switched"]


def test_the_handlers_are_a_copy_in_registration_order() -> None:
    handlers = SignalHandlers()

    def first(value: int) -> None: ...

    def second(value: int) -> None: ...

    handlers.on(DONE)(first)
    handlers.on(DONE)(second)
    listed = handlers.handlers(DONE)
    assert listed == [first, second]

    listed.clear()

    assert handlers.handlers(DONE) == [first, second]


def test_a_listener_is_told_only_of_a_signal_that_gets_its_first_handler() -> None:
    handlers = SignalHandlers()
    told: list[str] = []
    handlers.when_new(told.append)

    handlers.on(DONE)(lambda value: None)
    handlers.on(DONE)(lambda value: None)
    handlers.on(SWITCHED)(lambda value: None)

    assert told == ["chat.run_completed", "session.switched"]


def test_every_listener_is_told_and_one_added_late_is_not_told_of_what_exists() -> None:
    handlers = SignalHandlers()
    handlers.on(DONE)(lambda value: None)
    early: list[str] = []
    late: list[str] = []
    handlers.when_new(early.append)
    handlers.when_new(late.append)

    handlers.on(SWITCHED)(lambda value: None)

    assert early == late == ["session.switched"]


async def test_emit_runs_every_handler_in_order_with_the_value() -> None:
    handlers = SignalHandlers()
    seen: list[tuple[str, int]] = []

    @handlers.on(DONE)
    async def first(value: int) -> None:
        seen.append(("first", value))

    @handlers.on(DONE)
    def second(value: int) -> None:
        seen.append(("second", value))

    await handlers.emit(DONE, 7)

    assert seen == [("first", 7), ("second", 7)]


async def test_emit_with_no_handler_does_nothing() -> None:
    await SignalHandlers().emit(DONE, 1)


async def test_a_plain_handler_runs_off_the_loop() -> None:
    handlers = SignalHandlers()
    ran_in: list[threading.Thread] = []

    @handlers.on(DONE)
    def react(value: int) -> None:
        ran_in.append(threading.current_thread())

    await handlers.emit(DONE, 1)

    assert ran_in != [threading.current_thread()] and len(ran_in) == 1


@pytest.mark.parametrize("plain", [True, False])
async def test_a_failing_handler_is_logged_and_the_others_still_run(
    plain: bool, caplog: pytest.LogCaptureFixture
) -> None:
    handlers = SignalHandlers()
    ran: list[str] = []

    if plain:

        @handlers.on(DONE)
        def broken(value: int) -> None:
            raise RuntimeError("boom")
    else:

        @handlers.on(DONE)
        async def broken(value: int) -> None:
            raise RuntimeError("boom")

    @handlers.on(DONE)
    async def after(value: int) -> None:
        ran.append("after")

    with caplog.at_level(logging.ERROR):
        await handlers.emit(DONE, 1)

    assert ran == ["after"]
    assert "chat.run_completed" in caplog.text and "boom" in caplog.text


async def test_deliver_reads_the_hosts_json_as_the_signals_type() -> None:
    handlers = SignalHandlers()
    seen: list[int] = []
    handlers.on(DONE)(seen.append)

    await handlers.deliver("chat.run_completed", 5)

    assert seen == [5]


async def test_deliver_ignores_a_signal_nobody_handles() -> None:
    handlers = SignalHandlers()
    handlers.on(DONE)(lambda value: None)

    await handlers.deliver("session.switched", "s-1")
    await handlers.deliver("nothing.at.all", None)


async def test_a_value_in_the_wrong_shape_is_logged_and_no_handler_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handlers = SignalHandlers()
    seen: list[int] = []
    handlers.on(DONE)(seen.append)

    with caplog.at_level(logging.ERROR):
        await handlers.deliver("chat.run_completed", "not a number")

    assert seen == []
    assert "chat.run_completed arrived in a shape this SDK does not read" in caplog.text

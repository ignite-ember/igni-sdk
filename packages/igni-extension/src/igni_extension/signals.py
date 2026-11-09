"""Signals: what the host tells an extension happened, and who handles it.

Each object of `ext.host` has signals — `ext.host.sessions.current_changed`,
`ext.host.chat.run_completed` — that carry the new value. An extension
handles one with `@ext.on(signal)`; registering the first handler of a
signal subscribes to it on the host's socket, and the host delivers it
only if the manifest grants the object it belongs to (`permissions.host`).
A handler may read and write the model while it runs.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from igni_extension.members import Signal
from igni_extension.threads import OffTheLoop

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Awaitable[None] | None]
"""A reaction: `async def`, or a plain `def` the SDK runs in a worker thread."""


class SignalHandlers:
    """Handlers by signal, and the wire names they need subscribed.

    One per extension, as `ext.signals`; `@ext.on(signal)` is its `on`.
    The host's socket subscribes to `wires()` and hands each signal that
    arrives to `deliver`. A test runs the handlers with `emit` (a typed
    value) or `deliver` (the host's JSON), with no socket at all.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._signals: dict[str, Signal[Any]] = {}
        self._listeners: list[Callable[[str], None]] = []

    def on[T](
        self, signal: Signal[T]
    ) -> Callable[[Callable[[T], Awaitable[None] | None]], Callable[[T], Awaitable[None] | None]]:
        """Register a handler of `signal` (what `@ext.on(signal)` does); returns it unchanged.

        Several handlers per signal run in registration order. The first
        handler of a signal subscribes to it on a connected socket.
        """

        def register(
            handler: Callable[[T], Awaitable[None] | None],
        ) -> Callable[[T], Awaitable[None] | None]:
            first = signal.name not in self._handlers
            self._handlers.setdefault(signal.name, []).append(handler)
            self._signals[signal.name] = signal
            if first:
                for listener in list(self._listeners):
                    listener(signal.name)
            return handler

        return register

    def when_new(self, listener: Callable[[str], None]) -> None:
        """Be told the wire name of each signal that gets its first handler."""
        self._listeners.append(listener)

    def wires(self) -> list[str]:
        """Every signal somebody handles, by wire name."""
        return sorted(self._handlers)

    def handlers(self, signal: Signal[Any]) -> list[Handler]:
        """`signal`'s handlers, in registration order; empty when it has none."""
        return list(self._handlers.get(signal.name, []))

    async def emit[T](self, signal: Signal[T], value: T) -> None:
        """Run every handler of `signal` with `value`, in registration order.

        One handler failing is logged and does not stop the others: they
        are independent reactions to the same event.
        """
        for handler in self.handlers(signal):
            try:
                await OffTheLoop.call(handler, value)
            except Exception:
                logger.exception("igni: a handler of %s failed", signal.name)

    async def deliver(self, wire: str, raw: Any) -> None:
        """A signal arrived from the host: parse it and run its handlers.

        `wire` is the signal's wire name and `raw` its JSON value. A
        signal nobody handles is ignored; a value that does not parse is
        logged and skipped.
        """
        signal = self._signals.get(wire)
        if signal is None:
            return
        try:
            value = signal.parse(raw)
        except Exception:
            logger.exception("igni: %s arrived in a shape this SDK does not read", wire)
            return
        await self.emit(signal, value)


__all__ = ["Signal", "SignalHandlers"]

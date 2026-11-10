"""The extension's handlers for what igni and its service send: signals, hooks, service events."""

from __future__ import annotations

from igni_extension.hooks import HookHandlers
from igni_extension.service_events import ServiceEventHandlers
from igni_extension.signals import SignalHandlers


class ExtensionHandlers:
    """What `@ext.on`, `@ext.hook` and `@ext.on_service_event` registered.

    The host's socket reads all three: it subscribes the signals, answers
    the hooks, and hands each service event to its handler.
    """

    def __init__(self) -> None:
        self.signals = SignalHandlers()
        self.hooks = HookHandlers()
        self.service_events = ServiceEventHandlers()

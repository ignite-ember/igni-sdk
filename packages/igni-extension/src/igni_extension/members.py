"""The pieces `ext.host` is built from: objects, properties, signals, calls.

`igni_extension.host_model` is generated from igni's host schema and is
made of these. An author meets them as

    await ext.host.chat.processing            # read a property
    await ext.host.sessions.current.set(sid)  # write one
    await ext.host.chat.post("Done.")         # call a method

    @ext.on(ext.host.chat.run_completed)      # handle a signal
    async def reviewed(run: Run) -> None: ...

and never as a message on a socket: how a request reaches igni is the
`HostLink`'s business (`igni_extension.channel`).
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from functools import lru_cache
from typing import Any, Final, Protocol

from pydantic import TypeAdapter
from pydantic_core import to_jsonable_python

logger = logging.getLogger(__name__)

#: Any JSON value: the host's report of something whose shape is not
#: part of the model's promise yet.
type JsonValue = Any


class _NoResult:
    """A method that answers nothing."""


NO_RESULT: Final = _NoResult()
"""Passed as a method's result type when it returns nothing."""


class HostLink(Protocol):
    """How requests reach the igni host. One per extension process."""

    async def request(
        self,
        op: str,
        path: str,
        *,
        window: str | None = None,
        session: str | None = None,
        params: dict[str, Any] | None = None,
        value: Any = None,
    ) -> Any: ...


@lru_cache(maxsize=512)
def _adapter(annotation: Any) -> TypeAdapter[Any]:
    return TypeAdapter(annotation)


def parse(annotation: Any, value: Any) -> Any:
    """`value` as `annotation` describes it."""
    return _adapter(annotation).validate_python(value)


def plain(value: Any) -> Any:
    """Models and the like as JSON-ready values, for the wire."""
    return to_jsonable_python(value)


class HostObject:
    """One object of the host model: `host.chat`, `host.windows.ui(id)`,
    `host.sessions.chat(id)`."""

    PATH = ""
    """Where the object is in the host model: `chat`, `windows.ui`; empty for the root."""

    def __init__(
        self, link: HostLink, window: str | None = None, session: str | None = None
    ) -> None:
        self._link = link
        self._window = window
        self._session = session

    def _member(self, name: str) -> str:
        return f"{self.PATH}.{name}" if self.PATH else name

    async def _call(self, name: str, params: dict[str, Any], result: Any) -> Any:
        sent = {key: plain(value) for key, value in params.items() if value is not None}
        answer = await self._link.request(
            "call", self._member(name), window=self._window, session=self._session, params=sent
        )
        if result is NO_RESULT:
            return None
        return parse(result, answer)


class Property[T]:
    """A value of a host object. `await prop` reads it; `set` writes it.

    Args:
        owner: The host object the property belongs to: `host.chat`.
        name: The property's name on its object: `processing`.
        annotation: The type its value is read as.
        writable: Whether `set` may write it.
    """

    def __init__(self, owner: HostObject, name: str, annotation: Any, *, writable: bool) -> None:
        self._owner = owner
        self.name = name
        """The property's name on its object: `processing`."""
        self.annotation = annotation
        """The type its value is read as."""
        self.writable = writable
        """Whether `set` may write it."""

    @property
    def path(self) -> str:
        """Its full path in the host model: `chat.processing`."""
        return self._owner._member(self.name)

    async def get(self) -> T:
        """Read it from the host; `await prop` is the same. Raises `HostError` when the host
        refuses.
        """
        answer = await self._owner._link.request(
            "get", self.path, window=self._owner._window, session=self._owner._session
        )
        return parse(self.annotation, answer)  # type: ignore[no-any-return]

    async def set(self, value: T) -> None:
        """Write it, as the person's UI would. Refused where theirs would be.

        Args:
            value: The value to write, as the property's annotation describes it.
        """
        if not self.writable:
            raise TypeError(f"host.{self.path} cannot be set")
        await self._owner._link.request(
            "set",
            self.path,
            window=self._owner._window,
            session=self._owner._session,
            value=plain(value),
        )

    def __await__(self) -> Generator[Any, None, T]:
        return self.get().__await__()

    def __repr__(self) -> str:
        return f"Property({self.path!r})"


class Signal[T]:
    """One signal of one host object. `T` is the value it carries.

    `name` is its wire name — `chat.run_completed`, or for the four
    events that predate the model their topic strings
    (`session.switched`, `workspace.head-changed`, …).

    Args:
        name: The signal's wire name: `chat.run_completed`.
        carries: The type of the value the signal carries.
    """

    def __init__(self, name: str, carries: Any) -> None:
        self.name = name
        """Its wire name."""
        self.carries = carries
        """The type of the value it carries."""

    def parse(self, value: Any) -> T:
        """The value the host sent, as `T`.

        Args:
            value: The signal's value as the host sent it, before it was read as `T`.
        """
        return parse(self.carries, value)  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        return f"Signal({self.name!r})"


__all__ = [
    "NO_RESULT",
    "HostLink",
    "HostObject",
    "JsonValue",
    "Property",
    "Signal",
    "parse",
    "plain",
]

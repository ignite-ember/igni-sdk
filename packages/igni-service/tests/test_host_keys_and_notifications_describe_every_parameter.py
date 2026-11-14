"""Every parameter of the host, the key store and the notifier is described in an Args block.

The reference pages are generated from the docstrings, so a parameter with no
entry in `Args:` is a blank row on the page, and an entry for a parameter that
no longer exists is a lie. A class docstring documents its constructor.
"""

from __future__ import annotations

import inspect
import re

import pytest

from igni_service.host import Host
from igni_service.keystore import KeyCipher, KeyStore, MemoryKeyStore
from igni_service.notifications import Notification, Notifier


def _documented(doc: str) -> list[str]:
    """The parameter names an `Args:` block lists, each with a non-empty description."""
    lines = doc.splitlines()
    if "Args:" not in [line.strip() for line in lines]:
        return []
    start = next(i for i, line in enumerate(lines) if line.strip() == "Args:")
    indent = len(lines[start]) - len(lines[start].lstrip())
    names: list[str] = []
    for line in lines[start + 1 :]:
        if not line.strip():
            if names:
                break
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        match = re.match(rf"^\s{{{indent + 4}}}(\w+): (\S.*)$", line)
        if match:
            names.append(match.group(1))
    return names


def _surface() -> list[tuple[str, object, str]]:
    surface: list[tuple[str, object, str]] = []
    for built in (Host, KeyCipher, Notifier):
        surface.append((built.__name__, built.__init__, inspect.getdoc(built) or ""))
    classes: tuple[type, ...] = (Host, KeyCipher, KeyStore, MemoryKeyStore, Notification, Notifier)
    for klass in classes:
        for name, member in klass.__dict__.items():
            if name.startswith("_"):
                continue
            function = member.__func__ if isinstance(member, staticmethod | classmethod) else member
            if inspect.isfunction(function):
                surface.append(
                    (f"{klass.__name__}.{name}", function, inspect.getdoc(function) or "")
                )
    return surface


def _parameters(function: object) -> list[str]:
    return [
        name
        for name in inspect.signature(function).parameters  # type: ignore[arg-type]
        if name not in ("self", "cls")
    ]


@pytest.mark.parametrize(
    ("where", "function", "doc"), _surface(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_every_parameter_has_an_entry_in_args(where: str, function: object, doc: str) -> None:
    assert _documented(doc) == _parameters(function), where


def test_the_check_reads_the_methods_that_take_parameters() -> None:
    reads = {where for where, function, _ in _surface() if _parameters(function)}
    assert reads >= {
        "Host",
        "Host.notify",
        "Host.agent",
        "Host.send_event",
        "KeyCipher",
        "KeyCipher.seal",
        "KeyCipher.open",
        "KeyStore.claim",
        "MemoryKeyStore.claim",
        "Notification.split",
        "Notifier",
        "Notifier.batches",
        "Notifier.send",
    }


def test_the_args_reader_tells_a_missing_entry_from_a_present_one() -> None:
    doc = "Summary.\n\nArgs:\n    first: One.\n        More of one.\n    second: Two.\n"
    assert _documented(doc) == ["first", "second"]
    assert _documented("Summary.") == []

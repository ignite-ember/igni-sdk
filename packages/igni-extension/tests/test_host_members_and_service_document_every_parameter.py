"""Every parameter of the host members, the service client and the service event is described.

The reference pages are generated from the docstrings, so a parameter with no
entry in `Args:` is a blank row on the page, and an entry for a parameter that
no longer exists is a lie. Fields documented by an attribute docstring carry
that text as their description.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from igni_extension.members import Property, Signal
from igni_extension.service import ServiceClient
from igni_extension.service_events import ServiceEvent

from .test_extension_documents_every_parameter import _documented


def _parameters(function: Callable[..., Any]) -> list[str]:
    """What the function takes, `**options` included: it is described like any other."""
    return [
        name
        for name, parameter in inspect.signature(function).parameters.items()
        if name != "self" and parameter.kind is not parameter.VAR_POSITIONAL
    ]


SURFACE: list[tuple[str, Callable[..., Any], Callable[..., Any]]] = [
    ("Property", Property.__init__, Property),
    ("Property.set", Property.set, Property.set),
    ("Signal", Signal.__init__, Signal),
    ("Signal.parse", Signal.parse, Signal.parse),
    ("ServiceClient", ServiceClient.__init__, ServiceClient),
    ("ServiceClient.for_", ServiceClient.for_, ServiceClient.for_),
    ("ServiceClient.websocket", ServiceClient.websocket, ServiceClient.websocket),
]


@pytest.mark.parametrize(
    ("where", "function", "documented_on"), SURFACE, ids=lambda v: v if isinstance(v, str) else ""
)
def test_every_parameter_has_an_entry_in_args(
    where: str, function: Callable[..., Any], documented_on: Callable[..., Any]
) -> None:
    doc = inspect.getdoc(documented_on) or ""

    assert _documented(doc) == _parameters(function), where


def test_the_check_reads_what_these_signatures_take() -> None:
    assert _parameters(Property.__init__) == ["owner", "name", "annotation", "writable"]
    assert _parameters(Signal.__init__) == ["name", "carries"]
    assert _parameters(ServiceClient.__init__) == ["base_url", "tokens", "transport", "timeout"]
    assert _parameters(ServiceClient.websocket) == ["path", "options"]
    assert _parameters(ServiceClient.for_) == ["caller"]


def test_every_field_of_a_service_event_says_what_it_is() -> None:
    blank = [
        name
        for name, field in ServiceEvent.model_fields.items()
        if not (field.description or "").strip()
    ]

    assert blank == []
    assert list(ServiceEvent.model_fields) == [
        "event_id",
        "extension_id",
        "client_id",
        "type",
        "payload",
        "event_key",
        "created_at",
        "expires_at",
    ]

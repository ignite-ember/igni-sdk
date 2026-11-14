"""Reading igni's frames: what `parse_event` makes of each, and that it never raises."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from igni_client import events
from igni_client.events import (
    EVENT_TYPES,
    PUSH_TYPES,
    ContentDelta,
    ErrorMessage,
    PushNotification,
    Unknown,
    parse_event,
)
from igni_client.models import ProcessLinePush


def test_a_known_type_is_its_class_with_its_fields() -> None:
    event = parse_event({"type": "error", "id": "q", "session_id": "s", "text": "boom"})

    assert type(event) is ErrorMessage
    assert (event.text, event.id, event.session_id) == ("boom", "q", "s")


def test_a_field_a_newer_igni_adds_to_a_known_type_is_kept() -> None:
    event = parse_event({"type": "error", "text": "boom", "severity": "high"})

    assert type(event) is ErrorMessage and event.model_extra == {"severity": "high"}


def test_a_known_type_whose_fields_do_not_fit_is_unknown_with_everything_and_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = {"type": "error", "text": ["not", "text"], "id": "q"}
    with caplog.at_level(logging.WARNING, logger="igni_client.events"):
        event = parse_event(raw)

    assert type(event) is Unknown and event.type == "error" and event.id == "q"
    assert event.model_extra == {"text": ["not", "text"]}
    [record] = caplog.records
    assert "sent a error this version cannot read" in record.getMessage()


def test_a_typed_push_that_does_not_fit_is_a_plain_push_and_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = {"type": "push_notification", "channel": "process_line", "payload": {"pid": "one"}}
    with caplog.at_level(logging.WARNING, logger="igni_client.events"):
        event = parse_event(raw)

    assert type(event) is PushNotification and event.payload == {"pid": "one"}
    [record] = caplog.records
    assert "pushed a process_line this version cannot read" in record.getMessage()


def test_a_push_without_a_channel_or_on_an_unknown_one_is_plain_and_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="igni_client.events"):
        bare = parse_event({"type": "push_notification", "payload": {"a": 1}})
        newer = parse_event(
            {"type": "push_notification", "channel": "not_yet", "payload": {"b": 2}}
        )

    assert type(bare) is PushNotification and bare.payload == {"a": 1}
    assert type(newer) is PushNotification and newer.channel == "not_yet"
    assert caplog.records == []


def test_a_typed_push_is_its_channel_s_class() -> None:
    event = parse_event(
        {"type": "push_notification", "channel": "process_line", "payload": {"pid": 3, "line": "x"}}
    )

    assert type(event) is ProcessLinePush and event.payload.line == "x"
    assert PUSH_TYPES["process_line"] is ProcessLinePush


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ({}, ""),
        ({"type": None}, "None"),
        ({"type": 7}, "7"),
        ({"type": "from_the_future", "ünï": "✓"}, "from_the_future"),
    ],
)
def test_a_frame_without_a_readable_type_is_unknown_with_the_type_as_text(
    raw: dict[str, Any], kind: str
) -> None:
    event = parse_event(raw)

    assert type(event) is Unknown and event.type == kind
    assert event.model_extra == {k: v for k, v in raw.items() if k != "type"}


def test_a_frame_even_unknown_cannot_hold_is_still_unknown_and_never_raises() -> None:
    event = parse_event({"type": "from_the_future", "id": {"nested": 1}, "event_seq": "x"})

    assert type(event) is Unknown and event.type == "from_the_future"


def test_a_huge_payload_is_read_like_a_small_one() -> None:
    text = "ü" * 1_000_000
    event = parse_event({"type": "content_delta", "text": text})

    assert isinstance(event, ContentDelta) and event.text == text


def test_every_generated_type_is_exported() -> None:
    assert set(EVENT_TYPES.values()) <= {
        getattr(events, n) for n in events.__all__ if isinstance(getattr(events, n), type)
    }
    assert {"EVENT_TYPES", "PUSH_TYPES", "Unknown", "parse_event"} <= set(events.__all__)
    assert all(hasattr(events, name) for name in events.__all__)

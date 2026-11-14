"""An ``Area`` describes one reference page, for both reference generators."""

from __future__ import annotations

import dataclasses

import pytest

from tools.reference_area import Area


def test_an_area_is_a_slug_a_title_the_sources_and_an_empty_note_by_default() -> None:
    area = Area("tokens", "Tokens", ("igni_service.tokens",))
    assert (area.slug, area.title, area.sources, area.note) == (
        "tokens",
        "Tokens",
        ("igni_service.tokens",),
        "",
    )
    assert Area("a", "A", (), "Why.").note == "Why."


def test_an_area_cannot_be_changed_once_made() -> None:
    area = Area("tokens", "Tokens", ("m",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        area.slug = "other"  # type: ignore[misc]


def test_an_area_is_hashable_and_equal_by_what_it_holds() -> None:
    one = Area("a", "A", ("m",), "n")
    assert one == Area("a", "A", ("m",), "n") and hash(one) == hash(Area("a", "A", ("m",), "n"))
    assert one != Area("a", "A", ("m",))
    assert len({one, Area("a", "A", ("m",), "n")}) == 1

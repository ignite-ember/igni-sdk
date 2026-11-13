"""The limits a notification carries, each at the edge: what is kept and what is refused."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from igni_extension import LocalNotification, Target
from igni_extension.notifications import (
    MAX_BODY,
    MAX_CONDITIONS,
    MAX_KEY,
    MAX_KIND,
    MAX_TARGET_BYTES,
    MAX_TARGET_PARAMS,
    MAX_TITLE,
    ConditionsNotification,
    ConditionsParams,
    NotifyNotification,
)

BASE: dict[str, Any] = {
    "kind": "export_ready",
    "title": "Runbook.pdf",
    "target": {"page": "acme.example"},
    "event_key": "e1",
}


def notification(**overrides: Any) -> LocalNotification:
    return LocalNotification.model_validate(BASE | overrides)


def test_igni_s_limits_are_the_ones_mirrored() -> None:
    assert (MAX_KIND, MAX_TITLE, MAX_KEY, MAX_BODY) == (64, 200, 200, 1000)
    assert (MAX_TARGET_PARAMS, MAX_TARGET_BYTES, MAX_CONDITIONS) == (32, 2048, 64)


@pytest.mark.parametrize(
    ("field", "limit"), [("kind", 64), ("title", 200), ("event_key", 200), ("body", 1000)]
)
def test_a_field_at_its_limit_is_kept_and_one_past_it_is_refused(field: str, limit: int) -> None:
    assert len(getattr(notification(**{field: "x" * limit}), field)) == limit
    with pytest.raises(ValidationError):
        notification(**{field: "x" * (limit + 1)})


def test_a_page_is_one_to_two_hundred_characters() -> None:
    assert Target(page="p").page == "p"
    assert len(Target(page="p" * 200).page) == 200
    for page in ("", "p" * 201):
        with pytest.raises(ValidationError):
            Target(page=page)


def test_a_body_is_collapsed_before_it_is_measured() -> None:
    padded = "ab  " * 300  # 1200 characters, 899 once the runs of spaces are single

    assert len(notification(body=padded).body) == 899
    assert len(notification(body=" " + "b" * 1000 + "\n").body) == 1000
    with pytest.raises(ValidationError):
        notification(body=" " + "b" * 1001 + " ")


@pytest.mark.parametrize(
    ("body", "line"),
    [("", ""), ("   ", ""), ("\n\t\n", ""), ("a\r\nb\tc", "a b c"), ("a b", "a b")],
)
def test_a_body_is_a_single_line_with_the_whitespace_collapsed(body: str, line: str) -> None:
    assert notification(body=body).body == line


def test_a_notification_with_no_body_has_an_empty_one() -> None:
    assert notification().body == ""


def test_a_target_takes_thirty_two_params_and_not_thirty_three() -> None:
    assert len(Target(page="p", params={f"k{n}": "v" for n in range(32)}).params) == 32
    with pytest.raises(ValidationError):
        Target(page="p", params={f"k{n}": "v" for n in range(33)})


def params_of_json_size(size: int) -> dict[str, str]:
    params = {"k": ""}
    params["k"] = "v" * (size - len(json.dumps(params)))
    assert len(json.dumps(params)) == size
    return params


def test_a_targets_params_are_two_thousand_and_forty_eight_bytes_of_json_at_most() -> None:
    assert Target(page="p", params=params_of_json_size(2048)).params
    with pytest.raises(ValidationError, match="2048 bytes"):
        Target(page="p", params=params_of_json_size(2049))


def test_the_size_of_params_counts_non_ascii_as_the_json_the_host_reads_it() -> None:
    """JSON escapes each such character: 6 bytes where the text is 1 character."""
    assert Target(page="p", params={"k": "é" * 300}).params  # 1800 bytes escaped
    with pytest.raises(ValidationError, match="2048 bytes"):
        Target(page="p", params={"k": "é" * 400})  # 400 characters, 2400 bytes escaped


def test_a_target_and_a_notification_are_frozen_and_take_no_extra_field() -> None:
    target = Target(page="p")
    with pytest.raises(ValidationError):
        target.page = "other"
    with pytest.raises(ValidationError):
        Target.model_validate({"page": "p", "anchor": "top"})
    with pytest.raises(ValidationError):
        notification().kind = "other"
    with pytest.raises(ValidationError):
        notification(recipients=["someone"])


def test_the_wire_notification_reads_back_as_the_local_one() -> None:
    local = notification(
        body=" a  b ", target={"page": "p", "params": {"export": "e1"}}, event_key="export:e1"
    )

    wire = NotifyNotification.of(local)

    assert wire.method == "notifications/igni/notify"
    assert wire.params.event_key == "export:e1"
    assert wire.local() == local
    assert wire.model_dump(by_alias=True, exclude_none=True)["params"]["event_key"] == "export:e1"
    assert "eventKey" not in wire.model_dump_json(by_alias=True)


def test_a_condition_name_is_lower_case_letters_digits_and_hyphens_starting_with_a_letter() -> None:
    names = {"a": True, "index-covers-head": False, "v2": True, "a-1-b": True}
    assert ConditionsParams(conditions=names).conditions == names
    for bad in ("A", "Ready", "has space", "", "1st", "-a", "a_b", "a.b", "é"):
        with pytest.raises(ValidationError):
            ConditionsParams(conditions={bad: True})


def test_sixty_four_conditions_are_one_message_and_sixty_five_are_not() -> None:
    assert len(ConditionsParams(conditions={f"c{n}": True for n in range(64)}).conditions) == 64
    with pytest.raises(ValidationError):
        ConditionsParams(conditions={f"c{n}": True for n in range(65)})


def test_a_condition_holds_a_boolean_not_a_word() -> None:
    with pytest.raises(ValidationError):
        ConditionsParams(conditions={"ready": "maybe"})  # type: ignore[dict-item]


def test_refresh_is_on_the_wire_only_when_asked_for() -> None:
    plain = ConditionsNotification(params=ConditionsParams(conditions={"a": True}))
    asking = ConditionsNotification(params=ConditionsParams(conditions={}, refresh=True))

    assert plain.model_dump(by_alias=True, exclude_none=True)["params"] == {
        "conditions": {"a": True}
    }
    assert asking.model_dump(by_alias=True, exclude_none=True)["params"] == {
        "conditions": {},
        "refresh": True,
    }
    assert plain.method == "notifications/igni/conditions"

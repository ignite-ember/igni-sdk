"""What a tool says it is: the four hints, their wire spelling, and the check that all are stated."""

from __future__ import annotations

from typing import Any

import pytest
from mcp.types import Tool, ToolAnnotations
from pydantic import ValidationError

from igni_extension import ToolHints, ToolHintsMissing

READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)
WRITES = ToolHints(read_only=False, destructive=True, idempotent=False, open_world=True)
FOUR = ("read_only_hint", "destructive_hint", "idempotent_hint", "open_world_hint")


def _tool(name: str, annotations: ToolAnnotations | None) -> Tool:
    return Tool(name=name, input_schema={"type": "object"}, annotations=annotations)


def test_the_four_hints_are_spelled_as_mcp_and_a_manifest_spell_them() -> None:
    assert READS.wire() == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert WRITES.wire() == {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }


def test_the_annotations_carry_each_hint_to_its_own_field() -> None:
    annotations = WRITES.annotations()
    assert [getattr(annotations, field) for field in FOUR] == [False, True, False, True]


def test_every_hint_is_required_and_no_other_is_accepted() -> None:
    with pytest.raises(ValidationError):
        ToolHints(read_only=True, destructive=False, idempotent=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ToolHints(  # type: ignore[call-arg]
            read_only=True, destructive=False, idempotent=True, open_world=False, title="x"
        )


def test_hints_are_fixed_once_stated() -> None:
    with pytest.raises(ValidationError):
        READS.read_only = False


def test_a_read_that_destroys_nothing_and_a_write_that_does_are_both_fine() -> None:
    ToolHints(read_only=False, destructive=True, idempotent=True, open_world=False)
    ToolHints(read_only=True, destructive=False, idempotent=True, open_world=True)
    with pytest.raises(ValidationError, match="read-only tool cannot also be destructive"):
        ToolHints(read_only=True, destructive=True, idempotent=False, open_world=False)


def test_false_counts_as_stated_and_any_hint_left_out_does_not() -> None:
    assert ToolHintsMissing.complete(READS.annotations())
    assert ToolHintsMissing.complete(
        ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    assert not ToolHintsMissing.complete(None)
    for left_out in FOUR:
        stated: dict[str, Any] = {field: True for field in FOUR if field != left_out}
        assert not ToolHintsMissing.complete(ToolAnnotations(**stated)), left_out


def test_the_check_names_each_tool_missing_a_hint_sorted_and_is_silent_otherwise() -> None:
    ToolHintsMissing.check([])
    ToolHintsMissing.check([_tool("fine", READS.annotations())])

    with pytest.raises(ToolHintsMissing) as raised:
        ToolHintsMissing.check(
            [
                _tool("mid", None),
                _tool("zeta", None),
                _tool("fine", READS.annotations()),
                _tool("alpha", ToolAnnotations(read_only_hint=True)),
            ]
        )

    assert raised.value.tools == ["alpha", "mid", "zeta"]
    message = str(raised.value)
    assert "alpha, mid, zeta" in message and "fine" not in message
    for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
        assert hint in message
    assert "ext.tool(hints=ToolHints(...))" in message

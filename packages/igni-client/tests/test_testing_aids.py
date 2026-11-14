"""`igni_client.testing`: `sample`, `Steps` and `read_frame`, the aids a test is built from."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import pytest
from pydantic import BaseModel, Field

from igni_client.models import (
    ContentDelta,
    ProcessTailResult,
    RunCompleted,
    RunStarted,
    ToolCompleted,
)
from igni_client.testing import Delay, Pause, Steps, UnknownFrame, sample
from igni_client.testing.inbound import read_frame
from igni_client.testing.samples import WHEN


class Inner(BaseModel):
    n: int


class Outer(BaseModel):
    s: str
    f: float
    b: bool
    when: datetime
    mode: Literal["a", "b"]
    either: int | str
    maybe: str | None
    items: list[Inner]
    table: dict[str, int]
    pair: tuple[int, str]
    tagged: Annotated[int, Field(ge=0)]
    anything: Any


def test_a_sample_fills_every_field_with_the_first_value_of_its_type() -> None:
    value = sample(Outer)

    assert value.s == "x"
    assert value.f == 1.5
    assert value.b is True
    assert value.when == WHEN == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert value.mode == "a"
    assert value.either == 1
    assert value.maybe == "x"
    assert value.items == [Inner(n=1)]
    assert value.table == {"k": 1}
    assert value.pair == (1, "x")
    assert value.tagged == 1
    assert value.anything == "x"


def test_a_sample_is_the_same_value_every_time() -> None:
    assert sample(Outer) == sample(Outer)
    assert sample(ProcessTailResult) == sample(ProcessTailResult)


def test_a_sample_of_the_contracts_own_model_is_a_valid_one() -> None:
    value = sample(ProcessTailResult)

    assert ProcessTailResult.model_validate(value.model_dump(by_alias=True)) == value


def test_a_sample_of_none_is_none_and_of_a_bare_scalar_is_its_value() -> None:
    assert sample(type(None)) is None
    assert sample(int) == 1
    assert sample(str) == "x"


def test_a_run_that_answers_starts_says_the_text_and_completes() -> None:
    steps = Steps.answer("hello there world", model="m", agent="a")

    assert steps == [
        RunStarted(run_id="r-1", agent_name="a", model="m"),
        ContentDelta(text="hello there world"),
        RunCompleted(run_id="r-1", input_tokens=10, output_tokens=3),
    ]


def test_the_default_run_answers_with_the_agent_and_model_igni_reports() -> None:
    started = Steps.answer("x")[0]

    assert isinstance(started, RunStarted)
    assert (started.agent_name, started.model) == ("igni", "igni-1")


def test_echo_answers_echo_colon_the_text() -> None:
    assert Steps.echo("hi")[1] == ContentDelta(text="echo: hi")


def test_an_approval_pauses_on_a_requirement_named_for_its_tool() -> None:
    pause = Steps.approval("write_file", path="/a")

    assert isinstance(pause, Pause)
    (req,) = pause.requirements
    assert req.requirement_id == "req-write_file"
    assert req.tool_name == "write_file"
    assert req.friendly_name == "write file"
    assert req.tool_args == {"path": "/a"}
    assert req.agent_path == []
    assert Steps.approval("t", requirement_id="mine").requirements[0].requirement_id == "mine"


def test_a_rejected_call_resumes_as_rejected_and_then_answers() -> None:
    steps = Steps.rejected()

    assert steps[0] == ToolCompleted(run_id="r-1", summary="rejected", is_rejected=True)
    assert steps[1:] == Steps.answer("I did not run it.")


def test_a_delay_holds_its_seconds() -> None:
    assert Delay(seconds=0.5).seconds == 0.5


def test_a_frame_the_client_built_is_read_back_as_its_typed_class() -> None:
    from igni_client.models import FRAME_TYPES

    name, cls = next(iter(FRAME_TYPES.items()))
    frame = read_frame(json.dumps({"type": name, **sample(cls).model_dump(by_alias=True)}))

    assert isinstance(frame, cls)


def test_a_frame_of_a_type_nobody_knows_is_an_unknown_frame_keeping_everything() -> None:
    frame = read_frame(b'{"type": "nope", "extra": 1}')

    assert isinstance(frame, UnknownFrame)
    assert frame.type == "nope"
    assert frame.model_extra == {"extra": 1}


def test_a_frame_with_no_type_is_unknown_with_an_empty_type() -> None:
    frame = read_frame('{"a": 1}')

    assert isinstance(frame, UnknownFrame)
    assert frame.type == ""


@pytest.mark.parametrize(("raw", "why"), [("{", "not JSON"), ("[1]", "not a JSON object")])
def test_what_is_not_a_json_object_is_refused_in_words(raw: str, why: str) -> None:
    with pytest.raises(ValueError, match=why):
        read_frame(raw)


def test_a_known_type_whose_fields_do_not_fit_is_refused() -> None:
    from igni_client.models import FRAME_TYPES

    name = next(iter(FRAME_TYPES))

    with pytest.raises(ValueError):
        read_frame(json.dumps({"type": name, "zz_unfit": 1, **{"__bad": object.__name__}}))

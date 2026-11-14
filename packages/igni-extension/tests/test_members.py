"""The pieces `ext.host` is built from: objects, properties and signals, in isolation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from igni_extension import HostError
from igni_extension.members import NO_RESULT, HostObject, Property, Signal, parse, plain


class Colour(StrEnum):
    RED = "red"


class Point(BaseModel):
    x: int
    colour: Colour = Colour.RED


class Link:
    """What igni answers: records each request and answers with `answer`."""

    def __init__(self, answer: Any = None, refuse: bool = False) -> None:
        self.requests: list[dict[str, Any]] = []
        self.answer = answer
        self.refuse = refuse

    async def request(
        self,
        op: str,
        path: str,
        *,
        window: str | None = None,
        session: str | None = None,
        params: dict[str, Any] | None = None,
        value: Any = None,
    ) -> Any:
        self.requests.append(
            {
                "op": op,
                "path": path,
                "window": window,
                "session": session,
                "params": params,
                "value": value,
            }
        )
        if self.refuse:
            raise HostError("not_granted", "chat.post is not granted")
        return self.answer


class Chat(HostObject):
    PATH = "chat"


def test_parse_reads_a_value_as_the_type_and_refuses_what_does_not_fit() -> None:
    assert parse(Point, {"x": 1}) == Point(x=1)
    assert parse(list[int], [1, 2]) == [1, 2]
    assert parse(int | None, None) is None
    with pytest.raises(ValidationError):
        parse(Point, {"x": "not a number"})
    with pytest.raises(ValidationError):
        parse(int, "7x")


def test_parse_works_for_a_type_pydantic_cannot_hash() -> None:
    assert parse(list[Point], [{"x": 2}]) == [Point(x=2)]
    assert parse(dict[str, list[int]], {"a": [1]}) == {"a": [1]}


def test_plain_turns_models_enums_and_nested_values_into_json() -> None:
    value = {"points": [Point(x=1)], "colours": (Colour.RED,), "n": 2, "none": None}

    assert plain(value) == {
        "points": [{"x": 1, "colour": "red"}],
        "colours": ["red"],
        "n": 2,
        "none": None,
    }
    assert plain("text") == "text"


async def test_a_call_sends_the_member_path_and_parameters_as_plain_values() -> None:
    link = Link(answer={"x": 5})
    chat = Chat(link, window="w-1", session="s-1")

    result = await chat._call("move", {"to": Point(x=3), "by": 2}, Point)

    assert result == Point(x=5)
    assert link.requests == [
        {
            "op": "call",
            "path": "chat.move",
            "window": "w-1",
            "session": "s-1",
            "params": {"to": {"x": 3, "colour": "red"}, "by": 2},
            "value": None,
        }
    ]


async def test_a_parameter_given_as_none_is_left_out_of_the_call_but_zero_and_empty_are_not() -> (
    None
):
    link = Link()
    chat = Chat(link)

    await chat._call(
        "post", {"text": "hi", "title": None, "count": 0, "tags": [], "flag": False}, NO_RESULT
    )

    assert link.requests[0]["params"] == {"text": "hi", "count": 0, "tags": [], "flag": False}


@pytest.mark.parametrize("answer", [None, "ignored", {"anything": 1}, 3])
async def test_a_method_that_returns_nothing_returns_none_whatever_the_host_answers(
    answer: Any,
) -> None:
    chat = Chat(Link(answer=answer))

    assert await chat._call("post", {}, NO_RESULT) is None


async def test_an_answer_that_does_not_fit_the_result_type_is_refused() -> None:
    chat = Chat(Link(answer={"x": "nope"}))

    with pytest.raises(ValidationError):
        await chat._call("move", {}, Point)


async def test_the_host_refusing_reaches_the_caller() -> None:
    chat = Chat(Link(refuse=True))

    with pytest.raises(HostError, match="not granted"):
        await chat._call("post", {}, NO_RESULT)


async def test_the_root_object_names_its_members_without_a_dot() -> None:
    link = Link(answer=True)
    root = HostObject(link)

    await root._call("ping", {}, bool)
    assert await Property(root, "version", bool, writable=False) is True

    assert [r["path"] for r in link.requests] == ["ping", "version"]


async def test_a_property_reads_as_its_type_with_the_objects_addressing() -> None:
    link = Link(answer={"x": 9})
    prop = Property[Point](Chat(link, window="w-1", session="s-1"), "origin", Point, writable=False)

    assert prop.path == "chat.origin"
    assert await prop == Point(x=9)
    assert await prop.get() == Point(x=9)
    assert [(r["op"], r["path"], r["window"], r["session"]) for r in link.requests] == [
        ("get", "chat.origin", "w-1", "s-1")
    ] * 2


async def test_a_property_read_that_does_not_fit_its_type_is_refused() -> None:
    prop = Property[int](Chat(Link(answer="seven")), "count", int, writable=False)

    with pytest.raises(ValidationError):
        await prop.get()


async def test_a_property_is_written_as_plain_value_with_the_objects_addressing() -> None:
    link = Link()
    prop = Property[Point](Chat(link, session="s-1"), "origin", Point, writable=True)

    await prop.set(Point(x=4))

    assert link.requests == [
        {
            "op": "set",
            "path": "chat.origin",
            "window": None,
            "session": "s-1",
            "params": None,
            "value": {"x": 4, "colour": "red"},
        }
    ]


async def test_a_property_that_is_not_writable_refuses_before_anything_is_sent() -> None:
    link = Link()
    prop = Property[bool](Chat(link), "processing", bool, writable=False)

    with pytest.raises(TypeError, match=r"host\.chat\.processing cannot be set"):
        await prop.set(True)

    assert link.requests == []


def test_a_property_and_a_signal_say_what_they_are() -> None:
    prop = Property[bool](Chat(Link()), "processing", bool, writable=True)
    signal = Signal[Point]("chat.run_completed", Point)

    assert repr(prop) == "Property('chat.processing')"
    assert repr(signal) == "Signal('chat.run_completed')"
    assert (prop.name, prop.annotation, prop.writable) == ("processing", bool, True)
    assert (signal.name, signal.carries) == ("chat.run_completed", Point)


def test_a_signal_reads_what_the_host_sent_as_the_type_it_carries() -> None:
    signal = Signal[Point]("chat.run_completed", Point)

    assert signal.parse({"x": 2}) == Point(x=2)
    with pytest.raises(ValidationError):
        signal.parse({"x": "two"})

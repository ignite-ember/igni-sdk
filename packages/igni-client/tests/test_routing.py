"""Where each message from igni goes: its call, its stream, its listeners and followers."""

from __future__ import annotations

import re
from typing import Any

from igni_client import RunInterrupted
from igni_client.events import parse_event
from igni_client.routing import Interruption, Router


def test_a_request_id_is_the_prefix_the_routers_own_tag_and_a_count() -> None:
    router = Router()

    first, second = router.new_id("run"), router.new_id("hitl")

    tag = re.fullmatch(r"run-([0-9a-f]{8})-1", first)
    assert tag is not None, first
    assert second == f"hitl-{tag.group(1)}-2", "one tag per router, a count that goes on"
    assert Router().new_id("run") != first, "another router's tag is its own"


async def test_a_request_that_asks_for_a_message_is_answered_by_one_and_not_by_an_rpc_response() -> (
    None
):
    router = Router()
    answer = router.expect("req-1", "message")
    stream = router.open_stream("req-1")

    router.deliver(parse_event({"type": "rpc_response", "id": "req-1", "result": 1}))
    assert not answer.done(), "this call is answered with a message of igni's own"
    router.deliver(parse_event({"type": "rpc_request", "id": "req-1", "method": "echoed"}))
    assert not answer.done(), "igni echoing a request is never its answer"
    router.deliver(parse_event({"type": "info_message", "id": "req-1", "text": "done"}))

    assert answer.result().type == "info_message"
    assert [e.type for e in _drained(stream)] == ["rpc_response", "rpc_request"], (
        "what is not the answer goes on to the stream"
    )


async def test_a_request_that_asks_for_an_rpc_response_is_answered_by_it_or_by_an_error() -> None:
    router = Router()
    refused = router.expect("req-1")
    streamed = router.open_stream("req-1")

    router.deliver(parse_event({"type": "info_message", "id": "req-1", "text": "streamed"}))
    assert not refused.done(), "a message carrying the id is one of the call's streamed events"
    router.deliver(parse_event({"type": "error", "id": "req-1", "text": "refused"}))

    assert refused.result().type == "error"
    assert [e.type for e in _drained(streamed)] == ["info_message"]


async def test_a_forgotten_call_lets_its_id_go_to_its_stream() -> None:
    router = Router()
    router.expect("req-1", "message")
    stream = router.open_stream("req-1")

    router.forget("req-1")
    router.deliver(parse_event({"type": "info_message", "id": "req-1", "text": "later"}))

    assert [e.type for e in _drained(stream)] == ["info_message"]


async def test_a_call_expected_again_after_it_was_forgotten_is_answered_as_asked_the_second_time() -> (
    None
):
    router = Router()
    router.expect("req-1", "message")
    router.forget("req-1")
    again = router.expect("req-1")

    router.deliver(parse_event({"type": "info_message", "id": "req-1", "text": "not it"}))
    assert not again.done(), "the first ask is forgotten with the call, not kept for the id"
    router.deliver(parse_event({"type": "rpc_response", "id": "req-1", "result": 1}))

    assert again.done()


async def test_a_follower_hears_everything_and_the_interruption_until_it_unfollows() -> None:
    router = Router()
    follower = router.follow()
    listener = router.listen()

    router.deliver(parse_event({"type": "info_message", "text": "no id"}))
    router.deliver(parse_event({"type": "info_message", "id": "nobody-waits", "text": "x"}))
    moved = RunInterrupted("igni moved")
    router.interrupt(moved)

    heard = _drained(follower)
    assert [getattr(item, "text", None) for item in heard[:2]] == ["no id", "x"]
    assert isinstance(heard[2], Interruption) and heard[2].error is moved
    assert listener.qsize() == 2, "a listener hears messages, never an interruption"

    router.unfollow(follower)
    router.unfollow(follower)  # unfollowing twice, or a queue never followed, is silent
    router.deliver(parse_event({"type": "info_message", "text": "after"}))
    router.interrupt(moved)
    assert follower.empty()


async def test_a_message_with_no_waiter_and_no_stream_is_dropped() -> None:
    router = Router()
    listener = router.listen()

    router.deliver(parse_event({"type": "info_message", "id": "nobody", "text": "x"}))

    assert listener.qsize() == 1, "heard by listeners, then it goes no further"
    assert router._waiting == {} and router._streams == {}


async def test_an_interruption_leaves_a_call_already_answered_as_it_was() -> None:
    router = Router()
    answered = router.expect("req-1")
    router.deliver(parse_event({"type": "rpc_response", "id": "req-1", "result": 1}))

    router.interrupt(RunInterrupted("igni moved"))

    assert answered.exception() is None and answered.result().type == "rpc_response"


def _drained(queue: Any) -> list[Any]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items

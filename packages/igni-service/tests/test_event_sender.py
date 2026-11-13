"""`EventSender`: which answers are retried, how the wait grows, and what is refused up front.

The sender is real; what it sends through is a scripted stand-in for the service's tokens, so
each test decides what igni answers, call by call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from igni_service import EventRefused, IgniUnavailable, Producer
from igni_service.events import (
    MAX_KEY,
    MAX_PAYLOAD_BYTES,
    MAX_TYPE,
    EventAccepted,
    EventSender,
    ServiceEventRequest,
)
from igni_service.service_tokens import ServiceTokens
from igni_service.urls import IgniPaths

STORED = {"event_id": "ev-1"}


class Scripted:
    """Answers `request` from a list: a response, or an exception to raise, call by call."""

    def __init__(self, *answers: httpx.Response | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    async def request(
        self, method: str, path: str, *, org_id: str, **kwargs: Any
    ) -> httpx.Response:
        self.calls.append({"method": method, "path": path, "org_id": org_id, **kwargs})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Waits:
    def __init__(self) -> None:
        self.seconds: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.seconds.append(seconds)


def sender(
    scripted: Scripted, waits: Waits, *, attempts: int | None = None, backoff: float | None = None
) -> EventSender:
    return EventSender(
        cast(ServiceTokens, scripted), attempts=attempts, backoff=backoff, sleep=waits
    )


def answer(status: int, body: Any = STORED) -> httpx.Response:
    return httpx.Response(status, json=body)


def event(**overrides: Any) -> ServiceEventRequest:
    return ServiceEventRequest(producer=Producer.person("u-max"), type="claim.created", **overrides)


async def test_the_defaults_are_three_tries_and_half_a_second() -> None:
    scripted = Scripted(*[answer(503)] * 3)
    waits = Waits()

    with pytest.raises(IgniUnavailable):
        await sender(scripted, waits).send("org-acme", event())

    assert (EventSender.ATTEMPTS, EventSender.BACKOFF) == (3, 0.5)
    assert len(scripted.calls) == 3
    assert waits.seconds == [0.5, 1.0]


async def test_an_event_is_posted_for_its_organisation_to_the_service_events_path() -> None:
    scripted = Scripted(answer(200))

    accepted = await sender(scripted, Waits()).send("org-acme", event(event_key="k"))

    assert accepted == EventAccepted(event_id="ev-1", expires_at=None, duplicate=False)
    [call] = scripted.calls
    assert (call["method"], call["path"], call["org_id"]) == (
        "POST",
        IgniPaths.SERVICE_EVENTS,
        "org-acme",
    )
    assert call["json"] == {
        "producer": {"kind": "person", "id": "u-max"},
        "type": "claim.created",
        "payload": {},
        "event_key": "k",
    }


async def test_a_202_is_as_good_as_a_200_and_says_when_igni_dropped_a_duplicate() -> None:
    scripted = Scripted(
        answer(202, {"event_id": "ev-9", "duplicate": True, "expires_at": "2026-12-01T10:00:00Z"})
    )

    accepted = await sender(scripted, Waits()).send("org-acme", event())

    assert accepted.duplicate is True
    assert accepted.expires_at == datetime(2026, 12, 1, 10, tzinfo=UTC)


async def test_an_expiry_goes_on_the_wire_as_an_iso_time() -> None:
    scripted = Scripted(answer(200))
    when = datetime(2026, 12, 1, 10, 30, tzinfo=UTC)

    await sender(scripted, Waits()).send("org-acme", event(expires_at=when))

    assert scripted.calls[0]["json"]["expires_at"] == "2026-12-01T10:30:00Z"


@pytest.mark.parametrize("status", [400, 403, 404, 409, 422])
async def test_a_refusal_other_than_429_is_final_and_carries_igni_s_words(status: int) -> None:
    scripted = Scripted(httpx.Response(status, text="no such producer"), answer(200))
    waits = Waits()

    with pytest.raises(EventRefused) as refused:
        await sender(scripted, waits).send("org-acme", event())

    assert (refused.value.status, refused.value.detail) == (status, "no such producer")
    assert len(scripted.calls) == 1 and waits.seconds == []


async def test_a_429_is_retried_and_the_next_answer_is_taken() -> None:
    scripted = Scripted(answer(429), answer(200))
    waits = Waits()

    accepted = await sender(scripted, waits, backoff=2).send("org-acme", event())

    assert accepted.event_id == "ev-1"
    assert len(scripted.calls) == 2 and waits.seconds == [2]


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_a_server_failure_is_retried_then_reported_with_its_status(status: int) -> None:
    scripted = Scripted(*[answer(status)] * 3)

    with pytest.raises(IgniUnavailable, match=str(status)):
        await sender(scripted, Waits()).send("org-acme", event())

    assert len(scripted.calls) == 3


async def test_the_wait_doubles_after_each_try_and_there_is_none_after_the_last() -> None:
    scripted = Scripted(*[answer(503)] * 4)
    waits = Waits()

    with pytest.raises(IgniUnavailable):
        await sender(scripted, waits, attempts=4, backoff=0.25).send("org-acme", event())

    assert waits.seconds == [0.25, 0.5, 1.0]


async def test_a_backoff_of_zero_waits_nothing_on_every_retry() -> None:
    scripted = Scripted(answer(503), answer(503), answer(200))
    waits = Waits()

    await sender(scripted, waits, backoff=0).send("org-acme", event())

    assert waits.seconds == [0, 0]


@pytest.mark.parametrize("attempts", [0, -3, 1])
async def test_fewer_than_one_try_still_tries_once(attempts: int) -> None:
    scripted = Scripted(answer(503), answer(200))
    waits = Waits()

    with pytest.raises(IgniUnavailable):
        await sender(scripted, waits, attempts=attempts).send("org-acme", event())

    assert len(scripted.calls) == 1 and waits.seconds == []


async def test_igni_not_reached_is_retried_and_the_last_failure_is_raised() -> None:
    first, last = IgniUnavailable("first"), IgniUnavailable("last")
    scripted = Scripted(first, last)
    waits = Waits()

    with pytest.raises(IgniUnavailable) as raised:
        await sender(scripted, waits, attempts=2).send("org-acme", event())

    assert raised.value is last
    assert len(scripted.calls) == 2 and len(waits.seconds) == 1


async def test_a_failure_then_a_good_answer_is_a_success() -> None:
    scripted = Scripted(IgniUnavailable("down"), answer(200))

    assert (await sender(scripted, Waits()).send("org-acme", event())).event_id == "ev-1"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"no": "event id"}),
        httpx.Response(202, json=["a list"]),
    ],
)
async def test_a_success_that_is_not_an_accepted_event_is_not_retried(
    response: httpx.Response,
) -> None:
    scripted = Scripted(response, answer(200))
    waits = Waits()

    with pytest.raises(IgniUnavailable, match="something else"):
        await sender(scripted, waits).send("org-acme", event())

    assert len(scripted.calls) == 1 and waits.seconds == []


class WithFiles(BaseModel):
    name: str
    attachments: list[str] | None = None


@pytest.mark.parametrize(
    ("item", "sent"),
    [
        (WithFiles(name="a", attachments=[]), {"name": "a"}),
        (WithFiles(name="a"), {"name": "a"}),
        (WithFiles(name="a", attachments=["f"]), {"name": "a", "attachments": ["f"]}),
    ],
)
async def test_an_empty_list_of_attachments_is_not_sent_and_a_full_one_is(
    item: WithFiles, sent: dict[str, Any]
) -> None:
    scripted = Scripted(answer(200))

    await sender(scripted, Waits()).post("org-acme", "/v1/anything", item, what="thing")

    assert scripted.calls[0]["path"] == "/v1/anything"
    assert scripted.calls[0]["json"] == sent


def test_a_payload_may_be_exactly_the_limit_as_json_and_not_one_more() -> None:
    # `{"a": "` and `"}` are nine characters around the value.
    event(payload={"a": "x" * (MAX_PAYLOAD_BYTES - 9)})

    with pytest.raises(ValidationError, match="at most 65536 bytes"):
        event(payload={"a": "x" * (MAX_PAYLOAD_BYTES - 8)})


@pytest.mark.parametrize(
    ("type_", "key", "ok"),
    [
        ("t" * MAX_TYPE, "k" * MAX_KEY, True),
        ("t" * (MAX_TYPE + 1), None, False),
        ("t", "k" * (MAX_KEY + 1), False),
        ("t", "", False),
        ("", None, False),
    ],
)
def test_a_type_and_a_key_have_igni_s_lengths(type_: str, key: str | None, ok: bool) -> None:
    def make() -> ServiceEventRequest:
        return ServiceEventRequest(producer=Producer.person("u"), type=type_, event_key=key)

    if ok:
        make()
    else:
        with pytest.raises(ValidationError):
            make()


def test_a_producer_has_an_id_a_known_kind_and_nothing_else() -> None:
    with pytest.raises(ValidationError):
        Producer.person("")
    with pytest.raises(ValidationError):
        Producer.app("")
    with pytest.raises(ValidationError):
        Producer.model_validate({"kind": "person", "id": "u", "extra": 1})
    with pytest.raises(ValidationError):
        event_with_extra = {"producer": {"kind": "app", "id": "a"}, "type": "t", "other": 1}
        ServiceEventRequest.model_validate(event_with_extra)
    assert Producer.app("a").model_dump() == {"kind": "app", "id": "a"}

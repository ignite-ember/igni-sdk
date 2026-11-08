"""`@ext.on_service_event`: an event the extension's service sent is the extension's to act on.

igni posts nothing for an event; the handler acts through its host calls.
The answer only says whether a handler took it — `allow` — or not:
`reject` with no handler for its type, `failed` when the handler raised.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from igni_extension import Caller, CallerKind, IgniExtension, ServiceEvent
from igni_extension.service_events import ServiceEventHandlers
from igni_extension.testing import FakeHost

EVENT = {
    "event_id": "evt-1",
    "extension_id": "acme.example",
    "type": "index.ready",
    "payload": {"repo": "acme/api"},
}


@pytest.fixture
async def host() -> AsyncIterator[FakeHost]:
    async with FakeHost() as fake:
        yield fake


async def _connected(ext: IgniExtension) -> asyncio.Task[None]:
    await ext.connect()
    return asyncio.create_task(ext.connection.serve_forever())


async def _answer(
    ext: IgniExtension, host: FakeHost, event: Any = EVENT, caller: Caller | None = None
) -> dict[str, Any]:
    task = await _connected(ext)
    try:
        return await host.hook("ServiceEvent", event, caller=caller)
    finally:
        task.cancel()
        await ext.aclose()


async def test_the_handler_for_the_type_takes_it_and_igni_posts_nothing(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    seen: list[ServiceEvent] = []

    @ext.on_service_event("index.ready")
    async def ready(event: ServiceEvent) -> None:
        seen.append(event)

    answer = await _answer(ext, host)
    assert answer["outcome"] == "allow" and "value" not in answer
    assert [e.payload for e in seen] == [{"repo": "acme/api"}]


async def test_without_a_handler_for_its_type_it_is_not_handled(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())

    @ext.on_service_event("build.failed")
    def failed(event: ServiceEvent) -> None:
        return None

    answer = await _answer(ext, host)
    assert answer["outcome"] == "reject"
    assert answer["reason"] == "no handler for index.ready"


async def test_a_handler_that_raises_is_reported_failed(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())

    @ext.on_service_event("index.ready")
    def broken(event: ServiceEvent) -> None:
        raise RuntimeError("the index service is down")

    answer = await _answer(ext, host)
    assert answer["outcome"] == "failed" and "the index service is down" in answer["reason"]


async def test_a_catch_all_handles_any_other_type(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    seen: list[str] = []

    @ext.on_service_event()
    def anything(event: ServiceEvent) -> None:
        seen.append(event.type)

    answer = await _answer(ext, host)
    assert seen == ["index.ready"] and answer["outcome"] == "allow"


async def test_an_event_that_does_not_validate_is_reported_failed(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())

    @ext.on_service_event()
    def anything(event: ServiceEvent) -> None:
        return None

    answer = await _answer(ext, host, {"event_id": "evt-2"})
    assert answer["outcome"] == "failed" and answer["reason"].startswith("not an event")


def test_a_type_has_one_handler() -> None:
    ext = IgniExtension("acme.example", environ={})
    ext.on_service_event("x")(lambda event: None)
    with pytest.raises(ValueError, match="has a handler already"):
        ext.on_service_event("x")(lambda event: None)


async def test_a_handler_that_returns_a_value_still_takes_it_and_igni_says_nothing(
    host: FakeHost, caplog: pytest.LogCaptureFixture
) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())

    async def old_style(event: ServiceEvent) -> str:
        return "The index is ready; review it."

    # A handler returns nothing, and a type checker says so.
    ext.on_service_event("index.ready")(old_style)  # type: ignore[arg-type]

    with caplog.at_level(logging.DEBUG, logger="igni_extension.service_events"):
        answer = await _answer(ext, host)
    assert answer["outcome"] == "allow" and "value" not in answer
    assert host.calls == []
    assert [r for r in caplog.records if r.name == "igni_extension.service_events"] == []


async def test_the_handler_for_the_type_wins_over_the_catch_all(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    seen: list[str] = []

    @ext.on_service_event()
    def anything(event: ServiceEvent) -> None:
        seen.append("catch-all")

    @ext.on_service_event("index.ready")
    def ready(event: ServiceEvent) -> None:
        seen.append("index.ready")

    assert (await _answer(ext, host))["outcome"] == "allow"
    assert seen == ["index.ready"]


def test_no_type_and_none_are_both_the_catch_all() -> None:
    ext = IgniExtension("acme.example", environ={})
    ext.on_service_event(None)(lambda event: None)
    with pytest.raises(ValueError, match=r"service event '\*' has a handler already"):
        ext.on_service_event()(lambda event: None)


async def test_the_handler_sees_the_caller_igni_named(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    ada = Caller(kind=CallerKind.PERSON, id="u-ada", org="org-acme", group="g-legal")
    seen: list[Caller | None] = []

    @ext.on_service_event("index.ready")
    def ready(event: ServiceEvent) -> None:
        seen.append(Caller.current())

    assert (await _answer(ext, host, caller=ada))["outcome"] == "allow"
    assert seen == [ada]


async def test_a_malformed_principal_is_no_caller_to_the_handler(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    heard: asyncio.Future[Caller | None] = asyncio.get_running_loop().create_future()

    @ext.on_service_event("index.ready")
    def ready(event: ServiceEvent) -> None:
        heard.get_loop().call_soon_threadsafe(heard.set_result, Caller.current())

    task = await _connected(ext)
    frame = {
        "op": "hook",
        "id": "h-raw",
        "event": "ServiceEvent",
        "value": EVENT,
        "principal": {"kind": "person"},
    }
    try:
        await host.tell("SessionEnd", {})  # nothing hooks it; returns once connected
        for socket in list(host._sockets):
            await socket.send(json.dumps(frame))
        assert await asyncio.wait_for(heard, 5) is None
    finally:
        task.cancel()
        await ext.aclose()


async def test_answer_puts_the_caller_it_is_given_in_scope() -> None:
    handlers = ServiceEventHandlers()
    ada = Caller(kind=CallerKind.PERSON, id="u-ada", org="org-acme", group="g-legal")
    seen: list[Caller | None] = []
    handlers.on()(lambda event: seen.append(Caller.current()))

    answer = await handlers.answer("h-1", EVENT, caller=ada)

    assert answer.outcome == "allow"
    assert seen == [ada] and seen[0] is ada
    with pytest.raises(TypeError, match="principal"):
        await handlers.answer("h-2", EVENT, principal=ada.model_dump(mode="json"))  # type: ignore[call-arg]


async def test_a_plain_def_handler_runs_off_the_loop(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    threads: list[int] = []

    @ext.on_service_event("index.ready")
    def ready(event: ServiceEvent) -> None:
        threads.append(threading.get_ident())

    assert (await _answer(ext, host))["outcome"] == "allow"
    assert threads and threads[0] != threading.get_ident()


async def test_a_handler_that_raises_is_logged_with_its_traceback(
    host: FakeHost, caplog: pytest.LogCaptureFixture
) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())

    @ext.on_service_event("index.ready")
    def broken(event: ServiceEvent) -> None:
        raise RuntimeError("the index service is down")

    with caplog.at_level(logging.ERROR, logger="igni_extension.service_events"):
        answer = await _answer(ext, host)
    assert (answer["outcome"], answer["reason"]) == ("failed", "the index service is down")
    (record,) = [r for r in caplog.records if r.name == "igni_extension.service_events"]
    assert record.getMessage() == "igni: the handler of service event index.ready failed"
    assert record.exc_info is not None and isinstance(record.exc_info[1], RuntimeError)


async def test_an_event_keeps_fields_igni_adds_and_defaults_the_rest(host: FakeHost) -> None:
    ext = IgniExtension("acme.example", environ=host.environment())
    seen: list[ServiceEvent] = []

    @ext.on_service_event("index.ready")
    async def ready(event: ServiceEvent) -> None:
        seen.append(event)

    raw = {"event_id": "evt-3", "type": "index.ready", "attempt": 2}
    assert (await _answer(ext, host, raw))["outcome"] == "allow"
    (event,) = seen
    assert (event.extension_id, event.client_id, event.payload) == ("", "", {})
    assert (event.event_key, event.created_at, event.expires_at) == (None, None, None)
    assert event.model_extra == {"attempt": 2}


@pytest.mark.parametrize(
    "raw",
    [None, "index.ready", ["evt-1"], {"event_id": "evt-4"}, {"event_id": 4, "type": "x"}],
)
async def test_what_is_not_an_event_is_failed_with_why(raw: object) -> None:
    handlers = ServiceEventHandlers()
    handlers.on()(lambda event: None)
    with pytest.raises(ValidationError) as invalid:
        ServiceEvent.model_validate(raw)

    answer = await handlers.answer("h-1", raw)
    assert answer.outcome == "failed"
    assert answer.reason == f"not an event: {invalid.value}"


class _Unreadable(Mapping[str, object]):
    """A mapping that breaks when read — never what a JSON frame decodes to."""

    def __getitem__(self, key: str) -> object:
        raise RuntimeError("cannot read it")

    def __iter__(self) -> Iterator[str]:
        return iter(["event_id", "type"])

    def __len__(self) -> int:
        return 2


async def test_only_a_validation_error_is_answered_not_an_event() -> None:
    handlers = ServiceEventHandlers()
    handlers.on()(lambda event: None)
    with pytest.raises(RuntimeError, match="cannot read it"):
        await handlers.answer("h-1", _Unreadable())

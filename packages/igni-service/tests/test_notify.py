"""`host.notify`: the §10.1 wire, igni's limits, and retries."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from igni_service import (
    IgniService,
    IgniUnavailable,
    Notification,
    NotificationRefused,
    Target,
)
from igni_service.notifications import Notifier
from igni_service.testing import FakeIgni
from igni_service.urls import IgniPaths

from .conftest import ORG
from .test_registration import write_bundle


def comment_values(n: int = 1) -> dict[str, object]:
    return {
        "kind": "comment",
        "title": "Runbook",
        "body": "Ada: can we drop step 3?",
        "actor": "ada@acme.test",
        "target": Target(page="acme.example", params={"slug": "runbook", "comment": f"c{n}"}),
        "event_key": f"comment:c{n}",
        "recipients": ["max@acme.test", "u-sam"],
    }


def comment(n: int = 1, **overrides: object) -> Notification:
    return Notification.model_validate(comment_values(n) | overrides)


async def test_a_notification_goes_on_the_wire_as_igni_reads_it(
    igni: IgniService, fake: FakeIgni
) -> None:
    delivered = await igni.host(ORG).notify(comment())

    assert delivered.delivered == 2
    [seen] = fake.traffic.requests_to(IgniPaths.NOTIFICATIONS)
    assert seen.headers["authorization"].startswith("Bearer service-")
    assert seen.json_body() == {
        "notifications": [
            {
                "kind": "comment",
                "title": "Runbook",
                "body": "Ada: can we drop step 3?",
                "actor": "ada@acme.test",
                "target": {"page": "acme.example", "params": {"slug": "runbook", "comment": "c1"}},
                "event_key": "comment:c1",
                "recipients": ["max@acme.test", "u-sam"],
            }
        ]
    }
    assert {d.user_id for d in fake.notifications.deliveries} == {"u-max", "u-sam"}


async def test_many_notifications_go_in_calls_of_at_most_a_hundred(
    igni: IgniService, fake: FakeIgni
) -> None:
    delivered = await igni.host(ORG).notify(*(comment(n) for n in range(250)))

    calls = [len(call.notifications) for call in fake.notifications.calls]
    assert calls == [100, 100, 50]
    assert delivered.delivered == 500


async def test_a_long_recipient_list_is_split_under_one_event_key(
    igni: IgniService, fake: FakeIgni
) -> None:
    recipients = [f"stranger-{n}@acme.test" for n in range(2400)] + ["max@acme.test"]

    delivered = await igni.host(ORG).notify(comment(recipients=recipients))

    [call] = fake.notifications.calls
    assert [len(n.recipients) for n in call.notifications] == [1000, 1000, 401]
    assert {n.event_key for n in call.notifications} == {"comment:c1"}
    assert delivered.delivered == 1


async def test_a_notification_that_concerns_nobody_is_not_sent(
    igni: IgniService, fake: FakeIgni
) -> None:
    delivered = await igni.host(ORG).notify(comment(recipients=[]))

    assert delivered.delivered == 0
    assert fake.traffic.requests_to(IgniPaths.NOTIFICATIONS) == []


async def test_igni_tells_each_person_once_and_never_the_actor(
    igni: IgniService, fake: FakeIgni
) -> None:
    host = igni.host(ORG)
    notification = comment(recipients=["ada@acme.test", "u-max", "u-gone", "eve@other.test"])

    first = await host.notify(notification)
    again = await host.notify(notification)

    assert first.delivered == 1
    assert again.delivered == 0
    assert [d.user_id for d in fake.notifications.deliveries] == ["u-max"]


async def test_a_call_igni_could_not_take_is_retried(igni: IgniService, fake: FakeIgni) -> None:
    fake.traffic.fail(IgniPaths.NOTIFICATIONS, 503)
    pauses: list[float] = []

    async def recover(seconds: float) -> None:
        pauses.append(seconds)
        fake.traffic.heal()

    igni.notifier = Notifier(igni.tokens, sleep=recover)

    delivered = await igni.host(ORG).notify(comment())

    assert delivered.delivered == 2
    assert pauses == [0.5]
    assert len(fake.traffic.requests_to(IgniPaths.NOTIFICATIONS)) == 2


async def test_igni_staying_away_is_raised_after_the_retries(
    igni: IgniService, fake: FakeIgni
) -> None:
    fake.traffic.fail(IgniPaths.NOTIFICATIONS, 502)

    with pytest.raises(IgniUnavailable, match="502"):
        await igni.host(ORG).notify(comment())

    assert len(fake.traffic.requests_to(IgniPaths.NOTIFICATIONS)) == Notifier.ATTEMPTS


async def test_a_refusal_is_not_retried(igni: IgniService, fake: FakeIgni, tmp_path: Path) -> None:
    igni.registration._bundle_path = str(write_bundle(tmp_path))
    await igni.registration.start()

    with pytest.raises(NotificationRefused) as refused:
        await igni.host(ORG).notify(comment(target=Target(page="someone-elses.page")))

    assert refused.value.status == 400
    assert len(fake.traffic.requests_to(IgniPaths.NOTIFICATIONS)) == 1


def test_a_body_is_one_line() -> None:
    assert comment(body="  two\n  lines\tand  spaces ").body == "two lines and spaces"


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": ""},
        {"kind": "k" * 65},
        {"title": ""},
        {"title": "t" * 201},
        {"event_key": "e" * 201},
        {"actor": "a" * 321},
        {"recipients": ["r" * 321]},
        {"target": {"page": ""}},
        {"target": {"page": "p", "params": {f"k{n}": n for n in range(33)}}},
        {"target": {"page": "p", "params": {"big": "x" * 2100}}},
        {"target": {"page": "p", "params": {"nested": {"no": "dicts"}}}},
    ],
)
def test_what_igni_would_refuse_is_refused_where_it_is_written(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Notification.model_validate(comment_values() | overrides)


def test_the_host_is_for_one_organisation(igni: IgniService) -> None:
    with pytest.raises(ValueError, match="one organisation"):
        igni.host("")


async def test_a_busy_igni_is_retried_but_other_client_errors_are_not(
    igni: IgniService, fake: FakeIgni
) -> None:
    fake.traffic.fail(IgniPaths.NOTIFICATIONS, 429)
    with pytest.raises(IgniUnavailable, match="429"):
        await igni.host(ORG).notify(comment())
    assert len(fake.traffic.requests_to(IgniPaths.NOTIFICATIONS)) == Notifier.ATTEMPTS

    fake.traffic.reset()
    fake.traffic.fail(IgniPaths.NOTIFICATIONS, 404)
    with pytest.raises(NotificationRefused) as refused:
        await igni.host(ORG).notify(comment())
    assert refused.value.status == 404
    assert len(fake.traffic.requests_to(IgniPaths.NOTIFICATIONS)) == 1


async def test_the_wait_between_tries_doubles_and_none_follows_the_last(
    igni: IgniService, fake: FakeIgni
) -> None:
    fake.traffic.fail(IgniPaths.NOTIFICATIONS, 500)
    pauses: list[float] = []

    async def note(seconds: float) -> None:
        pauses.append(seconds)

    igni.notifier = Notifier(igni.tokens, attempts=4, backoff=0.25, sleep=note)

    with pytest.raises(IgniUnavailable):
        await igni.host(ORG).notify(comment())

    assert pauses == [0.25, 0.5, 1.0]
    assert len(fake.traffic.requests_to(IgniPaths.NOTIFICATIONS)) == 4


@pytest.mark.parametrize("attempts", [0, -3])
async def test_fewer_than_one_attempt_still_makes_one(
    igni: IgniService, fake: FakeIgni, attempts: int
) -> None:
    fake.traffic.fail(IgniPaths.NOTIFICATIONS, 500)
    pauses: list[float] = []

    async def note(seconds: float) -> None:
        pauses.append(seconds)

    igni.notifier = Notifier(igni.tokens, attempts=attempts, sleep=note)

    with pytest.raises(IgniUnavailable):
        await igni.host(ORG).notify(comment())

    assert len(fake.traffic.requests_to(IgniPaths.NOTIFICATIONS)) == 1
    assert pauses == []


class _Tokens:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls = 0

    async def request(self, *args: object, **kwargs: object) -> httpx.Response:
        self.calls += 1
        return self.response


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=["delivered"]),
        httpx.Response(200, json={"delivered": "many"}),
    ],
)
async def test_an_answer_that_is_not_a_delivery_count_is_igni_unavailable_and_not_retried(
    response: httpx.Response,
) -> None:
    tokens = _Tokens(response)
    notifier = Notifier(tokens, sleep=_no_sleep)  # type: ignore[arg-type]

    with pytest.raises(IgniUnavailable, match="something else"):
        await notifier.send(ORG, [comment()])

    assert tokens.calls == 1


async def _no_sleep(_: float) -> None:
    return None


def test_recipients_are_stripped_deduplicated_and_blanks_dropped() -> None:
    notification = comment(recipients=[" max@acme.test ", "max@acme.test", "", "   ", "u-sam"])

    assert notification.recipients == ["max@acme.test", "u-sam"]


def test_a_notification_is_split_into_groups_in_order_and_nothing_else_changes() -> None:
    notification = comment(recipients=["a", "b", "c", "d", "e"])

    parts = notification.split(2)

    assert [p.recipients for p in parts] == [["a", "b"], ["c", "d"], ["e"]]
    assert {p.event_key for p in parts} == {notification.event_key}
    assert notification.split(10)[0].recipients == notification.recipients
    assert comment(recipients=[]).split(2) == []


async def test_every_limit_is_accepted_at_its_edge() -> None:
    from igni_service.notifications import MAX_IDENTITY, MAX_KEY, MAX_KIND, MAX_TITLE

    notification = comment(
        kind="k" * MAX_KIND,
        title="t" * MAX_TITLE,
        event_key="e" * MAX_KEY,
        actor="a" * MAX_IDENTITY,
        recipients=["r" * MAX_IDENTITY],
        target=Target(page="p", params={f"k{n}": n for n in range(32)}),
    )

    assert len(notification.recipients[0]) == MAX_IDENTITY

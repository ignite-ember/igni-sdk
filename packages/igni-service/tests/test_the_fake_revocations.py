"""What the fake's revocation feed publishes and answers, read at its edges.

`FakeRevocations.publish` writes the watermark; `page` is the feed a
service polls: the cursor is how many were published, a poll that is up
to date is a 304, and a cursor igni cannot read is a 422.
"""

from __future__ import annotations

from typing import Any

import pytest

from igni_service.revocations import RevokedKind
from igni_service.testing import ManualClock
from igni_service.testing_revocations import FakeRevocations
from igni_service.testing_wire import RoutedCall, SeenRequest
from igni_service.urls import IgniPaths


def poll(
    feed: FakeRevocations, since: str | None = None, etag: str | None = None
) -> tuple[int, Any]:
    seen = SeenRequest(
        method="GET",
        path=IgniPaths.REVOCATIONS,
        headers={} if etag is None else {"if-none-match": etag},
        body=b"",
        query={} if since is None else {"since": [since]},
    )
    response = feed.page(RoutedCall(seen=seen))
    return response.status_code, (response.json() if response.content else {})


@pytest.fixture
def feed() -> FakeRevocations:
    return FakeRevocations(ManualClock(start=1_800_000_000.25))


def test_a_published_watermark_is_the_clocks_milliseconds_now(feed: FakeRevocations) -> None:
    revocation = feed.publish("u-ada", org_id="org-acme", incarnation="inc-2")

    assert revocation.not_before_ms == 1_800_000_000_250
    assert revocation.incarnation == "inc-2"
    assert (revocation.kind, revocation.reason, revocation.org_id) == (
        RevokedKind.PERSON,
        "removed",
        "org-acme",
    )
    assert feed.revocations == [revocation]


def test_a_watermark_for_no_organisation_is_every_organisations(feed: FakeRevocations) -> None:
    feed.publish("u-ada", org_id=None, reason="sessions withdrawn")

    _, body = poll(feed)

    assert body["revocations"][0]["org_id"] is None
    assert body["revocations"][0]["reason"] == "sessions withdrawn"


def test_the_feed_answers_what_follows_the_cursor_and_the_cursor_is_the_count(
    feed: FakeRevocations,
) -> None:
    for subject in ("a", "b", "c"):
        feed.publish(subject, org_id="org-acme")

    status, everything = poll(feed)
    _, after_one = poll(feed, since="1")
    _, after_all = poll(feed, since="3")
    _, beyond = poll(feed, since="99")

    assert status == 200 and everything["cursor"] == "3"
    assert [r["subject_id"] for r in everything["revocations"]] == ["a", "b", "c"]
    assert [r["subject_id"] for r in after_one["revocations"]] == ["b", "c"]
    assert after_all["revocations"] == [] and after_all["cursor"] == "3"
    assert beyond["revocations"] == [] and beyond["cursor"] == "3"


def test_an_empty_since_is_the_start(feed: FakeRevocations) -> None:
    feed.publish("a", org_id="org-acme")

    assert len(poll(feed, since="")[1]["revocations"]) == 1


def test_a_poll_that_is_up_to_date_is_not_modified_and_a_stale_one_is_answered(
    feed: FakeRevocations,
) -> None:
    assert poll(feed, etag='"0"')[0] == 304
    feed.publish("a", org_id="org-acme")

    stale = poll(feed, etag='"0"')
    current = poll(feed, etag='"1"')

    assert stale[0] == 200 and stale[1]["cursor"] == "1"
    assert current[0] == 304


@pytest.mark.parametrize("since", ["yesterday", "-1", "1.5", "²", "١"])
def test_a_cursor_that_is_not_ascii_digits_is_a_422_not_a_crash(
    feed: FakeRevocations, since: str
) -> None:
    status, body = poll(feed, since=since)

    assert status == 422
    assert body == {"detail": f"since must be a cursor, not {since!r}"}


def test_reset_forgets_every_revocation_and_the_cursor_starts_over(
    feed: FakeRevocations,
) -> None:
    feed.publish("a", org_id=None)

    feed.reset()

    assert feed.revocations == []
    assert poll(feed) == (200, {"revocations": [], "cursor": "0"})

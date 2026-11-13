"""The revocation list's boundaries and the feed's reads: what a watermark covers, what a read sends and how it fails."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from igni_service.errors import IgniUnavailable
from igni_service.grants import Grant
from igni_service.revocations import (
    Revocation,
    RevocationFeed,
    RevocationList,
    RevocationPage,
    RevocationsStale,
    Revoked,
    RevokedKind,
)
from igni_service.server import IgniServer
from igni_service.testing import ManualClock
from igni_service.token_endpoint import GrantRefused, IssuedTokens
from igni_service.tokens import TokenRefused

DAY_MS = 86_400_000


def revocation(
    subject: str = "u1",
    not_before_ms: int = 5_000,
    *,
    kind: RevokedKind = RevokedKind.PERSON,
    org: str | None = "o1",
) -> Revocation:
    return Revocation(kind=kind, org_id=org, subject_id=subject, not_before_ms=not_before_ms)


def person(iat_ms: int | None = 5_000, **claims: Any) -> dict[str, Any]:
    token: dict[str, Any] = {"token_use": "user", "sub": "u1", "org": "o1", **claims}
    if iat_ms is not None:
        token["iat_ms"] = iat_ms
    return token


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def heard(clock: ManualClock) -> RevocationList:
    """A list that has just heard a page holding one watermark: u1 in o1, a day ago."""
    listing = RevocationList(max_staleness=30.0, clock=clock)
    mark = wall_ms(clock) - DAY_MS
    listing.heard(RevocationPage(revocations=[revocation(not_before_ms=mark)], cursor="c1"))
    return listing


def wall_ms(clock: ManualClock) -> int:
    return int(clock.wall() * 1000)


class TestAWatermarkCoversATokenIssuedAtOrBeforeIt:
    def test_a_token_issued_at_the_watermark_is_refused_and_one_a_millisecond_later_is_not(
        self, clock: ManualClock
    ) -> None:
        mark = wall_ms(clock) - DAY_MS
        listing = RevocationList(clock=clock)
        listing.heard(RevocationPage(revocations=[revocation(not_before_ms=mark)]))

        with pytest.raises(Revoked):
            listing.check(person(mark))
        with pytest.raises(Revoked):
            listing.check(person(mark - 1))
        listing.check(person(mark + 1))

    def test_a_token_without_iat_ms_counts_from_its_iat_seconds(self, clock: ManualClock) -> None:
        seconds = int(clock.wall()) - 86_400
        listing = RevocationList(clock=clock)
        listing.heard(RevocationPage(revocations=[revocation(not_before_ms=seconds * 1000)]))

        with pytest.raises(Revoked):
            listing.check(person(None, iat=seconds))
        with pytest.raises(Revoked):
            listing.check(person(None, iat=str(seconds - 1)))
        listing.check(person(None, iat=seconds + 0.5))
        listing.check(person(None, iat=seconds + 1))

    @pytest.mark.parametrize(
        "claims",
        [
            {},
            {"iat": "yesterday"},
            {"iat": None},
            {"iat": [1]},
            {"iat_ms": "later"},
        ],
        ids=["no iat", "words", "null", "list", "iat_ms words"],
    )
    def test_a_token_whose_issue_time_is_not_a_number_is_refused(
        self, heard: RevocationList, claims: dict[str, Any]
    ) -> None:
        with pytest.raises(TokenRefused, match="iat is not a number"):
            heard.check({"token_use": "user", "sub": "u1", "org": "o1", **claims})

    def test_an_organisation_watermark_does_not_cover_another_organisation(
        self, heard: RevocationList
    ) -> None:
        heard.check(person(1, org="o2"))
        heard.check(person(1, org=None))
        with pytest.raises(Revoked):
            heard.check(person(1))

    def test_a_watermark_for_no_organisation_covers_every_organisation(
        self, clock: ManualClock
    ) -> None:
        listing = RevocationList(clock=clock)
        listing.heard(
            RevocationPage(revocations=[revocation(org=None, not_before_ms=wall_ms(clock))])
        )

        for org in ("o1", "o2", None):
            with pytest.raises(Revoked):
                listing.check(person(1, org=org))

    def test_a_watermark_is_for_its_kind_and_its_subject(self, heard: RevocationList) -> None:
        heard.check(person(1, sub="u2"))
        heard.check({"token_use": "app", "sub": "u1", "org": "o1", "iat_ms": 1})
        heard.check({"token_use": "space", "sub": "u1", "org": "o1", "iat_ms": 1})

    @pytest.mark.parametrize(
        "claims",
        [
            {"token_use": "service", "sub": "u1", "org": "o1"},
            {"sub": "u1", "org": "o1"},
            {"token_use": "user", "org": "o1"},
            {"token_use": "user", "sub": "", "org": "o1"},
        ],
        ids=["unknown use", "no use", "no sub", "empty sub"],
    )
    def test_a_token_that_names_no_kind_or_subject_is_checked_for_freshness_only(
        self, heard: RevocationList, claims: dict[str, Any]
    ) -> None:
        heard.check({**claims, "iat_ms": 1})


class TestWhatTheListKeeps:
    def test_a_lower_watermark_heard_later_does_not_lower_the_one_held(
        self, clock: ManualClock
    ) -> None:
        mark = wall_ms(clock) - DAY_MS
        listing = RevocationList(clock=clock)
        listing.heard(RevocationPage(revocations=[revocation(not_before_ms=mark)]))
        listing.heard(RevocationPage(revocations=[revocation(not_before_ms=mark - 1000)]))

        with pytest.raises(Revoked):
            listing.check(person(mark))

    def test_a_higher_watermark_replaces_the_one_held(self, clock: ManualClock) -> None:
        mark = wall_ms(clock) - DAY_MS
        listing = RevocationList(clock=clock)
        listing.heard(RevocationPage(revocations=[revocation(not_before_ms=mark)]))
        listing.heard(RevocationPage(revocations=[revocation(not_before_ms=mark + 1000)]))

        with pytest.raises(Revoked):
            listing.check(person(mark + 1000))
        assert len(listing) == 1

    def test_the_cursor_moves_only_when_a_page_gives_one(self, clock: ManualClock) -> None:
        listing = RevocationList(clock=clock)
        assert listing.cursor is None

        listing.heard(RevocationPage(cursor="c1"))
        listing.heard(RevocationPage(cursor=None))
        assert listing.cursor == "c1"

        listing.heard(RevocationPage(cursor="c2"))
        assert listing.cursor == "c2"

    def test_a_watermark_older_than_thirty_one_days_is_dropped_and_a_newer_one_kept(
        self, clock: ManualClock
    ) -> None:
        now = wall_ms(clock)
        listing = RevocationList(clock=clock)
        listing.heard(
            RevocationPage(
                revocations=[
                    revocation("old", now - 31 * DAY_MS - 1),
                    revocation("edge", now - 31 * DAY_MS),
                    revocation("new", now - 30 * DAY_MS),
                ]
            )
        )

        assert len(listing) == 2
        listing.check(person(1, sub="old"))
        with pytest.raises(Revoked):
            listing.check(person(1, sub="edge"))
        with pytest.raises(Revoked):
            listing.check(person(1, sub="new"))

    def test_a_held_watermark_is_dropped_once_it_ages_out(self, clock: ManualClock) -> None:
        listing = RevocationList(max_staleness=10**9, clock=clock)
        listing.heard(RevocationPage(revocations=[revocation(not_before_ms=wall_ms(clock))]))
        assert len(listing) == 1

        clock.advance(31 * 86_400 + 1)
        listing.heard(RevocationPage())

        assert len(listing) == 0


class TestFreshness:
    def test_a_list_that_never_heard_refuses_and_one_at_the_bound_is_still_fresh(
        self, clock: ManualClock
    ) -> None:
        listing = RevocationList(max_staleness=30.0, clock=clock)
        assert not listing.has_heard
        with pytest.raises(RevocationsStale, match="not fresh"):
            listing.check(person())

        listing.heard(RevocationPage())
        assert listing.has_heard
        clock.advance(30)
        listing.check(person())

        clock.advance(0.5)
        with pytest.raises(RevocationsStale, match="30s"):
            listing.check(person())

        listing.heard(RevocationPage())
        listing.check(person())


class Igni:
    """igni's two revocation calls, and its token endpoint's grant, with what each was asked."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.answers: list[httpx.Response | Exception] = []
        self.grants: list[Grant] = []
        self.expires_in = 600
        self.refuse: GrantRefused | None = None

    async def grant(self, grant: Grant) -> IssuedTokens:
        self.grants.append(grant)
        if self.refuse is not None:
            raise self.refuse
        return IssuedTokens(access_token=f"token-{len(self.grants)}", expires_in=self.expires_in)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        await asyncio.sleep(0)  # an answer takes a moment: a loop that asks again gives way
        answer = self.answers.pop(0) if self.answers else httpx.Response(200, json={})
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def igni() -> Igni:
    return Igni()


@pytest.fixture
def feed(igni: Igni, clock: ManualClock) -> RevocationFeed:
    http = httpx.AsyncClient(transport=httpx.MockTransport(igni.handle))
    server = IgniServer(base_url="http://igni.test", http=http)
    return RevocationFeed(
        server,
        igni,  # type: ignore[arg-type]
        RevocationList(clock=clock),
        clock=clock,
    )


class TestTheReads:
    async def test_a_pull_without_a_cursor_asks_for_everything_served_with_the_bearer(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        igni.answers = [httpx.Response(200, json={"revocations": [], "cursor": "c9"})]

        page = await feed.pull(wait=25)

        request = igni.requests[0]
        assert request.url.path == "/v1/revocations"
        assert dict(request.url.params) == {"scope": "served", "wait": "25"}
        assert "if-none-match" not in request.headers
        assert request.headers["authorization"] == "Bearer token-1"
        assert page.cursor == "c9"
        assert igni.grants[0].form()["scope"] == "revocations"

    async def test_a_pull_after_a_cursor_sends_since_and_the_quoted_etag(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        feed.revocations.heard(RevocationPage(cursor="c3"))
        igni.answers = [httpx.Response(200, json={"revocations": []})]

        await feed.pull()

        request = igni.requests[0]
        assert dict(request.url.params) == {"scope": "served", "wait": "0", "since": "c3"}
        assert request.headers["if-none-match"] == '"c3"'

    async def test_a_304_is_an_empty_page_with_the_same_cursor(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        feed.revocations.heard(RevocationPage(cursor="c3"))
        igni.answers = [httpx.Response(304)]

        page = await feed.pull(wait=25)

        assert page.revocations == [] and page.cursor == "c3"

    async def test_a_pull_that_is_not_answered_with_a_page_is_igni_unavailable(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        for answer in (
            httpx.Response(500),
            httpx.Response(403),
            httpx.Response(200, text="<html>"),
            httpx.Response(200, json=[1]),
            httpx.Response(200, json={"revocations": [{"kind": "robot"}]}),
        ):
            igni.answers = [answer]
            with pytest.raises(IgniUnavailable):
                await feed.pull()

    async def test_served_organisations_are_read_and_a_bad_answer_is_igni_unavailable(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        igni.answers = [
            httpx.Response(200, json={"organisations": [{"org_id": "o1", "name": "A"}]})
        ]
        served = await feed.served_organisations()
        assert [(o.org_id, o.name) for o in served] == [("o1", "A")]
        assert igni.requests[0].url.path == "/v1/organisations/served"

        for answer in (
            httpx.Response(503),
            httpx.Response(200, text="nope"),
            httpx.Response(200, json={"organisations": [{"name": "no id"}]}),
        ):
            igni.answers = [answer]
            with pytest.raises(IgniUnavailable):
                await feed.served_organisations()

    async def test_a_network_error_is_igni_unavailable(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        igni.answers = [httpx.ConnectError("no route")]

        with pytest.raises(IgniUnavailable, match="ConnectError"):
            await feed.pull()

    async def test_a_401_is_tried_once_more_with_a_new_token(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        igni.answers = [httpx.Response(401), httpx.Response(200, json={"cursor": "c1"})]

        page = await feed.pull()

        assert page.cursor == "c1"
        assert [r.headers["authorization"] for r in igni.requests] == [
            "Bearer token-1",
            "Bearer token-2",
        ]

    async def test_a_second_401_is_the_answer_and_is_igni_unavailable(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        igni.answers = [httpx.Response(401), httpx.Response(401), httpx.Response(200, json={})]

        with pytest.raises(IgniUnavailable, match="401"):
            await feed.pull()

        assert len(igni.requests) == 2
        assert len(igni.grants) == 2


class TestTheToken:
    async def test_it_is_kept_until_a_minute_before_it_expires(
        self, feed: RevocationFeed, igni: Igni, clock: ManualClock
    ) -> None:
        await feed.pull()
        clock.advance(539)
        await feed.pull()
        assert len(igni.grants) == 1

        clock.advance(1)
        await feed.pull()
        assert len(igni.grants) == 2
        assert igni.requests[-1].headers["authorization"] == "Bearer token-2"

    async def test_one_that_lives_less_than_the_renewal_margin_is_renewed_every_call(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        igni.expires_in = 30

        await feed.pull()
        await feed.pull()
        await feed.pull()

        assert len(igni.grants) == 3

    async def test_a_refused_grant_is_igni_unavailable_and_says_why(
        self, feed: RevocationFeed, igni: Igni
    ) -> None:
        igni.refuse = GrantRefused(403, "client_state: pending")

        with pytest.raises(IgniUnavailable, match="refused a revocations token.*pending"):
            await feed.pull()

        assert igni.requests == []


class TestTheFeedRuns:
    async def test_it_checks_nothing_before_it_runs_and_after_it_stops(
        self, feed: RevocationFeed
    ) -> None:
        assert not feed.running
        await feed.check(person())  # a never-heard list would refuse; the feed is not running

        stop = asyncio.Event()
        task = asyncio.create_task(feed.run(stop))
        await asyncio.sleep(0)
        assert feed.running
        stop.set()
        await task
        assert not feed.running
        await feed.check(person())

    async def test_stopping_cancels_a_read_that_is_in_flight(
        self, igni: Igni, clock: ManualClock
    ) -> None:
        cancelled = asyncio.Event()

        async def hold(request: httpx.Request) -> httpx.Response:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return httpx.Response(200, json={})

        server = IgniServer(
            base_url="http://igni.test",
            http=httpx.AsyncClient(transport=httpx.MockTransport(hold)),
        )
        feed = RevocationFeed(server, igni, RevocationList(clock=clock), clock=clock)  # type: ignore[arg-type]
        stop = asyncio.Event()
        task = asyncio.create_task(feed.run(stop))
        await asyncio.sleep(0.01)

        started = asyncio.get_running_loop().time()
        stop.set()
        await asyncio.wait_for(task, timeout=2)

        assert cancelled.is_set()
        assert asyncio.get_running_loop().time() - started < 1  # stopped, not timed out

    async def test_an_instant_empty_answer_to_a_long_poll_is_asked_again_only_after_a_pause(
        self, igni: Igni, clock: ManualClock
    ) -> None:
        stop = asyncio.Event()
        pauses: list[float] = []

        async def sleep(seconds: float) -> None:
            pauses.append(seconds)
            stop.set()

        igni.answers = [
            httpx.Response(200, json={"organisations": []}),
            httpx.Response(200, json={"revocations": [], "cursor": "c1"}),
            httpx.Response(200, json={"revocations": [], "cursor": "c1"}),
        ]
        server = IgniServer(
            base_url="http://igni.test",
            http=httpx.AsyncClient(transport=httpx.MockTransport(igni.handle)),
        )
        feed = RevocationFeed(
            server,
            igni,  # type: ignore[arg-type]
            RevocationList(clock=clock),
            clock=clock,
            sleep=sleep,
        )

        await asyncio.wait_for(feed.run(stop), timeout=2)

        waits = [r.url.params["wait"] for r in igni.requests if r.url.path == "/v1/revocations"]
        assert waits[:2] == ["0", "25"]
        assert pauses == [RevocationFeed.POLL_SECONDS]
        assert feed.revocations.cursor == "c1"

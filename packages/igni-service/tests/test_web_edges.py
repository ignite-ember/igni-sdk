"""Signing in to the service's pages, at its edges: refusals, outages, cookies, races and open redirects."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from urllib.parse import parse_qs, quote, urlsplit

import httpx
import pytest
from fastapi import Depends, FastAPI

from igni_service import (
    IgniService,
    MemoryKeyStore,
    Person,
)
from igni_service.testing import FakeIgni, ManualClock, SettingsOverrides
from igni_service.urls import IgniPaths
from igni_service.web import ReturnTo

from .conftest import ORG

SERVICE = "https://service.test"
PAGE = {"Accept": "text/html"}
DAY = 24 * 3600.0


class Wire(httpx.AsyncBaseTransport):
    """The fake igni on a wire that takes time, and that can be told what to do with a renewal."""

    def __init__(self, fake: FakeIgni) -> None:
        self.inner = fake.transport()
        self.before_refresh: Callable[[], Awaitable[httpx.Response | None]] | None = None
        self.sends_no_new_refresh_token = False
        """Whether igni answers a renewal with an access token alone."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.005)  # a real wire takes time: callers overlap
        if (
            self.before_refresh is not None
            and request.url.path == IgniPaths.TOKEN
            and b"grant_type=refresh_token" in request.content
        ):
            answer = await self.before_refresh()
            if answer is not None:
                return answer
        answer = await self.inner.handle_async_request(request)
        if (
            self.sends_no_new_refresh_token
            and request.url.path == IgniPaths.TOKEN
            and b"grant_type=refresh_token" in request.content
        ):
            body = json.loads(answer.content)
            body.pop("refresh_token")
            return httpx.Response(answer.status_code, json=body)
        return answer


@pytest.fixture
def wire(fake: FakeIgni) -> Wire:
    return Wire(fake)


@pytest.fixture
def igni(fake: FakeIgni, wire: Wire) -> IgniService:
    return IgniService(
        fake.settings(SettingsOverrides(public_base_url=SERVICE)),
        key_store=MemoryKeyStore(),
        http=httpx.AsyncClient(transport=wire),
        clock=fake.clock,
        retry_min=0.01,
    )


@pytest.fixture
def web_app(igni: IgniService) -> FastAPI:
    app = FastAPI()
    app.include_router(igni.web.router)

    @app.get("/settings")
    async def settings(person: Person = Depends(igni.web.person)) -> Person:
        return person

    return app


@pytest.fixture
async def browser(web_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url=SERVICE
    ) as client:
        yield client


async def start(browser: httpx.AsyncClient, fake: FakeIgni, return_to: str = "/") -> str:
    """Begin a sign-in and play igni's portal: where the portal sends the browser back."""
    login = await browser.get("/auth/login", params={"return_to": return_to})
    assert login.status_code == 303
    return fake.oauth.sign_ins.authorize(login.headers["location"], user_id="u-max", org_id=ORG)


async def sign_in(browser: httpx.AsyncClient, fake: FakeIgni, return_to: str = "/") -> None:
    assert (await browser.get(await start(browser, fake, return_to))).status_code == 303


def cookie_lines(response: httpx.Response) -> dict[str, str]:
    """Each cookie the response sets, by name, with its attributes in lower case."""
    lines = response.headers.get_list("set-cookie")
    return {line.split("=", 1)[0]: line.lower() for line in lines}


# ── ReturnTo ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "kept"),
    [
        (None, "/"),
        ("", "/"),
        ("   ", "/"),
        ("/a\nb", "/"),
        ("/a\rb", "/"),
        ("/a\tb", "/"),
        ("/a\x00", "/"),
        ("/\\evil.test", "/"),
        ("//evil.test", "/"),
        ("///evil.test", "/"),
        ("\n//evil.test", "/"),
        ("https://evil.test/", "/"),
        ("HTTP://evil.test/", "/"),
        ("javascript:alert(1)", "/"),
        ("evil.test/path", "/"),
        ("  /padded  ", "/padded"),
        ("/", "/"),
        ("/a/b?c=d&e=f", "/a/b?c=d&e=f"),
        ("/café/日本", "/café/日本"),
        ("/" + "x" * 5000, "/" + "x" * 5000),
    ],
)
def test_return_to_is_a_path_on_this_service_or_the_root(value: str | None, kept: str) -> None:
    assert ReturnTo.safe(value) == kept


# ── Login ────────────────────────────────────────────────────────────


async def test_each_login_has_its_own_state_and_verifier(
    browser: httpx.AsyncClient, igni: IgniService
) -> None:
    first = await browser.get("/auth/login")
    second = await browser.get("/auth/login")

    queries = [parse_qs(urlsplit(r.headers["location"]).query) for r in (first, second)]
    assert queries[0]["state"] != queries[1]["state"]
    assert queries[0]["code_challenge"] != queries[1]["code_challenge"]
    assert all(len(q["state"][0]) >= 43 for q in queries)


async def test_the_login_cookie_lives_ten_minutes_on_the_auth_paths_only(
    browser: httpx.AsyncClient,
) -> None:
    login = await browser.get("/auth/login")

    cookie = cookie_lines(login)["igni_login"]
    assert "max-age=600" in cookie
    assert "path=/auth;" in cookie + ";"
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie


async def test_login_adds_to_an_endpoint_that_already_has_a_query(
    browser: httpx.AsyncClient, igni: IgniService, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def endpoint() -> str:
        return "https://igni.test/portal/authorize?tenant=7"

    monkeypatch.setattr(igni.connection.server, "authorization_endpoint", endpoint)

    login = await browser.get("/auth/login")

    location = login.headers["location"]
    assert location.startswith("https://igni.test/portal/authorize?tenant=7&response_type=code")
    assert location.count("?") == 1


async def test_login_says_so_when_igni_cannot_be_reached(
    browser: httpx.AsyncClient, fake: FakeIgni
) -> None:
    fake.traffic.fail(IgniPaths.DISCOVERY, 503)

    login = await browser.get("/auth/login")

    assert login.status_code == 503
    assert "cannot be reached" in login.text
    assert login.headers["content-type"].startswith("text/plain")
    assert "set-cookie" not in login.headers


# ── Callback ─────────────────────────────────────────────────────────


async def test_the_session_cookie_lasts_thirty_days_and_the_login_cookie_is_cleared(
    browser: httpx.AsyncClient, fake: FakeIgni
) -> None:
    back = await browser.get(await start(browser, fake))

    cookies = cookie_lines(back)
    session = cookies["igni_session"]
    assert f"max-age={30 * 24 * 3600}" in session
    assert "path=/;" in session
    assert "httponly" in session and "secure" in session and "samesite=lax" in session
    assert "max-age=0" in cookies["igni_login"]
    assert "path=/auth" in cookies["igni_login"]
    assert "igni_login" not in browser.cookies


async def test_the_token_endpoint_is_sent_the_code_the_verifier_and_the_callback(
    browser: httpx.AsyncClient, fake: FakeIgni
) -> None:
    login = await browser.get("/auth/login")
    challenge = parse_qs(urlsplit(login.headers["location"]).query)["code_challenge"][0]
    back = fake.oauth.sign_ins.authorize(login.headers["location"], user_id="u-max", org_id=ORG)
    code = parse_qs(urlsplit(back).query)["code"][0]

    await browser.get(back)

    [grant] = [r.form() for r in fake.traffic.requests_to(IgniPaths.TOKEN)]
    assert grant.grant_type == "authorization_code"
    assert grant.code == code
    assert grant.redirect_uri == f"{SERVICE}/auth/callback"
    digest = hashlib.sha256(grant.code_verifier.encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == challenge
    assert grant.is_jwt_bearer


async def test_a_renewal_sends_the_refresh_token_the_session_holds(
    browser: httpx.AsyncClient, fake: FakeIgni, igni: IgniService, clock: ManualClock
) -> None:
    await sign_in(browser, fake)
    session = await igni.web.store.get(browser.cookies["igni_session"])
    assert session is not None
    clock.advance(600)

    assert (await browser.get("/settings")).status_code == 200

    renewal = [r.form() for r in fake.traffic.requests_to(IgniPaths.TOKEN)][-1]
    assert renewal.grant_type == "refresh_token"
    assert renewal.refresh_token == session.refresh_token
    assert renewal.code == "" and renewal.code_verifier == ""


async def test_a_callback_that_igni_cannot_finish_is_a_503_and_leaves_no_session(
    browser: httpx.AsyncClient, fake: FakeIgni
) -> None:
    back = await start(browser, fake)
    fake.traffic.fail(IgniPaths.TOKEN, 503)

    refused = await browser.get(back)

    assert refused.status_code == 503
    assert "cannot be reached" in refused.text
    assert "igni_session" not in refused.headers.get("set-cookie", "")
    assert (await browser.get("/settings")).status_code == 401


@pytest.mark.parametrize(
    "bend",
    [
        {"azp": "another-client"},
        {"org": ""},
    ],
    ids=["a token for another client", "a token for no organisation"],
)
async def test_a_token_that_is_not_for_this_client_and_organisation_is_refused(
    browser: httpx.AsyncClient,
    fake: FakeIgni,
    monkeypatch: pytest.MonkeyPatch,
    bend: dict[str, str],
) -> None:
    signer = fake.oauth.signer
    sign = signer.sign
    monkeypatch.setattr(
        signer,
        "sign",
        lambda sub, claims, overrides=None: sign(sub, claims.model_copy(update=bend), overrides),
    )

    refused = await browser.get(await start(browser, fake))

    assert refused.status_code == 400
    assert "not for this service" in refused.text
    assert "igni_session" not in refused.headers.get("set-cookie", "")
    assert (await browser.get("/settings")).status_code == 401


async def test_a_token_for_nobody_is_refused(
    browser: httpx.AsyncClient, fake: FakeIgni, monkeypatch: pytest.MonkeyPatch
) -> None:
    signer = fake.oauth.signer
    sign = signer.sign
    monkeypatch.setattr(
        signer, "sign", lambda sub, claims, overrides=None: sign("", claims, overrides)
    )

    refused = await browser.get(await start(browser, fake))

    assert refused.status_code == 400
    assert (await browser.get("/settings")).status_code == 401


async def test_igni_refusing_the_code_is_a_400_and_no_session(
    browser: httpx.AsyncClient, fake: FakeIgni
) -> None:
    back = await start(browser, fake)
    fake.oauth.sign_ins.codes.clear()

    refused = await browser.get(back)

    assert refused.status_code == 400
    assert "did not accept" in refused.text
    assert "igni_session" not in refused.headers.get("set-cookie", "")


@pytest.mark.parametrize(
    "query",
    [
        {"code": "", "state": "s"},
        {"code": "c", "state": ""},
        {},
    ],
    ids=["no code", "no state", "nothing"],
)
async def test_a_callback_without_a_code_or_a_state_is_refused(
    browser: httpx.AsyncClient, query: dict[str, str]
) -> None:
    browser.cookies.set("igni_login", "s", domain="service.test", path="/auth")

    refused = await browser.get("/auth/callback", params=query)

    assert refused.status_code == 400
    assert "not started here" in refused.text


async def test_a_state_that_is_not_the_cookie_s_is_refused_and_its_attempt_stays_for_its_owner(
    browser: httpx.AsyncClient, fake: FakeIgni
) -> None:
    back = await start(browser, fake)
    state = parse_qs(urlsplit(back).query)["state"][0]
    browser.cookies.set("igni_login", state + "x", domain="service.test", path="/auth")
    assert (await browser.get(back)).status_code == 400

    browser.cookies.set("igni_login", state, domain="service.test", path="/auth")
    assert (await browser.get(back)).status_code == 303


async def test_a_sign_in_not_finished_in_ten_minutes_is_void(
    browser: httpx.AsyncClient, fake: FakeIgni, clock: ManualClock
) -> None:
    back = await start(browser, fake)
    clock.advance(600)

    refused = await browser.get(back)

    assert refused.status_code == 400
    assert "expired" in refused.text


# ── Logout ───────────────────────────────────────────────────────────


async def test_a_link_to_logout_signs_out_as_a_post_does(
    browser: httpx.AsyncClient, fake: FakeIgni, igni: IgniService
) -> None:
    await sign_in(browser, fake)
    session_id = browser.cookies["igni_session"]
    session = await igni.web.store.get(session_id)
    assert session is not None

    out = await browser.get("/auth/logout")

    assert out.status_code == 303
    assert out.headers["location"] == "/"
    assert "max-age=0" in cookie_lines(out)["igni_session"]
    assert fake.oauth.revoked == [session.refresh_token]
    assert await igni.web.store.get(session_id) is None


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    ("return_to", "sent_to"),
    [("/goodbye?x=1", "/goodbye?x=1"), ("//evil.test", "/"), ("https://evil.test", "/")],
)
async def test_logout_returns_to_a_path_here_and_never_elsewhere(
    browser: httpx.AsyncClient, method: str, return_to: str, sent_to: str
) -> None:
    out = await browser.request(method, "/auth/logout", params={"return_to": return_to})

    assert out.status_code == 303
    assert out.headers["location"] == sent_to


async def test_logout_with_a_cookie_nobody_holds_asks_igni_nothing(
    browser: httpx.AsyncClient, fake: FakeIgni
) -> None:
    browser.cookies.set("igni_session", "never-issued", domain="service.test")

    out = await browser.post("/auth/logout")

    assert out.status_code == 303
    assert "max-age=0" in cookie_lines(out)["igni_session"]
    assert fake.traffic.requests_to(IgniPaths.REVOKE) == []


async def test_logout_of_a_session_without_a_refresh_token_asks_igni_nothing(
    browser: httpx.AsyncClient, fake: FakeIgni, igni: IgniService, clock: ManualClock
) -> None:
    await sign_in(browser, fake)
    session_id = browser.cookies["igni_session"]
    held = await igni.web.store.get(session_id)
    assert held is not None
    await igni.web.store.put(session_id, held.model_copy(update={"refresh_token": ""}))

    out = await browser.post("/auth/logout")

    assert out.status_code == 303
    assert fake.traffic.requests_to(IgniPaths.REVOKE) == []
    assert await igni.web.store.get(session_id) is None


# ── Renewal ──────────────────────────────────────────────────────────


async def test_requests_at_once_on_a_session_to_renew_cause_one_renewal(
    browser: httpx.AsyncClient, fake: FakeIgni, clock: ManualClock
) -> None:
    await sign_in(browser, fake)
    clock.advance(600)

    pages = await asyncio.gather(*(browser.get("/settings") for _ in range(6)))

    assert [p.status_code for p in pages] == [200] * 6
    assert fake.oauth.grants == ["authorization_code", "refresh_token"]


async def test_two_sessions_renew_each_on_their_own(
    browser: httpx.AsyncClient, fake: FakeIgni, clock: ManualClock, web_app: FastAPI
) -> None:
    await sign_in(browser, fake)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url=SERVICE
    ) as other:
        await sign_in(other, fake)
        clock.advance(600)

        pages = await asyncio.gather(browser.get("/settings"), other.get("/settings"))

    assert [p.status_code for p in pages] == [200, 200]
    assert fake.oauth.grants.count("refresh_token") == 2


async def test_a_renewal_another_replica_won_leaves_the_session_standing(
    browser: httpx.AsyncClient, fake: FakeIgni, igni: IgniService, clock: ManualClock, wire: Wire
) -> None:
    await sign_in(browser, fake)
    session_id = browser.cookies["igni_session"]
    held = await igni.web.store.get(session_id)
    assert held is not None

    async def another_replica_renews_first() -> httpx.Response:
        rotated = held.model_copy(
            update={
                "refresh_token": "rotated-elsewhere",
                "access_expires_at": clock.wall() + 600,
            }
        )
        await igni.web.store.put(session_id, rotated)
        return httpx.Response(400, json={"error": "invalid_grant"})

    wire.before_refresh = another_replica_renews_first
    clock.advance(600)

    page = await browser.get("/settings")

    assert page.status_code == 200
    assert page.json()["user_id"] == "u-max"
    kept = await igni.web.store.get(session_id)
    assert kept is not None and kept.refresh_token == "rotated-elsewhere"


async def test_a_renewal_refused_with_nothing_rotated_signs_the_person_out(
    browser: httpx.AsyncClient, fake: FakeIgni, igni: IgniService, clock: ManualClock, wire: Wire
) -> None:
    await sign_in(browser, fake)
    session_id = browser.cookies["igni_session"]

    async def refuse() -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    wire.before_refresh = refuse
    clock.advance(600)

    assert (await browser.get("/settings")).status_code == 401
    assert await igni.web.store.get(session_id) is None


async def test_a_renewal_that_brings_a_token_for_another_client_signs_the_person_out(
    browser: httpx.AsyncClient,
    fake: FakeIgni,
    igni: IgniService,
    clock: ManualClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await sign_in(browser, fake)
    session_id = browser.cookies["igni_session"]
    signer = fake.oauth.signer
    sign = signer.sign
    monkeypatch.setattr(
        signer,
        "sign",
        lambda sub, claims, overrides=None: sign(
            sub, claims.model_copy(update={"azp": "another-client"}), overrides
        ),
    )
    clock.advance(600)

    assert (await browser.get("/settings")).status_code == 401
    assert await igni.web.store.get(session_id) is None


async def test_a_renewal_sets_the_access_token_and_the_session_afresh(
    browser: httpx.AsyncClient, fake: FakeIgni, igni: IgniService, clock: ManualClock
) -> None:
    await sign_in(browser, fake)
    session_id = browser.cookies["igni_session"]
    first = await igni.web.store.get(session_id)
    assert first is not None
    clock.advance(600)

    await browser.get("/settings")

    renewed = await igni.web.store.get(session_id)
    assert renewed is not None
    assert renewed.access_expires_at == clock.wall() + 600
    assert renewed.expires_at == clock.wall() + 30 * DAY


async def test_a_session_is_dead_after_thirty_days_without_a_renewal(
    browser: httpx.AsyncClient, fake: FakeIgni, clock: ManualClock
) -> None:
    await sign_in(browser, fake)
    clock.advance(30 * DAY)

    assert (await browser.get("/settings")).status_code == 401
    assert fake.oauth.grants == ["authorization_code"]


async def test_a_session_renewed_within_thirty_days_lives_thirty_days_from_the_renewal(
    browser: httpx.AsyncClient, fake: FakeIgni, clock: ManualClock
) -> None:
    await sign_in(browser, fake)
    clock.advance(20 * DAY)
    assert (await browser.get("/settings")).status_code == 200
    clock.advance(20 * DAY)

    assert (await browser.get("/settings")).status_code == 200


async def test_a_renewal_that_brings_no_new_refresh_token_keeps_the_one_held(
    browser: httpx.AsyncClient,
    fake: FakeIgni,
    igni: IgniService,
    clock: ManualClock,
    wire: Wire,
) -> None:
    await sign_in(browser, fake)
    session_id = browser.cookies["igni_session"]
    first = await igni.web.store.get(session_id)
    assert first is not None
    wire.sends_no_new_refresh_token = True
    clock.advance(600)

    assert (await browser.get("/settings")).status_code == 200

    renewed = await igni.web.store.get(session_id)
    assert renewed is not None
    assert renewed.refresh_token == first.refresh_token != ""
    assert renewed.access_token != first.access_token


# ── Where a page sends a stranger ────────────────────────────────────


async def test_a_page_with_a_query_beyond_ascii_comes_back_to_exactly_that_address(
    browser: httpx.AsyncClient, fake: FakeIgni
) -> None:
    sent = await browser.get("/settings?q=caf%C3%A9&n=1", headers=PAGE)
    login_url = urlsplit(sent.headers["location"])
    assert login_url.path == "/auth/login"
    return_to = parse_qs(login_url.query)["return_to"][0]
    assert return_to == "/settings?q=caf%C3%A9&n=1"
    assert sent.headers["location"].endswith(quote(return_to, safe=""))

    back = await browser.get(await start(browser, fake, return_to))

    assert back.headers["location"] == "/settings?q=caf%C3%A9&n=1"


async def test_only_a_request_that_accepts_html_is_sent_to_sign_in(
    browser: httpx.AsyncClient,
) -> None:
    api = await browser.get("/settings", headers={"Accept": "application/json"})
    page = await browser.get("/settings", headers={"Accept": "application/json, text/html;q=0.9"})
    nothing = await browser.get("/settings", headers={"Accept": "*/*"})

    assert api.status_code == 401
    assert api.headers["www-authenticate"] == "Bearer"
    assert api.json() == {"detail": "Not signed in"}
    assert page.status_code == 303
    assert nothing.status_code == 401

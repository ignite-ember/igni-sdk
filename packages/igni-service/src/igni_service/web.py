"""People signing in to a service's own pages through igni (§5).

    app.include_router(igni.web.router)

    @app.get("/settings")
    async def settings(person: Person = Depends(igni.web.person)): ...

The authorization-code flow with PKCE (S256), run entirely on the server:

* `/auth/login` sends the browser to igni's portal with a fresh `state`
  and PKCE challenge, and remembers the verifier server-side;
* `/auth/callback` checks the `state` against the cookie the login set,
  exchanges the code at igni's token endpoint with the service's own
  client assertion, checks the access token as any other (`aud` = this
  service's URL, `token_use` = `user`, `azp` = this client), opens a
  server-side session and sets only its id in an HttpOnly, SameSite=Lax
  cookie (Secure on https);
* `/auth/logout` ends the session here and revokes its refresh token at
  igni (RFC 7009), so the sign-in is over at igni too: no refresh token
  of it renews again. Signing out here works whether or not igni can be
  reached to hear it. It answers `GET` as well as `POST`, so a plain
  link signs out as a form does; the most a link from another site can
  do with it is sign somebody out.

The access token lives ten minutes and is renewed with the refresh token
a minute before it runs out, inside `person`. igni refusing the renewal —
the person was removed, deactivated, or had their sessions withdrawn —
signs them out here too.

The pieces live beside this module: `web_redirects` (the link to igni and
the way back), `web_tokens` (the tokens redeemed and checked),
`web_renewal` (the sessions renewed) and `web_sessions` (where they are
kept).
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse, RedirectResponse

from igni_service.clock import Clock
from igni_service.errors import IgniUnavailable
from igni_service.grants import AuthorizationCodeGrant
from igni_service.registration import ServiceRegistration
from igni_service.server import IgniServer
from igni_service.signing import SigningKey
from igni_service.token_endpoint import GrantRefused
from igni_service.tokens import Person, TokenRefused, TokenVerifier
from igni_service.web_redirects import AuthorizationRequest, Pkce, ReturnTo, SignInRequired
from igni_service.web_renewal import RenewalUnavailable, SessionTiming, WebSessions
from igni_service.web_sessions import LoginAttempt, WebSessionStore
from igni_service.web_tokens import WebTokenExchange

logger = logging.getLogger(__name__)

__all__ = ["Pkce", "ReturnTo", "SignInRequired", "WebSignIn"]


class WebSignIn:
    """Sign-in to the service's own pages, and the dependencies that require it.

    Args:
        igni: igni server as this service reaches it: where a person's
            browser is sent to sign in, and whose issuer and keys every
            token it accepts comes from.
        registration: This service's registration with igni; its client id
            is asked of it, registering first when there is none.
        key: This deployment's signing key: it signs the client assertion
            with which this service asks igni for tokens.
        verifier: Checks the access token igni issued: that it is a user
            token, and that it is for this service and this client.
        store: Where the sessions and the sign-ins in flight are kept.
        clock: The clock the sign-in's expiry and the access token's
            renewal are read from; the system's own clock when not given.
    """

    PREFIX = "/auth"
    """Where the sign-in routes are mounted: `/auth/login`, `/auth/callback`,
    `/auth/logout`."""
    COOKIE = "igni_session"
    """The cookie holding a signed-in person's session id (HttpOnly, SameSite=Lax)."""
    LOGIN_COOKIE = "igni_login"
    """The cookie tying a sign-in in flight to the browser that started it."""
    LOGIN_TTL = 600.0
    """How long a sign-in may take at igni's portal."""
    SESSION_TTL = 30 * 24 * 3600.0
    """How long a session lives from the sign-in or its last renewal, which
    sets it afresh: a session not renewed within this is dead."""
    RENEW_BEFORE = 60.0
    """How long before the access token expires it is renewed."""

    def __init__(
        self,
        igni: IgniServer,
        registration: ServiceRegistration,
        key: SigningKey,
        verifier: TokenVerifier,
        store: WebSessionStore,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._igni = igni
        self._clock = clock or Clock()
        self._tokens = WebTokenExchange(igni, registration, key, verifier)
        self._sessions = WebSessions(
            self._tokens,
            store,
            self._clock,
            SessionTiming(session_ttl=self.SESSION_TTL, renew_before=self.RENEW_BEFORE),
        )
        self._router: APIRouter | None = None

    @classmethod
    def redirect_uri_for(cls, own_url: str) -> str:
        """The callback address igni sends a person back to, for a service at `own_url`.

        Args:
            own_url: The service's own URL, as igni knows it: the base the
                callback path is put on.
        """
        return f"{own_url}{cls.PREFIX}/callback"

    @property
    def redirect_uri(self) -> str:
        """This service's callback address: `PUBLIC_BASE_URL` + `/auth/callback`."""
        return self.redirect_uri_for(self._igni.own_url)

    @property
    def login_path(self) -> str:
        """Where a page links to sign in; it brings the browser back after."""
        return f"{self.PREFIX}/login"

    @property
    def logout_path(self) -> str:
        """Where a page sends the browser to sign out of this service: a form
        posts to it, and a plain link to it signs out too."""
        return f"{self.PREFIX}/logout"

    @property
    def store(self) -> WebSessionStore:
        """Where the sessions and sign-ins in flight are kept."""
        return self._sessions.store

    @property
    def _secure(self) -> bool:
        return self._igni.own_url.startswith("https://")

    # ── The routes ──────────────────────────────────────────────────

    @property
    def router(self) -> APIRouter:
        """The sign-in routes: `GET /auth/login`, `GET /auth/callback`, and
        `GET` or `POST /auth/logout`. `igni.install(app)` mounts them."""
        if self._router is None:
            router = APIRouter(prefix=self.PREFIX, tags=["sign-in"])
            router.add_api_route("/login", self.login, methods=["GET"], include_in_schema=False)
            router.add_api_route(
                "/callback", self.callback, methods=["GET"], include_in_schema=False
            )
            router.add_api_route(
                "/logout", self.logout, methods=["GET", "POST"], include_in_schema=False
            )
            self._router = router
        return self._router

    async def login(self, return_to: str = "/") -> Response:
        """Send the browser to igni to sign in, and come back to `return_to`.

        Args:
            return_to: Where to bring the person once they are signed in: a
                path on this service, or ``/`` when the value is not one.
        """
        try:
            client_id = await self._tokens.client_id()
            endpoint = await self._igni.authorization_endpoint()
        except IgniUnavailable as exc:
            logger.error("igni: cannot start a sign-in: %s", exc)
            return PlainTextResponse("igni cannot be reached to sign you in.", status_code=503)
        attempt = LoginAttempt(
            state=secrets.token_urlsafe(32),
            verifier=Pkce.verifier(),
            return_to=ReturnTo.safe(return_to),
            expires_at=self._clock.wall() + self.LOGIN_TTL,
        )
        await self.store.put_login(attempt)
        authorize = AuthorizationRequest.for_verifier(
            client_id=client_id,
            redirect_uri=self.redirect_uri,
            state=attempt.state,
            verifier=attempt.verifier,
        )
        response = RedirectResponse(authorize.url(endpoint), status_code=303)
        response.set_cookie(
            self.LOGIN_COOKIE,
            attempt.state,
            max_age=int(self.LOGIN_TTL),
            path=self.PREFIX,
            secure=self._secure,
            httponly=True,
            samesite="lax",
        )
        return response

    async def callback(
        self, request: Request, code: str = "", state: str = "", error: str = ""
    ) -> Response:
        """igni sending the browser back: exchange the code, open a session.

        Args:
            request: The request igni sent the browser back on: its
                ``igni_login`` cookie says which sign-in in flight this is.
            code: The authorization code igni issued, exchanged at igni for
                the person's access and refresh tokens.
            state: The OAuth ``state`` igni echoed back, matched against the
                cookie and the sign-in in flight.
            error: The error igni reported instead of a code, when it refused
                to sign the person in.
        """
        if error:
            return self._failed(f"igni did not sign you in ({error}).")
        expected = request.cookies.get(self.LOGIN_COOKIE, "")
        # Bytes, not text: `compare_digest` raises on a str beyond ASCII, and
        # a state anybody can put in a link must be refused, not crash.
        if not code or not state or not secrets.compare_digest(expected.encode(), state.encode()):
            return self._failed("This sign-in was not started here, or has expired.")
        attempt = await self.store.take_login(state)
        if attempt is None:
            return self._failed("This sign-in was not started here, or has expired.")
        try:
            signed_in = await self._tokens.sign_in(
                AuthorizationCodeGrant(
                    code=code, code_verifier=attempt.verifier, redirect_uri=self.redirect_uri
                )
            )
        except GrantRefused as exc:
            logger.warning("igni: refused a sign-in code: %s", exc)
            return self._failed("igni did not accept this sign-in. Try again.")
        except TokenRefused:
            return self._failed("igni answered with a token that is not for this service.")
        except IgniUnavailable as exc:
            logger.error("igni: cannot finish a sign-in: %s", exc)
            return PlainTextResponse("igni cannot be reached to sign you in.", status_code=503)
        session_id = await self._sessions.open(signed_in)
        response = RedirectResponse(attempt.return_to, status_code=303)
        response.set_cookie(
            self.COOKIE,
            session_id,
            max_age=int(self.SESSION_TTL),
            path="/",
            secure=self._secure,
            httponly=True,
            samesite="lax",
        )
        response.delete_cookie(self.LOGIN_COOKIE, path=self.PREFIX)
        return response

    async def logout(self, request: Request, return_to: str = "/") -> Response:
        """End the session here, and the sign-in at igni.

        The session goes first, so the person is signed out of these pages
        whatever igni says; then its refresh token is revoked, so nothing
        that ever held it can renew. The person stays signed in to igni's
        own portal — that is igni's session, not this service's.

        Args:
            request: The request that ends the sign-in: its ``igni_session``
                cookie names the session to end.
            return_to: Where to send the browser afterwards: a path on this
                service, or ``/`` when the value is not one.
        """
        session_id = request.cookies.get(self.COOKIE)
        if session_id:
            await self._sessions.end(session_id)
        response = RedirectResponse(ReturnTo.safe(return_to), status_code=303)
        response.delete_cookie(self.COOKIE, path="/")
        return response

    # ── The dependencies ────────────────────────────────────────────

    async def person(self, request: Request) -> Person:
        """FastAPI dependency: the person signed in to these pages.

        A page (a request that accepts HTML) is sent to sign in and brought
        back; anything else is answered 401.

        Args:
            request: The request to sign in for: its ``igni_session`` cookie
                names the session, and its ``Accept`` header says whether the
                caller is a page to redirect or a client to refuse.
        """
        person = await self._sessions.person(request.cookies.get(self.COOKIE, ""))
        if person is None:
            raise SignInRequired(request, self.login_path)
        return person

    async def signed_in(self, request: Request) -> Person | None:
        """FastAPI dependency: the person signed in to these pages, or `None`.

        For a page anybody may read that says more to somebody signed in.
        Never sends anybody to sign in; a session that cannot be renewed
        because igni is away counts as nobody, rather than failing a page
        that did not need one.

        Args:
            request: The request to read the session of: its ``igni_session``
                cookie names the session.
        """
        try:
            return await self._sessions.person(request.cookies.get(self.COOKIE, ""))
        except RenewalUnavailable:
            return None

    async def super_admin(self, request: Request) -> Person:
        """FastAPI dependency: a signed-in super admin; 403 for anybody else.

        Args:
            request: The request to check the role for: its ``igni_session``
                cookie names the session the person is read from.
        """
        person = await self.person(request)
        if not person.super_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admins only")
        return person

    async def org_admin(self, request: Request) -> Person:
        """FastAPI dependency: a signed-in admin of the organisation they signed in to.

        `org_role == "admin"` in that one organisation, as igni said when it
        last renewed the token; 403 for anybody else, a super admin included.

        Args:
            request: The request to check the role for: its ``igni_session``
                cookie names the session the person is read from.
        """
        person = await self.person(request)
        if not person.is_org_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Organisation admins only"
            )
        return person

    @staticmethod
    def _failed(message: str) -> Response:
        return PlainTextResponse(message, status_code=400)

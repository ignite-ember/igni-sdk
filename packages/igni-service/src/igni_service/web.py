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
  reached to hear it.

The access token lives ten minutes and is renewed with the refresh token
a minute before it runs out, inside `person`. igni refusing the renewal —
the person was removed, deactivated, or had their sessions withdrawn —
signs them out here too.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
from urllib.parse import quote, urlencode, urlsplit

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse, RedirectResponse

from igni_service.clock import Clock
from igni_service.errors import IgniError, IgniUnavailable
from igni_service.grants import AuthorizationCodeGrant, RefreshTokenGrant
from igni_service.registration import ServiceRegistration
from igni_service.server import IgniServer
from igni_service.signing import SigningKey
from igni_service.token_endpoint import GrantRefused, IssuedTokens, TokenEndpoint
from igni_service.tokens import Person, TokenRefused, TokenUse, TokenVerifier
from igni_service.web_sessions import LoginAttempt, WebSession, WebSessionStore

logger = logging.getLogger(__name__)


class Pkce:
    """RFC 7636, S256 only."""

    @staticmethod
    def verifier() -> str:
        return secrets.token_urlsafe(64)

    @staticmethod
    def challenge(verifier: str) -> str:
        """The S256 challenge for `verifier`: what the sign-in sends igni.

        Args:
            verifier: The PKCE code verifier the sign-in keeps; its SHA-256
                digest, in base64url, is the challenge sent with it.
        """
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class ReturnTo:
    """Where to send the browser afterwards: a path on this service, nothing else."""

    @staticmethod
    def safe(value: str | None) -> str:
        """Where to send the browser afterwards: a path on this service, nothing else.

        Args:
            value: The path asked for; anything that is not a path on this
                service becomes ``/``.
        """
        candidate = (value or "").strip()
        parts = urlsplit(candidate)
        if (
            not candidate.startswith("/")
            or candidate.startswith("//")
            or "\\" in candidate
            or parts.scheme
            or parts.netloc
            or any(ord(ch) < 0x20 for ch in candidate)
        ):
            return "/"
        return candidate


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
    """Where the sign-in routes are mounted: `/auth/login`, `/auth/callback`, `/auth/logout`."""
    COOKIE = "igni_session"
    """The cookie holding a signed-in person's session id (HttpOnly, SameSite=Lax)."""
    LOGIN_COOKIE = "igni_login"
    """The cookie tying a sign-in in flight to the browser that started it."""
    LOGIN_TTL = 600.0
    """How long a sign-in may take at igni's portal."""
    SESSION_TTL = 30 * 24 * 3600.0
    """A refresh token's life at igni: a session idle longer is dead."""
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
        self._registration = registration
        self._verifier = verifier
        self._endpoint = TokenEndpoint(igni, registration, key)
        self._store = store
        self._clock = clock or Clock()
        self._refreshing: dict[str, asyncio.Lock] = {}
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
        """Where a page posts to sign out of this service."""
        return f"{self.PREFIX}/logout"

    @property
    def store(self) -> WebSessionStore:
        """Where the sessions and sign-ins in flight are kept."""
        return self._store

    @property
    def _secure(self) -> bool:
        return self._igni.own_url.startswith("https://")

    # ── The routes ──────────────────────────────────────────────────

    @property
    def router(self) -> APIRouter:
        """The sign-in routes: `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout`. `igni.install(app)` mounts them."""
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
            client_id = await self._registration.client_id()
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
        await self._store.put_login(attempt)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": self.redirect_uri,
                "state": attempt.state,
                "code_challenge": Pkce.challenge(attempt.verifier),
                "code_challenge_method": "S256",
            }
        )
        separator = "&" if "?" in endpoint else "?"
        response = RedirectResponse(f"{endpoint}{separator}{query}", status_code=303)
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
        attempt = await self._store.take_login(state)
        if attempt is None:
            return self._failed("This sign-in was not started here, or has expired.")
        try:
            issued = await self._endpoint.grant(
                AuthorizationCodeGrant(
                    code=code, code_verifier=attempt.verifier, redirect_uri=self.redirect_uri
                )
            )
            person = await self._person_of(issued)
        except GrantRefused as exc:
            logger.warning("igni: refused a sign-in code: %s", exc)
            return self._failed("igni did not accept this sign-in. Try again.")
        except TokenRefused:
            return self._failed("igni answered with a token that is not for this service.")
        except IgniUnavailable as exc:
            logger.error("igni: cannot finish a sign-in: %s", exc)
            return PlainTextResponse("igni cannot be reached to sign you in.", status_code=503)
        session_id = secrets.token_urlsafe(32)
        await self._store.put(session_id, self._session(person, issued))
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
        session = await self._store.get(session_id) if session_id else None
        if session_id:
            await self._store.delete(session_id)
        if session is not None and session.refresh_token:
            await self._revoke(session.refresh_token)
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
        person = await self._current(request)
        if person is None:
            raise self._sign_in(request)
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
            return await self._current(request)
        except HTTPException:
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

    # ── Inside ──────────────────────────────────────────────────────

    async def _current(self, request: Request) -> Person | None:
        session_id = request.cookies.get(self.COOKIE, "")
        session = await self._store.get(session_id) if session_id else None
        if (
            session is not None
            and self._clock.wall() >= session.access_expires_at - self.RENEW_BEFORE
        ):
            session = await self._refreshed(session_id)
        return session.person if session is not None else None

    async def _revoke(self, refresh_token: str) -> None:
        """Revoke at igni, best effort: signing out here has already happened."""
        try:
            await self._endpoint.revoke(refresh_token)
        except IgniError as exc:
            # The refresh token was only ever in the session just deleted,
            # so it is not lost to anybody; it simply stays valid at igni
            # until it expires.
            logger.warning("igni: could not revoke a sign-in on sign-out: %s", exc)

    async def _refreshed(self, session_id: str) -> WebSession | None:
        lock = self._refreshing.setdefault(session_id, asyncio.Lock())
        try:
            async with lock:
                return await self._refresh(session_id)
        finally:
            if not lock.locked():
                self._refreshing.pop(session_id, None)

    async def _refresh(self, session_id: str) -> WebSession | None:
        current = await self._store.get(session_id)
        now = self._clock.wall()
        if current is None or now < current.access_expires_at - self.RENEW_BEFORE:
            return current
        try:
            issued = await self._endpoint.grant(
                RefreshTokenGrant(refresh_token=current.refresh_token)
            )
            person = await self._person_of(issued)
        except GrantRefused:
            latest = await self._store.get(session_id)
            if latest is not None and latest.refresh_token != current.refresh_token:
                # Another replica renewed it first; its tokens stand.
                return latest
            await self._store.delete(session_id)
            return None
        except TokenRefused:
            await self._store.delete(session_id)
            return None
        except IgniUnavailable as exc:
            if now < current.access_expires_at:
                logger.warning("igni: could not renew a session yet (%s)", exc)
                return current
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="igni server cannot be reached to renew this session",
            ) from exc
        renewed = self._session(person, issued, refresh_token=current.refresh_token)
        await self._store.put(session_id, renewed)
        return renewed

    async def _person_of(self, issued: IssuedTokens) -> Person:
        claims = await self._verifier.claims(issued.access_token, use=TokenUse.USER)
        client_id = await self._registration.client_id()
        if claims.get("azp") not in (None, client_id):
            raise TokenRefused(
                "the sign-in answered with a token for another client, or for no organisation"
            )
        person = Person.from_claims(claims)
        if not person.user_id or not person.org_id:
            raise TokenRefused(
                "the sign-in answered with a token for another client, or for no organisation"
            )
        return person

    def _session(
        self, person: Person, issued: IssuedTokens, *, refresh_token: str = ""
    ) -> WebSession:
        now = self._clock.wall()
        return WebSession(
            person=person,
            access_token=issued.access_token,
            refresh_token=issued.refresh_token or refresh_token,
            access_expires_at=now + issued.expires_in,
            expires_at=now + self.SESSION_TTL,
        )

    def _sign_in(self, request: Request) -> HTTPException:
        if "text/html" in request.headers.get("accept", ""):
            target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            return HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": f"{self.login_path}?return_to={quote(target, safe='')}"},
            )
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @staticmethod
    def _failed(message: str) -> Response:
        return PlainTextResponse(message, status_code=400)

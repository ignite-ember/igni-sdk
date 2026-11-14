"""The web sign-in's sessions: opened, read, renewed before they lapse, ended.

The access token lives ten minutes and is renewed with the refresh token
a minute before it runs out, when the session is read. igni refusing the
renewal — the person was removed, deactivated, or had their sessions
withdrawn — ends the session here too. One renewal per session runs at a
time in this process; another replica renewing first is noticed and its
tokens stand.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict

from igni_service.callers import Person
from igni_service.clock import Clock
from igni_service.errors import IgniUnavailable
from igni_service.grants import RefreshTokenGrant
from igni_service.keyed_locks import KeyedLocks
from igni_service.token_endpoint import GrantRefused
from igni_service.verified_claims import TokenRefused
from igni_service.web_sessions import WebSession, WebSessionStore
from igni_service.web_tokens import SignedIn, WebTokenExchange

logger = logging.getLogger(__name__)


class RenewalUnavailable(HTTPException):
    """A session's access token has run out and igni cannot be reached to renew it: 503."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="igni server cannot be reached to renew this session",
        )


class SessionTiming(BaseModel):
    """How long a web session lives, and when its access token is renewed."""

    model_config = ConfigDict(frozen=True)

    session_ttl: float
    """How long a session lives from the sign-in or its last renewal."""
    renew_before: float
    """How long before the access token expires it is renewed."""


class WebSessions:
    """The sessions of people signed in to the service's pages.

    Args:
        exchange: Where a session's refresh token is renewed and revoked.
        store: Where the sessions and the sign-ins in flight are kept.
        clock: The clock expiry and renewal are read from.
        timing: How long a session lives, and when it is renewed.
    """

    def __init__(
        self,
        exchange: WebTokenExchange,
        store: WebSessionStore,
        clock: Clock,
        timing: SessionTiming,
    ) -> None:
        self._exchange = exchange
        self._store = store
        self._clock = clock
        self._timing = timing
        self._renewing = KeyedLocks()

    @property
    def store(self) -> WebSessionStore:
        """Where the sessions and sign-ins in flight are kept."""
        return self._store

    async def open(self, signed_in: SignedIn) -> str:
        """A new session for `signed_in`; returns its id, the cookie's value."""
        session_id = secrets.token_urlsafe(32)
        await self._store.put(session_id, self._session(signed_in))
        return session_id

    async def person(self, session_id: str) -> Person | None:
        """The person session `session_id` is for, renewing it first when due.

        `None` when there is no such session, or igni refused to renew it.

        Raises:
            RenewalUnavailable: the access token has run out and igni cannot
                be reached to renew it.
        """
        session = await self._store.get(session_id) if session_id else None
        if session is not None and self._due(session):
            async with self._renewing.held(session_id):
                session = await self._renew(session_id)
        return session.person if session is not None else None

    async def end(self, session_id: str) -> None:
        """End session `session_id` here, then revoke its refresh token at igni."""
        session = await self._store.get(session_id)
        await self._store.delete(session_id)
        if session is not None and session.refresh_token:
            await self._exchange.revoke(session.refresh_token)

    def _due(self, session: WebSession, now: float | None = None) -> bool:
        at = self._clock.wall() if now is None else now
        return at >= session.access_expires_at - self._timing.renew_before

    async def _renew(self, session_id: str) -> WebSession | None:
        current = await self._store.get(session_id)
        now = self._clock.wall()
        if current is None or not self._due(current, now):
            return current
        try:
            signed_in = await self._exchange.sign_in(
                RefreshTokenGrant(refresh_token=current.refresh_token)
            )
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
            raise RenewalUnavailable() from exc
        renewed = self._session(signed_in, refresh_token=current.refresh_token)
        await self._store.put(session_id, renewed)
        return renewed

    def _session(self, signed_in: SignedIn, *, refresh_token: str = "") -> WebSession:
        now = self._clock.wall()
        issued = signed_in.issued
        return WebSession(
            person=signed_in.person,
            access_token=issued.access_token,
            refresh_token=issued.refresh_token or refresh_token,
            access_expires_at=now + issued.expires_in,
            expires_at=now + self._timing.session_ttl,
        )

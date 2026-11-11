"""Where a service keeps people signed in to its own pages.

Server-side: the browser holds an opaque, random session id in an
HttpOnly cookie and nothing else. The person's access and refresh tokens
stay here and are never sent to the browser.

`WebSessionStore` is the protocol; `MemoryWebSessionStore` is for tests
and a single process; `SqlWebSessionStore` is for a deployment — every
replica sees every session, because igni's callback may land on any of
them. It seals each row with the service's key encryption key and keys it
by a SHA-256 of the cookie, so a copy of the table signs nobody in.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from igni_service.clock import Clock
from igni_service.keystore import KeyCipher
from igni_service.sql_tables import TableMaker
from igni_service.tables import IgniTables
from igni_service.tokens import Person


class WebSession(BaseModel):
    """One person signed in to the service's pages."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    person: Person
    """Who is signed in."""
    access_token: str
    """Their current access token for this service."""
    refresh_token: str
    """What renews it, until the sign-in ends."""
    access_expires_at: float
    """Wall-clock second the access token stops working."""
    expires_at: float
    """Wall-clock second the session is dead: the refresh token's life."""


class LoginAttempt(BaseModel):
    """A sign-in in flight: sent to igni, not yet back."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    state: str
    """The OAuth `state` sent to igni: what the callback is matched by."""
    verifier: str
    """The PKCE code verifier for the code igni sends back."""
    return_to: str
    """Where to send the person once they are signed in."""
    expires_at: float
    """Wall-clock second after which the attempt is void."""


@runtime_checkable
class WebSessionStore(Protocol):
    """Where `igni.web` keeps its people's sessions and sign-ins in flight.

    `MemoryWebSessionStore` keeps them in the process; `SqlWebSessionStore`
    in the service's database, for several replicas. A store of your own
    implements these five methods. Session ids and `state`s are secrets:
    keep a digest of them, not the value.

    Args:
        args: The positional arguments a concrete store's constructor takes; the protocol itself takes none of them on.
        kwargs: The keyword arguments a concrete store's constructor takes; the protocol itself takes none of them on.
    """

    async def get(self, session_id: str) -> WebSession | None:
        """The session `session_id` names, or `None` when there is none or it has expired.

        Args:
            session_id: The opaque, random id the browser holds in its cookie. A secret: keep a digest of it, not the value.
        """
        ...

    async def put(self, session_id: str, session: WebSession) -> None:
        """Keep `session` under `session_id`, replacing what was there.

        Args:
            session_id: The opaque, random id the browser holds in its cookie, and the name the session is kept under.
            session: The session to keep: who is signed in, and the tokens that keep them signed in.
        """
        ...

    async def delete(self, session_id: str) -> None:
        """Forget the session `session_id` names. Not an error when there is none.

        Args:
            session_id: The opaque, random id of the session to forget.
        """
        ...

    async def put_login(self, attempt: LoginAttempt) -> None:
        """Keep a sign-in in flight until igni sends the person back.

        Args:
            attempt: The sign-in in flight: the OAuth `state` sent to igni, the PKCE verifier igni answers with, and where to send the person afterwards.
        """
        ...

    async def take_login(self, state: str) -> LoginAttempt | None:
        """The attempt for `state`, once: a second take finds nothing.

        Args:
            state: The OAuth `state` igni sent the person back with, matched against the sign-in in flight.
        """
        ...


class Digest:
    @staticmethod
    def of(secret: str) -> str:
        """The SHA-256 of a secret, as hex: what a store keeps a secret under.

        Args:
            secret: The secret to digest: a session id, or an OAuth `state`.
        """
        return hashlib.sha256(secret.encode()).hexdigest()


class MemoryWebSessionStore:
    """Sessions in this process only. For tests, and for one replica.

    Args:
        clock: Where the store reads the time, so a test can move it; the system's own clock when it is not given.
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or Clock()
        self._sessions: dict[str, WebSession] = {}
        self._logins: dict[str, LoginAttempt] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> WebSession | None:
        """The session `session_id` names, or `None` when there is none or it has expired.

        Args:
            session_id: The opaque, random id the browser holds in its cookie; the session is kept under a SHA-256 of it.
        """
        session = self._sessions.get(Digest.of(session_id))
        if session is not None and self._clock.wall() >= session.expires_at:
            self._sessions.pop(Digest.of(session_id), None)
            return None
        return session

    async def put(self, session_id: str, session: WebSession) -> None:
        """Keep `session` under `session_id`, replacing what was there.

        Args:
            session_id: The opaque, random id the browser holds in its cookie, and the name the session is kept under.
            session: The session to keep: who is signed in, and the tokens that keep them signed in.
        """
        self._sessions[Digest.of(session_id)] = session

    async def delete(self, session_id: str) -> None:
        """Forget the session `session_id` names.

        Args:
            session_id: The opaque, random id of the session to forget.
        """
        self._sessions.pop(Digest.of(session_id), None)

    async def put_login(self, attempt: LoginAttempt) -> None:
        """Keep a sign-in in flight until igni sends the person back.

        Args:
            attempt: The sign-in in flight, kept under a SHA-256 of its `state` until igni sends the person back.
        """
        self._logins[Digest.of(attempt.state)] = attempt

    async def take_login(self, state: str) -> LoginAttempt | None:
        """The attempt for `state`, once and unexpired: a second take finds nothing.

        Args:
            state: The OAuth `state` igni sent the person back with; the attempt kept under a SHA-256 of it is taken out of the store.
        """
        async with self._lock:
            attempt = self._logins.pop(Digest.of(state), None)
        if attempt is None or self._clock.wall() >= attempt.expires_at:
            return None
        return attempt


class SqlWebSessionStore:
    """Sessions in two of the service's tables, sealed. See `igni_service.tables`.

    Args:
        engine: The connection to the service's database, where the two tables are.
        cipher: The cipher the rows are sealed with, under the service's key encryption key.
        create_table: Whether the two tables are created on first use; `False` when the service owns its schema in migrations.
        clock: Where the store reads the time, so a test can move it; the system's own clock when it is not given.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        cipher: KeyCipher,
        *,
        create_table: bool = True,
        clock: Clock | None = None,
    ) -> None:
        self._engine = engine
        self._cipher = cipher
        self._clock = clock or Clock()
        self._tables = TableMaker(
            engine, [IgniTables.web_session, IgniTables.web_login], create=create_table
        )

    async def get(self, session_id: str) -> WebSession | None:
        """The session `session_id` names, unsealed, or `None` when there is none or it has expired.

        Args:
            session_id: The opaque, random id the browser holds in its cookie; the row is found under a SHA-256 of it.
        """
        await self._tables.ensure()
        table = IgniTables.web_session
        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    select(table.c.sealed, table.c.expires_at).where(
                        table.c.id_hash == Digest.of(session_id)
                    )
                )
            ).first()
        if row is None or self._clock.wall() >= float(row.expires_at):
            return None
        return WebSession.model_validate_json(self._cipher.open(str(row.sealed)))

    async def put(self, session_id: str, session: WebSession) -> None:
        """Keep `session`, sealed, under a digest of `session_id`, replacing what was there.

        Args:
            session_id: The opaque, random id the browser holds in its cookie; the row is keyed by a SHA-256 of it.
            session: The session to keep, sealed before it is written.
        """
        await self._tables.ensure()
        table = IgniTables.web_session
        values = {
            "sealed": self._cipher.seal(session.model_dump_json()),
            "expires_at": session.expires_at,
        }
        async with self._engine.begin() as connection:
            changed = await connection.execute(
                update(table).where(table.c.id_hash == Digest.of(session_id)).values(**values)
            )
            if changed.rowcount == 0:
                await connection.execute(
                    insert(table).values(id_hash=Digest.of(session_id), **values)
                )

    async def delete(self, session_id: str) -> None:
        """Forget the session `session_id` names.

        Args:
            session_id: The opaque, random id of the session to forget; the row under a SHA-256 of it is deleted.
        """
        await self._tables.ensure()
        table = IgniTables.web_session
        async with self._engine.begin() as connection:
            await connection.execute(delete(table).where(table.c.id_hash == Digest.of(session_id)))

    async def put_login(self, attempt: LoginAttempt) -> None:
        """Keep a sign-in in flight, sealed; sign-ins and sessions that have expired are deleted on the way.

        Args:
            attempt: The sign-in in flight, sealed before it is written and keyed by a SHA-256 of its `state`.
        """
        await self._tables.ensure()
        table = IgniTables.web_login
        now = self._clock.wall()
        async with self._engine.begin() as connection:
            # Sign-ins nobody finished, and dead sessions, go as new ones arrive.
            await connection.execute(delete(table).where(table.c.expires_at <= now))
            await connection.execute(
                delete(IgniTables.web_session).where(IgniTables.web_session.c.expires_at <= now)
            )
            await connection.execute(
                insert(table).values(
                    state_hash=Digest.of(attempt.state),
                    sealed=self._cipher.seal(attempt.model_dump_json()),
                    expires_at=attempt.expires_at,
                )
            )

    async def take_login(self, state: str) -> LoginAttempt | None:
        """The attempt for `state`, once and unexpired: of two replicas taking it, one gets it.

        Args:
            state: The OAuth `state` igni sent the person back with; the row under a SHA-256 of it is deleted, so of two replicas taking it, one gets it.
        """
        await self._tables.ensure()
        table = IgniTables.web_login
        async with self._engine.begin() as connection:
            row = (
                await connection.execute(
                    select(table.c.sealed, table.c.expires_at).where(
                        table.c.state_hash == Digest.of(state)
                    )
                )
            ).first()
            if row is None:
                return None
            taken = await connection.execute(
                delete(table).where(table.c.state_hash == Digest.of(state))
            )
        # Whoever deleted the row took the attempt; a racing second take
        # deletes nothing and gets nothing.
        if taken.rowcount != 1 or self._clock.wall() >= float(row.expires_at):
            return None
        return LoginAttempt.model_validate_json(self._cipher.open(str(row.sealed)))

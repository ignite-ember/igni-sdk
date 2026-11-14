"""`IgniService`: everything a service needs from igni, behind one object.

igni = IgniService.from_settings(IgniSettings())
app = FastAPI(lifespan=igni.lifespan)
igni.install(app)

@igni.on_erase
async def erase(subject: Subject) -> None: ...

@igni.on_organisation_deleted
async def organisation_deleted(org_id: str) -> None: ...

@app.get("/things")
async def things(person: Person = Depends(igni.person)): ...

await igni.host(person.org_id).notify(Notification(...))
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Collection

import httpx
from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from igni_service.bearer import BearerDependencies
from igni_service.callbacks import IgniCallbacks
from igni_service.clock import Clock
from igni_service.connection import IgniConnection
from igni_service.cors import BearerCors
from igni_service.errors import ConfigurationError
from igni_service.host import Host
from igni_service.jwks import IgniKeys
from igni_service.keystore import KeyCipher, KeyStore
from igni_service.logs import ServiceLogs
from igni_service.organisations import OrganisationDeletedHandler
from igni_service.outbound import IgniOutbound
from igni_service.settings import IgniSettings
from igni_service.sql_keystore import SqlKeyStore
from igni_service.subjects import EraseHandler, ExportHandler
from igni_service.tokens import PEOPLE_ONLY, CallerKind, TokenVerifier
from igni_service.web import WebSignIn
from igni_service.web_sessions import MemoryWebSessionStore, SqlWebSessionStore, WebSessionStore


class IgniService(BearerDependencies):
    """A service's place in an igni deployment.

    Composed of its connection to igni server (`connection`), the calls it
    makes to igni (`outbound`), sign-in to its own pages (`web`) and the
    handlers for igni's calls to it; the FastAPI dependencies that read a
    request's bearer token (`person`, `caller`, `igni_call`, ...) come from
    `BearerDependencies`.

    Args:
        settings: The service's settings: where igni server is, what this
            service is called, its own public URL and the rest.
        key_store: Where the service keeps its signing key.
        web_store: Where the service keeps the sign-in sessions of its own
            pages; in this process, in memory, when it is not given.
        http: The `httpx.AsyncClient` every call to igni server goes
            through; one of the service's own, which it closes, when it is
            not given.
        clock: The clock every token's age and expiry is read from; a test
            passes a `ManualClock`.
        retry_min: Seconds before the first retry of the registration with
            igni server, when it fails.
        accepted_callers: The kinds of caller `caller` lets in: people
            only, unless the service says more.
    """

    def __init__(
        self,
        settings: IgniSettings,
        *,
        key_store: KeyStore,
        web_store: WebSessionStore | None = None,
        http: httpx.AsyncClient | None = None,
        clock: Clock | None = None,
        retry_min: float | None = None,
        accepted_callers: Collection[CallerKind] = PEOPLE_ONLY,
    ) -> None:
        connection = IgniConnection(
            settings, key_store=key_store, http=http, clock=clock, retry_min=retry_min
        )
        super().__init__(
            TokenVerifier(
                connection.server,
                IgniKeys(connection.server, clock=connection.clock),
                clock=connection.clock,
                revocations=connection.revocation_feed,
            ),
            accepted_callers,
        )
        self.settings = settings
        """The settings the service was made with."""
        self.connection = connection
        """This service's standing at igni server (`IgniConnection`): `server`, `clock`, `key`,
        `registration` and the `revocation_feed`."""
        self.outbound = IgniOutbound(connection)
        """Every call to igni (`IgniOutbound`); `igni.host(org_id)` is one organisation's."""
        self.web = WebSignIn(
            connection.server,
            connection.registration,
            connection.key,
            self.verifier,
            web_store or MemoryWebSessionStore(clock=connection.clock),
            clock=connection.clock,
        )
        """Sign-in to the service's own pages, with cookies (`WebSignIn`):
        `igni.web.person`, `igni.web.router`."""
        self._callbacks = IgniCallbacks(self.outbound.directory, self.igni_call)
        self._owned_engine: AsyncEngine | None = None

    @classmethod
    def from_settings(
        cls,
        settings: IgniSettings,
        *,
        key_store: KeyStore | None = None,
        http: httpx.AsyncClient | None = None,
        clock: Clock | None = None,
    ) -> IgniService:
        """A service from its settings, keeping its key and its people's
        sessions in `IGNI_KEY_DATABASE_URL`.

        Pass `key_store` to keep the key somewhere else — a `SqlKeyStore` on
        the service's own engine, usually — and then construct `IgniService`
        directly to pass a `web_store` too.

        Args:
            settings: The service's settings: where igni server is, what
                this service is called, its own public URL and the rest.
            key_store: Where the service keeps its signing key; when it is
                not given, the key and the sessions are kept in
                `IGNI_KEY_DATABASE_URL` instead.
            http: The `httpx.AsyncClient` every call to igni server goes
                through; one of the service's own, which it closes, when it
                is not given.
            clock: The clock every token's age and expiry is read from; a
                test passes a `ManualClock`.
        """
        web_store: WebSessionStore | None = None
        engine: AsyncEngine | None = None
        if key_store is None:
            if not settings.key_database_url:
                raise ConfigurationError(
                    "igni: set IGNI_KEY_DATABASE_URL, or pass a key_store, so this service "
                    "can keep its key"
                )
            engine = create_async_engine(settings.key_database_url)
            cipher = KeyCipher(settings.key_encryption_key)
            key_store = SqlKeyStore(engine, cipher)
            web_store = SqlWebSessionStore(engine, cipher, clock=clock)
        service = cls(settings, key_store=key_store, web_store=web_store, http=http, clock=clock)
        service._owned_engine = engine
        return service

    # ── The FastAPI surface ─────────────────────────────────────────

    @contextlib.asynccontextmanager
    async def lifespan(self, app: FastAPI | None = None) -> AsyncIterator[None]:
        """Register with igni, and keep its revocation list, for as long as the app runs.

        Usable as `FastAPI(lifespan=igni.lifespan)`, or entered inside the
        service's own lifespan (`async with igni.lifespan(app): ...`).
        From the start every token is checked against the revocation list,
        which fails closed if it cannot be kept fresh.

        Args:
            app: The app the lifespan runs for, as FastAPI passes it in;
                igni does not use it.
        """
        ServiceLogs.make_visible()
        try:
            async with self.connection.running():
                yield
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        """Close what this object opened: its HTTP client, and its database engine."""
        await self.connection.aclose()
        if self._owned_engine is not None:
            await self._owned_engine.dispose()
            self._owned_engine = None

    def install(self, app: FastAPI) -> None:
        """Put igni's part of the service on `app`: igni's calls
        (`router`), sign-in to the service's own pages (`web.router`), and
        cross-origin calls from the extension's page to every route that
        takes its caller's bearer token (`BearerCors`: `person`,
        `optional_person`, `org_admin`, `caller`, `token`, `optional_token`)
        — any origin, the token and nothing else, never cookies.

        Args:
            app: The FastAPI app igni's routes and middleware are put on.
        """
        app.include_router(self.router)
        app.include_router(self.web.router)
        app.add_middleware(BearerCors, igni=self)

    @property
    def router(self) -> APIRouter:
        """The routes igni calls: erasure and export of one person, and a
        deleted organisation."""
        return self._callbacks.router

    def on_erase(self, handler: EraseHandler) -> EraseHandler:
        """Register what erases one person's data in one organisation.

        Args:
            handler: What to call when igni asks the service to erase or
                redact one person's data in one organisation; it is given a
                `Subject`, and must be idempotent, as igni repeats it until
                every service confirms.
        """
        return self._callbacks.on_erase(handler)

    def on_export(self, handler: ExportHandler) -> ExportHandler:
        """Register what lists one person's data in one organisation.

        Args:
            handler: What to call when igni asks what the service holds
                about one person in one organisation; it is given a
                `Subject` and answers with the sections of rows.
        """
        return self._callbacks.on_export(handler)

    def on_organisation_deleted(
        self, handler: OrganisationDeletedHandler
    ) -> OrganisationDeletedHandler:
        """Register what stops routing to an organisation igni deleted.

        Receives the organisation's id. Must be idempotent: igni repeats it
        until the service confirms.

        Args:
            handler: What to call when igni says an organisation was
                deleted; it is given the organisation's id, and must be
                idempotent.
        """
        return self._callbacks.on_organisation_deleted(handler)

    # ── Talking to igni ─────────────────────────────────────────────

    def host(self, org_id: str) -> Host:
        """igni for one organisation: `notify`, `agent(producer)`, `send_event`,
        `extension_vm_profile`, and its `directory`.

        Args:
            org_id: The organisation's id in igni, the one every call this
                host makes is for.
        """
        return self.outbound.host(org_id)

    async def thumbprint(self) -> str:
        """The key's RFC 7638 thumbprint: what a super admin compares."""
        return await self.connection.key.thumbprint()

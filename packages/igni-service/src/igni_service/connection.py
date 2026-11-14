"""`IgniConnection`: this service's standing at igni server.

Where igni server is, the key that is this deployment's identity there,
the registration made with that key, and the revocation feed that keeps
what igni has revoked fresh. `IgniService` keeps one as `igni.connection`
and runs it for as long as its lifespan does.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

import httpx

from igni_service.clock import Clock
from igni_service.errors import ConfigurationError
from igni_service.keystore import KeyStore
from igni_service.registration import ServiceRegistration
from igni_service.revocations import RevocationFeed, RevocationList
from igni_service.server import IgniServer
from igni_service.settings import IgniSettings
from igni_service.signing import SigningKey
from igni_service.token_endpoint import TokenEndpoint
from igni_service.web import WebSignIn


class IgniConnection:
    """A service's connection to igni server, made from its settings.

    Args:
        settings: The service's settings: where igni server is, what this
            service is called, its own public URL and the rest.
        key_store: Where the service keeps its signing key.
        http: The `httpx.AsyncClient` every call to igni server goes
            through; one of the service's own, which it closes, when it is
            not given.
        clock: The clock every token's age and expiry is read from.
        retry_min: Seconds before the first retry of the registration with
            igni server, when it fails.
    """

    def __init__(
        self,
        settings: IgniSettings,
        *,
        key_store: KeyStore,
        http: httpx.AsyncClient | None = None,
        clock: Clock | None = None,
        retry_min: float | None = None,
    ) -> None:
        self._require(settings)
        try:
            self.server = IgniServer(
                base_url=settings.igni_server_url,
                own_url=settings.public_base_url,
                timeout=settings.timeout,
                http=http,
            )
            """igni server as this service reaches it: its address, this
            service's own URL, the HTTP client."""
        except ValueError as exc:
            raise ConfigurationError(f"igni: PUBLIC_BASE_URL: {exc}") from exc
        self.clock = clock or Clock()
        """The clock every token's age and expiry is read from; tests pass a `ManualClock`."""
        self.key = SigningKey(key_store, clock=self.clock)
        """This deployment's signing key: its identity at igni."""
        self.registration = ServiceRegistration(
            self.server,
            self.key,
            service_name=settings.service_name,
            kind=settings.client_kind,
            redirect_uris=list(
                dict.fromkeys(
                    [WebSignIn.redirect_uri_for(self.server.own_url), *settings.redirect_uris]
                )
            ),
            bundle_path=settings.extension_bundle_path,
            retry_min=retry_min,
        )
        """This service's registration with igni and the shipping of its
        extension (`ServiceRegistration`)."""
        self.revocation_feed = RevocationFeed(
            self.server,
            TokenEndpoint(self.server, self.registration, self.key),
            RevocationList(max_staleness=settings.revocations_max_staleness, clock=self.clock),
            clock=self.clock,
        )
        """What igni has revoked (its `revocations`), kept fresh while
        `running` (`igni_service.revocations`)."""

    @staticmethod
    def _require(settings: IgniSettings) -> None:
        missing = [
            name
            for name, value in (
                ("IGNI_SERVER_URL", settings.igni_server_url),
                ("PUBLIC_BASE_URL", settings.public_base_url),
                ("SERVICE_NAME", settings.service_name),
            )
            if not value.strip()
        ]
        if missing:
            raise ConfigurationError(f"igni: {', '.join(missing)} must be set")

    @contextlib.asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        """Keep trying the registration, and keep the revocation list fresh, while inside."""
        stop = asyncio.Event()
        background = [
            asyncio.create_task(self.registration.keep_trying(stop)),
            asyncio.create_task(self.revocation_feed.run(stop)),
        ]
        try:
            yield
        finally:
            stop.set()
            for task in background:
                task.cancel()
            for task in background:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def aclose(self) -> None:
        """Close the HTTP client, when it is this connection's own."""
        await self.server.aclose()

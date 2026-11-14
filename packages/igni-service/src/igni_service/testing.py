"""igni server, played in-process, so a service can be tested without one.

    fake = FakeIgni()
    fake.directory.add_member("org-1", Member(user_id="u-ada", email="ada@acme.test", name="Ada"))
    igni = fake.service()                     # an IgniService wired to the fake
    app = FastAPI(lifespan=igni.lifespan)
    ...
    token = fake.signer.person_token("u-ada", org_id="org-1")
    headers = {"Authorization": f"Bearer {token}"}

It is a real issuer in every way a service can observe: it holds an RSA
key and publishes the public half with a `max-age`; it signs tokens RS256
with a `kid`; its issuer is not the address it is reached at, as a
deployment's is not. It checks what igni checks — client assertions
against the registered key with single-use `jti`s, bundle signatures and
digests, notification limits — and records what it was sent.

Each part of igni is a collaborator a test talks to directly:
`fake.directory` (organisations and members), `fake.clients`
(registrations; `approve`, `revoke`), `fake.signer` (tokens igni signs,
its keys), `fake.oauth` (grants, revoked refresh tokens, the portal's
sign-in as `fake.oauth.sign_ins.authorize`), `fake.extensions` (bundles,
assets, `hold`), `fake.notifications` (each call as sent, each person
told), `fake.revocations` (`publish`), `fake.traffic` (every request,
`fail` and `heal`), `fake.agents` and `fake.vm_profiles` (an org
admin's decisions as `fake.vm_profiles.approve(org_id,
VmProfileSubject.app(app_id))`). `fake.router` answers every request the
service sends, as igni's router does.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from igni_service.agent_wire import AgentWire
from igni_service.app import IgniApp
from igni_service.bundle.archive import BundleArchive
from igni_service.clock import Clock
from igni_service.crypto import RsaKeyPair
from igni_service.events import EventSender
from igni_service.keystore import KeyStore, MemoryKeyStore, StoredKey
from igni_service.notifications import Notifier
from igni_service.registration import ExtensionBundle
from igni_service.service import IgniService
from igni_service.settings import IgniSettings
from igni_service.testing_assertions import ClientAssertionVerifier
from igni_service.testing_bearers import BearerTokens
from igni_service.testing_bundles import BundleSource, HeldExtension
from igni_service.testing_claims import PersonClaims, SpaceClaims, TokenOverrides
from igni_service.testing_clients import FakeClientRegistry
from igni_service.testing_directory import FakeDirectory, OrganisationDeletion
from igni_service.testing_extensions import FakeExtensionStore
from igni_service.testing_items import FakeAgents, SentEvent
from igni_service.testing_notifications import Delivery, FakeNotifications, NotifyCall
from igni_service.testing_oauth import FakeTokenEndpoint
from igni_service.testing_revocations import FakeRevocations
from igni_service.testing_router import FakeRouter, RouteGuard, RouteTable
from igni_service.testing_routes import AgentRoutes, Route, RouteAuth, VmProfileRoutes
from igni_service.testing_seams import HeldKeyStore, ManualClock, no_sleep
from igni_service.testing_sessions import PortalRefused, SignIns
from igni_service.testing_settings import SettingsOverrides
from igni_service.testing_signer import FakeSigner
from igni_service.testing_vm_profiles import (
    FakeVmProfiles,
    NoVmProfileRequest,
    VmProfileSubject,
)
from igni_service.testing_vm_rules import FakeCaps
from igni_service.testing_wire import (
    BASE,
    ISSUER,
    SERVICE_URL,
    IgniAddresses,
    RecordedTraffic,
    SeenRequest,
)
from igni_service.tokens import PEOPLE_ONLY, CallerKind
from igni_service.urls import IgniPaths

if TYPE_CHECKING:
    from igni_service.testing_wire import RoutedCall


class FakeIgni:
    """Every igni endpoint a service calls, composed of one collaborator per part of igni.

    Args:
        clock: The clock the fake signs and expires by; a ``ManualClock`` moves it in a test.
        addresses: Where the fake is reached, the issuer its tokens name, and the
            service under test's own URL.
        require_approval: Whether a registration must be approved by a super admin
            before it is given a token.
    """

    BASE = BASE
    """Where the service reaches the fake."""
    ISSUER = ISSUER
    """Its issuer: its public URL, deliberately not `BASE`."""
    SERVICE_URL = SERVICE_URL
    """The service under test's own URL."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        addresses: IgniAddresses | None = None,
        require_approval: bool = False,
    ) -> None:
        self.addresses = addresses or IgniAddresses()
        """The fake's three addresses: `base_url`, `issuer`, `service_url`."""
        self.clock = clock or Clock()
        """The clock the fake signs and expires by; pass a `ManualClock` to move it."""
        self.traffic = RecordedTraffic()
        """Every request the fake was sent; `fail(path, status)` plays igni failing."""
        self.directory = FakeDirectory()
        """The organisations and their members: `add_member`, `add_organisation`, ..."""
        self.clients = FakeClientRegistry()
        """The registered services and apps: `approve()` and `revoke()` play a super admin."""
        self.signer = FakeSigner(
            addresses=self.addresses, clock=self.clock, directory=self.directory
        )
        """Signs the tokens a service receives: `person_token`, `app_token`, `space_token`,
        `igni_token`.
        """
        self.oauth = FakeTokenEndpoint(
            verifier=ClientAssertionVerifier(
                addresses=self.addresses,
                clock=self.clock,
                clients=self.clients,
                require_approval=require_approval,
            ),
            bearers=BearerTokens(),
            sign_ins=SignIns(
                addresses=self.addresses,
                clock=self.clock,
                clients=self.clients,
                directory=self.directory,
            ),
            signer=self.signer,
        )
        """The token and revocation endpoints, and the portal's sign-in."""
        self.extensions = FakeExtensionStore(self.clients)
        """The extension bundles and assets services uploaded; `hold(reason)` holds new versions."""
        self.notifications = FakeNotifications(directory=self.directory, extensions=self.extensions)
        """Every notification call, and every delivery after igni's rules."""
        self.revocations = FakeRevocations(self.clock)
        """What igni has revoked: `publish(subject_id, org_id=...)` removes somebody."""
        self.agents = FakeAgents(is_member=self.directory.is_member, clock=self.clock.wall)
        """The agent channel: items, uploaded files, their states."""
        self.vm_profiles = FakeVmProfiles(clock=self.clock.wall)
        """VM profiles: requests, an org admin's decisions, what a VM gets."""
        self._routes = self._route_table()

    @property
    def router(self) -> FakeRouter:
        """The pipeline every request the service sends goes through, as igni's router.

        Made from the fake's collaborators as they are now, so a test that
        replaces one (`fake.traffic = RecordedTraffic()`) is heard on the
        wire, as it was when the pipeline was `FakeIgni`'s own.
        """
        return FakeRouter(
            addresses=self.addresses,
            traffic=self.traffic,
            guard=RouteGuard(self.oauth.bearers, self.clients),
            table=self._routes,
        )

    def reset(self) -> None:
        """Forget what happened, keep who exists.

        For a fake shared across a session: requests, failures, grants,
        revoked tokens, sign-ins (codes and refresh tokens), notifications,
        deliveries, the once-per-event memory, revocations, agent items and
        held uploads go; organisations, members, registered clients, keys,
        uploaded extensions and assets stay, so the next test starts from
        the same world. Issued service and app tokens and used `jti`s stay
        too: a service shared across the session may still hold a cached
        token, and replay memory is never forgotten.
        """
        self.traffic.reset()
        self.oauth.reset()
        self.notifications.reset()
        self.revocations.reset()
        self.extensions.reset()
        self.agents.reset()

    # ── Setting the scene ───────────────────────────────────────────

    def service(
        self,
        settings: IgniSettings | None = None,
        *,
        key_store: KeyStore | None = None,
        clock: Clock | None = None,
        accepted_callers: Collection[CallerKind] = PEOPLE_ONLY,
    ) -> IgniService:
        """An `IgniService` wired to this fake: key in memory, retries without waiting.

        Args:
            settings: The settings the service is made with; the fake's own, pointing
                at it, by default.
            key_store: Where the service keeps its signing key; in memory, by default.
            clock: The clock the service reads the time from for its tokens' age and
                expiry.
            accepted_callers: Whose tokens the service's ``caller`` accepts: people
                only, unless the service is told more.
        """
        service = IgniService(
            settings or self.settings(),
            key_store=key_store or MemoryKeyStore(),
            http=self.http_client(),
            clock=clock or self.clock,
            retry_min=0.01,
            accepted_callers=accepted_callers,
        )
        service.outbound.notifier = Notifier(service.outbound.tokens, sleep=no_sleep)
        service.outbound.events = EventSender(service.outbound.tokens, sleep=no_sleep)
        service.outbound.agents = AgentWire(service.outbound.tokens, service.outbound.events)
        return service

    def app(self, app_id: str, *, org_id: str, name: str = "") -> IgniApp:
        """An app an org admin registered in `org_id`, as an `IgniApp` wired to this fake.

        Its key is made now and its public half registered, as the admin's
        paste on the portal's Apps page does; approved by that act.

        Args:
            app_id: The id the app is known by at igni, as the portal shows it.
            org_id: The organisation whose admin registered the app.
            name: The app's display name, as the portal shows it.
        """
        self.directory.ensure(org_id)
        pair = RsaKeyPair.generate()
        self.clients.add_app(app_id, org_id, name, pair)
        return IgniApp(
            app_id,
            igni_server_url=self.addresses.base_url,
            key_store=HeldKeyStore(
                StoredKey(kid=pair.thumbprint(), private_pem=pair.private_pem())
            ),
            http=self.http_client(),
            clock=self.clock,
        )

    def settings(self, overrides: SettingsOverrides | None = None) -> IgniSettings:
        """Settings that reach this fake, with what `overrides` sets.

        Args:
            overrides: What a test changes about the settings; only the fields it
                sets are applied, and the rest are the fake's own.
        """
        return (overrides or SettingsOverrides()).settings_for(self.addresses)

    async def upload(
        self, bundle: str | Path | ExtensionBundle, service: IgniService
    ) -> HeldExtension:
        """Upload an extension as `service` does at start-up: registered, signed, over the wire.

        `bundle` is a built `extension-bundle.tar.gz`, or an extension's
        directory — its `manifest.json`, `README.md`, `plugin/` and `ui/` are
        archived as they are, with no wheelhouse, which is all this fake
        reads. Answers what the fake now holds (or holds back, with
        `extensions.hold`). For a test that needs the extension on igni —
        its VM profile request, its pages — without a lifespan or a build.

        Args:
            bundle: The extension's bundle: a built archive, the extension's
                directory, or the ``ExtensionBundle`` already built.
            service: The service that ships the bundle, and whose registration the
                upload is made under.
        """
        if not isinstance(bundle, ExtensionBundle):
            bundle = BundleSource(path=Path(bundle)).bundle()
        await service.connection.registration.ship(bundle)
        return self.extensions.latest(await service.connection.registration.client_id())

    # ── The wire ────────────────────────────────────────────────────

    def transport(self) -> httpx.MockTransport:
        """An `httpx` transport that reaches the fake: pass it as a service's `http`."""
        return httpx.MockTransport(self._answer)

    def http_client(self) -> httpx.AsyncClient:
        """An `httpx.AsyncClient` that reaches the fake."""
        return httpx.AsyncClient(transport=self.transport())

    def _answer(self, request: httpx.Request) -> httpx.Response:
        return self.router.handle(request)

    def _fallback(self, call: RoutedCall) -> httpx.Response:
        """An authenticated service path no route takes: the fake's directory, as it is now."""
        return self.directory.route(call)

    def _route_table(self) -> RouteTable:
        """Every path igni serves a service, in the order they are matched."""
        agents = AgentRoutes(self.agents)
        vm = VmProfileRoutes(self.vm_profiles, self.clients, self.extensions)
        service, any_org = RouteAuth.SERVICE, RouteAuth.SERVICE_ANY_ORG
        routes = (
            Route(path=IgniPaths.DISCOVERY, handler=self.signer.discovery),
            Route(path=IgniPaths.JWKS, handler=self.signer.jwks),
            Route(path=IgniPaths.CLIENTS, method="POST", handler=self.clients.register),
            Route(path=f"{IgniPaths.CLIENTS}/", prefix=True, handler=self.extensions.route),
            Route(path=IgniPaths.TOKEN, handler=self.oauth.issue),
            Route(path=IgniPaths.REVOKE, handler=self.oauth.revoke),
            Route(path=f"{IgniPaths.APPS}/", prefix=True, auth=RouteAuth.APP, handler=vm.app),
            Route(path=IgniPaths.REVOCATIONS, auth=any_org, handler=self.revocations.page),
            Route(path=IgniPaths.SERVED, auth=any_org, handler=self.directory.served),
            Route(path=IgniPaths.NOTIFICATIONS, auth=service, handler=self.notifications.notify),
            Route(
                path=IgniPaths.SERVICE_VM_PROFILE, method="GET", auth=service, handler=vm.service
            ),
            Route(path=IgniPaths.SERVICE_EVENTS, method="POST", auth=service, handler=agents.event),
            Route(path=IgniPaths.SERVICE_ITEMS, method="POST", auth=service, handler=agents.item),
            Route(
                path=IgniPaths.SERVICE_ATTACHMENTS,
                method="POST",
                auth=service,
                handler=agents.upload,
            ),
            Route(
                path=f"{IgniPaths.SERVICE_EVENTS}/",
                prefix=True,
                method="GET",
                auth=service,
                handler=agents.status,
            ),
            Route(
                path=f"{IgniPaths.DIRECTORY}/",
                prefix=True,
                auth=service,
                handler=self.directory.route,
            ),
        )
        return RouteTable(routes=routes, fallback=self._fallback)


#: What a service's tests import: the fake, every type its public methods
#: answer or take, and the helpers a test builds a scene with.
#: `BundleArchive` builds a stand-in bundle so the fake knows an
#: extension's pages; `IgniPaths` names the routes `fake.traffic.fail` can
#: be told to fail.
__all__ = [
    "BundleArchive",
    "Delivery",
    "FakeAgents",
    "FakeCaps",
    "FakeIgni",
    "FakeVmProfiles",
    "HeldExtension",
    "IgniAddresses",
    "IgniPaths",
    "ManualClock",
    "NoVmProfileRequest",
    "NotifyCall",
    "OrganisationDeletion",
    "PersonClaims",
    "PortalRefused",
    "SeenRequest",
    "SentEvent",
    "SettingsOverrides",
    "SpaceClaims",
    "TokenOverrides",
    "VmProfileSubject",
]

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
`fail` and `heal`), `fake.agents` and `fake.vm_profiles`.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field

from igni_service.app import IgniApp
from igni_service.bundle import BundleArchive
from igni_service.clock import Clock
from igni_service.crypto import RsaKeyPair
from igni_service.keystore import KeyStore, MemoryKeyStore, StoredKey
from igni_service.notifications import Notifier
from igni_service.registration import ExtensionBundle
from igni_service.service import IgniService
from igni_service.settings import IgniSettings
from igni_service.testing_assertions import ClientAssertionVerifier
from igni_service.testing_bearers import BearerTokens, TokenHolder
from igni_service.testing_bundles import BundleSource, HeldExtension
from igni_service.testing_claims import PersonClaims, SpaceClaims, TokenOverrides
from igni_service.testing_clients import FakeClientRegistry
from igni_service.testing_directory import FakeDirectory, OrganisationDeletion
from igni_service.testing_extensions import FakeExtensionStore
from igni_service.testing_items import FakeAgents, SentEvent
from igni_service.testing_notifications import Delivery, FakeNotifications, NotifyCall
from igni_service.testing_oauth import FakeTokenEndpoint
from igni_service.testing_revocations import FakeRevocations
from igni_service.testing_routes import AgentRoutes, Route, RouteAuth, VmProfileRoutes
from igni_service.testing_seams import HeldKeyStore, ManualClock, no_sleep
from igni_service.testing_sessions import PortalRefused, SignIns
from igni_service.testing_signer import FakeSigner
from igni_service.testing_vm_profiles import (
    FakeCaps,
    FakeVmProfiles,
    NoVmProfileRequest,
    VmProfileSubject,
)
from igni_service.testing_wire import (
    BASE,
    ISSUER,
    SERVICE_URL,
    DetailError,
    IgniAddresses,
    RecordedTraffic,
    RoutedCall,
    SeenRequest,
)
from igni_service.tokens import PEOPLE_ONLY, CallerKind
from igni_service.urls import IgniPaths
from igni_service.vm_profiles import VmProfileRequestRecord

NOT_AUTHENTICATED = DetailError(detail="Not authenticated", status=401)
NOT_FOUND = DetailError(detail="Not Found", status=404)


class SettingsOverrides(BaseModel):
    """What a test changes about the settings a service is wired to the fake with.

    Only the fields a test sets are applied (`exclude_unset`): every other
    one is the fake's address, its URL for the service, or `IgniSettings`'
    own default. A field `IgniSettings` lacks is refused, not ignored.
    """

    model_config = ConfigDict(extra="forbid")

    igni_server_url: str = ""
    public_base_url: str = ""
    service_name: str = ""
    client_kind: str = "service"
    redirect_uris: list[str] = Field(default_factory=list)
    key_encryption_key: str = ""
    key_database_url: str = ""
    extension_bundle_path: str = ""
    revocations_max_staleness: float = 30.0
    timeout: float = 10.0


class FakeIgni:
    """Every igni endpoint a service calls, composed of one collaborator per part of igni."""

    #: Where the service reaches the fake.
    BASE = BASE
    #: Its issuer: its public URL, deliberately not `BASE`.
    ISSUER = ISSUER
    #: The service under test's own URL.
    SERVICE_URL = SERVICE_URL

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        addresses: IgniAddresses | None = None,
        require_approval: bool = False,
    ) -> None:
        self.addresses = addresses or IgniAddresses()
        self.clock = clock or Clock()
        self.traffic = RecordedTraffic()
        self.directory = FakeDirectory()
        self.clients = FakeClientRegistry()
        self.signer = FakeSigner(
            addresses=self.addresses, clock=self.clock, directory=self.directory
        )
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
        self.extensions = FakeExtensionStore(self.clients)
        self.notifications = FakeNotifications(directory=self.directory, extensions=self.extensions)
        self.revocations = FakeRevocations(self.clock)
        #: The agent channel: items, uploaded files, their states.
        self.agents = FakeAgents(is_member=self.directory.is_member, clock=self.clock.wall)
        #: VM profiles: requests, an org admin's decisions, what a VM gets.
        self.vm_profiles = FakeVmProfiles()
        self._routes = self._route_table()

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
        """An `IgniService` wired to this fake: key in memory, retries without waiting."""
        service = IgniService(
            settings or self.settings(),
            key_store=key_store or MemoryKeyStore(),
            http=self.http_client(),
            clock=clock or self.clock,
            retry_min=0.01,
            accepted_callers=accepted_callers,
        )
        service.notifier = Notifier(service.tokens, sleep=no_sleep)
        return service

    def app(self, app_id: str, *, org_id: str, name: str = "") -> IgniApp:
        """An app an org admin registered in `org_id`, as an `IgniApp` wired to this fake.

        Its key is made now and its public half registered, as the admin's
        paste on the portal's Apps page does; approved by that act.
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
        """Settings that reach this fake, with what `overrides` sets."""
        defaults = SettingsOverrides(
            igni_server_url=self.addresses.base_url,
            public_base_url=self.addresses.service_url,
            service_name="Service under test",
        ).model_dump(exclude_unset=True)
        changes = (overrides or SettingsOverrides()).model_dump(exclude_unset=True)
        return IgniSettings.model_validate(defaults | changes)

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
        """
        if not isinstance(bundle, ExtensionBundle):
            bundle = BundleSource(path=Path(bundle)).bundle()
        await service.registration.ship(bundle)
        return self.extensions.latest(await service.registration.client_id())

    def approve_vm_profile(
        self, org_id: str, *, app: str | None = None, extension: str | None = None
    ) -> VmProfileRequestRecord:
        """Play an org admin approving an app's or an extension's VM profile request.

        The request must exist: an app's once it asked
        (`app.vm_profile.request`), an extension's once its bundle is
        uploaded and the service asked after it
        (`host.extension_vm_profile()`). `NoVmProfileRequest` (a
        `LookupError`) otherwise, saying so.
        """
        subject = VmProfileSubject.of(app, extension)
        return self.vm_profiles.approve(org_id, subject.kind, subject.subject_id)

    def reject_vm_profile(
        self,
        org_id: str,
        *,
        app: str | None = None,
        extension: str | None = None,
        reason: str | None = None,
    ) -> VmProfileRequestRecord:
        """Play an org admin rejecting an app's or an extension's VM profile request."""
        subject = VmProfileSubject.of(app, extension)
        return self.vm_profiles.reject(org_id, subject.kind, subject.subject_id, reason=reason)

    # ── The wire ────────────────────────────────────────────────────

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport())

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Answer `request` as igni would: failures a test asked for first, then the route.

        The first route serving the path says which token it needs; that
        token is checked before the method is. An authenticated path no
        route takes is the directory's, as igni's router has it.
        """
        if not self.addresses.reaches(str(request.url)):
            raise httpx.ConnectError(f"{request.url.host} is not igni", request=request)
        seen = self.traffic.record(request)
        failure = self.traffic.failure_for(seen.path)
        if failure is not None:
            return failure
        family = next((route for route in self._routes if route.serves(seen.path)), None)
        if family is None:
            return NOT_FOUND.to_response()
        holder = self._authorise(seen, family.auth)
        if isinstance(holder, DetailError):
            return holder.to_response()
        call = RoutedCall(seen=seen, holder=holder)
        route = next((route for route in self._routes if route.takes(seen)), None)
        if route is not None:
            return route.handler(call)
        if family.auth.is_service:
            return self.directory.route(call)
        return NOT_FOUND.to_response()

    def _authorise(self, seen: SeenRequest, auth: RouteAuth) -> TokenHolder | DetailError:
        """Whom the request's bearer token stands for, when `auth` needs one."""
        if auth is RouteAuth.NONE:
            return TokenHolder()
        bearers = self.oauth.bearers
        if auth is RouteAuth.APP:
            holder = bearers.app_holder(seen.bearer())
        else:
            holder = bearers.service_holder(seen.bearer())
        client = self.clients.get(holder.client_id) if holder else None
        if holder is None or client is None or client.is_revoked:
            return NOT_AUTHENTICATED
        if auth is RouteAuth.SERVICE and not holder.org_id:
            return NOT_AUTHENTICATED
        return holder

    def _route_table(self) -> tuple[Route, ...]:
        """Every path igni serves a service, in the order they are matched."""
        agents = AgentRoutes(self.agents)
        vm = VmProfileRoutes(self.vm_profiles, self.clients, self.extensions)
        service, any_org = RouteAuth.SERVICE, RouteAuth.SERVICE_ANY_ORG
        return (
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

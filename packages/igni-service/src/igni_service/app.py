"""`IgniApp`: an app of one organisation, acting as itself.

An **app** — a review bot, an integration — is not a service. A service
is the deployment's, approved by a super admin, and serves every
organisation; an app belongs to one organisation, whose org admin
registered it on the portal (*Apps*) by pasting its **public** key. The app
then obtains tokens as itself: `client_credentials` with `private_key_jwt`,
`client_id` = its app id, no organisation (igni server's
`docs/service-identity.md` §11.1). Its VM in igni's cloud is its own.

    app = IgniApp("3f0c…", igni_server_url="https://igni.bank.internal", key_store=store)
    print((await app.public_jwks()).model_dump_json())  # once: what the org admin pastes
    record = await app.vm_profile.request(VmProfileRequest(packages=VmPackages(apt=["chromium"])))
    record.state                         # "pending" until an org admin approves it
    await app.vm_profile.status()        # later: "approved" / "rejected" + reason
    await app.vm_profile.effective()     # what the VM gets now

The key is made on first use and kept in `key_store`, exactly as a
service's is (`igni_service.keystore`); the private half never leaves the
app. Nothing here can approve a request: that is an org admin's, on the
portal.
"""

from __future__ import annotations

import asyncio
from types import TracebackType

import httpx

from igni_service.app_vm_profiles import AppVmProfiles
from igni_service.clock import Clock
from igni_service.crypto import JwkSet
from igni_service.errors import ConfigurationError, IgniUnavailable
from igni_service.grants import ClientCredentialsGrant
from igni_service.keystore import KeyStore
from igni_service.server import IgniServer
from igni_service.service_tokens import HeldToken
from igni_service.signing import SigningKey
from igni_service.token_endpoint import GrantRefused, TokenEndpoint


class AppId:
    """The client id an app authenticates as: its app id, from the portal.

    Args:
        app_id: The app's id, as an org admin registered it on the portal.
    """

    def __init__(self, app_id: str) -> None:
        self._app_id = app_id

    async def client_id(self) -> str:
        return self._app_id


class IgniApp:
    """An app's place in an igni deployment: its key, its token, its VM's profile.

    Args:
        app_id: The app's id, as an org admin registered it on the portal:
            the client id the app authenticates as, and the app whose VM
            profile it asks for.
        igni_server_url: Where igni server is: the address every call the
            app makes is made against.
        key_store: Where the app keeps its signing key; the key is made on
            first use and kept there, and its private half never leaves the
            app.
        http: The ``httpx.AsyncClient`` every call to igni server goes
            through; one igni server makes for itself, and closes, when it
            is not given.
        clock: The clock the token's age and expiry are read from, and the
            one the client assertion's times are taken from; a test passes a
            ``ManualClock``.
        timeout: Seconds to wait for igni server's answer before giving up;
            it is the timeout of the client igni server makes for itself, and
            a client given in ``http`` keeps the timeout it was made with.
    """

    RENEW_BEFORE = 60.0
    """How long before expiry the token is replaced, in seconds."""

    def __init__(
        self,
        app_id: str,
        *,
        igni_server_url: str,
        key_store: KeyStore,
        http: httpx.AsyncClient | None = None,
        clock: Clock | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not app_id.strip():
            raise ConfigurationError("igni: an app needs its app id, as the portal shows it")
        if not igni_server_url.strip():
            raise ConfigurationError("igni: IGNI_SERVER_URL must be set")
        self.app_id = app_id
        """The app's id, as an org admin registered it."""
        self.clock = clock or Clock()
        """The clock the token's age is read from; tests pass a `ManualClock`."""
        self.vm_profile = AppVmProfiles(app_id, self)
        """Its VM profile: `.request(wanted)`, `.status()`, `.effective()`."""
        self.server = IgniServer(base_url=igni_server_url, timeout=timeout, http=http)
        """igni server as the app reaches it."""
        self.key = SigningKey(key_store, clock=self.clock)
        """The app's signing key; `await app.public_jwks()` is what an org admin registers."""
        self._endpoint = TokenEndpoint(self.server, AppId(app_id), self.key)
        self._held: HeldToken | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> IgniApp:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client this object opened."""
        await self.server.aclose()

    # ── The key an org admin registers ──────────────────────────────

    async def public_jwks(self) -> JwkSet:
        """The public key as a JWK set — what the org admin pastes on the portal's Apps page."""
        return JwkSet(keys=[(await self.key.pair()).public_jwk()])

    async def thumbprint(self) -> str:
        """The key's RFC 7638 thumbprint, which the portal shows beside the app."""
        return await self.key.thumbprint()

    # ── Its own token ───────────────────────────────────────────────

    async def token(self) -> str:
        """The app's own token for igni (`token_use` = `app`). Raises `IgniUnavailable`."""
        held = self._fresh()
        if held is not None:
            return held
        async with self._lock:
            held = self._fresh()
            if held is not None:
                return held
            try:
                issued = await self._endpoint.grant(ClientCredentialsGrant())
            except GrantRefused as exc:
                # `invalid_client` until an org admin registers this key, and
                # after they delete the app or rotate its key.
                raise IgniUnavailable(f"igni server refused this app a token: {exc}") from exc
            self._held = HeldToken(
                token=issued.access_token,
                expires_at=self.clock.monotonic() + issued.expires_in,
            )
            return issued.access_token

    def _fresh(self) -> str | None:
        held = self._held
        if held is not None and self.clock.monotonic() < held.expires_at - self.RENEW_BEFORE:
            return held.token
        return None

    async def request(
        self, method: str, path: str, *, json: object | None = None
    ) -> httpx.Response:
        """One call to igni as this app; a 401 is retried once with a new token.

        Args:
            method: The HTTP method of the call, as it goes on the wire:
                ``GET``, ``PUT``, and the rest.
            path: The path on igni server, put after the address the app
                reaches it at.
            json: The JSON body of the call; nothing is sent when it is
                not given.
        """
        for attempt in (1, 2):
            token = await self.token()
            try:
                response = await self.server.http.request(
                    method,
                    self.server.url(path),
                    headers={"Authorization": f"Bearer {token}"},
                    json=json,
                )
            except httpx.HTTPError as exc:
                raise IgniUnavailable(f"could not reach igni server: {type(exc).__name__}") from exc
            if response.status_code != 401:
                return response
            self._held = None
            if attempt == 2:
                break
        raise IgniUnavailable("igni server refused this app's token")

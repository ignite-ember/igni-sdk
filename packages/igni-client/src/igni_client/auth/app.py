"""An app of an organisation, signing in as itself."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx

from igni_client.auth.grants import ClientCredentialsGrant, SpaceExchangeGrant
from igni_client.auth.keys import AppKey, ClientAssertion, JwkSet
from igni_client.auth.server import IgniServer
from igni_client.auth.spaces import Spaces
from igni_client.auth.tokens import IssuedToken, TokenCache


class App:
    """An app of an organisation, signing in as itself.

    `server` is igni server's address (not the gateway's). The key is the
    app's RSA private key; its public half — `public_jwks()` — is what an
    org admin registers for the app on igni server. Until they have, a
    token request is refused with `AuthError`.
    """

    #: Renew a token this many seconds before it runs out.
    RENEW_BEFORE = 60
    #: How long a client assertion lives; one is made per token request.
    ASSERTION_LIFETIME = 60

    def __init__(
        self,
        app_id: str,
        *,
        server: str,
        key_file: str | Path | None = None,
        key_pem: str | None = None,
        http: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not app_id:
            raise ValueError("an app needs its app id")
        if key_file is not None and key_pem is None:
            pem = Path(key_file).expanduser().read_text()
        elif key_pem is not None and key_file is None:
            pem = key_pem
        else:
            raise ValueError("give the app's key as exactly one of key_file= or key_pem=")
        self.app_id = app_id
        self.clock = clock
        self._key = AppKey.from_pem(pem)
        self._server = IgniServer(server, http=http)
        self._tokens = TokenCache(clock, renew_before=lambda: self.RENEW_BEFORE)

    @staticmethod
    def generate_key(path: str | Path) -> Path:
        """Make a new RSA key for an app and write it to `path`, readable by its owner only."""
        return AppKey.generate(path)

    @property
    def server(self) -> str:
        """igni server's address; assignable, as it was a plain attribute in 0.1.0."""
        return self._server.url

    @server.setter
    def server(self, url: str) -> None:
        self._server.url = url

    def thumbprint(self) -> str:
        """The key's RFC 7638 thumbprint: its `kid`, and what an admin compares."""
        return self._key.thumbprint()

    def public_jwks(self) -> JwkSet:
        """The public key as a JWK set: what an org admin registers for this app."""
        return self._key.jwks()

    async def token(self) -> str:
        """The app's own token (`token_use=app`), renewed shortly before it runs out."""
        return await self._tokens.get(self._sign_in)

    async def exchange(self, space_id: str) -> IssuedToken:
        """The app's token exchanged for the token of its space `space_id` (`token_use=space`)."""
        grant = SpaceExchangeGrant(subject_token=await self.token(), space=space_id)
        return await self._server.grant(grant, what="the space's token")

    async def request(
        self,
        method: str,
        path: str,
        *,
        what: str,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        """A call to igni server as this app, retried once with a fresh token on a 401."""
        response = await self._server.call(
            method, path, what=what, bearer=await self.token(), params=params
        )
        if response.status_code != 401:
            return response
        await self._tokens.forget()
        return await self._server.call(
            method, path, what=what, bearer=await self.token(), params=params
        )

    @property
    def spaces(self) -> Spaces:
        """This app's spaces: its end users, each a producer with an igni of its own."""
        return Spaces(self)

    async def aclose(self) -> None:
        await self._server.aclose()

    async def __aenter__(self) -> App:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _sign_in(self) -> IssuedToken:
        grant = ClientCredentialsGrant(client_assertion=await self._assertion())
        return await self._server.grant(grant, what="the app's token")

    async def _assertion(self) -> str:
        now = int(self.clock())
        return self._key.sign(
            ClientAssertion(
                iss=self.app_id,
                sub=self.app_id,
                aud=await self._server.issuer(),
                iat=now,
                exp=now + self.ASSERTION_LIFETIME,
                jti=uuid.uuid4().hex,
            )
        )

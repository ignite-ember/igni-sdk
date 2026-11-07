"""Who the client connects as: a person, an app, or one of an app's spaces.

Each is a token source — `await auth.token()` — that a target asks for a
bearer token every time it opens a connection. Fleet's gateway checks the
token only when the socket opens, so a short-lived token is fetched again
for each connection, never refreshed under one that is open.

* **A person** brings a session pinned to their organisation: the one
  `igni login` keeps, or one handed over explicitly. It lasts 30 days.
  There is no headless sign-in for a person.
* **An app** signs in as itself — `client_credentials` with a
  `private_key_jwt` assertion signed with its own key, whose public half
  an org admin registered on igni server. Its tokens last ten minutes and
  are renewed a minute before they run out.
* **A space** is one end user of an app. The app declares it, then
  exchanges its own token for the space's.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel, ConfigDict, ValidationError

from igni_client.errors import AuthError, NotAllowed, Unavailable

ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"  # noqa: S105 — an RFC 8693 grant type, not a token
ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"  # noqa: S105 — an RFC 8693 URN, not a token

#: The only signing algorithm on this wire.
ALGORITHM = "RS256"


class TokenSource(Protocol):
    """Anything a target can ask for a bearer token."""

    async def token(self) -> str: ...


# ── A person ─────────────────────────────────────────────────────────


class Person:
    """A person, by their igni session.

    The token must be pinned to an organisation — the session `igni login`
    stores is. A plain sign-in session without one is refused by Fleet.
    """

    def __init__(self, token: str) -> None:
        token = token.strip()
        if not token:
            raise AuthError("a person needs a session token")
        self._token = token

    @classmethod
    def from_api_key(
        cls,
        key: str | None = None,
        *,
        server: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> ApiKey:
        """A person by their API key — the way to give a program their access.

        Make the key on the portal (*API keys*). `key` defaults to
        `IGNI_API_KEY` and `server` — igni server's address — to
        `IGNI_SERVER_URL`. Each connection gets a fresh 15-minute session as
        the person; see `ApiKey`.
        """
        key = key or os.environ.get("IGNI_API_KEY", "")
        server = server or os.environ.get("IGNI_SERVER_URL", "")
        if not key:
            raise AuthError("no API key: pass one, or set IGNI_API_KEY")
        if not server:
            raise AuthError("where is igni server? pass server=, or set IGNI_SERVER_URL")
        return ApiKey(key, server=server, http=http)

    @classmethod
    def from_cli(cls, path: str | Path | None = None) -> Person:
        """The session `igni login` stored: `~/.igni/credentials.json`, or the file at `path`.

        Raises `AuthError` when there is none or it has expired — run
        `igni login` again. For a program, prefer an API key
        (`from_api_key`): it needs no browser.
        """
        candidates = [
            Path(path).expanduser()
            if path is not None
            else Path("~/.igni/credentials.json").expanduser()
        ]
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                stored = _StoredCredentials.model_validate_json(candidate.read_text())
            except (OSError, ValidationError) as exc:
                raise AuthError(f"{candidate} is not an igni credentials file") from exc
            if stored.expired():
                raise AuthError(f"the session in {candidate} has expired; run `igni login`")
            return cls(stored.access_token)
        raise AuthError("no igni session on this machine; run `igni login`")

    async def token(self) -> str:
        return self._token


class ApiKey:
    """A person's API key, exchanged for short sessions as them.

    The key comes from the portal (*API keys*). igni server exchanges it for
    a 15-minute session as the person, pinned to the key's organisation —
    every igni server route and Fleet's gateway take it. The session is
    renewed a minute before it runs out. It can do what the person can,
    except make more credentials. A revoked or expired key raises
    `AuthError`.
    """

    API_KEY_GRANT = "urn:igni:params:oauth:grant-type:api-key"
    RENEW_BEFORE = 60

    def __init__(
        self,
        key: str,
        *,
        server: str,
        http: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not key.strip().startswith("igpak1."):
            raise AuthError("not an igni API key (they start with 'igpak1.')")
        self._key = key.strip()
        self.server = server.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http is None
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        async with self._lock:
            if self._token is not None and self._clock() < self._expires_at:
                return self._token
            try:
                response = await self._http.post(
                    f"{self.server}/v1/oauth/token",
                    data={"grant_type": self.API_KEY_GRANT, "api_key": self._key},
                )
            except httpx.HTTPError as exc:
                raise Unavailable(
                    f"could not reach igni server for the key's session: {exc}"
                ) from exc
            if response.status_code in (400, 401, 403):
                try:
                    reason = str(response.json().get("error_description") or response.text)
                except ValueError:
                    reason = response.text
                raise AuthError(f"igni server refused the API key: {reason}")
            if response.status_code != 200:
                raise Unavailable(
                    f"igni server answered the key's exchange with {response.status_code}"
                )
            try:
                issued = _IssuedToken.model_validate(response.json())
            except (ValidationError, ValueError) as exc:
                raise Unavailable(
                    "igni server answered the key's exchange with something else"
                ) from exc
            self._token = issued.access_token
            self._expires_at = self._clock() + max(0, issued.expires_in - self.RENEW_BEFORE)
            return self._token

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    def __repr__(self) -> str:
        return f"ApiKey(server={self.server!r})"  # never the key


class _StoredCredentials(BaseModel):
    """`~/.igni/credentials.json`, as igni's CLI writes it."""

    model_config = ConfigDict(extra="ignore")

    access_token: str
    expires_at: str = ""

    def expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return datetime.now(UTC) >= expires


# ── An app ───────────────────────────────────────────────────────────


class _IssuedToken(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
    expires_in: int = 600


class SpaceRecord(BaseModel):
    """One space of an app, as igni server keeps it."""

    model_config = ConfigDict(extra="allow")

    space_id: str
    app_id: str = ""
    org_id: str = ""
    external_id: str = ""
    created_at: str = ""


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


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
        if (key_file is None) == (key_pem is None):
            raise ValueError("give the app's key as exactly one of key_file= or key_pem=")
        pem = Path(key_file).expanduser().read_text() if key_file is not None else key_pem
        assert pem is not None
        loaded = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(loaded, rsa.RSAPrivateKey):
            raise ValueError("an app's key must be an RSA private key")
        self.app_id = app_id
        self.server = server.rstrip("/")
        self._key = loaded
        self._http = http or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http is None
        self._clock = clock
        self._issuer: str | None = None
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    @staticmethod
    def generate_key(path: str | Path) -> Path:
        """Make a new RSA key for an app and write it to `path`, readable by its owner only."""
        target = Path(path).expanduser()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(pem)
        return target

    def thumbprint(self) -> str:
        """The key's RFC 7638 thumbprint: its `kid`, and what an admin compares."""
        numbers = self._key.public_key().public_numbers()
        members = {"e": _b64url_uint(numbers.e), "kty": "RSA", "n": _b64url_uint(numbers.n)}
        canonical = json.dumps(members, separators=(",", ":"), sort_keys=True).encode()
        return base64.urlsafe_b64encode(hashlib.sha256(canonical).digest()).rstrip(b"=").decode()

    def public_jwks(self) -> dict[str, Any]:
        """The public key as a JWK set: what an org admin registers for this app."""
        numbers = self._key.public_key().public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": ALGORITHM,
                    "kid": self.thumbprint(),
                    "n": _b64url_uint(numbers.n),
                    "e": _b64url_uint(numbers.e),
                }
            ]
        }

    async def token(self) -> str:
        """The app's own token (`token_use=app`), renewed shortly before it runs out."""
        async with self._lock:
            if self._token is not None and self._clock() < self._expires_at:
                return self._token
            issued = await self._grant(
                {
                    "grant_type": "client_credentials",
                    "client_assertion_type": ASSERTION_TYPE,
                    "client_assertion": await self._assertion(),
                },
                what="the app's token",
            )
            self._token = issued.access_token
            self._expires_at = self._clock() + max(0, issued.expires_in - self.RENEW_BEFORE)
            return self._token

    @property
    def spaces(self) -> Spaces:
        """This app's spaces: its end users, each a producer with an igni of its own."""
        return Spaces(self)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> App:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ── igni server ──

    async def _assertion(self) -> str:
        now = int(self._clock())
        return jwt.encode(
            {
                "iss": self.app_id,
                "sub": self.app_id,
                "aud": await self._issuer_url(),
                "iat": now,
                "exp": now + self.ASSERTION_LIFETIME,
                "jti": uuid.uuid4().hex,
            },
            self._key,
            algorithm=ALGORITHM,
            headers={"kid": self.thumbprint()},
        )

    async def _issuer_url(self) -> str:
        if self._issuer is None:
            response = await self._call(
                "GET", "/.well-known/openid-configuration", what="discovery"
            )
            issuer = response.json().get("issuer") if response.status_code == 200 else None
            if not isinstance(issuer, str) or not issuer:
                raise Unavailable("igni server published no issuer")
            self._issuer = issuer
        return self._issuer

    async def _grant(self, form: dict[str, str], *, what: str) -> _IssuedToken:
        response = await self._call("POST", "/v1/oauth/token", what=what, data=form)
        if response.status_code in (400, 401, 403):
            raise AuthError(f"igni server refused {what}: {response.text}")
        if response.status_code != 200:
            raise Unavailable(f"igni server answered {what} with {response.status_code}")
        try:
            return _IssuedToken.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise Unavailable(f"igni server answered {what} with something else") from exc

    async def _call(self, method: str, path: str, *, what: str, **kwargs: Any) -> httpx.Response:
        try:
            return await self._http.request(method, f"{self.server}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise Unavailable(f"could not reach igni server for {what}: {exc}") from exc

    async def _authorized(
        self, method: str, path: str, *, what: str, **kwargs: Any
    ) -> httpx.Response:
        """A call to igni server as this app, retried once with a fresh token on a 401."""
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {await self.token()}"}
            response = await self._call(method, path, what=what, headers=headers, **kwargs)
            if response.status_code != 401 or attempt:
                return response
            async with self._lock:
                self._token = None
        return response


# ── An app's spaces ──────────────────────────────────────────────────


class Spaces:
    """The spaces of one app: declare, look up, list and delete them, and act as one."""

    def __init__(self, app: App) -> None:
        self._app = app

    def _path(self, external_id: str = "") -> str:
        base = f"/v1/apps/{quote(self._app.app_id, safe='')}/spaces"
        return f"{base}/{quote(external_id, safe='')}" if external_id else base

    async def declare(self, external_id: str) -> Space:
        """The space for `external_id` (your own id for the user), made if it is new.

        Idempotent: declaring the same id again returns the same space.
        igni provisions its VM in the background.
        """
        if not external_id or "/" in external_id or len(external_id) > 200:
            raise ValueError("a space's external id is 1 to 200 characters, without '/'")
        response = await self._app._authorized(
            "PUT", self._path(external_id), what="declaring a space"
        )
        return self._space(self._record(response, what="declaring a space"))

    async def get(self, external_id: str) -> Space | None:
        """The space for `external_id`, or `None` when the app has none."""
        response = await self._app._authorized(
            "GET", self._path(external_id), what="reading a space"
        )
        if response.status_code == 404:
            return None
        return self._space(self._record(response, what="reading a space"))

    async def list(self, *, limit: int = 100) -> list[SpaceRecord]:
        """Every space of this app."""
        found: list[SpaceRecord] = []
        after: str | None = None
        while True:
            params: dict[str, str | int] = {"limit": limit}
            if after:
                params["after"] = after
            response = await self._app._authorized(
                "GET", self._path(), what="listing spaces", params=params
            )
            body = self._body(response, what="listing spaces")
            found.extend(SpaceRecord.model_validate(s) for s in body.get("spaces") or [])
            after = body.get("next")
            if not after:
                return found

    async def delete(self, external_id: str) -> None:
        """Delete a space: its credential stops working and its VM is erased."""
        response = await self._app._authorized(
            "DELETE", self._path(external_id), what="deleting a space"
        )
        if response.status_code not in (204, 404):
            self._body(response, what="deleting a space")

    def space(self, space_id: str) -> Space:
        """Act as a space you already know the id of."""
        return Space(self._app, space_id)

    def _space(self, record: SpaceRecord) -> Space:
        return Space(self._app, record.space_id, record=record)

    def _record(self, response: httpx.Response, *, what: str) -> SpaceRecord:
        return SpaceRecord.model_validate(self._body(response, what=what))

    @staticmethod
    def _body(response: httpx.Response, *, what: str) -> dict[str, Any]:
        if response.status_code == 403:
            raise NotAllowed(f"igni server refused {what}: {response.text}")
        if response.status_code in (400, 409):
            raise NotAllowed(f"igni server refused {what}: {response.text}")
        if response.status_code >= 300:
            raise Unavailable(f"igni server answered {what} with {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise Unavailable(f"igni server answered {what} with something else") from exc
        if not isinstance(body, dict):
            raise Unavailable(f"igni server answered {what} with something else")
        return body


class Space:
    """One space of an app, as a token source: the app's token exchanged for the space's."""

    def __init__(self, app: App, space_id: str, *, record: SpaceRecord | None = None) -> None:
        if not space_id:
            raise ValueError("a space needs its space id")
        self.app = app
        self.space_id = space_id
        self.record = record
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def external_id(self) -> str:
        return self.record.external_id if self.record else ""

    async def token(self) -> str:
        """The space's token (`token_use=space`), renewed shortly before it runs out."""
        async with self._lock:
            if self._token is not None and self.app._clock() < self._expires_at:
                return self._token
            issued = await self.app._grant(
                {
                    "grant_type": TOKEN_EXCHANGE,
                    "subject_token": await self.app.token(),
                    "subject_token_type": ACCESS_TOKEN_TYPE,
                    "space": self.space_id,
                },
                what="the space's token",
            )
            self._token = issued.access_token
            self._expires_at = self.app._clock() + max(0, issued.expires_in - App.RENEW_BEFORE)
            return self._token

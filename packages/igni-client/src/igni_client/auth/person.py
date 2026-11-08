"""A person: by the session `igni login` keeps, a session handed over, or an API key."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from igni_client.auth.grants import API_KEY_GRANT, ApiKeyGrant
from igni_client.auth.server import IgniServer
from igni_client.auth.tokens import IssuedToken, TokenCache
from igni_client.errors import AuthError, Unavailable

CLI_CREDENTIALS = Path("~/.igni/credentials.json")


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
        stored_at = Path(path if path is not None else CLI_CREDENTIALS).expanduser()
        if not stored_at.is_file():
            raise AuthError("no igni session on this machine; run `igni login`")
        try:
            stored = StoredCredentials.model_validate_json(stored_at.read_text())
        except (OSError, ValidationError) as exc:
            raise AuthError(f"{stored_at} is not an igni credentials file") from exc
        if stored.expired():
            raise AuthError(f"the session in {stored_at} has expired; run `igni login`")
        return cls(stored.access_token)

    async def token(self) -> str:
        return self._token


class StoredCredentials(BaseModel):
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


class ApiKey:
    """A person's API key, exchanged for short sessions as them.

    The key comes from the portal (*API keys*). igni server exchanges it for
    a 15-minute session as the person, pinned to the key's organisation —
    every igni server route and Fleet's gateway take it. The session is
    renewed a minute before it runs out. It can do what the person can,
    except make more credentials. A revoked or expired key raises
    `AuthError`.
    """

    API_KEY_GRANT = API_KEY_GRANT
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
        self._grant = ApiKeyGrant(api_key=key.strip())
        self._server = IgniServer(server, http=http)
        self._tokens = TokenCache(clock, renew_before=self.RENEW_BEFORE)

    @property
    def server(self) -> str:
        """igni server's address; assignable, as it was a plain attribute in 0.1.0."""
        return self._server.url

    @server.setter
    def server(self, url: str) -> None:
        self._server.url = url

    async def token(self) -> str:
        return await self._tokens.get(self._session)

    async def _session(self) -> IssuedToken:
        """A new session for the key; refused in igni server's own words."""
        response = await self._server.call(
            "POST", "/v1/oauth/token", what="the key's session", form=self._grant.form()
        )
        if response.status_code in (400, 401, 403):
            raise AuthError(f"igni server refused the API key: {IgniServer.reason(response)}")
        if response.status_code != 200:
            raise Unavailable(
                f"igni server answered the key's exchange with {response.status_code}"
            )
        try:
            return IssuedToken.model_validate_json(response.content)
        except ValidationError as exc:
            raise Unavailable(
                "igni server answered the key's exchange with something else"
            ) from exc

    async def aclose(self) -> None:
        await self._server.aclose()

    def __repr__(self) -> str:
        return f"ApiKey(server={self.server!r})"  # never the key

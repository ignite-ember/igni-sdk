"""igni server, as the client's auth reaches it: discovery and the token endpoint."""

from __future__ import annotations

from collections.abc import Mapping

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from igni_client.auth.grants import Grant
from igni_client.auth.tokens import IssuedToken
from igni_client.errors import AuthError, Unavailable


class _Discovery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    issuer: str


class _OAuthError(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error_description: str = ""


class IgniServer:
    """igni server's address and the HTTP client that reaches it."""

    def __init__(self, url: str, *, http: httpx.AsyncClient | None = None) -> None:
        self.url = url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http is None
        self._issuer: str | None = None

    async def call(
        self,
        method: str,
        path: str,
        *,
        what: str,
        bearer: str | None = None,
        form: Mapping[str, str] | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> httpx.Response:
        """One request; `Unavailable` when igni server cannot be reached."""
        headers = {"Authorization": f"Bearer {bearer}"} if bearer is not None else None
        try:
            return await self._http.request(
                method, f"{self.url}{path}", headers=headers, data=form, params=params
            )
        except httpx.HTTPError as exc:
            raise Unavailable(f"could not reach igni server for {what}: {exc}") from exc

    async def grant(self, grant: Grant, *, what: str) -> IssuedToken:
        """A token for `grant`; `AuthError`, with igni server's whole answer, when it refuses it."""
        response = await self.call("POST", "/v1/oauth/token", what=what, form=grant.form())
        if response.status_code in (400, 401, 403):
            raise AuthError(f"igni server refused {what}: {response.text}")
        if response.status_code != 200:
            raise Unavailable(f"igni server answered {what} with {response.status_code}")
        try:
            return IssuedToken.model_validate_json(response.content)
        except ValidationError as exc:
            raise Unavailable(f"igni server answered {what} with something else") from exc

    async def issuer(self) -> str:
        """igni server's issuer URL, from its discovery document; asked once."""
        if self._issuer is None:
            response = await self.call("GET", "/.well-known/openid-configuration", what="discovery")
            try:
                issuer = (
                    _Discovery.model_validate_json(response.content).issuer
                    if response.status_code == 200
                    else ""
                )
            except ValidationError:
                issuer = ""
            if not issuer:
                raise Unavailable("igni server published no issuer")
            self._issuer = issuer
        return self._issuer

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    @staticmethod
    def reason(response: httpx.Response) -> str:
        """Why igni server refused: its `error_description`, or else its whole answer."""
        try:
            return _OAuthError.model_validate_json(response.content).error_description or (
                response.text
            )
        except ValidationError:
            return response.text

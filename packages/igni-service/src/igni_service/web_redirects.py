"""Where the web sign-in sends a browser: to igni's portal, and back here.

`AuthorizationRequest` is the link to igni's authorization endpoint,
with the PKCE challenge (`Pkce`, S256 only) it carries; `ReturnTo` keeps
the address a person comes back to on this service; `SignInRequired`
sends a page nobody is signed in to off to sign in.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Literal
from urllib.parse import quote, urlencode, urlsplit

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, ConfigDict


class Pkce:
    """RFC 7636, S256 only."""

    @staticmethod
    def verifier() -> str:
        return secrets.token_urlsafe(64)

    @staticmethod
    def challenge(verifier: str) -> str:
        """The S256 challenge for `verifier`: what the sign-in sends igni.

        Args:
            verifier: The PKCE code verifier the sign-in keeps; its SHA-256
                digest, in base64url, is the challenge sent with it.
        """
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class ReturnTo:
    """Where to send the browser afterwards: a path on this service, nothing else."""

    @staticmethod
    def safe(value: str | None) -> str:
        """Where to send the browser afterwards: a path on this service, nothing else.

        Args:
            value: The path asked for; anything that is not a path on this
                service becomes ``/``.
        """
        candidate = (value or "").strip()
        parts = urlsplit(candidate)
        if (
            not candidate.startswith("/")
            or candidate.startswith("//")
            or "\\" in candidate
            or parts.scheme
            or parts.netloc
            or any(ord(ch) < 0x20 for ch in candidate)
        ):
            return "/"
        return candidate


class AuthorizationRequest(BaseModel):
    """The query a sign-in sends the browser to igni's authorization endpoint with."""

    model_config = ConfigDict(frozen=True)

    response_type: Literal["code"] = "code"
    client_id: str
    redirect_uri: str
    state: str
    code_challenge: str
    code_challenge_method: Literal["S256"] = "S256"

    @classmethod
    def for_verifier(
        cls, *, client_id: str, redirect_uri: str, state: str, verifier: str
    ) -> AuthorizationRequest:
        """The request for a sign-in that keeps `verifier`, sending its S256 challenge."""
        return cls(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=Pkce.challenge(verifier),
        )

    def url(self, endpoint: str) -> str:
        """This request on `endpoint`, after any query the endpoint already has."""
        separator = "&" if "?" in endpoint else "?"
        return f"{endpoint}{separator}{urlencode(self.model_dump())}"


class SignInRequired(HTTPException):
    """Nobody signed in where a dependency requires somebody.

    FastAPI ends a dependency with a response only by raising, so this is
    how `WebSignIn.person` answers: a page (a request that accepts HTML)
    is sent to sign in with a 303 and brought back; anything else is
    answered 401.
    """

    def __init__(self, request: Request, login_path: str) -> None:
        if "text/html" in request.headers.get("accept", ""):
            url = request.url
            target = url.path + (f"?{url.query}" if url.query else "")
            super().__init__(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": f"{login_path}?return_to={quote(target, safe='')}"},
            )
        else:
            super().__init__(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not signed in",
                headers={"WWW-Authenticate": "Bearer"},
            )

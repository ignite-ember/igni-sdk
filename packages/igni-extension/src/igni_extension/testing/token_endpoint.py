"""The host's loopback token endpoint, for an extension's tests.

host = FakeHostTokenEndpoint()
ext = IgniExtension("acme.example", environ=host.environment(),
                    token_transport=host.transport, service_transport=my_fake_service)
"""

from __future__ import annotations

import base64
import secrets
from collections.abc import Callable

import httpx
from pydantic import BaseModel

from igni_extension.caller import Caller, CallerKind


class TokenClaims(BaseModel):
    """What the fake host's tokens say: enough for `ext.tokens.signed_in`."""

    sub: str
    org: str
    email: str = ""
    name: str = ""
    aud: str
    token_use: str = "user"  # noqa: S105 — a claim's value, not a secret
    jti: str


#: Makes the token a fake host hands out for one person — see
#: `FakeHostTokenEndpoint(minter=...)`.
Minter = Callable[[TokenClaims], str]


class FakeHostTokenEndpoint:
    """The host's token endpoint for one extension process (service identity §9).

    Hands out tokens for whoever is signed in (`sign_in`, `sign_out`). By
    default a token is an unsigned JWT carrying the person's claims — enough
    for `ext.tokens.signed_in`, and refused by a real service. To test
    against a service that checks signatures (`igni_service.testing.FakeIgni`),
    pass `minter`: it is given the person's `TokenClaims` (`sub`, `org`,
    `email`, `name`, `aud` — the service URL — and a fresh `jti`) and
    returns the token to hand out:

        igni = FakeIgni(...)
        host = FakeHostTokenEndpoint(
            minter=lambda claims: igni.signer.person_token(claims.sub, org_id=claims.org)
        )
    """

    TOKEN_URL = "http://127.0.0.1:47011/igni/service-token"  # noqa: S105 — a loopback URL for tests, not a secret
    SERVICE_URL = "http://service.test"

    def __init__(
        self,
        *,
        service_url: str = SERVICE_URL,
        expires_in: float = 600,
        user_id: str = "u-ada",
        org_id: str = "org-acme",
        email: str = "ada@acme.test",
        name: str = "Ada",
        minter: Minter | None = None,
    ) -> None:
        self.service_url = service_url
        self.minter: Minter = minter or self.unsigned
        self.secret = secrets.token_urlsafe(24)
        self.expires_in = expires_in
        self.person: TokenClaims | None = None
        self.sign_in(user_id=user_id, org_id=org_id, email=email, name=name)
        #: Every token handed out, in order.
        self.issued: list[str] = []
        #: Every request, including refused ones.
        self.requests: list[httpx.Request] = []

    def environment(self, **extra: str) -> dict[str, str]:
        """The variables igni starts the process with, for its service."""
        return {
            "IGNI_SERVICE_URL": self.service_url,
            "IGNI_SERVICE_TOKEN_URL": self.TOKEN_URL,
            "IGNI_SERVICE_TOKEN_SECRET": self.secret,
            **extra,
        }

    def sign_in(self, *, user_id: str, org_id: str, email: str = "", name: str = "") -> None:
        self.person = TokenClaims(
            sub=user_id, org=org_id, email=email, name=name, aud=self.service_url, jti=""
        )

    def sign_out(self) -> None:
        self.person = None

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method != "GET" or str(request.url) != self.TOKEN_URL:
            return httpx.Response(404)
        if request.headers.get("authorization") != f"Bearer {self.secret}":
            return httpx.Response(401, json={"detail": "wrong secret"})
        if self.person is None:
            return httpx.Response(503, json={"detail": "nobody is signed in to igni"})
        named = request.headers.get(Caller.TOKEN_HEADER.lower(), "")
        if named and named != f"{CallerKind.PERSON.value}:{self.person.sub}":
            # As igni: a backend serving one person hands out that person's
            # token, and nobody else's.
            return httpx.Response(403, json={"error": f"not the signed-in person: {named}"})
        token = self.minter(self.person.model_copy(update={"jti": secrets.token_hex(8)}))
        self.issued.append(token)
        return httpx.Response(
            200,
            json={
                "access_token": token,
                "expires_in": self.expires_in,
                "service_url": self.service_url,
            },
        )

    @staticmethod
    def unsigned(claims: TokenClaims) -> str:
        """The default token: an unsigned JWT of `claims`."""

        def part(value: bytes) -> str:
            return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

        header = part(b'{"alg":"RS256","typ":"JWT"}')
        return f"{header}.{part(claims.model_dump_json().encode())}.{part(b'not-checked-here')}"

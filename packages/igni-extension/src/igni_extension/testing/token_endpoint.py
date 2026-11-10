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
from pydantic import BaseModel, ConfigDict

from igni_extension.caller import Caller, CallerKind


class TokenClaims(BaseModel):
    """What the fake host's tokens say: enough for `ext.tokens.signed_in`."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    sub: str
    """The person's user id."""
    org: str
    """Their organisation."""
    email: str = ""
    """Their email address."""
    name: str = ""
    """Their name."""
    aud: str
    """The service's URL: whom the token is for."""
    token_use: str = "user"  # noqa: S105 — a claim's value, not a secret
    """Always `user`: a person's token."""
    jti: str
    """The token's own id, fresh for each one handed out."""


Minter = Callable[[TokenClaims], str]
"""Makes the token a fake host hands out for one person — see
`FakeHostTokenEndpoint(minter=...)`.
"""


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

    Args:
        service_url: The service's URL, as the token's audience and `IGNI_SERVICE_URL`.
        expires_in: The lifetime it says each token has, in seconds.
        user_id: The person signed in to begin with: `u-ada`.
        org_id: The organisation that person belongs to: `org-acme`.
        email: That person's email address: `ada@acme.test`.
        name: That person's name: `Ada`.
        minter: What makes each token; `unsigned` when none is given.
    """

    TOKEN_URL = "http://127.0.0.1:47011/igni/service-token"  # noqa: S105 — a loopback URL for tests, not a secret
    """The endpoint's address, as `IGNI_SERVICE_TOKEN_URL` names it."""
    SERVICE_URL = "http://service.test"
    """The service's URL unless another is given."""

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
        """The service's URL: `IGNI_SERVICE_URL`, and every token's audience."""
        self.minter: Minter = minter or self.unsigned
        """What makes each token: `unsigned` unless one was given."""
        self.secret = secrets.token_urlsafe(24)
        """The secret the process presents: `IGNI_SERVICE_TOKEN_SECRET` in `environment()`."""
        self.expires_in = expires_in
        """The lifetime it says each token has, in seconds."""
        self.person: TokenClaims | None = None
        """Who is signed in; `None` after `sign_out`, when every request is answered 503."""
        self.sign_in(user_id=user_id, org_id=org_id, email=email, name=name)
        self.issued: list[str] = []
        """Every token handed out, in order."""
        self.requests: list[httpx.Request] = []
        """Every request, including refused ones."""

    def environment(self, **extra: str) -> dict[str, str]:
        """The variables igni starts the process with, for its service.

        Args:
            extra: More variables to hand the process, as igni set them: `IGNI_EXTENSION_DATA`.
        """
        return {
            "IGNI_SERVICE_URL": self.service_url,
            "IGNI_SERVICE_TOKEN_URL": self.TOKEN_URL,
            "IGNI_SERVICE_TOKEN_SECRET": self.secret,
            **extra,
        }

    def sign_in(self, *, user_id: str, org_id: str, email: str = "", name: str = "") -> None:
        """Play somebody signing in to igni: tokens are theirs from now on.

        Args:
            user_id: The person's igni user id: `u-ada`.
            org_id: The organisation the person belongs to: `org-acme`.
            email: The person's email address: `ada@acme.test`.
            name: The person's name: `Ada`.
        """
        self.person = TokenClaims(
            sub=user_id, org=org_id, email=email, name=name, aud=self.service_url, jti=""
        )

    def sign_out(self) -> None:
        """Play the person signing out: token requests are refused until `sign_in`."""
        self.person = None

    @property
    def transport(self) -> httpx.MockTransport:
        """An `httpx` transport answering as the endpoint: pass it as
        `IgniExtension(token_transport=...)`.
        """
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Answer one request as the host's token endpoint does.

        Args:
            request: The request the extension made to the token endpoint.
        """
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
        """The default token: an unsigned JWT of `claims`.

        Args:
            claims: What the token says: who it is for, and which service it is for.
        """

        def part(value: bytes) -> str:
            return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

        header = part(b'{"alg":"RS256","typ":"JWT"}')
        return f"{header}.{part(claims.model_dump_json().encode())}.{part(b'not-checked-here')}"

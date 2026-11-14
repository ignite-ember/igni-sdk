"""The fake's side of the HTTP boundary: where it is, what it was sent, how it answers.

`IgniAddresses` is where the fake is reached, its issuer and the service
under test's URL. `SeenRequest` is one request as the fake recorded it,
read as the typed bodies igni reads (`form()` is a `TokenForm`);
`DetailError` and `OAuthError` are the two error bodies igni answers
with. `RecordedTraffic` keeps every request and the failures a test
asked for (`fail`, `heal`).
"""

from __future__ import annotations

import json
from typing import Any, TypeVar
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from igni_service.server import Discovery
from igni_service.testing_bearers import TokenHolder
from igni_service.token_endpoint import ASSERTION_TYPE
from igni_service.urls import IgniPaths, ServiceUrl

BASE = "http://igni.test"
"""Where the service reaches the fake."""
ISSUER = "https://igni.example.test"
"""Its issuer: its public URL, deliberately not `BASE`."""
SERVICE_URL = "http://service.test"
"""The service under test's own URL."""

Body = TypeVar("Body", bound=BaseModel)


class FakeDiscovery(Discovery):
    """igni's metadata as the fake publishes it: every endpoint under its issuer."""

    jwks_uri: str
    """Where igni's public keys are."""
    token_endpoint: str
    """Where tokens are asked for."""
    revocation_endpoint: str
    """Where a sign-in is ended."""


class IgniAddresses(BaseModel):
    """Where the fake is reached, what it calls itself, and the service it signs for."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    base_url: str = BASE
    """Where the fake is reached: `http://igni.test`."""
    issuer: str = ISSUER
    """The issuer its tokens name, which is not where it is reached: `https://igni.example.test`."""
    service_url: str = SERVICE_URL
    """The service's URL its tokens are for: `http://service.test`."""

    @field_validator("base_url", "issuer")
    @classmethod
    def _no_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("service_url")
    @classmethod
    def _as_igni_writes_it(cls, value: str) -> str:
        return ServiceUrl.normalise(value)

    @property
    def authorization_endpoint(self) -> str:
        """The portal's `/authorize`, as igni's metadata publishes it."""
        return f"{self.issuer}/authorize"

    def reaches(self, url: str) -> bool:
        """Whether `url` is on the fake's own address.

        Args:
            url: The URL to test: its scheme and host are compared with the
                fake's own address, and its path is not looked at.
        """
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}" == self.base_url

    def assertion_audiences(self) -> list[str]:
        """Every `aud` a client assertion may carry."""
        return [self.issuer, f"{self.issuer}{IgniPaths.TOKEN}", f"{self.issuer}{IgniPaths.REVOKE}"]

    def discovery(self) -> FakeDiscovery:
        """The OpenID Connect discovery document these addresses make."""
        return FakeDiscovery(
            issuer=self.issuer,
            jwks_uri=f"{self.issuer}{IgniPaths.JWKS}",
            token_endpoint=f"{self.issuer}{IgniPaths.TOKEN}",
            revocation_endpoint=f"{self.issuer}{IgniPaths.REVOKE}",
            authorization_endpoint=self.authorization_endpoint,
        )


class DetailError(BaseModel):
    """`{"detail": ...}`, igni's error body everywhere but OAuth."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    detail: str
    """igni's words: why."""
    status: int = Field(default=400, exclude=True)
    """The HTTP status it is answered with; not part of the body."""

    @classmethod
    def not_found(cls) -> DetailError:
        """igni's 404 for a path or a method nothing serves."""
        return cls(detail="Not Found", status=404)

    @classmethod
    def not_authenticated(cls) -> DetailError:
        """igni's 401 for a missing, unknown or revoked bearer token."""
        return cls(detail="Not authenticated", status=401)

    def to_response(self) -> httpx.Response:
        """The error as igni answers it."""
        return httpx.Response(self.status, json=self.model_dump())


class OAuthError(BaseModel):
    """`{"error": ..., "error_description": ...}`, RFC 6749 §5.2's error body."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    error: str
    """RFC 6749's error code: `invalid_client`, `invalid_grant`, ..."""
    error_description: str | None = None
    """igni's words for why; left out of the body when none."""
    client_state: str | None = None
    """igni's own field beside `invalid_client`: the state of the client's
    registration when that is why it was refused (`token_endpoint.OAuthRefusal`).
    """
    status: int = Field(default=400, exclude=True)
    """The HTTP status it is answered with; not part of the body."""

    def to_response(self) -> httpx.Response:
        """The error as igni answers it: what it does not say is left out."""
        return httpx.Response(self.status, json=self.model_dump(exclude_none=True))


class TokenForm(BaseModel):
    """A form posted to the token or the revocation endpoint, as igni reads it."""

    model_config = ConfigDict(extra="ignore", use_attribute_docstrings=True)

    grant_type: str = ""
    """`client_credentials`, `authorization_code` or `refresh_token`."""
    client_assertion_type: str = ""
    """How the client authenticates: the JWT bearer assertion type."""
    client_assertion: str = ""
    """The client's signed assertion."""
    organisation: str = ""
    """The organisation a service token is asked for."""
    scope: str = ""
    """The scope asked for, if any."""
    code: str = ""
    """The authorization code a sign-in brought back."""
    redirect_uri: str = ""
    """The callback address the code was issued for."""
    code_verifier: str = ""
    """The PKCE verifier for `code`."""
    refresh_token: str = ""
    """The refresh token a renewal presents."""
    token: str = ""
    """The token a revocation names."""
    token_type_hint: str = ""
    """What kind of token `token` is: `refresh_token`."""

    @property
    def is_jwt_bearer(self) -> bool:
        """Whether the client authenticates with a `private_key_jwt` assertion."""
        return self.client_assertion_type == ASSERTION_TYPE


class SeenRequest(BaseModel):
    """One request the fake was sent."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    method: str
    """The HTTP method."""
    path: str
    """The path, without the query."""
    headers: dict[str, str]
    """The headers, names lower-cased."""
    body: bytes
    """The body's bytes."""
    query: dict[str, list[str]] = Field(default_factory=dict)
    """The query string, parsed: each name to its values."""

    @classmethod
    def of(cls, request: httpx.Request) -> SeenRequest:
        """What `request` was, read whole.

        Args:
            request: The request the fake was sent: its method, path,
                headers, body and query are what is kept of it.
        """
        url = urlsplit(str(request.url))
        return cls(
            method=request.method,
            path=url.path,
            headers={k.lower(): v for k, v in request.headers.items()},
            body=request.read(),
            query=parse_qs(url.query),
        )

    def json_body(self) -> Any:
        """The body, read as JSON."""
        return json.loads(self.body)

    def json_model(self, model: type[Body]) -> Body | DetailError:
        """The body as `model`, or the 422 igni answers a body it cannot read with.

        Args:
            model: The model the body is read as: what the body is expected
                to hold.
        """
        try:
            return model.model_validate_json(self.body)
        except ValidationError as exc:
            return DetailError(detail=str(exc), status=422)

    def form(self) -> TokenForm:
        """The body, read as the form a token or revocation request posts.

        Bytes that are not text read as replacement characters: a form igni
        refuses as unauthenticated, not one that crashes the fake.
        """
        text = self.body.decode(errors="replace")
        return TokenForm.model_validate({k: v[0] for k, v in parse_qs(text).items()})

    def bearer(self) -> str:
        """The bearer token the request carries; empty without one."""
        return self.headers.get("authorization", "").removeprefix("Bearer ")

    def first(self, name: str, default: str = "") -> str:
        """The first value of query parameter `name`, or `default`.

        Args:
            name: The name of the query parameter to read.
            default: The value to answer with when the request carries no
                such parameter.
        """
        return (self.query.get(name) or [default])[0]


class RoutedCall(BaseModel):
    """A request routed to a handler, with whoever its bearer token stands for."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    seen: SeenRequest
    """The request, as the fake recorded it."""
    holder: TokenHolder = Field(default_factory=TokenHolder)
    """Empty on a route that needs no token."""


class RecordedTraffic:
    """Every request the fake was sent, and the paths a test made it fail."""

    def __init__(self) -> None:
        self.seen: list[SeenRequest] = []
        self.failing: dict[str, int] = {}
        """Path prefix → status to answer instead, to play igni failing."""

    def record(self, request: httpx.Request) -> SeenRequest:
        """Keep `request` as the fake was sent it, and read it as it was.

        Args:
            request: The request the fake was sent: its method, path,
                headers, body and query are what is kept of it.
        """
        seen = SeenRequest.of(request)
        self.seen.append(seen)
        return seen

    def failure_for(self, path: str) -> httpx.Response | None:
        """The failure a test asked for on `path`, if it asked for one.

        Args:
            path: The path of the request being answered: the first failing
                prefix that covers it decides the answer.
        """
        for prefix, status in self.failing.items():
            if path.startswith(prefix):
                return DetailError(detail="failing on purpose", status=status).to_response()
        return None

    def fail(self, prefix: str, status: int) -> None:
        """Answer every request under `prefix` with `status`, until `heal`.

        Args:
            prefix: The path prefix to fail: every request whose path starts
                with it is answered as told.
            status: The HTTP status to answer those requests with.
        """
        self.failing[prefix] = status

    def heal(self) -> None:
        """Stop failing every path `fail` was asked to."""
        self.failing.clear()

    def requests_to(self, path: str) -> list[SeenRequest]:
        """Every request the fake was sent to `path`.

        Args:
            path: The path to look for: only the requests made to exactly
                it are answered.
        """
        return [seen for seen in self.seen if seen.path == path]

    def reset(self) -> None:
        """Forget every request seen and every failure asked for."""
        self.seen.clear()
        self.failing.clear()


__all__ = [
    "BASE",
    "ISSUER",
    "SERVICE_URL",
    "DetailError",
    "FakeDiscovery",
    "IgniAddresses",
    "OAuthError",
    "RecordedTraffic",
    "RoutedCall",
    "SeenRequest",
    "TokenForm",
]

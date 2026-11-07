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

#: Where the service reaches the fake.
BASE = "http://igni.test"
#: Its issuer: its public URL, deliberately not `BASE`.
ISSUER = "https://igni.example.test"
#: The service under test's own URL.
SERVICE_URL = "http://service.test"

Body = TypeVar("Body", bound=BaseModel)


class FakeDiscovery(Discovery):
    """igni's metadata as the fake publishes it: every endpoint under its issuer."""

    jwks_uri: str
    token_endpoint: str
    revocation_endpoint: str


class IgniAddresses(BaseModel):
    """Where the fake is reached, what it calls itself, and the service it signs for."""

    model_config = ConfigDict(frozen=True)

    base_url: str = BASE
    issuer: str = ISSUER
    service_url: str = SERVICE_URL

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
        """Whether `url` is on the fake's own address."""
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}" == self.base_url

    def assertion_audiences(self) -> list[str]:
        """Every `aud` a client assertion may carry."""
        return [self.issuer, f"{self.issuer}{IgniPaths.TOKEN}", f"{self.issuer}{IgniPaths.REVOKE}"]

    def discovery(self) -> FakeDiscovery:
        return FakeDiscovery(
            issuer=self.issuer,
            jwks_uri=f"{self.issuer}{IgniPaths.JWKS}",
            token_endpoint=f"{self.issuer}{IgniPaths.TOKEN}",
            revocation_endpoint=f"{self.issuer}{IgniPaths.REVOKE}",
            authorization_endpoint=self.authorization_endpoint,
        )


class DetailError(BaseModel):
    """`{"detail": ...}`, igni's error body everywhere but OAuth."""

    detail: str
    status: int = Field(default=400, exclude=True)

    def to_response(self) -> httpx.Response:
        return httpx.Response(self.status, json=self.model_dump())


class OAuthError(BaseModel):
    """`{"error": ..., "error_description": ...}`, RFC 6749 §5.2's error body."""

    error: str
    error_description: str | None = None
    status: int = Field(default=400, exclude=True)

    def to_response(self) -> httpx.Response:
        return httpx.Response(self.status, json=self.model_dump(exclude_none=True))


class TokenForm(BaseModel):
    """A form posted to the token or the revocation endpoint, as igni reads it."""

    model_config = ConfigDict(extra="ignore")

    grant_type: str = ""
    client_assertion_type: str = ""
    client_assertion: str = ""
    organisation: str = ""
    scope: str = ""
    code: str = ""
    redirect_uri: str = ""
    code_verifier: str = ""
    refresh_token: str = ""
    token: str = ""
    token_type_hint: str = ""

    @property
    def is_jwt_bearer(self) -> bool:
        """Whether the client authenticates with a `private_key_jwt` assertion."""
        return self.client_assertion_type == ASSERTION_TYPE


class SeenRequest(BaseModel):
    """One request the fake was sent."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes
    query: dict[str, list[str]] = Field(default_factory=dict)

    @classmethod
    def of(cls, request: httpx.Request) -> SeenRequest:
        url = urlsplit(str(request.url))
        return cls(
            method=request.method,
            path=url.path,
            headers={k.lower(): v for k, v in request.headers.items()},
            body=request.read(),
            query=parse_qs(url.query),
        )

    def json_body(self) -> Any:
        return json.loads(self.body)

    def json_model(self, model: type[Body]) -> Body | DetailError:
        """The body as `model`, or the 422 igni answers a body it cannot read with."""
        try:
            return model.model_validate_json(self.body)
        except ValidationError as exc:
            return DetailError(detail=str(exc), status=422)

    def form(self) -> TokenForm:
        return TokenForm.model_validate({k: v[0] for k, v in parse_qs(self.body.decode()).items()})

    def bearer(self) -> str:
        """The bearer token the request carries; empty without one."""
        return self.headers.get("authorization", "").removeprefix("Bearer ")

    def first(self, name: str, default: str = "") -> str:
        """The first value of query parameter `name`, or `default`."""
        return (self.query.get(name) or [default])[0]


class RoutedCall(BaseModel):
    """A request routed to a handler, with whoever its bearer token stands for."""

    seen: SeenRequest
    #: Empty on a route that needs no token.
    holder: TokenHolder = Field(default_factory=TokenHolder)


class RecordedTraffic:
    """Every request the fake was sent, and the paths a test made it fail."""

    def __init__(self) -> None:
        self.seen: list[SeenRequest] = []
        #: Path prefix → status to answer instead, to play igni failing.
        self.failing: dict[str, int] = {}

    def record(self, request: httpx.Request) -> SeenRequest:
        seen = SeenRequest.of(request)
        self.seen.append(seen)
        return seen

    def failure_for(self, path: str) -> httpx.Response | None:
        """The failure a test asked for on `path`, if it asked for one."""
        for prefix, status in self.failing.items():
            if path.startswith(prefix):
                return DetailError(detail="failing on purpose", status=status).to_response()
        return None

    def fail(self, prefix: str, status: int) -> None:
        """Answer every request under `prefix` with `status`, until `heal`."""
        self.failing[prefix] = status

    def heal(self) -> None:
        self.failing.clear()

    def requests_to(self, path: str) -> list[SeenRequest]:
        return [seen for seen in self.seen if seen.path == path]

    def reset(self) -> None:
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

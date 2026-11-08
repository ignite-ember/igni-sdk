"""Signing in as a person, an app or a space, and running commands in a VM."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

import igni_client
from igni_client import (
    ApiKey,
    App,
    AuthError,
    IgniClient,
    NotAllowed,
    NotSupported,
    Person,
    Unavailable,
)
from igni_client.auth.grants import ACCESS_TOKEN_TYPE, ASSERTION_TYPE, TOKEN_EXCHANGE
from igni_client.auth.keys import JwkSet
from igni_client.commands.wire import ProducerRef
from igni_client.events import Unknown, parse_event
from igni_client.testing import FakeGateway, FakeIgni, PlayedCommand

ISSUER = "https://igni.example.test"


class IgniServer:
    """igni server's discovery, token endpoint and spaces, as an `httpx.MockTransport`."""

    def __init__(self, app: dict[str, Any] | None = None) -> None:
        self.jwks: JwkSet | None = None
        self.token_requests: list[dict[str, str]] = []
        self.spaces: dict[str, dict[str, Any]] = {}
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER})
        if path == "/v1/oauth/token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            if form["grant_type"] == "client_credentials":
                header = jwt.get_unverified_header(form["client_assertion"])
                key = jwt.PyJWK(self.jwks.keys[0].model_dump()) if self.jwks else None
                if key is None or header.get("kid") != key.key_id:
                    return httpx.Response(401, json={"error": "invalid_client"})
                # Signature, key and audience are checked; time is the test's own clock.
                claims = jwt.decode(
                    form["client_assertion"],
                    key.key,
                    algorithms=["RS256"],
                    audience=ISSUER,
                    options={"verify_exp": False, "verify_iat": False},
                )
                return httpx.Response(
                    200, json={"access_token": f"app:{claims['sub']}", "expires_in": 600}
                )
            if form["grant_type"].endswith("token-exchange"):
                return httpx.Response(
                    200, json={"access_token": f"space:{form['space']}", "expires_in": 600}
                )
        if path.startswith("/v1/apps/") and "/spaces" in path:
            if request.headers.get("Authorization") != "Bearer app:app-bot":
                return httpx.Response(401)
            external_id = path.rsplit("/", 1)[-1]
            if request.method == "PUT":
                record = self.spaces.setdefault(
                    external_id,
                    {
                        "space_id": f"sp-{len(self.spaces) + 1}",
                        "app_id": "app-bot",
                        "external_id": external_id,
                    },
                )
                return httpx.Response(201, json=record)
            if request.method == "DELETE":
                self.spaces.pop(external_id, None)
                return httpx.Response(204)
        return httpx.Response(404)


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    return App.generate_key(tmp_path / "app-key.pem")


def _app(key_file: Path, server: IgniServer, clock: Any = None) -> App:
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    kwargs: dict[str, Any] = {"server": "http://igni.test", "key_file": key_file, "http": http}
    if clock is not None:
        kwargs["clock"] = clock
    return App("app-bot", **kwargs)


async def test_an_app_signs_in_with_its_registered_key_and_keeps_the_token(key_file: Path) -> None:
    server = IgniServer()
    app = _app(key_file, server)
    server.jwks = app.public_jwks()

    first, second = await app.token(), await app.token()

    assert first == second == "app:app-bot"
    assert len(server.token_requests) == 1
    assert key_file.stat().st_mode & 0o777 == 0o600


async def test_an_app_renews_its_token_before_it_runs_out(key_file: Path) -> None:
    now = [1_000.0]
    server = IgniServer()
    app = _app(key_file, server, clock=lambda: now[0])
    server.jwks = app.public_jwks()

    await app.token()
    now[0] += 600 - App.RENEW_BEFORE + 1
    await app.token()

    assert len(server.token_requests) == 2


async def test_an_unregistered_key_is_an_auth_error(key_file: Path) -> None:
    app = _app(key_file, IgniServer())
    with pytest.raises(AuthError, match="refused"):
        await app.token()


async def test_a_space_is_declared_and_signed_in_by_exchanging_the_apps_token(
    key_file: Path,
) -> None:
    server = IgniServer()
    app = _app(key_file, server)
    server.jwks = app.public_jwks()

    space = await app.spaces.declare("customer-42")
    again = await app.spaces.declare("customer-42")
    token = await space.token()
    await app.spaces.delete("customer-42")

    assert space.space_id == again.space_id == "sp-1"
    assert space.external_id == "customer-42"
    assert token == "space:sp-1"
    exchange = server.token_requests[-1]
    assert exchange["subject_token"] == "app:app-bot" and exchange["space"] == "sp-1"
    assert "customer-42" not in server.spaces


async def test_a_space_id_with_a_slash_is_refused_before_asking(key_file: Path) -> None:
    app = _app(key_file, IgniServer())
    with pytest.raises(ValueError, match="without '/'"):
        await app.spaces.declare("a/b")


def _spaces_app(
    key_file: Path, spaces: Callable[[httpx.Request], httpx.Response]
) -> tuple[App, IgniServer]:
    """An app whose sign-in `IgniServer` plays and whose spaces routes `spaces` answers."""
    server = IgniServer()

    def route(request: httpx.Request) -> httpx.Response:
        if "/spaces" in request.url.path:
            server.calls.append(request)
            return spaces(request)
        return server(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(route))
    app = App("app-bot", server="http://igni.test", key_file=key_file, http=http)
    server.jwks = app.public_jwks()
    return app, server


async def test_spaces_are_listed_page_by_page(key_file: Path) -> None:
    pages = {
        "": {"spaces": [{"space_id": "sp-1", "external_id": "a"}], "next": "sp-1"},
        "sp-1": {"spaces": [{"space_id": "sp-2", "external_id": "b"}], "next": None},
    }
    asked: list[dict[str, str]] = []

    def spaces(request: httpx.Request) -> httpx.Response:
        asked.append(dict(request.url.params))
        return httpx.Response(200, json=pages[request.url.params.get("after", "")])

    app, _ = _spaces_app(key_file, spaces)
    listed = await app.spaces.list(limit=1)

    assert [(s.space_id, s.external_id) for s in listed] == [("sp-1", "a"), ("sp-2", "b")]
    assert asked == [{"limit": "1"}, {"limit": "1", "after": "sp-1"}]


async def test_a_space_the_app_does_not_have_is_none_and_deleting_it_is_fine(
    key_file: Path,
) -> None:
    app, _ = _spaces_app(key_file, lambda request: httpx.Response(404))

    assert await app.spaces.get("nobody") is None
    await app.spaces.delete("nobody")


@pytest.mark.parametrize(
    ("answer", "error", "said"),
    [
        (httpx.Response(403, text="not your app"), NotAllowed, "refused declaring a space"),
        (httpx.Response(409, text="taken"), NotAllowed, "refused declaring a space: taken"),
        (httpx.Response(400, text="bad id"), NotAllowed, "refused declaring a space: bad id"),
        (httpx.Response(502), Unavailable, "answered declaring a space with 502"),
        (httpx.Response(200, text="<html>"), Unavailable, "with something else"),
        (httpx.Response(200, json={"external_id": "a"}), Unavailable, "with something else"),
    ],
)
async def test_a_space_igni_server_will_not_declare_says_why(
    key_file: Path, answer: httpx.Response, error: type[Exception], said: str
) -> None:
    app, _ = _spaces_app(key_file, lambda request: answer)

    with pytest.raises(error, match=said):
        await app.spaces.declare("a")


async def test_a_token_igni_server_stops_honouring_is_renewed_once(key_file: Path) -> None:
    answers = iter([httpx.Response(401), httpx.Response(200, json={"space_id": "sp-1"})])
    app, server = _spaces_app(key_file, lambda request: next(answers))

    space = await app.spaces.get("a")

    assert space is not None and space.space_id == "sp-1"
    assert len(server.token_requests) == 2, "the refused token was dropped and a new one asked"


async def test_a_second_401_is_not_retried_again(key_file: Path) -> None:
    app, server = _spaces_app(key_file, lambda request: httpx.Response(401))

    with pytest.raises(Unavailable, match="401"):
        await app.spaces.get("a")

    assert len(server.token_requests) == 2


@pytest.mark.parametrize(
    "discovery",
    [
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json=[ISSUER]),
        httpx.Response(200, json={"issuer": ""}),
        httpx.Response(404, json={"issuer": ISSUER}),
    ],
)
async def test_igni_server_without_an_issuer_is_unavailable(
    key_file: Path, discovery: httpx.Response
) -> None:
    def no_issuer(request: httpx.Request) -> httpx.Response:
        return discovery

    http = httpx.AsyncClient(transport=httpx.MockTransport(no_issuer))
    app = App("app-bot", server="http://igni.test", key_file=key_file, http=http)

    with pytest.raises(Unavailable, match="published no issuer"):
        await app.token()


def test_an_app_takes_its_key_exactly_once(key_file: Path) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        App("app-bot", server="http://igni.test")
    with pytest.raises(ValueError, match="exactly one"):
        App("app-bot", server="http://igni.test", key_file=key_file, key_pem=key_file.read_text())


class KeyExchange:
    """igni server's api-key grant, as an `httpx.MockTransport`."""

    def __init__(self, *, refuse: str = "") -> None:
        self.forms: list[dict[str, str]] = []
        self.refuse = refuse

    def __call__(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.forms.append(form)
        if self.refuse:
            return httpx.Response(
                400, json={"error": "invalid_grant", "error_description": self.refuse}
            )
        return httpx.Response(
            200, json={"access_token": f"session-{len(self.forms)}", "expires_in": 900}
        )


def _key(exchange: KeyExchange, clock: Any = None) -> ApiKey:
    http = httpx.AsyncClient(transport=httpx.MockTransport(exchange))
    return ApiKey(
        "igpak1.org.k1.secret", server="http://igni.test", http=http, clock=clock or (lambda: 0.0)
    )


async def test_an_api_key_buys_a_session_and_keeps_it_until_near_its_end() -> None:
    now = [1_000.0]
    exchange = KeyExchange()
    key = _key(exchange, clock=lambda: now[0])

    first, again = await key.token(), await key.token()
    now[0] += 900 - ApiKey.RENEW_BEFORE + 1
    renewed = await key.token()

    assert first == again == "session-1" and renewed == "session-2"
    assert exchange.forms[0] == {
        "grant_type": "urn:igni:params:oauth:grant-type:api-key",
        "api_key": "igpak1.org.k1.secret",
    }


async def test_a_revoked_key_is_an_auth_error_with_igni_s_reason() -> None:
    key = _key(KeyExchange(refuse="this API key has been revoked"))

    with pytest.raises(AuthError, match="this API key has been revoked"):
        await key.token()


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (httpx.Response(503), "igni server answered the key's exchange with 503"),
        (
            httpx.Response(200, text="<html>"),
            "igni server answered the key's exchange with something else",
        ),
    ],
)
async def test_an_exchange_igni_server_could_not_make_is_unavailable(
    answer: httpx.Response, said: str
) -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: answer))
    key = ApiKey("igpak1.org.k1.secret", server="http://igni.test", http=http)

    with pytest.raises(Unavailable) as unavailable:
        await key.token()

    assert str(unavailable.value) == said


async def test_an_igni_server_out_of_reach_is_unavailable_for_the_key_s_session() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(unreachable))
    key = ApiKey("igpak1.org.k1.secret", server="http://igni.test", http=http)

    with pytest.raises(Unavailable, match="could not reach igni server for the key's session"):
        await key.token()


def test_the_api_key_grant_is_named_on_the_class() -> None:
    assert ApiKey.API_KEY_GRANT == "urn:igni:params:oauth:grant-type:api-key"


async def test_a_refused_app_is_told_igni_server_s_whole_answer(key_file: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER})
        return httpx.Response(
            401, json={"error": "invalid_client", "error_description": "unknown key"}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    app = App("app-bot", server="http://igni.test", key_file=key_file, http=http)

    with pytest.raises(AuthError) as refused:
        await app.token()

    said = str(refused.value)
    assert said.startswith("igni server refused the app's token: ")
    assert "invalid_client" in said and "unknown key" in said


def test_an_api_key_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IGNI_API_KEY", "igpak1.org.k1.secret")
    monkeypatch.setenv("IGNI_SERVER_URL", "http://igni.test/")

    key = Person.from_api_key()

    assert key.server == "http://igni.test"
    assert "secret" not in repr(key)


def test_a_missing_or_malformed_key_says_what_to_do(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IGNI_API_KEY", raising=False)
    with pytest.raises(AuthError, match="IGNI_API_KEY"):
        Person.from_api_key(server="http://igni.test")
    with pytest.raises(AuthError, match="igpak1"):
        Person.from_api_key("eyJ-a-session-not-a-key", server="http://igni.test")


def test_a_person_comes_from_the_cli_credentials(tmp_path: Path) -> None:
    stored = tmp_path / "credentials.json"
    later = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    stored.write_text(json.dumps({"access_token": "t-ada", "expires_at": later}))

    assert Person.from_cli(stored)._token == "t-ada"


def test_an_expired_or_missing_session_says_to_sign_in(tmp_path: Path) -> None:
    stored = tmp_path / "credentials.json"
    stored.write_text(json.dumps({"access_token": "t", "expires_at": "2020-01-01T00:00:00+00:00"}))
    with pytest.raises(AuthError, match="igni login"):
        Person.from_cli(stored)
    with pytest.raises(AuthError, match="igni login"):
        Person.from_cli(tmp_path / "nothing.json")


# ── The import paths 0.1.0 had ───────────────────────────────────────


def test_the_0_1_0_auth_names_still_import_from_igni_client_auth() -> None:
    from igni_client.auth import (  # noqa: PLC0415 — the import path is what is tested
        ACCESS_TOKEN_TYPE,
        ALGORITHM,
        ASSERTION_TYPE,
        TOKEN_EXCHANGE,
        ApiKey,
        App,
        Person,
        Space,
        SpaceRecord,
        Spaces,
        TokenSource,
    )

    assert (App, ApiKey, Person, Space, Spaces, SpaceRecord, TokenSource) == (
        igni_client.App,
        igni_client.ApiKey,
        igni_client.Person,
        igni_client.Space,
        igni_client.Spaces,
        igni_client.SpaceRecord,
        igni_client.TokenSource,
    )
    assert ASSERTION_TYPE == "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
    assert TOKEN_EXCHANGE == "urn:ietf:params:oauth:grant-type:token-exchange"
    assert ACCESS_TOKEN_TYPE == "urn:ietf:params:oauth:token-type:access_token"
    assert ALGORITHM == "RS256"


def test_the_auth_names_are_exported_from_igni_client() -> None:
    names = {"ApiKey", "App", "Person", "Space", "SpaceRecord", "Spaces", "TokenSource"}

    assert names <= set(igni_client.__all__)


# ── An app's key ─────────────────────────────────────────────────────


def _public_numbers(key_file: Path) -> rsa.RSAPublicNumbers:
    key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    return key.public_key().public_numbers()


def test_an_app_s_jwk_set_is_the_json_an_admin_pastes(key_file: Path) -> None:
    app = _app(key_file, IgniServer())

    jwks = app.public_jwks()
    pasted = json.loads(jwks.model_dump_json())

    assert isinstance(jwks, JwkSet)
    assert list(pasted) == ["keys"] and len(pasted["keys"]) == 1
    jwk = pasted["keys"][0]
    assert list(jwk) == ["kty", "use", "alg", "kid", "n", "e"]
    assert (jwk["kty"], jwk["use"], jwk["alg"], jwk["kid"]) == (
        "RSA",
        "sig",
        "RS256",
        app.thumbprint(),
    )
    assert jwt.PyJWK(jwk).key.public_numbers() == _public_numbers(key_file)


def test_an_app_s_kid_is_its_key_s_rfc_7638_thumbprint(key_file: Path) -> None:
    jwk = _app(key_file, IgniServer()).public_jwks().keys[0]

    # RFC 7638 §3: the required members, sorted, without whitespace, SHA-256, base64url.
    members = json.dumps({"e": jwk.e, "kty": "RSA", "n": jwk.n}, separators=(",", ":"))
    digest = hashlib.sha256(members.encode()).digest()

    assert jwk.kid == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert jwk.e == "AQAB"


def test_a_new_key_is_a_2048_bit_rsa_key_only_its_owner_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    made = App.generate_key("~/app-key.pem")
    first = _public_numbers(made)
    App.generate_key("~/app-key.pem")

    assert made == tmp_path / "app-key.pem"
    assert made.read_text().startswith("-----BEGIN PRIVATE KEY-----")
    assert made.stat().st_mode & 0o777 == 0o600
    assert first.n.bit_length() == 2048
    assert _public_numbers(made) != first, "a second key replaces the first"


def test_an_app_needs_its_id_and_an_rsa_key(key_file: Path) -> None:
    not_rsa = (
        ec.generate_private_key(ec.SECP256R1())
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )

    with pytest.raises(ValueError, match="an app needs its app id"):
        App("", server="http://igni.test", key_file=key_file)
    with pytest.raises(ValueError, match="an app's key must be an RSA private key"):
        App("app-bot", server="http://igni.test", key_pem=not_rsa)


# ── An app signing in ────────────────────────────────────────────────


async def test_an_app_s_assertion_is_signed_for_igni_server_and_lives_a_minute(
    key_file: Path,
) -> None:
    server = IgniServer()
    app = _app(key_file, server, clock=lambda: 1_000.5)
    server.jwks = app.public_jwks()

    await app.token()

    form = server.token_requests[0]
    assert list(form) == ["grant_type", "client_assertion_type", "client_assertion"]
    assert form["grant_type"] == "client_credentials"
    assert form["client_assertion_type"] == ASSERTION_TYPE
    header = jwt.get_unverified_header(form["client_assertion"])
    assert (header["alg"], header["kid"]) == ("RS256", app.thumbprint())
    claims = jwt.decode(form["client_assertion"], options={"verify_signature": False})
    assert list(claims) == ["iss", "sub", "aud", "iat", "exp", "jti"]
    assert (claims["iss"], claims["sub"], claims["aud"]) == ("app-bot", "app-bot", ISSUER)
    assert (claims["iat"], claims["exp"]) == (1_000, 1_060)
    assert len(claims["jti"]) == 32


async def test_igni_server_s_issuer_is_asked_for_once(key_file: Path) -> None:
    now = [1_000.0]
    server = IgniServer()
    app = _app(key_file, server, clock=lambda: now[0])
    server.jwks = app.public_jwks()

    await app.token()
    now[0] += 600
    await app.token()

    discovery = [c for c in server.calls if c.url.path == "/.well-known/openid-configuration"]
    assert len(server.token_requests) == 2 and len(discovery) == 1


async def test_an_igni_server_out_of_reach_is_unavailable_for_discovery(key_file: Path) -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(unreachable))
    app = App("app-bot", server="http://igni.test", key_file=key_file, http=http)

    with pytest.raises(Unavailable, match="could not reach igni server for discovery"):
        await app.token()


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (httpx.Response(503), "igni server answered the app's token with 503"),
        (
            httpx.Response(200, text="<html>"),
            "igni server answered the app's token with something else",
        ),
        (
            httpx.Response(200, json={"expires_in": 600}),
            "igni server answered the app's token with something else",
        ),
    ],
)
async def test_a_token_igni_server_could_not_make_for_an_app_is_unavailable(
    key_file: Path, answer: httpx.Response, said: str
) -> None:
    def token(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER})
        return answer

    http = httpx.AsyncClient(transport=httpx.MockTransport(token))
    app = App("app-bot", server="http://igni.test", key_file=key_file, http=http)

    with pytest.raises(Unavailable) as unavailable:
        await app.token()

    assert str(unavailable.value) == said


async def test_an_app_and_an_api_key_can_be_pointed_at_another_igni_server(
    key_file: Path,
) -> None:
    server, exchange = IgniServer(), KeyExchange()
    hosts: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return exchange(request) if b"api-key" in request.content else server(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(route))
    app = App("app-bot", server="http://old.test", key_file=key_file, http=http)
    key = ApiKey("igpak1.org.k1.secret", server="http://old.test", http=http)
    server.jwks = app.public_jwks()

    app.server = "http://igni.test"
    key.server = "http://igni.test"
    await app.token()
    await key.token()

    assert app.server == key.server == "http://igni.test"
    assert set(hosts) == {"igni.test"}


async def test_an_app_exchanges_its_token_for_a_space_s_and_calls_igni_server_as_itself(
    key_file: Path,
) -> None:
    def clock() -> float:
        return 1_000.0

    server = IgniServer()
    app = _app(key_file, server, clock=clock)
    server.jwks = app.public_jwks()

    issued = await app.exchange("sp-9")
    answer = await app.request(
        "PUT", "/v1/apps/app-bot/spaces/a", what="declaring a space", params={"limit": 3}
    )

    assert app.clock is clock
    assert (issued.access_token, issued.expires_in) == ("space:sp-9", 600)
    assert server.token_requests[-1] == {
        "grant_type": TOKEN_EXCHANGE,
        "subject_token": "app:app-bot",
        "subject_token_type": ACCESS_TOKEN_TYPE,
        "space": "sp-9",
    }
    assert answer.status_code == 201
    asked = server.calls[-1]
    assert asked.headers["Authorization"] == "Bearer app:app-bot"
    assert asked.url.params["limit"] == "3"


async def test_an_app_closes_only_the_http_client_it_made(key_file: Path) -> None:
    theirs = httpx.AsyncClient(transport=httpx.MockTransport(IgniServer()))
    async with App("app-bot", server="http://igni.test", key_file=key_file, http=theirs):
        pass
    async with App("app-bot", server="http://igni.test", key_file=key_file) as own:
        pass
    key = ApiKey("igpak1.org.k1.secret", server="http://igni.test", http=theirs)
    await key.aclose()
    own_key = ApiKey("igpak1.org.k1.secret", server="http://igni.test")
    await own_key.aclose()

    assert not theirs.is_closed
    assert own._server._http.is_closed and own_key._server._http.is_closed


# ── A token kept and renewed ─────────────────────────────────────────


def _key_answering(answer: Callable[[], httpx.Response], clock: Callable[[], float]) -> ApiKey:
    async def respond(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)  # let another caller in while this one waits
        return answer()

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    return ApiKey("igpak1.org.k1.secret", server="http://igni.test", http=http, clock=clock)


async def test_a_token_without_a_lifetime_is_kept_ten_minutes_less_the_margin() -> None:
    now, issued = [1_000.0], [0]

    def answer() -> httpx.Response:
        issued[0] += 1
        return httpx.Response(200, json={"access_token": f"session-{issued[0]}"})

    key = _key_answering(answer, clock=lambda: now[0])

    await key.token()
    now[0] += 600 - ApiKey.RENEW_BEFORE - 1
    kept = await key.token()
    now[0] += 2
    renewed = await key.token()

    assert (kept, renewed) == ("session-1", "session-2")


async def test_a_token_shorter_than_the_margin_is_asked_for_every_time() -> None:
    issued = [0]

    def answer() -> httpx.Response:
        issued[0] += 1
        return httpx.Response(200, json={"access_token": f"s-{issued[0]}", "expires_in": 30})

    key = _key_answering(answer, clock=lambda: 1_000.0)

    assert [await key.token(), await key.token()] == ["s-1", "s-2"]


async def test_callers_asking_at_once_share_one_new_token() -> None:
    issued = [0]

    def answer() -> httpx.Response:
        issued[0] += 1
        return httpx.Response(200, json={"access_token": f"s-{issued[0]}", "expires_in": 900})

    key = _key_answering(answer, clock=lambda: 1_000.0)

    tokens = await asyncio.gather(key.token(), key.token(), key.token())

    assert list(tokens) == ["s-1", "s-1", "s-1"] and issued[0] == 1


async def test_a_margin_set_on_an_api_key_after_it_is_made_is_honoured() -> None:
    now, issued = [1_000.0], [0]

    def answer() -> httpx.Response:
        issued[0] += 1
        return httpx.Response(200, json={"access_token": f"s-{issued[0]}", "expires_in": 600})

    key = _key_answering(answer, clock=lambda: now[0])
    key.RENEW_BEFORE = 300

    await key.token()
    now[0] += 301

    assert await key.token() == "s-2"


async def test_a_margin_set_on_an_app_after_it_is_made_is_honoured_by_it_and_its_spaces(
    key_file: Path,
) -> None:
    now = [1_000.0]
    server = IgniServer()
    app = _app(key_file, server, clock=lambda: now[0])
    server.jwks = app.public_jwks()
    space = app.spaces.space("sp-9")
    app.RENEW_BEFORE = 300

    await app.token()
    await space.token()
    now[0] += 301
    await app.token()
    await space.token()

    grants = [f["grant_type"] for f in server.token_requests]
    assert grants.count("client_credentials") == 2 and grants.count(TOKEN_EXCHANGE) == 2


# ── A person ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (httpx.Response(401, text="no such key"), "no such key"),
        (httpx.Response(403, json=["revoked"]), '["revoked"]'),
        (httpx.Response(400, json={"error": "invalid_grant"}), '{"error":"invalid_grant"}'),
    ],
)
async def test_a_refused_key_without_igni_s_reason_is_told_igni_s_whole_answer(
    answer: httpx.Response, said: str
) -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: answer))
    key = ApiKey("igpak1.org.k1.secret", server="http://igni.test", http=http)

    with pytest.raises(AuthError) as refused:
        await key.token()

    assert str(refused.value) == f"igni server refused the API key: {said}"


@pytest.mark.parametrize(
    ("described", "said"),
    [
        (42, "42"),
        (["revoked", "expired"], "['revoked', 'expired']"),
        (0, '{"error_description":0}'),
    ],
)
async def test_a_reason_igni_server_did_not_write_as_text_is_told_as_it_was(
    described: Any, said: str
) -> None:
    answer = httpx.Response(401, json={"error_description": described})
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: answer))
    key = ApiKey("igpak1.org.k1.secret", server="http://igni.test", http=http)

    with pytest.raises(AuthError) as refused:
        await key.token()

    assert str(refused.value) == f"igni server refused the API key: {said}"


def test_an_api_key_needs_to_know_where_igni_server_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IGNI_SERVER_URL", raising=False)

    with pytest.raises(AuthError, match="pass server=, or set IGNI_SERVER_URL"):
        Person.from_api_key("igpak1.org.k1.secret")


def test_a_person_needs_a_session_token() -> None:
    with pytest.raises(AuthError, match="a person needs a session token"):
        Person("  ")


@pytest.mark.parametrize("stored", ["not json", json.dumps({"expires_at": ""}), "[]"])
def test_a_file_that_is_not_igni_s_credentials_says_so(tmp_path: Path, stored: str) -> None:
    path = tmp_path / "credentials.json"
    path.write_text(stored)

    with pytest.raises(AuthError, match="is not an igni credentials file"):
        Person.from_cli(path)


@pytest.mark.parametrize(
    ("expires_at", "usable"),
    [
        ("", True),
        ("whenever", True),
        ((datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None).isoformat(), True),
        ((datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None).isoformat(), False),
    ],
)
def test_a_stored_session_without_a_clear_end_is_used_and_a_naive_one_is_utc(
    tmp_path: Path, expires_at: str, usable: bool
) -> None:
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"access_token": "t-ada", "expires_at": expires_at, "user": "x"}))

    if usable:
        assert Person.from_cli(path)._token == "t-ada"
    else:
        with pytest.raises(AuthError, match="has expired"):
            Person.from_cli(path)


def test_the_cli_session_is_found_in_the_home_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".igni").mkdir()
    (tmp_path / ".igni" / "credentials.json").write_text(json.dumps({"access_token": "t-ada"}))

    assert Person.from_cli()._token == "t-ada"


# ── An app's spaces ──────────────────────────────────────────────────


@pytest.mark.parametrize("external_id", ["", "x" * 201])
async def test_an_external_id_empty_or_too_long_is_refused_before_asking(
    key_file: Path, external_id: str
) -> None:
    app, server = _spaces_app(key_file, lambda request: httpx.Response(500))

    with pytest.raises(ValueError, match="1 to 200 characters"):
        await app.spaces.declare(external_id)

    assert server.calls == []


async def test_an_app_s_and_a_space_s_ids_are_escaped_in_the_path(key_file: Path) -> None:
    server = IgniServer()
    paths: list[bytes] = []

    def route(request: httpx.Request) -> httpx.Response:
        if "/spaces" in request.url.path:
            paths.append(request.url.raw_path)
            return httpx.Response(200, json={"space_id": "sp-1"})
        return server(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(route))
    app = App("acme/bot", server="http://igni.test", key_file=key_file, http=http)
    server.jwks = app.public_jwks()

    await app.spaces.declare("a b?c" + "x" * 195)
    await app.spaces.get("ü")

    assert paths == [
        b"/v1/apps/acme%2Fbot/spaces/a%20b%3Fc" + b"x" * 195,
        b"/v1/apps/acme%2Fbot/spaces/%C3%BC",
    ]


@pytest.mark.parametrize(
    ("ask", "answer", "error", "said"),
    [
        (
            "get",
            httpx.Response(403, text="no"),
            NotAllowed,
            "igni server refused reading a space: no",
        ),
        ("get", httpx.Response(500), Unavailable, "igni server answered reading a space with 500"),
        (
            "get",
            httpx.Response(200, json={}),
            Unavailable,
            "answered reading a space with something else",
        ),
        ("list", httpx.Response(400, text="limit"), NotAllowed, "refused listing spaces: limit"),
        ("list", httpx.Response(503), Unavailable, "igni server answered listing spaces with 503"),
        (
            "list",
            httpx.Response(200, json={"spaces": [{"external_id": "a"}]}),
            Unavailable,
            "igni server answered listing spaces with something else",
        ),
        (
            "list",
            httpx.Response(200, json=[]),
            Unavailable,
            "answered listing spaces with something else",
        ),
        ("delete", httpx.Response(409, text="busy"), NotAllowed, "refused deleting a space: busy"),
        (
            "delete",
            httpx.Response(302),
            Unavailable,
            "igni server answered deleting a space with 302",
        ),
    ],
)
async def test_igni_server_s_refusal_to_read_list_or_delete_says_why(
    key_file: Path, ask: str, answer: httpx.Response, error: type[Exception], said: str
) -> None:
    app, _ = _spaces_app(key_file, lambda request: answer)
    asks = {"get": app.spaces.get, "delete": app.spaces.delete}

    with pytest.raises(error, match=re.escape(said)):
        await (app.spaces.list() if ask == "list" else asks[ask]("a"))


async def test_an_empty_page_written_as_null_lists_no_spaces(key_file: Path) -> None:
    pages = {
        "": {"spaces": [{"space_id": "sp-1"}], "next": 2},
        "2": {"spaces": None, "next": None},
    }
    asked: list[dict[str, str]] = []

    def spaces(request: httpx.Request) -> httpx.Response:
        asked.append(dict(request.url.params))
        return httpx.Response(200, json=pages[request.url.params.get("after", "")])

    app, _ = _spaces_app(key_file, spaces)
    listed = await app.spaces.list()

    assert [s.space_id for s in listed] == ["sp-1"]
    assert asked == [{"limit": "100"}, {"limit": "100", "after": "2"}]


@pytest.mark.parametrize("empty", [[], {}, "", 0, False])
async def test_a_page_with_any_empty_spaces_lists_none(key_file: Path, empty: Any) -> None:
    app, _ = _spaces_app(
        key_file, lambda request: httpx.Response(200, json={"spaces": empty, "next": None})
    )

    assert await app.spaces.list() == []


@pytest.mark.parametrize(
    ("cursor", "sent"),
    [(True, ["true"]), (1.5, ["1.5"]), (["sp-1", "sp-2"], ["sp-1", "sp-2"])],
)
async def test_igni_server_s_cursor_is_passed_back_as_it_came(
    key_file: Path, cursor: Any, sent: list[str]
) -> None:
    asked: list[list[str]] = []

    def spaces(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params.get_list("after"))
        first = len(asked) == 1
        return httpx.Response(200, json={"spaces": [], "next": cursor if first else None})

    app, _ = _spaces_app(key_file, spaces)
    await app.spaces.list()

    assert asked == [[], sent]


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(200), httpx.Response(202, text="<html>"), httpx.Response(200, json=[])],
)
async def test_a_space_deleted_is_done_whatever_igni_server_says_with_it(
    key_file: Path, answer: httpx.Response
) -> None:
    app, _ = _spaces_app(key_file, lambda request: answer)

    await app.spaces.delete("a")


async def test_a_space_record_keeps_what_igni_server_added(key_file: Path) -> None:
    record = {"space_id": "sp-1", "external_id": "a", "org_id": "org-acme", "vm": "ready"}
    app, _ = _spaces_app(key_file, lambda request: httpx.Response(200, json=record))

    space = await app.spaces.get("a")

    assert space is not None and space.record is not None
    assert (space.external_id, space.record.org_id, space.record.created_at) == (
        "a",
        "org-acme",
        "",
    )
    assert space.record.model_extra == {"vm": "ready"}


async def test_a_space_known_by_its_id_signs_in_without_being_looked_up(key_file: Path) -> None:
    server = IgniServer()
    app = _app(key_file, server)
    server.jwks = app.public_jwks()

    space = app.spaces.space("sp-9")

    assert (await space.token(), space.external_id, space.record) == ("space:sp-9", "", None)
    assert not any("/spaces" in c.url.path for c in server.calls)
    with pytest.raises(ValueError, match="a space needs its space id"):
        app.spaces.space("")


async def test_a_space_s_token_is_kept_and_renewed_by_its_app_s_margin(key_file: Path) -> None:
    class EagerApp(App):
        RENEW_BEFORE = 300

    now = [1_000.0]
    server = IgniServer()
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    app = EagerApp(
        "app-bot", server="http://igni.test", key_file=key_file, http=http, clock=lambda: now[0]
    )
    server.jwks = app.public_jwks()
    space = app.spaces.space("sp-9")

    await space.token()
    now[0] += 600 - 300 - 1
    await space.token()
    exchanged_before = sum(f["grant_type"] == TOKEN_EXCHANGE for f in server.token_requests)
    now[0] += 2
    await space.token()
    exchanged = sum(f["grant_type"] == TOKEN_EXCHANGE for f in server.token_requests)

    assert (exchanged_before, exchanged) == (1, 2)


async def test_a_refused_space_is_told_igni_server_s_whole_answer(key_file: Path) -> None:
    server = IgniServer()

    def route(request: httpx.Request) -> httpx.Response:
        if b"token-exchange" in request.content:
            return httpx.Response(
                403, json={"error": "access_denied", "error_description": "not your space"}
            )
        return server(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(route))
    app = App("app-bot", server="http://igni.test", key_file=key_file, http=http)
    server.jwks = app.public_jwks()

    with pytest.raises(AuthError) as refused:
        await app.spaces.space("sp-9").token()

    said = str(refused.value)
    assert said.startswith("igni server refused the space's token: ")
    assert "access_denied" in said and "not your space" in said


async def test_a_command_streams_its_output_and_ends_with_its_exit_code() -> None:
    gateway = FakeGateway({"t-ada": "person:u-ada"})
    gateway.commands["make test"] = PlayedCommand(stdout="ok\n", stderr="warn\n", exit_code=2)
    async with (
        FakeIgni(gateway=gateway) as fake,
        IgniClient(fake.fleet(Person("t-ada"))) as igni,
    ):
        run = await igni.commands.run("make test", timeout_s=30)
        finished = await run.wait()
        me = await igni.me()

    assert run.stdout == "ok\n" and run.stderr == "warn\n"
    assert finished.exit_code == 2 and not finished.ok
    assert run.woken is not None and run.woken.how == "paused"
    assert run.record is not None and run.record.command == "make test"
    assert gateway.commands_run[0].producer == ProducerRef(kind="person", id="u-ada")
    assert (me.kind, me.id, me.org) == ("person", "u-ada", "org-acme")


async def test_the_fake_gateway_says_how_it_woke_the_vm_and_recorded_the_command() -> None:
    async with (
        FakeIgni(gateway=FakeGateway({"t-ada": "person:u-ada"})) as fake,
        IgniClient(fake.fleet(Person("t-ada"))) as igni,
    ):
        run = await igni.commands.run("ls")
        finished = await run.wait()

    assert run.woken is not None and (run.woken.how, run.woken.node) == ("paused", "n1")
    assert run.woken.ms == 12.345
    assert run.record is not None and (run.record.command_id, run.record.state) == (
        "c-1",
        "running",
    )
    assert (finished.exit_code, finished.duration_ms) == (0, 5)
    assert run.stdout == "ran ls\n"


async def test_the_fake_gateway_records_and_wakes_before_the_output_and_ends_last() -> None:
    gateway = FakeGateway({"t-ada": "person:u-ada"})
    gateway.commands["make"] = PlayedCommand(stdout="ok\n", stderr="warn\n")
    seen = []
    async with (
        FakeIgni(gateway=gateway) as fake,
        IgniClient(fake.fleet(Person("t-ada"))) as igni,
    ):
        run = await igni.commands.run("make")
        async for output in run:
            seen.append((output.stream, run.record is not None, run.woken is not None))
            assert run.finished is None

    assert seen == [("stdout", True, True), ("stderr", True, True)]
    assert run.finished is not None and run.finished.ok


async def test_a_command_in_somebody_elses_vm_is_refused() -> None:
    async with (
        FakeIgni(gateway=FakeGateway({"t-ada": "person:u-ada"})) as fake,
        IgniClient(fake.fleet(Person("t-ada"))) as igni,
    ):
        run = await igni.commands.run("id", producer="person:u-bob")
        with pytest.raises(NotAllowed, match="not your VM"):
            await run.wait()


async def test_a_local_igni_has_no_commands() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        with pytest.raises(NotSupported, match="needs Fleet's gateway"):
            await igni.commands.run("ls")


def test_a_message_this_version_does_not_know_keeps_everything() -> None:
    event = parse_event({"type": "hologram", "id": "x", "colour": "teal"})

    assert isinstance(event, Unknown)
    assert event.type == "hologram" and event.model_extra == {"colour": "teal"}


def test_a_newer_field_on_a_known_message_is_kept() -> None:
    event = parse_event({"type": "content_delta", "text": "hi", "language": "en"})

    assert event.type == "content_delta" and event.model_extra == {"language": "en"}

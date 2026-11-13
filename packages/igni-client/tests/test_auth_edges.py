"""The edges of signing in: keys, grants, tokens, discovery, credentials files and space ids."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from pydantic import ValidationError

from igni_client import ApiKey, App, AuthError, Person, Unavailable
from igni_client import auth as auth_package
from igni_client.auth.grants import (
    ACCESS_TOKEN_TYPE,
    API_KEY_GRANT,
    ASSERTION_TYPE,
    TOKEN_EXCHANGE,
    ApiKeyGrant,
    ClientCredentialsGrant,
    SpaceExchangeGrant,
)
from igni_client.auth.keys import AppKey, ClientAssertion, _b64url_uint
from igni_client.auth.tokens import IssuedToken, TokenCache

ISSUER = "https://igni.example.test"


def _pem(key: Any, encryption: Any = None) -> str:
    pem: bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        encryption or serialization.NoEncryption(),
    )
    return pem.decode()


def _rsa_pem() -> str:
    return _pem(rsa.generate_private_key(public_exponent=65537, key_size=2048))


def _app_on(route: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> App:
    http = httpx.AsyncClient(transport=httpx.MockTransport(route))
    return App("app-bot", server="http://igni.test", key_pem=_rsa_pem(), http=http, **kwargs)


# ── The package's names ──────────────────────────────────────────────


def test_igni_client_auth_exports_exactly_the_names_0_1_0_had() -> None:
    assert set(auth_package.__all__) == {
        "ACCESS_TOKEN_TYPE",
        "ALGORITHM",
        "ASSERTION_TYPE",
        "TOKEN_EXCHANGE",
        "ApiKey",
        "App",
        "Person",
        "Space",
        "SpaceRecord",
        "Spaces",
        "TokenSource",
    }
    assert all(hasattr(auth_package, name) for name in auth_package.__all__)


# ── The grants ───────────────────────────────────────────────────────


def test_the_grant_urns_are_the_ones_igni_server_and_the_rfcs_name() -> None:
    assert ASSERTION_TYPE == "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
    assert TOKEN_EXCHANGE == "urn:ietf:params:oauth:grant-type:token-exchange"
    assert ACCESS_TOKEN_TYPE == "urn:ietf:params:oauth:token-type:access_token"
    assert API_KEY_GRANT == "urn:igni:params:oauth:grant-type:api-key"


def test_each_grant_is_its_form_in_the_order_igni_server_was_sent() -> None:
    assert ApiKeyGrant(api_key="k").form() == {"grant_type": API_KEY_GRANT, "api_key": "k"}
    assert list(ClientCredentialsGrant(client_assertion="a").form().items()) == [
        ("grant_type", "client_credentials"),
        ("client_assertion_type", ASSERTION_TYPE),
        ("client_assertion", "a"),
    ]
    assert list(SpaceExchangeGrant(subject_token="t", space="sp").form().items()) == [
        ("grant_type", TOKEN_EXCHANGE),
        ("subject_token", "t"),
        ("subject_token_type", ACCESS_TOKEN_TYPE),
        ("space", "sp"),
    ]


def test_a_grant_cannot_name_another_grant_type_and_needs_its_own_fields() -> None:
    with pytest.raises(ValidationError):
        ApiKeyGrant(api_key="k", grant_type="client_credentials")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ClientCredentialsGrant(client_assertion="a", client_assertion_type="other")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SpaceExchangeGrant(subject_token="t", space="sp", subject_token_type="refresh")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ClientCredentialsGrant(client_assertion="a", grant_type="api-key")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SpaceExchangeGrant(subject_token="t", space="sp", grant_type="client_credentials")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SpaceExchangeGrant(subject_token="t")  # type: ignore[call-arg]


# ── An app's key ─────────────────────────────────────────────────────


def test_an_assertion_is_signed_with_the_key_the_published_jwk_describes() -> None:
    key = AppKey.from_pem(_rsa_pem())
    claims = ClientAssertion(iss="a", sub="a", aud=ISSUER, iat=1_000, exp=1_060, jti="j")

    token = key.sign(claims)

    jwk = key.jwks().keys[0]
    public = jwt.PyJWK(jwk.model_dump()).key
    assert jwt.get_unverified_header(token) == {"alg": "RS256", "typ": "JWT", "kid": jwk.kid}
    decoded = jwt.decode(
        token, public, algorithms=["RS256"], audience=ISSUER, options={"verify_exp": False}
    )
    assert decoded == claims.model_dump()


def test_a_number_is_written_as_its_big_endian_bytes_in_base64url() -> None:
    assert _b64url_uint(0) == "AA"
    assert _b64url_uint(65537) == "AQAB"
    assert _b64url_uint(0x80) == "gA"
    assert _b64url_uint(0x100) == "AQA"


async def test_every_sign_in_carries_an_assertion_of_its_own() -> None:
    assertions: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER})
        assertions.append(parse_qs(request.content.decode())["client_assertion"][0])
        return httpx.Response(200, json={"access_token": "t", "expires_in": 0})

    app = _app_on(route)
    await app.token()
    await app.token()

    ids = [jwt.decode(a, options={"verify_signature": False})["jti"] for a in assertions]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_an_app_reads_its_key_file_from_the_home_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    App.generate_key("~/key.pem")

    app = App("app-bot", server="http://igni.test", key_file="~/key.pem")

    assert app.thumbprint() == AppKey.from_pem((tmp_path / "key.pem").read_text()).thumbprint()


def test_an_app_whose_key_file_is_missing_says_so_as_an_os_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        App("app-bot", server="http://igni.test", key_file=tmp_path / "nope.pem")


# ── An app calling igni server ───────────────────────────────────────


async def test_the_retry_after_a_401_sends_the_same_call_with_the_same_params() -> None:
    asked: list[httpx.Request] = []
    signed_in = [0]

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER})
        if request.url.path == "/v1/oauth/token":
            signed_in[0] += 1
            return httpx.Response(200, json={"access_token": f"t{signed_in[0]}"})
        asked.append(request)
        return httpx.Response(401 if len(asked) == 1 else 200)

    app = _app_on(route)

    answer = await app.request("GET", "/v1/x", what="asking", params={"limit": 7})

    assert answer.status_code == 200
    assert [(r.method, r.url.path, dict(r.url.params)) for r in asked] == [
        ("GET", "/v1/x", {"limit": "7"})
    ] * 2
    assert [r.headers["Authorization"] for r in asked] == ["Bearer t1", "Bearer t2"]


async def test_a_server_address_with_trailing_slashes_is_asked_without_a_double_slash() -> None:
    urls: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER})
        return httpx.Response(200, json={"access_token": "t"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(route))
    app = App("app-bot", server="http://igni.test//", key_pem=_rsa_pem(), http=http)

    await app.token()

    assert app.server == "http://igni.test"
    assert urls == [
        "http://igni.test/.well-known/openid-configuration",
        "http://igni.test/v1/oauth/token",
    ]


# ── Discovery and the token endpoint ─────────────────────────────────


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json={"issuer": ""}),
        httpx.Response(200, json={}),
        httpx.Response(404),
    ],
)
async def test_discovery_that_names_no_issuer_is_unavailable_whatever_it_says(
    answer: httpx.Response,
) -> None:
    app = _app_on(lambda request: answer)

    with pytest.raises(Unavailable, match="igni server published no issuer"):
        await app.token()


async def test_a_token_answer_without_a_token_is_unavailable() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER})
        return httpx.Response(200, json={"expires_in": 600})

    with pytest.raises(Unavailable, match="the app's token with something else"):
        await _app_on(route).token()


@pytest.mark.parametrize("described", [None, ""])
async def test_a_refusal_without_a_description_is_told_as_igni_server_wrote_it(
    described: Any,
) -> None:
    body = {"error": "invalid_grant", "error_description": described}
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json=body))
    )
    key = ApiKey("igpak1.org.k1.secret", server="http://igni.test", http=http)

    with pytest.raises(AuthError) as refused:
        await key.token()

    assert str(refused.value).startswith("igni server refused the API key: {")
    assert "invalid_grant" in str(refused.value)


# ── The token cache ──────────────────────────────────────────────────


async def _fetcher(*lifetimes: int) -> Callable[[], Any]:
    issued = iter(lifetimes)
    count = [0]

    async def fetch() -> IssuedToken:
        count[0] += 1
        return IssuedToken(access_token=f"t{count[0]}", expires_in=next(issued))

    return fetch


async def test_a_token_is_fetched_again_the_moment_its_margin_is_reached() -> None:
    now = [0.0]
    cache = TokenCache(lambda: now[0], renew_before=lambda: 60)
    fetch = await _fetcher(600, 600)

    first = await cache.get(fetch)
    now[0] = 539.999
    kept = await cache.get(fetch)
    now[0] = 540.0
    renewed = await cache.get(fetch)

    assert (first, kept, renewed) == ("t1", "t1", "t2")


@pytest.mark.parametrize("lifetime", [0, -5, 30])
async def test_a_token_that_lives_less_than_the_margin_is_never_kept(lifetime: int) -> None:
    cache = TokenCache(lambda: 100.0, renew_before=lambda: 60)
    fetch = await _fetcher(lifetime, lifetime)

    assert (await cache.get(fetch), await cache.get(fetch)) == ("t1", "t2")


async def test_a_fetch_that_fails_leaves_the_cache_free_and_the_next_fetch_unpoisoned() -> None:
    now = [0.0]
    cache = TokenCache(lambda: now[0], renew_before=lambda: 60)
    good = await _fetcher(600)
    assert await cache.get(good) == "t1"
    now[0] = 600.0

    async def broken() -> IssuedToken:
        raise Unavailable("down")

    with pytest.raises(Unavailable):
        await cache.get(broken)

    async def fresh() -> IssuedToken:
        return IssuedToken(access_token="fresh")

    assert await asyncio.wait_for(cache.get(fresh), timeout=1) == "fresh"


async def test_a_forgotten_token_is_fetched_again() -> None:
    cache = TokenCache(lambda: 0.0, renew_before=lambda: 60)
    fetch = await _fetcher(600, 600)

    first = await cache.get(fetch)
    await cache.forget()

    assert (first, await cache.get(fetch)) == ("t1", "t2")


# ── A person ─────────────────────────────────────────────────────────


def test_an_api_key_never_shows_the_key_and_a_padded_one_is_sent_trimmed() -> None:
    key = ApiKey("  igpak1.org.k1.secret \n", server="http://igni.test")

    assert "secret" not in repr(key)
    assert repr(key) == "ApiKey(server='http://igni.test')"
    assert key._grant.form()["api_key"] == "igpak1.org.k1.secret"


async def test_a_person_s_session_token_is_kept_without_its_padding() -> None:
    assert await Person("  t-ada\n").token() == "t-ada"


def test_an_api_key_from_the_person_uses_the_client_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IGNI_API_KEY", "")
    monkeypatch.setenv("IGNI_SERVER_URL", "")
    http = httpx.AsyncClient()

    key = Person.from_api_key("igpak1.org.k1.secret", server="http://igni.test", http=http)

    assert key._server._http is http and not key._server._owns_http
    with pytest.raises(AuthError, match="no API key"):
        Person.from_api_key()


def test_an_empty_environment_variable_is_no_key_and_no_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IGNI_API_KEY", "")
    monkeypatch.setenv("IGNI_SERVER_URL", "")

    with pytest.raises(AuthError, match="no API key"):
        Person.from_api_key(server="http://igni.test")
    with pytest.raises(AuthError, match="where is igni server"):
        Person.from_api_key("igpak1.org.k1.secret")


def test_a_credentials_path_that_is_a_directory_is_no_session(tmp_path: Path) -> None:
    with pytest.raises(AuthError, match="no igni session on this machine"):
        Person.from_cli(tmp_path)


# ── A space's id ─────────────────────────────────────────────────────


def _spaces_on(
    answer: Callable[[httpx.Request], httpx.Response],
) -> tuple[App, list[httpx.Request]]:
    asked: list[httpx.Request] = []

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER})
        if request.url.path == "/v1/oauth/token":
            return httpx.Response(200, json={"access_token": "t"})
        asked.append(request)
        return answer(request)

    return _app_on(route), asked


async def test_an_external_id_of_two_hundred_characters_is_declared() -> None:
    app, asked = _spaces_on(lambda request: httpx.Response(200, json={"space_id": "sp-1"}))

    space = await app.spaces.declare("x" * 200)

    assert space.space_id == "sp-1"
    assert asked[0].url.path.endswith("/spaces/" + "x" * 200)


async def test_a_declare_answered_with_something_that_is_no_space_is_unavailable() -> None:
    app, _ = _spaces_on(lambda request: httpx.Response(200, json={"id": "sp-1"}))

    with pytest.raises(Unavailable, match="declaring a space with something else"):
        await app.spaces.declare("a")


def test_a_new_key_replacing_a_looser_file_is_still_only_its_owner_s(tmp_path: Path) -> None:
    target = tmp_path / "app-key.pem"
    target.write_text("old")
    target.chmod(0o644)

    App.generate_key(target)

    assert target.stat().st_mode & 0o777 == 0o600
    assert target.read_text().startswith("-----BEGIN PRIVATE KEY-----")


def test_a_key_that_is_encrypted_or_not_rsa_is_refused_as_a_value_error() -> None:
    encrypted = _pem(
        rsa.generate_private_key(public_exponent=65537, key_size=2048),
        serialization.BestAvailableEncryption(b"pw"),
    )
    not_rsa = _pem(ec.generate_private_key(ec.SECP256R1()))

    for pem in (encrypted, not_rsa, "", "not a pem"):
        with pytest.raises(ValueError, match="RSA private key"):
            AppKey.from_pem(pem)

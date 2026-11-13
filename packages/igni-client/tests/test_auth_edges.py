"""The edges of signing in: keys, grants, tokens, discovery, credentials files and space ids."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from igni_client import App
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

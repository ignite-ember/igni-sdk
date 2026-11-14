"""The web sign-in's collaborators on their own: the authorization link and the 401/303."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from fastapi import status
from starlette.requests import Request

from igni_service.web_redirects import AuthorizationRequest, Pkce, SignInRequired


def _request(path: str, query: str, accept: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": query.encode(),
            "headers": [(b"accept", accept.encode())],
        }
    )


def test_the_authorization_link_carries_the_s256_challenge_of_the_verifier() -> None:
    request = AuthorizationRequest.for_verifier(
        client_id="c-1", redirect_uri="https://s.test/auth/callback", state="st", verifier="v"
    )

    query = parse_qs(urlsplit(request.url("https://igni.test/authorize")).query)

    assert query == {
        "response_type": ["code"],
        "client_id": ["c-1"],
        "redirect_uri": ["https://s.test/auth/callback"],
        "state": ["st"],
        "code_challenge": [Pkce.challenge("v")],
        "code_challenge_method": ["S256"],
    }


def test_the_authorization_link_keeps_a_query_the_endpoint_already_has() -> None:
    request = AuthorizationRequest.for_verifier(
        client_id="c", redirect_uri="r", state="s", verifier="v"
    )

    url = request.url("https://igni.test/authorize?tenant=a")

    assert url.startswith("https://igni.test/authorize?tenant=a&response_type=code&")


def test_a_page_nobody_is_signed_in_to_is_sent_to_sign_in_and_back() -> None:
    refused = SignInRequired(_request("/settings", "tab=a&b=c", "text/html"), "/auth/login")

    assert refused.status_code == status.HTTP_303_SEE_OTHER
    assert refused.headers == {"Location": "/auth/login?return_to=%2Fsettings%3Ftab%3Da%26b%3Dc"}


def test_a_client_nobody_is_signed_in_for_is_answered_401() -> None:
    refused = SignInRequired(_request("/api", "", "application/json"), "/auth/login")

    assert refused.status_code == status.HTTP_401_UNAUTHORIZED
    assert refused.detail == "Not signed in"
    assert refused.headers == {"WWW-Authenticate": "Bearer"}

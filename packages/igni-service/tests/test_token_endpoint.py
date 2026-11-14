"""The token endpoint client, against a transport that answers whatever a test says.

`TokenEndpoint` asks igni for tokens and ends sign-ins, each call
authenticated by a fresh single-use assertion. The fake igni plays igni's
good answers; these play the rest: every status, a body that is not a
token, a refusal in any shape, and a network that fails.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from igni_service import IgniUnavailable, MemoryKeyStore
from igni_service.grants import ClientCredentialsGrant, RefreshTokenGrant
from igni_service.server import IgniServer
from igni_service.signing import SigningKey
from igni_service.token_endpoint import (
    ASSERTION_TYPE,
    GrantRefused,
    IssuedTokens,
    OAuthRefusal,
    TokenEndpoint,
)
from igni_service.urls import IgniPaths

BASE = "http://igni.test"
ISSUER = "https://igni.example.test"

Answer = Callable[[httpx.Request], httpx.Response]


class StaticClient:
    async def client_id(self) -> str:
        return "client-42"


class Igni:
    """A transport that serves discovery and answers the two endpoints as told."""

    def __init__(self, answer: Answer | httpx.Response) -> None:
        self._answer = answer
        self.posts: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == IgniPaths.DISCOVERY:
            return httpx.Response(200, json={"issuer": ISSUER + "/"})
        self.posts.append(request)
        if isinstance(self._answer, httpx.Response):
            return self._answer
        return self._answer(request)

    def form(self, index: int = -1) -> dict[str, str]:
        parsed = parse_qs(self.posts[index].content.decode(), keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items()}


def endpoint(igni: Igni) -> TokenEndpoint:
    http = httpx.AsyncClient(transport=httpx.MockTransport(igni))
    server = IgniServer(base_url=BASE + "/", http=http)
    return TokenEndpoint(server, StaticClient(), SigningKey(MemoryKeyStore()))


def claims(assertion: str) -> dict[str, Any]:
    payload = assertion.split(".")[1]
    decoded: dict[str, Any] = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )
    return decoded


GOOD = {"access_token": "at", "expires_in": 300, "refresh_token": "rt"}


class TestAGrantIsAsked:
    async def test_the_form_goes_to_the_token_path_with_the_assertion_beside_it(self) -> None:
        igni = Igni(httpx.Response(200, json=GOOD))

        tokens = await endpoint(igni).grant(ClientCredentialsGrant(organisation="org-1"))

        [post] = igni.posts
        assert post.method == "POST"
        assert str(post.url) == f"{BASE}{IgniPaths.TOKEN}"
        form = igni.form()
        assert form["grant_type"] == "client_credentials"
        assert form["organisation"] == "org-1"
        assert form["client_assertion_type"] == ASSERTION_TYPE
        assert tokens == IssuedTokens(access_token="at", expires_in=300, refresh_token="rt")

    async def test_the_assertion_is_from_the_client_to_igni_s_issuer_and_single_use(self) -> None:
        igni = Igni(httpx.Response(200, json=GOOD))
        tokens = endpoint(igni)

        await tokens.grant(ClientCredentialsGrant())
        await tokens.grant(ClientCredentialsGrant())

        first, second = (claims(igni.form(i)["client_assertion"]) for i in (0, 1))
        for claim in (first, second):
            assert claim["iss"] == claim["sub"] == "client-42"
            # The issuer as discovery wrote it, without its trailing slash.
            assert claim["aud"] == ISSUER
        assert first["jti"] != second["jti"]

    async def test_a_token_body_with_only_an_access_token_has_igni_s_defaults(self) -> None:
        igni = Igni(httpx.Response(200, json={"access_token": "at", "scope": "ignored"}))

        tokens = await endpoint(igni).grant(RefreshTokenGrant(refresh_token="r"))

        assert (tokens.expires_in, tokens.refresh_token, tokens.token_type) == (600, "", "Bearer")

    @pytest.mark.parametrize(
        "body",
        [
            httpx.Response(200, text="<html>welcome</html>"),
            httpx.Response(200, content=b""),
            httpx.Response(200, json={"expires_in": 5}),
            httpx.Response(200, json={"access_token": 7}),
            httpx.Response(200, json={"access_token": "at", "expires_in": "soon"}),
            httpx.Response(200, json=["access_token"]),
        ],
    )
    async def test_an_answer_that_is_not_a_token_is_igni_unavailable(
        self, body: httpx.Response
    ) -> None:
        with pytest.raises(IgniUnavailable, match="answered a token request with something else"):
            await endpoint(Igni(body)).grant(ClientCredentialsGrant())


class TestWhatIgniAnswersWithOtherThanTokens:
    @pytest.mark.parametrize("status", [400, 401, 403])
    async def test_these_three_are_a_refusal_carrying_the_body(self, status: int) -> None:
        body = json.dumps({"error": "invalid_client", "client_state": "pending"})
        igni = Igni(httpx.Response(status, text=body))

        with pytest.raises(GrantRefused) as raised:
            await endpoint(igni).grant(ClientCredentialsGrant())

        assert raised.value.status == status
        assert raised.value.detail == body
        assert str(raised.value) == f"{status} {body}"
        assert raised.value.refusal == OAuthRefusal(error="invalid_client", client_state="pending")

    @pytest.mark.parametrize("status", [201, 204, 302, 404, 409, 429, 500, 503])
    async def test_every_other_status_is_igni_unavailable_naming_it(self, status: int) -> None:
        with pytest.raises(IgniUnavailable, match=f"answered a token request {status}$"):
            await endpoint(Igni(httpx.Response(status, json=GOOD))).grant(ClientCredentialsGrant())

    async def test_a_network_failure_is_igni_unavailable_naming_only_the_error_type(self) -> None:
        def down(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("secret-host:5432 timed out")

        with pytest.raises(IgniUnavailable) as raised:
            await endpoint(Igni(down)).grant(ClientCredentialsGrant())

        assert (
            str(raised.value) == "could not reach igni server for a token request: ConnectTimeout"
        )
        assert isinstance(raised.value.__cause__, httpx.ConnectTimeout)

    async def test_discovery_failing_means_nothing_is_posted(self) -> None:
        igni = Igni(httpx.Response(200, json=GOOD))

        def broken(request: httpx.Request) -> httpx.Response:
            if request.url.path == IgniPaths.DISCOVERY:
                return httpx.Response(503)
            return igni(request)

        http = httpx.AsyncClient(transport=httpx.MockTransport(broken))
        tokens = TokenEndpoint(
            IgniServer(base_url=BASE, http=http), StaticClient(), SigningKey(MemoryKeyStore())
        )

        with pytest.raises(IgniUnavailable, match="could not read igni server's metadata"):
            await tokens.grant(ClientCredentialsGrant())
        assert igni.posts == []


class TestARevocation:
    async def test_it_posts_the_token_and_its_hint_to_the_revoke_path_and_a_200_is_enough(
        self,
    ) -> None:
        igni = Igni(httpx.Response(200))

        await endpoint(igni).revoke("rt-1")

        assert str(igni.posts[0].url) == f"{BASE}{IgniPaths.REVOKE}"
        form = igni.form()
        assert form["token"] == "rt-1"
        assert form["token_type_hint"] == "refresh_token"
        assert form["client_assertion_type"] == ASSERTION_TYPE
        assert claims(form["client_assertion"])["aud"] == ISSUER

    async def test_a_refresh_token_is_sent_whole_whatever_it_holds(self) -> None:
        igni = Igni(httpx.Response(200))
        token = "ünï+cødé/=&" + "x" * 5000

        await endpoint(igni).revoke(token)

        assert igni.form()["token"] == token

    async def test_an_empty_token_is_sent_and_left_to_igni(self) -> None:
        igni = Igni(httpx.Response(200))

        await endpoint(igni).revoke("")

        assert igni.form()["token"] == ""

    async def test_a_refusal_is_raised_with_the_words_igni_used(self) -> None:
        body = '{"error": "unsupported_token_type"}'
        with pytest.raises(GrantRefused) as raised:
            await endpoint(Igni(httpx.Response(400, text=body))).revoke("eyJ.access")

        assert raised.value.refusal.error == "unsupported_token_type"

    @pytest.mark.parametrize("status", [404, 500, 502])
    async def test_other_failures_say_it_was_a_revocation(self, status: int) -> None:
        with pytest.raises(IgniUnavailable, match=f"answered a revocation {status}$"):
            await endpoint(Igni(httpx.Response(status))).revoke("rt")

    async def test_a_network_failure_says_it_was_a_revocation(self) -> None:
        def down(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadError("reset")

        with pytest.raises(IgniUnavailable, match="for a revocation: ReadError$"):
            await endpoint(Igni(down)).revoke("rt")


class TestARefusalIsRead:
    def test_rfc_6749_json_is_read_with_igni_s_client_state(self) -> None:
        refusal = OAuthRefusal.read(
            json.dumps(
                {
                    "error": "invalid_client",
                    "error_description": "not approved",
                    "client_state": "revoked",
                    "extra": 1,
                }
            )
        )

        assert refusal == OAuthRefusal(
            error="invalid_client", error_description="not approved", client_state="revoked"
        )

    def test_an_older_igni_names_no_client_state(self) -> None:
        assert OAuthRefusal.read('{"error": "invalid_client"}').client_state is None

    @pytest.mark.parametrize(
        "body",
        ["", "<html>Bad Gateway</html>", "[]", "[1, 2]", "42", '"text"', "null", '{"error": 5}'],
    )
    def test_anything_else_is_an_empty_refusal(self, body: str) -> None:
        assert OAuthRefusal.read(body) == OAuthRefusal()

    def test_a_refusal_whose_body_is_not_json_still_keeps_the_body(self) -> None:
        refused = GrantRefused(403, "Forbidden")

        assert (refused.status, refused.detail, str(refused)) == (403, "Forbidden", "403 Forbidden")
        assert refused.refusal == OAuthRefusal()

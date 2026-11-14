"""What the fake's token and revocation endpoints answer for each grant, edge by edge.

Pinned over the fake's own HTTP transport with real client assertions:
the grant types, whom a `client_credentials` token is for, a person's
tokens from a code and from a refresh token, what revoking ends, and what
`reset` forgets.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from igni_service.crypto import Base64Url, RsaKeyPair
from igni_service.testing import FakeIgni
from igni_service.testing_clients import ClientKind, ClientState, FakeClient
from igni_service.testing_oauth import GrantType
from igni_service.token_endpoint import ASSERTION_TYPE
from igni_service.urls import IgniPaths

from .conftest import ORG

CALLBACK = "http://svc.test/auth/callback"
VERIFIER = "v" * 43
CHALLENGE = Base64Url.encode(hashlib.sha256(VERIFIER.encode()).digest())


class Clients:
    """Two services registered with the fake, each with its own key."""

    def __init__(self, fake: FakeIgni) -> None:
        self.fake = fake
        self.pairs: dict[str, RsaKeyPair] = {}
        for client_id in ("svc-1", "svc-2"):
            pair = RsaKeyPair.generate()
            self.pairs[client_id] = pair
            fake.clients.clients[client_id] = FakeClient(
                client_id=client_id,
                client_name=client_id,
                client_uri=f"http://{client_id}.test",
                kind=ClientKind.SERVICE,
                redirect_uris=[CALLBACK],
                state=ClientState.APPROVED,
                thumbprint=pair.thumbprint(),
                jwk=pair.public_jwk(),
            )

    def form(self, client_id: str = "svc-1", **fields: str) -> dict[str, str]:
        now = int(self.fake.clock.wall())
        signed = self.pairs[client_id].sign_jwt(
            {
                "iss": client_id,
                "sub": client_id,
                "aud": FakeIgni.ISSUER,
                "iat": now,
                "exp": now + 60,
                "jti": uuid.uuid4().hex,
            }
        )
        return {"client_assertion_type": ASSERTION_TYPE, "client_assertion": signed, **fields}

    async def post(self, path: str, form: dict[str, str]) -> httpx.Response:
        async with self.fake.http_client() as http:
            return await http.post(f"{FakeIgni.BASE}{path}", data=form)

    async def token(self, client_id: str = "svc-1", **fields: str) -> httpx.Response:
        return await self.post(IgniPaths.TOKEN, self.form(client_id, **fields))

    async def revoke(self, client_id: str, token: str) -> httpx.Response:
        return await self.post(IgniPaths.REVOKE, self.form(client_id, token=token))

    async def sign_in(self, client_id: str = "svc-1", user_id: str = "u-ada") -> dict[str, Any]:
        """Authorize and redeem a code: the tokens a person's sign-in gets."""
        query = urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "code_challenge_method": "S256",
                "code_challenge": CHALLENGE,
                "redirect_uri": CALLBACK,
                "state": "st",
            }
        )
        back = self.fake.oauth.sign_ins.authorize(
            f"{self.fake.addresses.authorization_endpoint}?{query}", user_id=user_id, org_id=ORG
        )
        code = parse_qs(urlsplit(back).query)["code"][0]
        response = await self.token(
            client_id,
            grant_type="authorization_code",
            code=code,
            code_verifier=VERIFIER,
            redirect_uri=CALLBACK,
        )
        assert response.status_code == 200, response.text
        tokens: dict[str, Any] = response.json()
        return tokens


@pytest.fixture
def clients(fake: FakeIgni) -> Clients:
    return Clients(fake)


def claims_of(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    claims: dict[str, Any] = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )
    return claims


def test_a_grant_type_is_parsed_or_is_none() -> None:
    assert GrantType.parse("client_credentials") is GrantType.CLIENT_CREDENTIALS
    assert GrantType.parse("authorization_code") is GrantType.AUTHORIZATION_CODE
    assert GrantType.parse("refresh_token") is GrantType.REFRESH_TOKEN
    assert GrantType.parse("password") is None
    assert GrantType.parse("") is None
    assert GrantType.parse("Client_Credentials") is None


async def test_the_token_endpoint_wants_a_jwt_bearer_assertion_and_the_revoke_endpoint_a_401(
    clients: Clients,
) -> None:
    form = {"grant_type": "client_credentials", "client_assertion_type": "other"}

    token = await clients.post(IgniPaths.TOKEN, form)
    revoke = await clients.post(IgniPaths.REVOKE, {**form, "token": "refresh-x"})

    assert (token.status_code, token.json()) == (400, {"error": "invalid_request"})
    assert (revoke.status_code, revoke.json()) == (401, {"error": "invalid_client"})
    assert clients.fake.oauth.grants == [], "not even asked of a client"


async def test_a_service_asks_for_one_organisation_and_gets_a_token_for_it(
    clients: Clients,
) -> None:
    response = await clients.token(grant_type="client_credentials", organisation=ORG)

    body = response.json()
    assert response.status_code == 200
    assert body["access_token"].startswith("service-") and "refresh_token" not in body
    holder = clients.fake.oauth.bearers.service_holder(body["access_token"])
    assert holder is not None and (holder.client_id, holder.org_id) == ("svc-1", ORG)


async def test_a_service_asking_for_no_organisation_is_refused(clients: Clients) -> None:
    response = await clients.token(grant_type="client_credentials")

    assert (response.status_code, response.json()) == (400, {"error": "invalid_request"})


async def test_the_revocations_scope_with_no_organisation_is_a_token_for_none(
    clients: Clients,
) -> None:
    response = await clients.token(grant_type="client_credentials", scope="revocations")

    token = response.json()["access_token"]
    holder = clients.fake.oauth.bearers.service_holder(token)
    assert response.status_code == 200 and token.startswith("revocations-")
    assert holder is not None and (holder.client_id, holder.org_id) == ("svc-1", "")


async def test_the_revocations_scope_with_an_organisation_is_an_ordinary_service_token(
    clients: Clients,
) -> None:
    response = await clients.token(
        grant_type="client_credentials", scope="revocations", organisation=ORG
    )

    token = response.json()["access_token"]
    holder = clients.fake.oauth.bearers.service_holder(token)
    assert token.startswith("service-")
    assert holder is not None and holder.org_id == ORG


async def test_a_code_signs_a_person_in_for_the_clients_own_address(clients: Clients) -> None:
    tokens = await clients.sign_in("svc-2", "u-ada")

    claims = claims_of(tokens["access_token"])
    assert claims["aud"] == "http://svc-2.test"
    assert claims["azp"] == "svc-2"
    assert claims["sub"] == "u-ada"
    assert claims["org"] == ORG
    assert tokens["refresh_token"].startswith("refresh-")


async def test_a_code_is_an_invalid_grant_without_its_verifier_and_once_used(
    clients: Clients,
) -> None:
    redeem = {"grant_type": "authorization_code", "redirect_uri": CALLBACK}
    sign_ins = clients.fake.oauth.sign_ins
    query = urlencode(
        {
            "client_id": "svc-1",
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": CHALLENGE,
            "redirect_uri": CALLBACK,
            "state": "st",
        }
    )
    back = sign_ins.authorize(
        f"{clients.fake.addresses.authorization_endpoint}?{query}", user_id="u-ada", org_id=ORG
    )
    code = parse_qs(urlsplit(back).query)["code"][0]

    wrong = await clients.token(**redeem, code=code, code_verifier="w" * 43)
    right_but_used_up = await clients.token(**redeem, code=code, code_verifier=VERIFIER)

    assert (wrong.status_code, wrong.json()) == (400, {"error": "invalid_grant"})
    assert right_but_used_up.status_code == 400


async def test_a_refresh_token_is_renewed_once_for_a_new_one(clients: Clients) -> None:
    first = (await clients.sign_in())["refresh_token"]

    renewed = await clients.token(grant_type="refresh_token", refresh_token=first)
    again = await clients.token(grant_type="refresh_token", refresh_token=first)

    assert renewed.status_code == 200
    assert renewed.json()["refresh_token"] not in (first, "")
    assert (again.status_code, again.json()) == (400, {"error": "invalid_grant"})


async def test_revoking_another_clients_refresh_token_is_an_invalid_grant_and_ends_nothing(
    clients: Clients,
) -> None:
    refresh = (await clients.sign_in("svc-1"))["refresh_token"]

    response = await clients.revoke("svc-2", refresh)

    assert (response.status_code, response.json()) == (400, {"error": "invalid_grant"})
    assert clients.fake.oauth.revoked == []
    assert clients.fake.oauth.sign_ins.held(refresh) is not None


async def test_revoking_ones_own_refresh_token_ends_the_whole_sign_in(clients: Clients) -> None:
    first = (await clients.sign_in())["refresh_token"]
    renewed = (await clients.token(grant_type="refresh_token", refresh_token=first)).json()
    sibling = clients.fake.oauth.sign_ins.held(renewed["refresh_token"])
    assert sibling is not None
    other = clients.fake.oauth.sign_ins.hold(sibling)  # a second token of the same sign-in

    response = await clients.revoke("svc-1", renewed["refresh_token"])

    assert response.status_code == 200
    assert clients.fake.oauth.revoked == [renewed["refresh_token"]]
    assert clients.fake.oauth.sign_ins.held(other) is None


async def test_reset_forgets_what_was_asked_and_every_sign_in_but_not_the_bearers_issued(
    clients: Clients,
) -> None:
    bearer = (await clients.token(grant_type="client_credentials", organisation=ORG)).json()[
        "access_token"
    ]
    refresh = (await clients.sign_in())["refresh_token"]
    await clients.revoke("svc-1", (await clients.sign_in())["refresh_token"])
    oauth = clients.fake.oauth
    assert oauth.grants and oauth.revoked

    oauth.reset()

    assert oauth.grants == [] and oauth.revoked == []
    assert oauth.sign_ins.held(refresh) is None and oauth.sign_ins.codes == {}
    assert oauth.bearers.service_holder(bearer) is not None

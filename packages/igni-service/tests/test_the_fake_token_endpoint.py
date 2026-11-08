"""What the fake's token and revocation endpoints refuse, as igni refuses it.

The fake's OAuth side came out of one class into a client assertion
verifier, a token endpoint and the portal's sign-ins. These pin the
refusals a service only meets when something is wrong: a replayed or
long-lived assertion, a grant igni does not issue, an app asking for
another organisation, and the portal turning a browser away.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from igni_service.crypto import RsaKeyPair
from igni_service.testing import FakeIgni, PortalRefused
from igni_service.token_endpoint import ASSERTION_TYPE
from igni_service.urls import IgniPaths

from .conftest import ORG, OTHER_ORG

APP = "app-bot"


@pytest.fixture
def pair(fake: FakeIgni) -> RsaKeyPair:
    """An app's key, registered by an org admin of `ORG`."""
    pair = RsaKeyPair.generate()
    fake.clients.add_app(APP, ORG, "Bot", pair)
    return pair


def assertion(fake: FakeIgni, pair: RsaKeyPair, **changes: Any) -> str:
    now = int(fake.clock.wall())
    claims = {
        "iss": APP,
        "sub": APP,
        "aud": FakeIgni.ISSUER,
        "iat": now,
        "exp": now + 60,
        "jti": uuid.uuid4().hex,
    }
    return pair.sign_jwt({**claims, **changes})


async def post(fake: FakeIgni, path: str, form: dict[str, str]) -> httpx.Response:
    async with fake.http_client() as http:
        return await http.post(f"{FakeIgni.BASE}{path}", data=form)


def grant(signed: str, **form: str) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "client_assertion_type": ASSERTION_TYPE,
        "client_assertion": signed,
        **form,
    }


async def test_an_app_gets_its_own_token(fake: FakeIgni, pair: RsaKeyPair) -> None:
    response = await post(fake, IgniPaths.TOKEN, grant(assertion(fake, pair)))

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"].startswith("app-") and body["expires_in"] == 600
    assert "refresh_token" not in body, "a bearer token comes without one"


async def test_an_assertion_is_used_once(fake: FakeIgni, pair: RsaKeyPair) -> None:
    signed = assertion(fake, pair)

    first = await post(fake, IgniPaths.TOKEN, grant(signed))
    again = await post(fake, IgniPaths.TOKEN, grant(signed))

    assert first.status_code == 200
    assert (again.status_code, again.json()) == (401, {"error": "invalid_client"})


@pytest.mark.parametrize(
    "changes",
    [
        {"exp_after": 301},
        {"exp_after": 0},
        {"sub": "someone-else"},
        {"aud": "https://not-igni.test"},
    ],
    ids=["lives-too-long", "already-expired", "other-subject", "other-audience"],
)
async def test_an_assertion_igni_would_not_take_proves_nobody(
    fake: FakeIgni, pair: RsaKeyPair, changes: dict[str, Any]
) -> None:
    if "exp_after" in changes:
        changes = {"exp": int(fake.clock.wall()) + changes.pop("exp_after")}

    response = await post(fake, IgniPaths.TOKEN, grant(assertion(fake, pair, **changes)))

    assert (response.status_code, response.json()) == (401, {"error": "invalid_client"})


async def test_a_revoked_client_is_told_so_in_igni_s_words(
    fake: FakeIgni, pair: RsaKeyPair
) -> None:
    fake.clients.revoke(APP)

    response = await post(fake, IgniPaths.TOKEN, grant(assertion(fake, pair)))

    assert response.status_code == 401
    assert response.json() == {
        "error": "invalid_client",
        "error_description": "this client has been revoked",
    }


async def test_a_grant_igni_does_not_issue_is_unsupported(fake: FakeIgni, pair: RsaKeyPair) -> None:
    response = await post(
        fake, IgniPaths.TOKEN, grant(assertion(fake, pair), grant_type="password")
    )

    assert (response.status_code, response.json()) == (400, {"error": "unsupported_grant_type"})
    assert fake.oauth.grants == ["password"], "asked, and recorded as asked"


async def test_an_app_asks_for_its_own_organisation_only(fake: FakeIgni, pair: RsaKeyPair) -> None:
    other = await post(fake, IgniPaths.TOKEN, grant(assertion(fake, pair), organisation=OTHER_ORG))
    own = await post(fake, IgniPaths.TOKEN, grant(assertion(fake, pair), organisation=ORG))

    assert (other.status_code, other.json()) == (400, {"error": "invalid_target"})
    assert own.status_code == 200


@pytest.mark.parametrize(
    ("token", "status", "body"),
    [
        ("", 400, {"error": "invalid_request"}),
        ("eyJhbGciOiJSUzI1NiJ9.e30.sig", 400, {"error": "unsupported_token_type"}),
        ("refresh-nobody-holds", 200, None),
    ],
    ids=["no-token", "an-access-token", "one-igni-does-not-honour"],
)
async def test_revoking_answers_as_rfc_7009_has_igni_answer(
    fake: FakeIgni, pair: RsaKeyPair, token: str, status: int, body: dict[str, str] | None
) -> None:
    form = {
        "client_assertion_type": ASSERTION_TYPE,
        "client_assertion": assertion(fake, pair),
        "token": token,
    }

    response = await post(fake, IgniPaths.REVOKE, form)

    assert response.status_code == status
    if body is not None:
        assert response.json() == body
    assert fake.oauth.revoked == []


@pytest.mark.parametrize(
    ("location", "said"),
    [
        ("https://elsewhere.test/authorize?client_id=x", "is not igni's sign-in page"),
        (f"{FakeIgni.ISSUER}/authorize?client_id=nobody", "unknown client"),
        (
            f"{FakeIgni.ISSUER}/authorize?client_id={APP}&response_type=token",
            "only the code flow with S256",
        ),
        (
            f"{FakeIgni.ISSUER}/authorize?client_id={APP}&response_type=code"
            "&code_challenge_method=S256&redirect_uri=https://evil.test/cb",
            "is not a registered redirect URI",
        ),
    ],
    ids=["another-page", "unknown-client", "implicit-flow", "unregistered-redirect"],
)
def test_the_portal_turns_a_browser_away(
    fake: FakeIgni, pair: RsaKeyPair, location: str, said: str
) -> None:
    with pytest.raises(PortalRefused, match=said):
        fake.oauth.sign_ins.authorize(location, user_id="u-ada", org_id=ORG)


def test_a_portal_refusal_is_still_a_value_error() -> None:
    assert issubclass(PortalRefused, ValueError), "0.1.0 raised ValueError"


async def test_a_registration_with_other_than_one_public_key_is_refused(fake: FakeIgni) -> None:
    pair = RsaKeyPair.generate()
    metadata = {
        "client_name": "Two keys",
        "client_uri": "https://service.test",
        "redirect_uris": [],
        "jwks": {
            "keys": [pair.public_jwk().as_dict(), RsaKeyPair.generate().public_jwk().as_dict()]
        },
    }

    async with fake.http_client() as http:
        response = await http.post(f"{FakeIgni.BASE}{IgniPaths.CLIENTS}", json=metadata)

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_client_metadata",
        "error_description": "exactly one public key is required",
    }
    assert fake.clients.clients == {}

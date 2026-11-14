"""The portal the fake plays: what it refuses, what a code is good for, and how a sign-in ends.

`SignIns.authorize` hands a browser back with a code; the code is
redeemed once, with its PKCE verifier, by the client it was issued for at
the redirect it named, inside sixty seconds. A refresh token is used up by
a renewal, and ending a sign-in ends every token of it.
"""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from igni_service.crypto import Base64Url, RsaKeyPair
from igni_service.testing import FakeIgni, ManualClock
from igni_service.testing_clients import ClientKind, ClientState, FakeClient
from igni_service.testing_sessions import (
    CODE_LIFETIME,
    AuthorizeRequest,
    HeldRefresh,
    IssuedCode,
    PortalRefused,
    SignIns,
)
from igni_service.testing_wire import TokenForm

from .conftest import ORG

CALLBACK = "http://svc.test/auth/callback"
VERIFIER = "v" * 43
CHALLENGE = Base64Url.encode(hashlib.sha256(VERIFIER.encode()).digest())


@pytest.fixture
def sign_ins(fake: FakeIgni) -> SignIns:
    for client_id in ("svc-1", "svc-2"):
        pair = RsaKeyPair.generate()
        fake.clients.clients[client_id] = FakeClient(
            client_id=client_id,
            client_name=client_id,
            client_uri="http://svc.test",
            kind=ClientKind.SERVICE,
            redirect_uris=[CALLBACK],
            state=ClientState.APPROVED,
            thumbprint=pair.thumbprint(),
            jwk=pair.public_jwk(),
        )
    return fake.oauth.sign_ins


def location(fake: FakeIgni, **changes: str) -> str:
    query = {
        "client_id": "svc-1",
        "response_type": "code",
        "code_challenge_method": "S256",
        "code_challenge": CHALLENGE,
        "redirect_uri": CALLBACK,
        "state": "st-1",
        **changes,
    }
    return f"{fake.addresses.authorization_endpoint}?{urlencode(query)}"


def code_of(back: str) -> str:
    return parse_qs(urlsplit(back).query)["code"][0]


def redeeming(code: str, **changes: str) -> TokenForm:
    return TokenForm(code=code, code_verifier=VERIFIER, redirect_uri=CALLBACK, **changes)


def test_the_browser_is_sent_back_with_a_code_and_its_state(
    fake: FakeIgni, sign_ins: SignIns
) -> None:
    back = sign_ins.authorize(location(fake), user_id="u-ada", org_id=ORG)

    parts = urlsplit(back)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == CALLBACK
    query = parse_qs(parts.query)
    assert query["state"] == ["st-1"]
    [code] = query["code"]
    issued = sign_ins.codes[code]
    assert (issued.client_id, issued.user_id, issued.org_id) == ("svc-1", "u-ada", ORG)
    assert issued.expires_at == fake.clock.wall() + CODE_LIFETIME == fake.clock.wall() + 60


def test_a_redirect_uri_with_a_query_already_gets_the_code_after_an_ampersand() -> None:
    asked = AuthorizeRequest(redirect_uri="https://svc.test/cb?next=%2F", state="a b")

    assert asked.redirect("c1") == "https://svc.test/cb?next=%2F&code=c1&state=a+b"
    assert AuthorizeRequest(redirect_uri="https://svc.test/cb", state="s").redirect("c1") == (
        "https://svc.test/cb?code=c1&state=s"
    )


def test_the_first_value_of_each_query_parameter_is_read_and_the_rest_ignored() -> None:
    asked = AuthorizeRequest.parse("client_id=a&client_id=b&state=s&utm=x&code_challenge=")

    assert (asked.client_id, asked.state, asked.code_challenge) == ("a", "s", "")


@pytest.mark.parametrize(
    ("changes", "said"),
    [
        ({"client_id": ""}, "unknown client"),
        ({"response_type": ""}, "only the code flow with S256"),
        ({"code_challenge_method": "plain"}, "only the code flow with S256"),
        ({"code_challenge": ""}, "a challenge and a state are required"),
        ({"state": ""}, "a challenge and a state are required"),
    ],
    ids=["no-client", "no-flow", "plain-challenge", "no-challenge", "no-state"],
)
def test_the_portal_refuses_a_request_missing_what_it_needs(
    fake: FakeIgni, sign_ins: SignIns, changes: dict[str, str], said: str
) -> None:
    with pytest.raises(PortalRefused, match=said):
        sign_ins.authorize(location(fake, **changes), user_id="u-ada", org_id=ORG)

    assert sign_ins.codes == {}


def test_the_portal_refuses_a_client_that_has_been_revoked(
    fake: FakeIgni, sign_ins: SignIns
) -> None:
    fake.clients.revoke("svc-1")

    with pytest.raises(PortalRefused, match="unknown client"):
        sign_ins.authorize(location(fake), user_id="u-ada", org_id=ORG)


@pytest.mark.parametrize(
    "user_id", ["u-gone", "u-eve", "u-nobody"], ids=["deactivated", "other-org", "unknown"]
)
def test_the_portal_signs_in_only_an_active_member_of_the_organisation(
    fake: FakeIgni, sign_ins: SignIns, user_id: str
) -> None:
    with pytest.raises(PortalRefused, match=f"{user_id} is not an active member of {ORG}"):
        sign_ins.authorize(location(fake), user_id=user_id, org_id=ORG)


def test_a_url_that_is_not_the_sign_in_page_is_refused_whatever_its_query(
    fake: FakeIgni, sign_ins: SignIns
) -> None:
    other = location(fake).replace(fake.addresses.issuer, "https://elsewhere.test")

    with pytest.raises(PortalRefused, match="is not igni's sign-in page"):
        sign_ins.authorize(other, user_id="u-ada", org_id=ORG)


def test_a_code_is_redeemed_once_for_a_sign_in_of_its_own(
    fake: FakeIgni, sign_ins: SignIns
) -> None:
    first = code_of(sign_ins.authorize(location(fake), user_id="u-ada", org_id=ORG))
    second = code_of(sign_ins.authorize(location(fake), user_id="u-ada", org_id=ORG))

    held = sign_ins.redeem(redeeming(first), "svc-1")
    again = sign_ins.redeem(redeeming(first), "svc-1")
    other = sign_ins.redeem(redeeming(second), "svc-1")

    assert held is not None and other is not None
    assert (held.client_id, held.user_id, held.org_id) == ("svc-1", "u-ada", ORG)
    assert again is None, "used"
    assert held.grant != other.grant


@pytest.mark.parametrize(
    ("form", "client"),
    [
        ({"code_verifier": "w" * 43}, "svc-1"),
        ({"code_verifier": ""}, "svc-1"),
        ({"redirect_uri": "http://svc.test/elsewhere"}, "svc-1"),
        ({}, "svc-2"),
    ],
    ids=["wrong-verifier", "no-verifier", "wrong-redirect", "other-client"],
)
def test_a_code_is_not_redeemed_without_its_verifier_redirect_and_client(
    fake: FakeIgni, sign_ins: SignIns, form: dict[str, str], client: str
) -> None:
    code = code_of(sign_ins.authorize(location(fake), user_id="u-ada", org_id=ORG))
    asked = redeeming(code).model_copy(update=form)

    assert sign_ins.redeem(asked, client) is None
    assert sign_ins.redeem(redeeming(code), "svc-1") is None, "a try, right or wrong, uses it up"


def test_a_code_is_good_until_sixty_seconds_and_not_at_sixty(
    fake: FakeIgni, sign_ins: SignIns, clock: ManualClock
) -> None:
    early = code_of(sign_ins.authorize(location(fake), user_id="u-ada", org_id=ORG))
    late = code_of(sign_ins.authorize(location(fake), user_id="u-ada", org_id=ORG))

    clock.advance(59.5)
    assert sign_ins.redeem(redeeming(early), "svc-1") is not None
    clock.advance(0.5)
    assert sign_ins.redeem(redeeming(late), "svc-1") is None


def test_an_issued_code_says_whether_a_form_redeems_it() -> None:
    issued = IssuedCode(
        client_id="svc-1",
        redirect_uri=CALLBACK,
        challenge=CHALLENGE,
        user_id="u-ada",
        org_id=ORG,
        expires_at=100.0,
    )

    assert issued.redeems(redeeming("x"), "svc-1", now=99.9)
    assert not issued.redeems(redeeming("x"), "svc-1", now=100.0)
    assert not issued.redeems(redeeming("x"), "svc-2", now=0.0)


def held_by(sign_ins: SignIns, client_id: str = "svc-1", user_id: str = "u-ada") -> HeldRefresh:
    return HeldRefresh(client_id=client_id, user_id=user_id, org_id=ORG, grant=f"g-{user_id}")


def test_a_refresh_token_is_used_up_by_the_renewal_it_is_given_to(sign_ins: SignIns) -> None:
    held = held_by(sign_ins)
    token = sign_ins.hold(held)

    renewed = sign_ins.renew(TokenForm(refresh_token=token), "svc-1")

    assert renewed == held
    assert sign_ins.held(token) is None
    assert sign_ins.renew(TokenForm(refresh_token=token), "svc-1") is None
    assert sign_ins.renew(TokenForm(refresh_token="refresh-unknown"), "svc-1") is None


def test_another_clients_renewal_is_refused(sign_ins: SignIns) -> None:
    token = sign_ins.hold(held_by(sign_ins))

    assert sign_ins.renew(TokenForm(refresh_token=token), "svc-2") is None


def test_a_member_who_left_is_not_renewed(fake: FakeIgni, sign_ins: SignIns) -> None:
    token = sign_ins.hold(held_by(sign_ins, user_id="u-max"))
    fake.directory.organisations[ORG].deactivate("u-max")

    assert sign_ins.renew(TokenForm(refresh_token=token), "svc-1") is None


def test_ending_a_sign_in_ends_each_of_its_tokens_and_nobody_elses(sign_ins: SignIns) -> None:
    ada = held_by(sign_ins, user_id="u-ada")
    max_ = held_by(sign_ins, user_id="u-max")
    first, second = sign_ins.hold(ada), sign_ins.hold(ada)
    kept = sign_ins.hold(max_)

    sign_ins.end(ada)

    assert sign_ins.held(first) is None and sign_ins.held(second) is None
    assert sign_ins.held(kept) == max_


def test_every_token_is_distinct_and_reset_forgets_codes_and_tokens(
    fake: FakeIgni, sign_ins: SignIns
) -> None:
    held = held_by(sign_ins)
    tokens = {sign_ins.hold(held) for _ in range(3)}
    sign_ins.authorize(location(fake), user_id="u-ada", org_id=ORG)

    sign_ins.reset()

    assert len(tokens) == 3 and all(t.startswith("refresh-") for t in tokens)
    assert sign_ins.codes == {} and sign_ins.refresh == {}


def test_a_held_refresh_describes_its_grant_in_the_schema() -> None:
    described = HeldRefresh.model_fields["grant"].description

    assert described == "The sign-in it belongs to: what a revocation ends."

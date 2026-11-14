"""The client assertion verifier: what proves a client, and what proves nobody.

Driven directly with the registry it checks against, so each rule of
RFC 7523 as igni applies it is one assertion: the five-minute limit and
its edges, each claim that must be there, who it is addressed to and
signed by, which refusal wins, and what the error body says.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import jwt
import pytest

from igni_service.crypto import RsaKeyPair
from igni_service.testing import FakeIgni, ManualClock
from igni_service.testing_assertions import (
    MAX_ASSERTION_LIFETIME,
    AssertionResult,
    ClientAssertionVerifier,
)
from igni_service.testing_clients import ClientState, FakeClientRegistry
from igni_service.testing_wire import IgniAddresses, TokenForm
from igni_service.urls import IgniPaths

APP = "app-bot"
ADDRESSES = IgniAddresses()


class Scene:
    """A verifier, its registry and clock, and one registered app with its key."""

    def __init__(self, *, require_approval: bool = False) -> None:
        self.clock = ManualClock()
        self.clients = FakeClientRegistry()
        self.pair = RsaKeyPair.generate()
        self.clients.add_app(APP, "org-1", "Bot", self.pair)
        self.verifier = ClientAssertionVerifier(
            addresses=ADDRESSES,
            clock=self.clock,
            clients=self.clients,
            require_approval=require_approval,
        )

    def claims(self, **changes: Any) -> dict[str, Any]:
        now = int(self.clock.wall())
        claims: dict[str, Any] = {
            "iss": APP,
            "sub": APP,
            "aud": FakeIgni.ISSUER,
            "iat": now,
            "exp": now + 60,
            "jti": uuid.uuid4().hex,
        }
        claims.update(changes)
        return {key: value for key, value in claims.items() if value is not ...}

    def verify(self, assertion: str) -> AssertionResult:
        return self.verifier.verify(TokenForm(client_assertion=assertion))

    def verify_claims(self, **changes: Any) -> AssertionResult:
        return self.verify(self.pair.sign_jwt(self.claims(**changes)))


@pytest.fixture
def scene() -> Scene:
    return Scene()


def proves_nobody(result: AssertionResult) -> bool:
    return result == AssertionResult()


def test_a_good_assertion_proves_the_client_it_names(scene: Scene) -> None:
    result = scene.verify_claims()

    assert result.client is scene.clients.get(APP)
    assert (result.refusal, result.client_state) == (None, None)


@pytest.mark.parametrize("path", ["", IgniPaths.TOKEN, IgniPaths.REVOKE])
def test_an_assertion_may_be_addressed_to_the_issuer_or_either_endpoint(
    scene: Scene, path: str
) -> None:
    assert scene.verify_claims(aud=f"{FakeIgni.ISSUER}{path}").client is not None


def test_an_assertion_may_live_exactly_five_minutes_and_not_a_second_more(scene: Scene) -> None:
    now = int(scene.clock.wall())

    assert MAX_ASSERTION_LIFETIME == 300
    assert scene.verify_claims(exp=now + 300).client is not None
    assert proves_nobody(scene.verify_claims(exp=now + 301))


@pytest.mark.parametrize("ahead", [0, -1, -3600])
def test_an_assertion_alive_for_no_time_proves_nobody(scene: Scene, ahead: int) -> None:
    assert proves_nobody(scene.verify_claims(exp=int(scene.clock.wall()) + ahead))


def test_the_lifetime_is_counted_from_the_fakes_clock_not_from_iat(scene: Scene) -> None:
    signed = scene.pair.sign_jwt(scene.claims(iat=0, exp=int(scene.clock.wall()) + 100))

    assert scene.verify(signed).client is not None
    scene.clock.advance(100)
    assert proves_nobody(
        scene.verify(scene.pair.sign_jwt(scene.claims(iat=0, exp=int(scene.clock.wall()) - 1)))
    )


@pytest.mark.parametrize("missing", ["exp", "jti", "sub"])
def test_an_assertion_without_a_required_claim_proves_nobody(scene: Scene, missing: str) -> None:
    assert proves_nobody(scene.verify_claims(**{missing: ...}))


def test_an_assertion_without_an_issuer_names_no_client(scene: Scene) -> None:
    assert proves_nobody(scene.verify_claims(iss=...))


def test_the_subject_must_be_the_client(scene: Scene) -> None:
    assert proves_nobody(scene.verify_claims(sub="someone-else"))


def test_the_audience_must_be_igni(scene: Scene) -> None:
    assert proves_nobody(scene.verify_claims(aud="https://not-igni.test"))
    assert proves_nobody(scene.verify_claims(aud=...))
    assert proves_nobody(scene.verify_claims(aud=f"{FakeIgni.ISSUER}/v1/other"))


def test_the_issuer_must_be_a_registered_client(scene: Scene) -> None:
    assert proves_nobody(scene.verify_claims(iss="nobody", sub="nobody"))
    assert proves_nobody(scene.verify_claims(iss="", sub=""))
    assert proves_nobody(scene.verify_claims(iss="пользователь", sub="пользователь"))


def test_an_assertion_signed_with_another_key_proves_nobody(scene: Scene) -> None:
    other = RsaKeyPair.generate()

    assert proves_nobody(scene.verify(other.sign_jwt(scene.claims())))


def test_an_assertion_signed_with_another_algorithm_proves_nobody(scene: Scene) -> None:
    hmac = jwt.encode(scene.claims(), "x" * 64, algorithm="HS256")
    unsigned = jwt.encode(scene.claims(), "", algorithm="none")

    assert proves_nobody(scene.verify(hmac))
    assert proves_nobody(scene.verify(unsigned))


@pytest.mark.parametrize("garbage", ["", "not a jwt", "a.b.c", "....", "é"])
def test_something_that_is_not_a_jwt_proves_nobody(scene: Scene, garbage: str) -> None:
    assert proves_nobody(scene.verify(garbage))


def test_a_jti_is_used_once_and_each_new_one_is_taken(scene: Scene) -> None:
    signed = scene.pair.sign_jwt(scene.claims(jti="one"))

    assert scene.verify(signed).client is not None
    assert proves_nobody(scene.verify(signed))
    assert scene.verify_claims(jti="two").client is not None
    assert scene.verifier.jtis == {"one", "two"}


def test_a_jti_is_remembered_even_when_the_assertion_expires_and_the_fake_resets() -> None:
    fake = FakeIgni(clock=ManualClock())
    pair = RsaKeyPair.generate()
    fake.clients.add_app(APP, "org-1", "Bot", pair)
    now = int(fake.clock.wall())
    signed = pair.sign_jwt(
        {"iss": APP, "sub": APP, "aud": FakeIgni.ISSUER, "exp": now + 60, "jti": "j"}
    )
    verifier = fake.oauth.verifier

    assert verifier.verify(TokenForm(client_assertion=signed)).client is not None
    fake.reset()
    assert proves_nobody(verifier.verify(TokenForm(client_assertion=signed)))


def test_a_refused_assertion_does_not_spend_its_jti(scene: Scene) -> None:
    assert proves_nobody(scene.verify_claims(jti="j", sub="someone-else"))

    assert scene.verify_claims(jti="j").client is not None


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": "soon"},
        {"exp": [1]},
        {"exp": None},
        {"exp": {"at": 1}},
        {"jti": ["a"]},
        {"jti": {"a": 1}},
        {"jti": 5},
        {"exp": True},
        {"jti": None},
    ],
    ids=lambda changes: json.dumps(changes),
)
def test_an_assertion_whose_exp_or_jti_is_the_wrong_kind_of_thing_proves_nobody(
    scene: Scene, changes: dict[str, Any]
) -> None:
    assert proves_nobody(scene.verify_claims(**changes))


def test_a_revoked_client_is_refused_in_igni_s_words_with_its_state(scene: Scene) -> None:
    scene.clients.revoke(APP)

    result = scene.verify_claims()

    assert result == AssertionResult(
        refusal="this client has been revoked", client_state=ClientState.REVOKED
    )


def test_a_client_is_refused_as_revoked_before_its_assertion_is_looked_at(scene: Scene) -> None:
    scene.clients.revoke(APP)

    result = scene.verify(scene.pair.sign_jwt(scene.claims(sub="someone-else")))

    assert result.client_state is ClientState.REVOKED


def test_a_pending_client_is_refused_only_when_approval_is_required() -> None:
    required = Scene(require_approval=True)
    required.clients.get(APP).state = ClientState.PENDING  # type: ignore[union-attr]
    lax = Scene(require_approval=False)
    lax.clients.get(APP).state = ClientState.PENDING  # type: ignore[union-attr]

    assert required.verify_claims() == AssertionResult(
        refusal="this client is waiting for a super admin to approve it",
        client_state=ClientState.PENDING,
    )
    assert lax.verify_claims().client is lax.clients.get(APP)


def test_an_approved_client_passes_when_approval_is_required() -> None:
    scene = Scene(require_approval=True)

    assert scene.verify_claims().client is not None


def test_a_revoked_client_wins_over_a_pending_one() -> None:
    """Revoked is checked first: `revoke` after `pending` says revoked."""
    scene = Scene(require_approval=True)
    client = scene.clients.get(APP)
    assert client is not None
    client.state = ClientState.PENDING
    assert scene.verify_claims().client_state is ClientState.PENDING

    scene.clients.revoke(APP)

    assert scene.verify_claims().client_state is ClientState.REVOKED


def test_an_older_igni_names_no_state_but_still_says_it_in_words(scene: Scene) -> None:
    scene.verifier.names_client_state = False
    scene.clients.revoke(APP)

    assert scene.verify_claims() == AssertionResult(refusal="this client has been revoked")


def test_a_refusal_with_no_reason_is_a_bare_401_invalid_client() -> None:
    response = AssertionResult().to_error()

    assert response.status_code == 401
    assert json.loads(response.content) == {"error": "invalid_client"}


def test_a_refusal_with_a_reason_and_a_state_says_both() -> None:
    response = AssertionResult(refusal="words", client_state=ClientState.PENDING).to_error()

    assert response.status_code == 401
    assert json.loads(response.content) == {
        "error": "invalid_client",
        "error_description": "words",
        "client_state": "pending",
    }

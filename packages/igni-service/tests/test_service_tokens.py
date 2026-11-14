"""The service's own tokens: one per organisation, renewed early, with fresh assertions."""

from __future__ import annotations

import json

import jwt
import pytest

from igni_service import (
    IgniService,
    IgniUnavailable,
    ServiceNotApproved,
    ServiceRevoked,
    testing_assertions,
)
from igni_service.testing import FakeIgni, ManualClock
from igni_service.token_endpoint import GrantRefused
from igni_service.urls import IgniPaths

from .conftest import ORG, OTHER_ORG


async def test_a_token_is_kept_per_organisation(igni: IgniService, fake: FakeIgni) -> None:
    first = await igni.outbound.tokens.token(ORG)
    again = await igni.outbound.tokens.token(ORG)
    other = await igni.outbound.tokens.token(OTHER_ORG)

    assert first == again
    assert other != first
    forms = [seen.form() for seen in fake.traffic.requests_to(IgniPaths.TOKEN)]
    assert [form.organisation for form in forms] == [ORG, OTHER_ORG]
    assert all(form.grant_type == "client_credentials" for form in forms)


async def test_a_token_is_renewed_a_minute_before_it_expires(
    igni: IgniService, fake: FakeIgni, clock: ManualClock
) -> None:
    first = await igni.outbound.tokens.token(ORG)
    clock.advance(600 - 61)
    assert await igni.outbound.tokens.token(ORG) == first

    clock.advance(2)

    assert await igni.outbound.tokens.token(ORG) != first
    assert len(fake.traffic.requests_to(IgniPaths.TOKEN)) == 2


async def test_each_assertion_is_signed_by_the_service_key_for_igni_and_used_once(
    igni: IgniService, fake: FakeIgni, clock: ManualClock
) -> None:
    await igni.outbound.tokens.token(ORG)
    await igni.outbound.tokens.token(OTHER_ORG)

    assertions = [
        seen.form().client_assertion for seen in fake.traffic.requests_to(IgniPaths.TOKEN)
    ]
    client_id = await igni.connection.registration.client_id()
    claims = [jwt.decode(a, options={"verify_signature": False}) for a in assertions]
    headers = [jwt.get_unverified_header(a) for a in assertions]
    assert len({c["jti"] for c in claims}) == 2
    for claim, header in zip(claims, headers, strict=True):
        assert claim["iss"] == claim["sub"] == client_id
        assert claim["aud"] == FakeIgni.ISSUER
        assert 0 < claim["exp"] - claim["iat"] <= 300
        assert header == {"alg": "RS256", "kid": await igni.thumbprint(), "typ": "JWT"}


async def test_a_token_igni_stops_honouring_is_replaced_once(
    igni: IgniService, fake: FakeIgni
) -> None:
    await igni.host(ORG).directory.organisation()
    fake.oauth.bearers.expire_service()

    organisation = await igni.host(ORG).directory.organisation()

    assert organisation.org_id == ORG
    assert len(fake.traffic.requests_to(IgniPaths.TOKEN)) == 2


async def test_a_revoked_service_gets_no_token(igni: IgniService, fake: FakeIgni) -> None:
    await igni.outbound.tokens.token(ORG)
    fake.clients.revoke()
    igni.outbound.tokens.forget()

    with pytest.raises(IgniUnavailable, match="invalid_client"):
        await igni.outbound.tokens.token(ORG)


async def test_an_unapproved_service_is_told_so_in_igni_words(clock: ManualClock) -> None:
    fake = FakeIgni(clock=clock, require_approval=True)
    igni = fake.service()

    with pytest.raises(IgniUnavailable, match="invalid_client"):
        await igni.outbound.tokens.token(ORG)

    fake.clients.approve()
    assert await igni.outbound.tokens.token(ORG)


async def test_a_service_waiting_for_approval_is_told_it_is_not_approved(
    clock: ManualClock,
) -> None:
    """Not "unavailable": nothing will change by retrying until a super admin approves it."""
    fake = FakeIgni(clock=clock, require_approval=True)
    igni = fake.service()
    await igni.connection.registration.register()

    with pytest.raises(ServiceNotApproved, match="waiting for a super admin") as refused:
        await igni.outbound.tokens.token(ORG)

    # Every `except IgniUnavailable` written before still catches it.
    assert isinstance(refused.value, IgniUnavailable)
    # igni named the state, so the registration was not asked again.
    assert len(fake.traffic.requests_to(IgniPaths.CLIENTS)) == 1


async def test_a_revoked_service_is_told_it_is_revoked(igni: IgniService, fake: FakeIgni) -> None:
    await igni.outbound.tokens.token(ORG)
    fake.clients.revoke()
    igni.outbound.tokens.forget()

    with pytest.raises(ServiceRevoked, match="revoked") as refused:
        await igni.outbound.tokens.token(ORG)

    assert isinstance(refused.value, IgniUnavailable)
    assert len(fake.traffic.requests_to(IgniPaths.CLIENTS)) == 1


def swap_igni_words(monkeypatch: pytest.MonkeyPatch) -> None:
    """igni saying each state in the other's words: the words must decide nothing."""
    waiting, revoked = testing_assertions.WAITING, testing_assertions.REVOKED
    monkeypatch.setattr(testing_assertions, "WAITING", revoked)
    monkeypatch.setattr(testing_assertions, "REVOKED", waiting)


async def test_the_state_is_read_from_igni_s_field_not_its_words(
    clock: ManualClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    swap_igni_words(monkeypatch)
    fake = FakeIgni(clock=clock, require_approval=True)
    igni = fake.service()

    with pytest.raises(ServiceNotApproved, match="has been revoked"):
        await igni.outbound.tokens.token(ORG)

    fake.clients.revoke()
    with pytest.raises(ServiceRevoked, match="waiting for a super admin"):
        await igni.outbound.tokens.token(ORG)


@pytest.mark.parametrize("revoke", [False, True])
async def test_an_igni_that_names_no_state_is_igni_unavailable(
    clock: ManualClock, monkeypatch: pytest.MonkeyPatch, revoke: bool
) -> None:
    """Without `client_state` the state is said only in words, which decide
    nothing, and the registration is not asked again."""
    swap_igni_words(monkeypatch)
    fake = FakeIgni(clock=clock, require_approval=True)
    fake.oauth.verifier.names_client_state = False
    igni = fake.service()
    await igni.connection.registration.register()
    if revoke:
        fake.clients.revoke()

    with pytest.raises(IgniUnavailable) as raised:
        await igni.outbound.tokens.token(ORG)

    assert type(raised.value) is IgniUnavailable
    assert len(fake.traffic.requests_to(IgniPaths.CLIENTS)) == 1


def refused(**body: str) -> GrantRefused:
    return GrantRefused(401, json.dumps(body))


async def test_a_refusal_that_is_not_invalid_client_is_igni_unavailable(
    igni: IgniService, fake: FakeIgni
) -> None:
    await igni.connection.registration.register()
    fake.traffic.fail(IgniPaths.TOKEN, 401)

    with pytest.raises(IgniUnavailable) as raised:
        await igni.outbound.tokens.token(ORG)

    assert type(raised.value) is IgniUnavailable
    assert len(fake.traffic.requests_to(IgniPaths.CLIENTS)) == 1, "not asked: not about the client"


async def test_a_state_igni_names_that_the_sdk_does_not_know_is_igni_unavailable(
    igni: IgniService,
) -> None:
    exc = refused(error="invalid_client", client_state="suspended")

    assert type(igni.outbound.tokens.refusal(exc)) is IgniUnavailable


@pytest.mark.parametrize(
    ("state", "raised"), [("pending", ServiceNotApproved), ("revoked", ServiceRevoked)]
)
async def test_the_client_state_beside_invalid_client_names_the_error(
    igni: IgniService, state: str, raised: type[IgniUnavailable]
) -> None:
    exc = refused(error="invalid_client", client_state=state)

    assert type(igni.outbound.tokens.refusal(exc)) is raised


async def test_a_client_state_beside_another_error_decides_nothing(igni: IgniService) -> None:
    exc = refused(error="invalid_grant", client_state="revoked")

    assert type(igni.outbound.tokens.refusal(exc)) is IgniUnavailable


async def test_invalid_client_naming_no_state_is_igni_unavailable(igni: IgniService) -> None:
    """`invalid_client` with no `client_state` is some other refusal (a
    replayed assertion, a moved key), whatever igni's words say."""
    exc = refused(error="invalid_client", error_description="this client has been revoked")

    assert type(igni.outbound.tokens.refusal(exc)) is IgniUnavailable


@pytest.mark.parametrize("body", ["", "not json", "[1, 2]", '{"error": 7}'])
async def test_a_refusal_body_that_is_not_rfc_6749_reads_as_no_error(
    igni: IgniService, body: str
) -> None:
    exc = GrantRefused(401, body)

    assert exc.refusal.error == "" and exc.refusal.client_state is None
    assert type(igni.outbound.tokens.refusal(exc)) is IgniUnavailable


async def test_a_token_names_one_organisation(igni: IgniService) -> None:
    with pytest.raises(IgniUnavailable, match="one organisation"):
        await igni.outbound.tokens.token("")

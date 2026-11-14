"""The verifier's own rules, read from tokens signed with exactly the claims a test names."""

from __future__ import annotations

from typing import Any

import pytest

from igni_service import App, CallerKind, Person, Space
from igni_service.testing import FakeIgni, ManualClock, SpaceClaims
from igni_service.tokens import PEOPLE_ONLY, TokenRefused, TokenUse, TokenVerifier

from .conftest import ORG


def signed(fake: FakeIgni, clock: ManualClock, **changes: Any) -> str:
    """A person's token with these claims, `None` taking a claim away."""
    now = int(clock.wall())
    claims: dict[str, Any] = {
        "iss": fake.signer.addresses.issuer,
        "sub": "u-ada",
        "aud": fake.signer.addresses.service_url,
        "token_use": "user",
        "iat": now,
        "exp": now + 600,
        "org": ORG,
    }
    claims.update(changes)
    claims = {k: v for k, v in claims.items() if v is not None}
    return fake.signer.keys.pair.sign_jwt(claims, kid=fake.signer.keys.kid)


@pytest.fixture
def verifier(fake: FakeIgni) -> TokenVerifier:
    return fake.service().verifier


async def reason_of(verifier: TokenVerifier, token: str, use: str = "user") -> str:
    with pytest.raises(TokenRefused) as refused:
        await verifier.claims(token, use=use)
    return refused.value.reason


async def test_a_token_is_read_with_or_without_the_bearer_prefix_and_around_whitespace(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    token = signed(fake, clock)

    for form in (token, f"Bearer {token}", f"  {token}\n", f"Bearer  {token} "):
        assert (await verifier.claims(form, use="user"))["sub"] == "u-ada"


@pytest.mark.parametrize("token", [None, "", "   ", "Bearer ", "Bearer", "a.b.c"])
async def test_nothing_or_something_that_is_not_a_jwt_is_refused_as_such(
    verifier: TokenVerifier, token: str | None
) -> None:
    reason = await reason_of(verifier, token)  # type: ignore[arg-type]

    assert reason == "the token is not a JWT"


@pytest.mark.parametrize("claim", ["sub", "exp", "iat", "iss", "aud"])
async def test_each_missing_required_claim_is_named(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock, claim: str
) -> None:
    reason = await reason_of(verifier, signed(fake, clock, **{claim: None}))

    assert reason == f"the token has no {claim!r} claim"


async def test_a_token_expires_at_its_exp_not_after(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    token = signed(fake, clock, exp=int(clock.wall()) + 10)

    clock.advance(9)
    assert (await verifier.claims(token, use="user"))["sub"] == "u-ada"
    clock.advance(1)

    assert await reason_of(verifier, token) == "the token has expired"


async def test_an_iat_up_to_the_leeway_ahead_is_accepted_and_beyond_it_is_not(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    now = int(clock.wall())
    edge = signed(fake, clock, iat=now + int(TokenVerifier.LEEWAY))
    over = signed(fake, clock, iat=now + int(TokenVerifier.LEEWAY) + 1)

    assert TokenVerifier.LEEWAY == 60.0
    assert (await verifier.claims(edge, use="user"))["sub"] == "u-ada"
    assert await reason_of(verifier, over) == (
        "the token was issued in the future; check this machine's clock"
    )


@pytest.mark.parametrize(
    "changes",
    [{"exp": "soon"}, {"iat": "yesterday"}, {"exp": [1]}, {"iat": {"a": 1}}],
    ids=["exp-text", "iat-text", "exp-list", "iat-object"],
)
async def test_a_time_that_is_not_a_number_is_refused(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock, changes: dict[str, Any]
) -> None:
    reason = await reason_of(verifier, signed(fake, clock, **changes))

    assert reason == "the token's exp or iat is not a number"


async def test_the_kind_may_be_one_string_or_any_of_a_collection(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    token = signed(fake, clock)

    assert (await verifier.claims(token, use=["app", "user"]))["token_use"] == "user"
    assert (await verifier.claims(token, use={"user"}))["token_use"] == "user"
    reason = await reason_of(verifier, token, use="app")
    assert reason == "the wrong kind of token: token_use 'user', and this takes app"
    with pytest.raises(TokenRefused) as several:
        await verifier.claims(token, use=("space", "app"))
    assert several.value.reason.endswith("and this takes app or space")


async def test_a_token_without_a_kind_is_refused(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    reason = await reason_of(verifier, signed(fake, clock, token_use=None))

    assert reason.startswith("the wrong kind of token: token_use None")


async def test_a_refusal_has_a_default_reason_and_carries_the_given_one() -> None:
    assert TokenRefused().reason == "the token is not one this service accepts"
    assert str(TokenRefused()) == "the token is not one this service accepts"
    assert TokenRefused("because").reason == "because"


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"sub": ""}, "no person, or no organisation"),
        ({"org": ""}, "no person, or no organisation"),
        ({"org": None}, "no person, or no organisation"),
    ],
)
async def test_a_person_needs_an_id_and_an_organisation(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock, change: dict[str, Any], said: str
) -> None:
    token = signed(fake, clock, **change)

    with pytest.raises(TokenRefused, match=said):
        await verifier.person(token)
    with pytest.raises(TokenRefused, match=said):
        await verifier.caller(token)


async def test_accept_may_be_given_as_plain_strings_and_must_name_real_kinds(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    app = fake.signer.app_token("reporter", org_id=ORG, name="Reporter")

    caller = await verifier.caller(app, accept=["app"])  # type: ignore[list-item]
    assert caller == App(app_id="reporter", org_id=ORG, name="Reporter")
    with pytest.raises(ValueError, match="not a valid CallerKind"):
        await verifier.caller(app, accept=["robot"])  # type: ignore[list-item]


async def test_accepting_nobody_refuses_everybody(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    with pytest.raises(TokenRefused):
        await verifier.caller(signed(fake, clock), accept=[])


async def test_a_person_is_a_caller_by_default_and_an_app_is_not(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    person = await verifier.caller(signed(fake, clock, name="Ada", org_role="admin"))
    assert person == Person(user_id="u-ada", org_id=ORG, name="Ada", org_role="admin")
    with pytest.raises(TokenRefused, match="wrong kind of token"):
        await verifier.caller(fake.signer.app_token("reporter", org_id=ORG))


async def test_an_app_and_a_space_must_name_what_they_are_for(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    everybody = frozenset(CallerKind)
    no_app = signed(fake, clock, sub="", token_use="app")
    no_org = signed(fake, clock, token_use="app", org="")
    no_space = signed(fake, clock, sub="", token_use="space", app="r", external_id="c")
    no_space_org = signed(fake, clock, token_use="space", app="r", org="")
    no_parent = signed(fake, clock, token_use="space", org=ORG)

    for token in (no_app, no_org):
        with pytest.raises(TokenRefused, match="names no app, or no organisation"):
            await verifier.caller(token, accept=everybody)
    for token in (no_space, no_space_org, no_parent):
        with pytest.raises(TokenRefused, match="names no space, app or organisation"):
            await verifier.caller(token, accept=everybody)


async def test_an_igni_token_must_come_from_igni_for_an_organisation(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    issuer = fake.signer.addresses.issuer

    call = await verifier.igni_call(signed(fake, clock, sub=issuer, token_use="igni"))
    assert call.org_id == ORG
    for token in (
        signed(fake, clock, sub=issuer, token_use="igni", org=None),
        signed(fake, clock, sub="u-ada", token_use="igni"),
    ):
        with pytest.raises(TokenRefused, match="not igni's own call for an organisation"):
            await verifier.igni_call(token)


class Revoked:
    """A revocation feed that has revoked everything it is asked about."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def check(self, claims: dict[str, Any]) -> None:
        self.asked.append(claims["token_use"])
        raise TokenRefused("the token was revoked")


async def test_revocation_is_asked_of_every_kind_of_token_but_igni_own(
    verifier: TokenVerifier, fake: FakeIgni, clock: ManualClock
) -> None:
    feed = Revoked()
    verifier.revocations = feed  # type: ignore[assignment]
    issuer = fake.signer.addresses.issuer
    space = fake.signer.space_token("sp-1", SpaceClaims(org=ORG, app="r", external_id="c"))

    for token, use in (
        (signed(fake, clock), "user"),
        (fake.signer.app_token("reporter", org_id=ORG), "app"),
        (space, "space"),
    ):
        assert await reason_of(verifier, token, use=use) == "the token was revoked"
    igni = await verifier.claims(signed(fake, clock, sub=issuer, token_use="igni"), use="igni")

    assert feed.asked == ["user", "app", "space"]
    assert igni["sub"] == issuer


def test_the_token_use_claims_and_their_kinds() -> None:
    assert (TokenUse.USER, TokenUse.IGNI, TokenUse.APP, TokenUse.SPACE) == (
        "user",
        "igni",
        "app",
        "space",
    )
    assert CallerKind.PERSON.token_use == "user"
    assert CallerKind.APP.token_use == "app"
    assert CallerKind.SPACE.token_use == "space"
    assert frozenset({CallerKind.PERSON}) == PEOPLE_ONLY
    assert Person(user_id="u", org_id="o").kind is CallerKind.PERSON


def test_a_person_from_claims_fills_what_is_missing_and_reads_only_true_as_super_admin() -> None:
    bare = Person.from_claims({"sub": "u", "org": "o"})
    assert bare == Person(user_id="u", org_id="o")
    assert (bare.org_role, bare.org_name, bare.super_admin) == ("member", "", False)

    nones = Person.from_claims(
        {"sub": "u", "org": "o", "org_role": None, "name": None, "email": None}
    )
    assert nones == bare
    for other in ("true", 1, "yes", [True]):
        assert (
            Person.from_claims({"sub": "u", "org": "o", "super_admin": other}).super_admin is False
        )
    assert Person.from_claims({"sub": "u", "org": "o", "super_admin": True}).super_admin is True
    assert Person.from_claims({"sub": 7, "org": "o"}).user_id == "7"
    assert Person.from_claims({}).user_id == ""


def test_a_person_is_an_org_admin_only_as_admin_and_shows_a_name_or_an_email() -> None:
    assert Person(user_id="u", org_id="o", org_role="admin").is_org_admin is True
    assert Person(user_id="u", org_id="o").is_org_admin is False
    assert Person(user_id="u", org_id="o", org_role="owner").is_org_admin is False
    named = Person(user_id="u", org_id="o", name="Ada", email="a@x.test")
    assert named.display_name == "Ada"
    assert Person(user_id="u", org_id="o", email="a@x.test").display_name == "a@x.test"
    assert Person(user_id="u", org_id="o").display_name == ""


def test_an_app_and_a_space_from_claims() -> None:
    assert App.from_claims({"sub": "a", "org": "o", "name": "N"}) == App(
        app_id="a", org_id="o", name="N"
    )
    assert App.from_claims({}) == App(app_id="", org_id="")
    space = Space.from_claims({"sub": "s", "org": "o", "app": "a", "external_id": "x"})
    assert space == Space(space_id="s", org_id="o", app_id="a", external_id="x")
    assert Space.from_claims({"sub": "s", "external_id": None}).external_id == ""


def test_the_callers_are_frozen() -> None:
    for caller in (
        Person(user_id="u", org_id="o"),
        App(app_id="a", org_id="o"),
        Space(space_id="s", org_id="o", app_id="a"),
    ):
        with pytest.raises(ValueError, match="frozen"):
            caller.org_id = "other"

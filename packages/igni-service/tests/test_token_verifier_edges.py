"""TokenVerifier read directly: what it refuses and says, claim by claim, and the models it builds."""

from __future__ import annotations

from typing import Any

import pytest

from igni_service import App, CallerKind, IgniService, Person, Space
from igni_service.testing import FakeIgni, ManualClock
from igni_service.tokens import PEOPLE_ONLY, IgniCall, TokenRefused, TokenUse, TokenVerifier

from .conftest import ORG

LIFETIME = 600


def mint(fake: FakeIgni, clock: ManualClock, **changes: Any) -> str:
    """A user token signed with igni's own key, its claims set claim by claim."""
    now = int(clock.wall())
    payload: dict[str, Any] = {
        "iss": fake.signer.addresses.issuer,
        "sub": "u-ada",
        "aud": fake.signer.addresses.service_url,
        "token_use": "user",
        "org": ORG,
        "iat": now,
        "exp": now + LIFETIME,
    }
    payload |= changes
    return fake.signer.keys.pair.sign_jwt(payload, kid=fake.signer.keys.kid)


def mint_without(fake: FakeIgni, clock: ManualClock, claim: str) -> str:
    """The same token with one claim left out."""
    now = int(clock.wall())
    payload: dict[str, Any] = {
        "iss": fake.signer.addresses.issuer,
        "sub": "u-ada",
        "aud": fake.signer.addresses.service_url,
        "token_use": "user",
        "org": ORG,
        "iat": now,
        "exp": now + LIFETIME,
    }
    del payload[claim]
    return fake.signer.keys.pair.sign_jwt(payload, kid=fake.signer.keys.kid)


@pytest.fixture
def verifier(fake: FakeIgni) -> TokenVerifier:
    return fake.service().verifier


async def reason(verifier: TokenVerifier, token: str, use: str = "user") -> str:
    with pytest.raises(TokenRefused) as refused:
        await verifier.claims(token, use=use)
    return refused.value.reason


class TestTheClaimsAToken:
    @pytest.mark.parametrize("missing", ["exp", "iat", "sub", "iss", "aud"])
    async def test_a_missing_required_claim_is_named(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier, missing: str
    ) -> None:
        token = mint_without(fake, clock, missing)

        assert await reason(verifier, token) == f"the token has no {missing!r} claim"

    @pytest.mark.parametrize("bad", ["soon", "", [1], {}])
    @pytest.mark.parametrize("claim", ["exp", "iat"])
    async def test_an_exp_or_iat_that_is_not_a_number_is_refused(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier, claim: str, bad: object
    ) -> None:
        token = mint(fake, clock, **{claim: bad})

        assert await reason(verifier, token) == "the token's exp or iat is not a number"

    async def test_a_token_expires_at_its_exp_not_after_it(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        token = mint(fake, clock)

        clock.advance(LIFETIME - 1)
        assert (await verifier.claims(token, use="user"))["sub"] == "u-ada"
        clock.advance(1)
        assert await reason(verifier, token) == "the token has expired"

    async def test_iat_may_be_a_minute_ahead_and_no_more(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        now = int(clock.wall())
        within = mint(fake, clock, iat=now + 60)
        beyond = mint(fake, clock, iat=now + 61)

        assert (await verifier.claims(within, use="user"))["sub"] == "u-ada"
        assert "issued in the future" in await reason(verifier, beyond)
        assert TokenVerifier.LEEWAY == 60.0

    async def test_numbers_written_as_text_are_numbers(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        now = int(clock.wall())
        token = mint(fake, clock, exp=str(now + LIFETIME), iat=str(now))

        assert (await verifier.claims(token, use="user"))["sub"] == "u-ada"

    async def test_nbf_is_not_checked(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        token = mint(fake, clock, nbf=int(clock.wall()) + 100_000)

        assert (await verifier.claims(token, use="user"))["sub"] == "u-ada"

    @pytest.mark.parametrize("value", ["", "refresh", "USER", 1])
    async def test_a_token_use_that_is_not_the_kind_asked_for_is_the_wrong_kind(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier, value: object
    ) -> None:
        token = mint(fake, clock, token_use=value)

        assert (await reason(verifier, token)).startswith("the wrong kind of token: token_use")

    async def test_a_token_missing_its_use_names_none(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        token = mint_without(fake, clock, "token_use")

        assert await reason(verifier, token) == (
            "the wrong kind of token: token_use None, and this takes user"
        )

    async def test_several_kinds_may_be_asked_for_and_all_are_named(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        both = await verifier.claims(mint(fake, clock, token_use="app"), use=["user", "app"])
        said = await reason(verifier, mint(fake, clock, token_use="space"), use=["user", "app"])  # type: ignore[arg-type]

        assert both["token_use"] == "app"
        assert said.endswith("and this takes app or user")

    @pytest.mark.parametrize("token", ["", "   ", "Bearer ", "Bearer    "])
    async def test_nothing_is_not_a_jwt(self, verifier: TokenVerifier, token: str) -> None:
        assert await reason(verifier, token) == "the token is not a JWT"

    async def test_none_is_nothing(self, verifier: TokenVerifier) -> None:
        assert await reason(verifier, None) == "the token is not a JWT"  # type: ignore[arg-type]

    @pytest.mark.parametrize("wrap", ["Bearer {}", "Bearer {}  ", "  {}  "])
    async def test_the_bearer_prefix_and_blanks_are_stripped(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier, wrap: str
    ) -> None:
        token = wrap.format(mint(fake, clock))

        assert (await verifier.claims(token, use="user"))["sub"] == "u-ada"

    async def test_a_truncated_token_is_not_a_jwt(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        token = mint(fake, clock)

        assert await reason(verifier, token[:-8]) == "the token is not a JWT"

    async def test_a_token_with_no_kid_is_not_signed_by_igni(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        now = int(clock.wall())
        payload = {
            "iss": fake.signer.addresses.issuer,
            "sub": "u-ada",
            "aud": fake.signer.addresses.service_url,
            "token_use": "user",
            "iat": now,
            "exp": now + LIFETIME,
        }
        import jwt

        token = jwt.encode(payload, fake.signer.keys.pair._private, algorithm="RS256")  # noqa: SLF001

        assert "not signed by igni" in await reason(verifier, token)

    async def test_an_audience_is_compared_as_the_string_igni_wrote(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        own = fake.signer.addresses.service_url
        for aud in (own + "/", own.upper()):
            said = await reason(verifier, mint(fake, clock, aud=aud))
            assert said == f"the token is for another audience; this service's is {own}"


class TestWhoACallerIs:
    async def test_the_kinds_say_the_token_use_they_carry(self) -> None:
        assert [kind.token_use for kind in CallerKind] == ["user", "app", "space"]
        assert (TokenUse.USER, TokenUse.IGNI, TokenUse.APP, TokenUse.SPACE) == (
            "user",
            "igni",
            "app",
            "space",
        )
        assert {CallerKind.PERSON} == PEOPLE_ONLY

    async def test_a_kind_that_is_none_is_a_value_error(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        with pytest.raises(ValueError, match="bogus"):
            await verifier.caller(mint(fake, clock), accept=["bogus"])  # type: ignore[list-item]

    async def test_a_kind_may_be_given_as_its_value(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        caller = await verifier.caller(mint(fake, clock), accept=["person"])  # type: ignore[list-item]

        assert isinstance(caller, Person)

    @pytest.mark.parametrize("gap", ["sub", "org"])
    async def test_a_person_without_an_id_or_organisation_is_refused(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier, gap: str
    ) -> None:
        token = mint(fake, clock, **{gap: ""})

        with pytest.raises(TokenRefused, match="names no person, or no organisation"):
            await verifier.caller(token)
        with pytest.raises(TokenRefused, match="names no person, or no organisation"):
            await verifier.person(token)

    @pytest.mark.parametrize("gap", ["sub", "org"])
    async def test_an_app_without_an_id_or_organisation_is_refused(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier, gap: str
    ) -> None:
        token = mint(fake, clock, token_use="app", **{gap: ""})

        with pytest.raises(TokenRefused, match="names no app, or no organisation"):
            await verifier.caller(token, accept={CallerKind.APP})

    @pytest.mark.parametrize("gap", ["sub", "org", "app"])
    async def test_a_space_without_an_id_app_or_organisation_is_refused(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier, gap: str
    ) -> None:
        token = mint(fake, clock, token_use="space", **{"app": "app-r", gap: ""})

        with pytest.raises(TokenRefused, match="names no space, app or organisation"):
            await verifier.caller(token, accept={CallerKind.SPACE})

    async def test_a_service_that_takes_apps_still_asks_for_each_kind_by_name(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        user = mint(fake, clock)
        space = mint(fake, clock, token_use="space", app="app-r")

        with pytest.raises(TokenRefused, match="token_use 'user', and this takes app"):
            await verifier.caller(user, accept={CallerKind.APP})
        with pytest.raises(TokenRefused, match="token_use 'space', and this takes app or user"):
            await verifier.caller(space, accept={CallerKind.APP, CallerKind.PERSON})


class TestIgniCalling:
    async def test_an_igni_token_for_an_organisation_is_igni_calling(
        self, fake: FakeIgni, verifier: TokenVerifier
    ) -> None:
        call = await verifier.igni_call(fake.signer.igni_token(ORG))

        assert call == IgniCall(org_id=ORG)

    async def test_an_igni_token_for_no_organisation_is_refused(
        self, fake: FakeIgni, verifier: TokenVerifier
    ) -> None:
        with pytest.raises(TokenRefused, match="igni's own call for an organisation"):
            await verifier.igni_call(fake.signer.igni_token(""))

    async def test_an_igni_token_whose_subject_is_not_igni_is_refused(
        self, fake: FakeIgni, clock: ManualClock, verifier: TokenVerifier
    ) -> None:
        token = mint(fake, clock, token_use="igni", sub="somebody-else")

        with pytest.raises(TokenRefused, match="igni's own call for an organisation"):
            await verifier.igni_call(token)

    async def test_a_person_token_is_not_igni(
        self, fake: FakeIgni, verifier: TokenVerifier
    ) -> None:
        with pytest.raises(TokenRefused, match="token_use 'user', and this takes igni"):
            await verifier.igni_call(fake.signer.person_token("u-ada", org_id=ORG))

    async def test_igni_calling_is_not_checked_against_the_revocations(
        self, fake: FakeIgni, service: IgniService | None = None
    ) -> None:
        class Revoked:
            seen: list[object] = []  # noqa: RUF012

            async def check(self, claims: dict[str, Any]) -> None:
                self.seen.append(claims["token_use"])
                raise TokenRefused("revoked")

        verifier = fake.service().verifier
        verifier.revocations = Revoked()  # type: ignore[assignment]

        assert (await verifier.igni_call(fake.signer.igni_token(ORG))).org_id == ORG
        with pytest.raises(TokenRefused, match="revoked"):
            await verifier.person(fake.signer.person_token("u-ada", org_id=ORG))
        assert Revoked.seen == ["user"]


class TestTheModelsOfWhoCalls:
    def test_a_person_from_a_bare_token_has_defaults(self) -> None:
        person = Person.from_claims({"sub": "u", "org": "o"})

        assert person == Person(
            user_id="u",
            org_id="o",
            org_name="",
            org_role="member",
            email="",
            name="",
            super_admin=False,
        )
        assert person.kind is CallerKind.PERSON
        assert not person.is_org_admin

    def test_missing_or_null_claims_are_empty_text_and_a_member(self) -> None:
        person = Person.from_claims(
            {
                "sub": None,
                "org": None,
                "org_name": None,
                "org_role": None,
                "email": None,
                "name": None,
            }
        )

        assert person.model_dump() == {
            "user_id": "",
            "org_id": "",
            "org_name": "",
            "org_role": "member",
            "email": "",
            "name": "",
            "super_admin": False,
        }

    @pytest.mark.parametrize("value", ["true", 1, "yes", None, [True], 1.0])
    def test_super_admin_is_only_ever_true(self, value: object) -> None:
        assert (
            Person.from_claims({"sub": "u", "org": "o", "super_admin": value}).super_admin is False
        )
        assert Person.from_claims({"sub": "u", "org": "o", "super_admin": True}).super_admin is True

    def test_only_the_admin_role_is_an_org_admin(self) -> None:
        assert Person.from_claims({"org_role": "admin"}).is_org_admin
        assert not Person.from_claims({"org_role": "Admin"}).is_org_admin
        assert not Person.from_claims({"org_role": "owner", "super_admin": True}).is_org_admin

    def test_a_display_name_is_the_name_else_the_email(self) -> None:
        assert Person(user_id="u", org_id="o", name="Ada", email="a@x").display_name == "Ada"
        assert Person(user_id="u", org_id="o", email="a@x").display_name == "a@x"
        assert Person(user_id="u", org_id="o").display_name == ""

    def test_claims_that_are_not_text_are_written_as_text(self) -> None:
        person = Person.from_claims({"sub": 42, "org": 7, "name": "Zoë ✓", "email": 1.5})

        assert (person.user_id, person.org_id, person.name, person.email) == (
            "42",
            "7",
            "Zoë ✓",
            "1.5",
        )

    def test_an_app_and_a_space_read_their_own_claims(self) -> None:
        app = App.from_claims({"sub": "a", "org": "o", "name": None})
        space = Space.from_claims({"sub": "s", "org": "o", "app": "a", "external_id": "ext"})

        assert app == App(app_id="a", org_id="o", name="")
        assert space == Space(space_id="s", org_id="o", app_id="a", external_id="ext")
        assert Space.from_claims({}) == Space(space_id="", org_id="", app_id="")

    def test_who_calls_cannot_be_changed_afterwards(self) -> None:
        for model in (
            Person(user_id="u", org_id="o"),
            App(app_id="a", org_id="o"),
            Space(space_id="s", org_id="o", app_id="a"),
            IgniCall(org_id="o"),
        ):
            with pytest.raises(ValueError, match="frozen"):
                model.org_id = "other"

    def test_a_refusal_has_a_default_reason_and_keeps_the_one_given(self) -> None:
        assert TokenRefused().reason == "the token is not one this service accepts"
        assert str(TokenRefused()) == "the token is not one this service accepts"
        assert TokenRefused("no").reason == "no"

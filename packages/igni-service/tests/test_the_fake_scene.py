"""Setting the scene with `FakeIgni`: `app`, `settings`, `service` and what `reset` keeps."""

from __future__ import annotations

import asyncio
import time

import pytest

from igni_service import IgniService
from igni_service.errors import IgniUnavailable
from igni_service.events import Producer
from igni_service.keystore import MemoryKeyStore
from igni_service.testing import FakeIgni, ManualClock, SettingsOverrides
from igni_service.testing_wire import IgniAddresses
from igni_service.tokens import CallerKind

from .conftest import ORG, bearer


class TestAnApp:
    async def test_an_app_in_an_organisation_the_fake_has_not_seen_creates_it(self) -> None:
        fake = FakeIgni()
        assert "org-new" not in fake.directory.organisations

        async with fake.app("app-bot", org_id="org-new", name="Bot") as app:
            token = await app.token()

        assert token.startswith("app-")
        organisation = fake.directory.organisations["org-new"]
        assert (organisation.organisation.name, organisation.organisation.slug) == (
            "org-new",
            "org-new",
        )

    async def test_an_app_in_an_organisation_that_exists_leaves_it_as_it_is(
        self, fake: FakeIgni
    ) -> None:
        fake.app("app-bot", org_id=ORG)

        assert fake.directory.organisations[ORG].organisation.name == "Acme"

    async def test_an_app_is_registered_approved_under_its_id_and_name(
        self, fake: FakeIgni
    ) -> None:
        fake.app("app-bot", org_id=ORG, name="Bot")
        fake.app("app-plain", org_id=ORG)

        bot, plain = fake.clients.get("app-bot"), fake.clients.get("app-plain")
        assert bot is not None and plain is not None
        assert (bot.client_name, bot.org_id, bot.is_approved) == ("Bot", ORG, True)
        assert plain.client_name == "app-plain", "no name: the id stands for it"

    async def test_an_app_reaches_the_fake_with_its_own_token_for_its_organisation(
        self, fake: FakeIgni
    ) -> None:
        async with fake.app("app-bot", org_id=ORG) as app:
            token = await app.token()

        holder = fake.oauth.bearers.app_holder(token)
        assert holder is not None and (holder.client_id, holder.org_id) == ("app-bot", ORG)

    async def test_each_app_has_a_key_of_its_own(self, fake: FakeIgni) -> None:
        async with fake.app("app-a", org_id=ORG) as a, fake.app("app-b", org_id=ORG) as b:
            assert await a.thumbprint() != await b.thumbprint()
            first, second = fake.clients.get("app-a"), fake.clients.get("app-b")
            assert first is not None and second is not None
            assert first.thumbprint == await a.thumbprint()
            assert second.thumbprint == await b.thumbprint()


class TestTheSettings:
    def test_they_reach_the_fake_and_name_the_service_under_test(self) -> None:
        settings = FakeIgni().settings()

        assert settings.igni_server_url == FakeIgni.BASE
        assert settings.public_base_url == FakeIgni.SERVICE_URL
        assert settings.service_name == "Service under test"

    def test_they_follow_the_fakes_addresses(self) -> None:
        fake = FakeIgni(
            addresses=IgniAddresses(
                base_url="http://igni.elsewhere.test", service_url="https://svc.example.test"
            )
        )

        settings = fake.settings()

        assert settings.igni_server_url == "http://igni.elsewhere.test"
        assert settings.public_base_url == "https://svc.example.test"

    def test_what_a_test_sets_wins_and_the_rest_is_the_fakes(self) -> None:
        settings = FakeIgni().settings(
            SettingsOverrides(service_name="Mine", igni_server_url="http://other.test")
        )

        assert settings.service_name == "Mine"
        assert settings.igni_server_url == "http://other.test"
        assert settings.public_base_url == FakeIgni.SERVICE_URL

    def test_an_override_set_to_its_default_is_still_an_override(self) -> None:
        """`exclude_unset`: an explicit blank is the test's word, not 'unchanged'."""
        settings = FakeIgni().settings(SettingsOverrides(service_name=""))

        assert settings.service_name == ""


class TestTheService:
    async def test_it_is_wired_to_the_fake_with_a_key_in_memory_and_people_only(
        self, fake: FakeIgni
    ) -> None:
        service = fake.service()

        assert service.settings == fake.settings()
        assert service.clock is fake.clock
        assert service.accepted_callers == frozenset({CallerKind.PERSON})
        token = fake.signer.person_token("u-ada", org_id=ORG)
        assert (await service.person_of(token)).user_id == "u-ada"

    async def test_a_key_store_and_a_clock_the_test_gives_are_the_ones_used(
        self, fake: FakeIgni
    ) -> None:
        store, clock = MemoryKeyStore(), ManualClock()

        service = fake.service(key_store=store, clock=clock)
        await service.registration.register()

        assert service.clock is clock
        assert await store.get() is not None

    async def test_two_services_of_one_fake_keep_separate_keys_and_registrations(
        self, fake: FakeIgni
    ) -> None:
        one, two = fake.service(), fake.service()

        assert await one.registration.client_id() != await two.registration.client_id()

    async def test_settings_the_test_gives_are_the_services(self, fake: FakeIgni) -> None:
        settings = fake.settings(SettingsOverrides(service_name="Mine"))

        assert fake.service(settings).settings.service_name == "Mine"


class TestWhatAResetKeeps:
    async def test_issued_service_tokens_still_hold_after_a_reset(
        self, fake: FakeIgni, igni: IgniService
    ) -> None:
        token = await igni.tokens.token(ORG)

        fake.reset()

        holder = fake.oauth.bearers.service_holder(token)
        assert holder is not None and holder.org_id == ORG
        async with fake.http_client() as http:
            response = await http.get(
                f"{FakeIgni.BASE}/v1/directory/members", headers=bearer(token)
            )
        assert response.status_code == 200

    async def test_issued_app_tokens_still_hold_after_a_reset(self, fake: FakeIgni) -> None:
        async with fake.app("app-bot", org_id=ORG) as app:
            token = await app.token()

            fake.reset()

            assert fake.oauth.bearers.app_holder(token) is not None

    async def test_used_jtis_are_remembered_after_a_reset(
        self, fake: FakeIgni, igni: IgniService
    ) -> None:
        await igni.tokens.token(ORG)
        used = set(fake.oauth.verifier.jtis)
        assert used

        fake.reset()

        assert fake.oauth.verifier.jtis == used

    async def test_registered_clients_and_the_signing_keys_stay(
        self, fake: FakeIgni, igni: IgniService
    ) -> None:
        await igni.registration.register()
        clients = dict(fake.clients.clients)
        kids = set(fake.signer.keys.published)

        fake.reset()

        assert fake.clients.clients == clients and clients
        assert set(fake.signer.keys.published) == kids

    async def test_the_fake_is_still_usable_after_a_reset(
        self, fake: FakeIgni, igni: IgniService
    ) -> None:
        await igni.tokens.token(ORG)
        fake.reset()
        igni.tokens.forget()

        assert await igni.tokens.token(ORG)


def test_the_addresses_default_to_the_published_constants() -> None:
    fake = FakeIgni()

    assert (fake.addresses.base_url, fake.addresses.issuer, fake.addresses.service_url) == (
        FakeIgni.BASE,
        FakeIgni.ISSUER,
        FakeIgni.SERVICE_URL,
    )
    assert FakeIgni.ISSUER != FakeIgni.BASE
    assert fake.clock is not None


@pytest.mark.parametrize("approval", [False, True])
async def test_require_approval_is_the_verifiers(approval: bool) -> None:
    fake = FakeIgni(require_approval=approval)

    assert fake.oauth.verifier.require_approval is approval


class TestRetriesWithoutWaiting:
    async def test_events_and_agent_items_retry_without_sleeping(self, fake: FakeIgni) -> None:
        igni = fake.service()
        assert igni.events._sleep is not asyncio.sleep
        assert igni.agents._sender is igni.events
        fake.traffic.fail("/v1/service-events", 503)
        started = time.monotonic()
        with pytest.raises(IgniUnavailable):
            await igni.host(ORG).send_event(Producer.person("u-ada"), "claim.created")
        assert time.monotonic() - started < 0.4, "the default backoff would take 1.5 seconds"

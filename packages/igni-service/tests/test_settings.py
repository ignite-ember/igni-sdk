"""Starting a service from its environment."""

from __future__ import annotations

from pathlib import Path

import pytest

from igni_service import (
    ConfigurationError,
    IgniService,
    IgniSettings,
    KeyCipher,
    SqlKeyStore,
    SqlWebSessionStore,
)
from igni_service.testing import FakeIgni, SettingsOverrides
from igni_service.testing_wire import IgniAddresses


async def test_the_environment_names_igni_the_service_and_its_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = KeyCipher.generate()
    monkeypatch.setenv("IGNI_SERVER_BASE_URL", "http://igni-api:8000")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://Acme.example.test/")
    monkeypatch.setenv("SERVICE_NAME", "Acme")
    monkeypatch.setenv("IGNI_KEY_ENCRYPTION_KEY", key)
    monkeypatch.setenv("IGNI_KEY_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'k.db'}")
    monkeypatch.setenv("IGNI_EXTENSION_BUNDLE", "/app/extension-bundle.tar.gz")

    igni = IgniService.from_settings(IgniSettings())

    assert igni.server.base_url == "http://igni-api:8000"
    assert igni.server.own_url == "https://acme.example.test"
    assert isinstance(igni.key.store, SqlKeyStore)
    assert isinstance(igni.web.store, SqlWebSessionStore)
    assert igni.settings.extension_bundle_path == "/app/extension-bundle.tar.gz"
    await igni.aclose()


async def test_the_key_from_settings_is_kept_in_the_database(tmp_path: Path) -> None:
    fake = FakeIgni()
    settings = fake.settings(
        SettingsOverrides(
            key_encryption_key=KeyCipher.generate(),
            key_database_url=f"sqlite+aiosqlite:///{tmp_path / 'k.db'}",
        )
    )

    first = IgniService.from_settings(settings, http=fake.http_client())
    second = IgniService.from_settings(settings, http=fake.http_client())

    assert await first.thumbprint() == await second.thumbprint()
    await first.aclose()
    await second.aclose()


@pytest.mark.parametrize("missing", ["igni_server_url", "public_base_url", "service_name"])
def test_a_service_without_its_addresses_does_not_start(missing: str) -> None:
    fake = FakeIgni()
    settings = fake.settings(SettingsOverrides.model_validate({missing: ""}))

    with pytest.raises(ConfigurationError):
        fake.service(settings)


def test_a_public_url_that_is_not_one_is_said_at_start() -> None:
    fake = FakeIgni()

    with pytest.raises(ConfigurationError, match="PUBLIC_BASE_URL"):
        fake.service(fake.settings(SettingsOverrides(public_base_url="artifacts.example.test")))


def test_with_nowhere_to_keep_the_key_the_service_says_so() -> None:
    with pytest.raises(ConfigurationError, match="IGNI_KEY_DATABASE_URL"):
        IgniService.from_settings(FakeIgni().settings())


def test_a_test_can_override_every_setting() -> None:
    assert set(SettingsOverrides.model_fields) == set(IgniSettings.model_fields)


def test_the_fakes_settings_reach_it_and_what_a_test_sets_wins() -> None:
    fake = FakeIgni()

    plain = fake.settings()
    changed = fake.settings(
        SettingsOverrides(
            igni_server_url="http://elsewhere.test",
            public_base_url="https://other.example.test",
            service_name="Other",
            timeout=2.5,
        )
    )

    assert (plain.igni_server_url, plain.public_base_url, plain.service_name) == (
        FakeIgni.BASE,
        FakeIgni.SERVICE_URL,
        "Service under test",
    )
    assert (changed.igni_server_url, changed.public_base_url, changed.service_name) == (
        "http://elsewhere.test",
        "https://other.example.test",
        "Other",
    )
    assert changed.timeout == 2.5


def test_a_setting_a_test_leaves_alone_is_igni_settings_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IGNI_SERVER_TIMEOUT", "3")
    monkeypatch.setenv("IGNI_REVOCATIONS_MAX_STALENESS", "5")

    settings = FakeIgni().settings(SettingsOverrides(service_name="Mine"))

    assert (settings.timeout, settings.revocations_max_staleness) == (3.0, 5.0)


def test_settings_for_other_addresses_reach_those() -> None:
    addresses = IgniAddresses(base_url="http://igni.other:9000/", service_url="https://svc.test")

    settings = SettingsOverrides(key_encryption_key="k").settings_for(addresses)

    assert settings.igni_server_url == "http://igni.other:9000"
    assert settings.public_base_url == addresses.service_url
    assert settings.key_encryption_key == "k"


def test_a_setting_a_test_sets_to_its_default_is_still_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IGNI_SERVER_TIMEOUT", "3")

    settings = FakeIgni().settings(SettingsOverrides(timeout=10.0))

    assert settings.timeout == 10.0

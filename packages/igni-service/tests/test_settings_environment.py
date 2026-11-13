"""IgniSettings: which variables it reads, their defaults, and what it refuses."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from igni_service import IgniSettings

NAMES = [
    "IGNI_SERVER_URL",
    "IGNI_SERVER_BASE_URL",
    "PUBLIC_BASE_URL",
    "SERVICE_NAME",
    "IGNI_CLIENT_KIND",
    "IGNI_REDIRECT_URIS",
    "IGNI_KEY_ENCRYPTION_KEY",
    "IGNI_KEY_DATABASE_URL",
    "IGNI_EXTENSION_BUNDLE",
    "EXTENSION_BUNDLE_PATH",
    "IGNI_REVOCATIONS_MAX_STALENESS",
    "IGNI_SERVER_TIMEOUT",
]


@pytest.fixture(autouse=True)
def empty_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def test_an_empty_environment_gives_empty_addresses_and_the_documented_defaults() -> None:
    settings = IgniSettings()

    assert settings.model_dump() == {
        "igni_server_url": "",
        "public_base_url": "",
        "service_name": "",
        "client_kind": "service",
        "redirect_uris": [],
        "key_encryption_key": "",
        "key_database_url": "",
        "extension_bundle_path": "",
        "revocations_max_staleness": 30.0,
        "timeout": 10.0,
    }


def test_every_variable_reaches_its_field(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "IGNI_SERVER_URL": "http://igni:8000",
        "PUBLIC_BASE_URL": "https://svc.test",
        "SERVICE_NAME": "Svc",
        "IGNI_CLIENT_KIND": "app",
        "IGNI_REDIRECT_URIS": '["https://a.test/cb", "https://b.test/cb"]',
        "IGNI_KEY_ENCRYPTION_KEY": "kek",
        "IGNI_KEY_DATABASE_URL": "sqlite+aiosqlite:///k.db",
        "IGNI_EXTENSION_BUNDLE": "/b.tar.gz",
        "IGNI_REVOCATIONS_MAX_STALENESS": "12.5",
        "IGNI_SERVER_TIMEOUT": "2",
    }.items():
        monkeypatch.setenv(name, value)

    settings = IgniSettings()

    assert settings.model_dump() == {
        "igni_server_url": "http://igni:8000",
        "public_base_url": "https://svc.test",
        "service_name": "Svc",
        "client_kind": "app",
        "redirect_uris": ["https://a.test/cb", "https://b.test/cb"],
        "key_encryption_key": "kek",
        "key_database_url": "sqlite+aiosqlite:///k.db",
        "extension_bundle_path": "/b.tar.gz",
        "revocations_max_staleness": 12.5,
        "timeout": 2.0,
    }


def test_igni_server_base_url_is_the_other_name_of_igni_server_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IGNI_SERVER_BASE_URL", "http://base")
    assert IgniSettings().igni_server_url == "http://base"

    monkeypatch.setenv("IGNI_SERVER_URL", "http://url")
    assert IgniSettings().igni_server_url == "http://url", "IGNI_SERVER_URL wins"


def test_the_extension_bundle_has_two_names_and_the_first_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTENSION_BUNDLE_PATH", "/old.tar.gz")
    assert IgniSettings().extension_bundle_path == "/old.tar.gz"

    monkeypatch.setenv("IGNI_EXTENSION_BUNDLE", "/new.tar.gz")
    assert IgniSettings().extension_bundle_path == "/new.tar.gz"


def test_a_variable_igni_does_not_know_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IGNI_NOT_A_SETTING", "1")

    assert IgniSettings(igni_server_url="http://x", surprise="y").igni_server_url == "http://x"  # type: ignore[call-arg]


def test_a_field_can_be_passed_by_its_name_and_beats_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVICE_NAME", "From the environment")

    settings = IgniSettings(service_name="By name", timeout=3, redirect_uris=["https://a.test/cb"])

    assert settings.service_name == "By name"
    assert settings.timeout == 3.0
    assert settings.redirect_uris == ["https://a.test/cb"]


@pytest.mark.parametrize("name", ["IGNI_SERVER_TIMEOUT", "IGNI_REVOCATIONS_MAX_STALENESS"])
def test_a_number_that_is_not_one_is_refused(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "soon")

    with pytest.raises(ValidationError):
        IgniSettings()

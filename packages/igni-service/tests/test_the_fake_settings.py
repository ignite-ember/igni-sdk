"""What the settings a test overrides mean: set is what the test said, even when it says the default."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from igni_service.testing import FakeIgni, SettingsOverrides
from igni_service.testing_wire import IgniAddresses


def test_a_value_set_to_its_own_default_still_beats_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IGNI_SERVER_TIMEOUT", "3")
    monkeypatch.setenv("IGNI_CLIENT_KIND", "app")

    left = FakeIgni().settings(SettingsOverrides())
    said = FakeIgni().settings(SettingsOverrides(timeout=10.0, client_kind="service"))

    assert (left.timeout, left.client_kind) == (3.0, "app")
    assert (said.timeout, said.client_kind) == (10.0, "service")


def test_the_overrides_are_applied_to_the_settings_they_name() -> None:
    settings = SettingsOverrides(
        client_kind="app",
        key_database_url="sqlite+aiosqlite:///k.db",
        redirect_uris=["https://a.test/cb"],
        revocations_max_staleness=1.5,
        extension_bundle_path="/b.tar.gz",
    ).settings_for(IgniAddresses())

    assert settings.client_kind == "app"
    assert settings.key_database_url == "sqlite+aiosqlite:///k.db"
    assert settings.redirect_uris == ["https://a.test/cb"]
    assert settings.revocations_max_staleness == 1.5
    assert settings.extension_bundle_path == "/b.tar.gz"


def test_a_value_igni_settings_cannot_read_raises_from_it() -> None:
    with pytest.raises(ValidationError, match="timeout"):
        SettingsOverrides.model_validate({"timeout": "soon"}).settings_for(IgniAddresses())

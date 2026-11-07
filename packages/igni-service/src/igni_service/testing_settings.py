"""What a test changes about the settings a service is wired to `FakeIgni` with."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from igni_service.settings import IgniSettings
from igni_service.testing_wire import IgniAddresses


class SettingsOverrides(BaseModel):
    """What a test changes about the settings a service is wired to the fake with.

    Only the fields a test sets are applied (`exclude_unset`): every other
    one is the fake's address, its URL for the service, or `IgniSettings`'
    own default. A field `IgniSettings` lacks is refused, not ignored.
    """

    model_config = ConfigDict(extra="forbid")

    igni_server_url: str = ""
    public_base_url: str = ""
    service_name: str = ""
    client_kind: str = "service"
    redirect_uris: list[str] = Field(default_factory=list)
    key_encryption_key: str = ""
    key_database_url: str = ""
    extension_bundle_path: str = ""
    revocations_max_staleness: float = 30.0
    timeout: float = 10.0

    def settings_for(self, addresses: IgniAddresses) -> IgniSettings:
        """Settings that reach the fake at `addresses`, with what this sets."""
        defaults = SettingsOverrides(
            igni_server_url=addresses.base_url,
            public_base_url=addresses.service_url,
            service_name="Service under test",
        ).model_dump(exclude_unset=True)
        return IgniSettings.model_validate(defaults | self.model_dump(exclude_unset=True))


__all__ = ["SettingsOverrides"]

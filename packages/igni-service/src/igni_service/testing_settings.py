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

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    igni_server_url: str = ""
    """`IGNI_SERVER_URL`; the fake's address unless set."""
    public_base_url: str = ""
    """`PUBLIC_BASE_URL`; `http://service.test` unless set."""
    service_name: str = ""
    """`SERVICE_NAME`."""
    client_kind: str = "service"
    """`IGNI_CLIENT_KIND`: `service`."""
    redirect_uris: list[str] = Field(default_factory=list)
    """`IGNI_REDIRECT_URIS`: more addresses igni may send a signed-in person back to."""
    key_encryption_key: str = ""
    """`IGNI_KEY_ENCRYPTION_KEY`."""
    key_database_url: str = ""
    """`IGNI_KEY_DATABASE_URL`."""
    extension_bundle_path: str = ""
    """`IGNI_EXTENSION_BUNDLE_PATH`: the bundle the service uploads at start-up."""
    revocations_max_staleness: float = 30.0
    """`IGNI_REVOCATIONS_MAX_STALENESS`, in seconds."""
    timeout: float = 10.0
    """`IGNI_SERVER_TIMEOUT`: each call to igni, in seconds."""

    def settings_for(self, addresses: IgniAddresses) -> IgniSettings:
        """Settings that reach the fake at `addresses`, with what this sets."""
        defaults = SettingsOverrides(
            igni_server_url=addresses.base_url,
            public_base_url=addresses.service_url,
            service_name="Service under test",
        ).model_dump(exclude_unset=True)
        return IgniSettings.model_validate(defaults | self.model_dump(exclude_unset=True))


__all__ = ["SettingsOverrides"]

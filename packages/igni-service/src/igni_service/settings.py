"""What a service is deployed with.

Two addresses and a key are all of it: igni's URL, the service's own
public URL, and the Fernet key its own signing key is sealed under.
Everything else — igni's issuer, its signing keys, this service's client
id — is learned from igni or generated.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IgniSettings(BaseSettings):
    """Read from the environment. Every field can also be passed directly."""

    model_config = SettingsConfigDict(
        extra="ignore", populate_by_name=True, use_attribute_docstrings=True
    )

    igni_server_url: str = Field(
        default="", validation_alias=AliasChoices("IGNI_SERVER_URL", "IGNI_SERVER_BASE_URL")
    )
    """Where this service reaches igni server. Often an in-cluster address,
    not igni's public URL — the two need not match.
    """
    public_base_url: str = Field(default="", validation_alias=AliasChoices("PUBLIC_BASE_URL"))
    """This service's own public URL, on a hostname of its own. It is the
    audience of every token people bring, and where igni calls it.
    """
    service_name: str = Field(default="", validation_alias=AliasChoices("SERVICE_NAME"))
    """What the registration is called in igni's portal."""
    client_kind: str = Field(default="service", validation_alias=AliasChoices("IGNI_CLIENT_KIND"))
    """`service`, or `app` for something acting only for signed-in people."""
    redirect_uris: list[str] = Field(
        default_factory=list, validation_alias=AliasChoices("IGNI_REDIRECT_URIS")
    )
    """Where people's browsers come back to after signing in to this
    service's own portal, if it has one.
    """
    key_encryption_key: str = Field(
        default="", validation_alias=AliasChoices("IGNI_KEY_ENCRYPTION_KEY")
    )
    """The Fernet key this service's private key is sealed under."""
    key_database_url: str = Field(
        default="", validation_alias=AliasChoices("IGNI_KEY_DATABASE_URL")
    )
    """An async SQLAlchemy URL for the key store, when the service does not
    hand one over itself (`postgresql+asyncpg://…`).
    """
    extension_bundle_path: str = Field(
        default="", validation_alias=AliasChoices("IGNI_EXTENSION_BUNDLE", "EXTENSION_BUNDLE_PATH")
    )
    """The extension bundle this service ships. Empty or missing: nothing
    is uploaded.
    """
    revocations_max_staleness: float = Field(
        default=30.0, validation_alias=AliasChoices("IGNI_REVOCATIONS_MAX_STALENESS")
    )
    """Seconds the revocation list may go unrefreshed before every token is
    refused (it fails closed): a removed person can do nothing after that.
    """
    timeout: float = Field(default=10.0, validation_alias=AliasChoices("IGNI_SERVER_TIMEOUT"))
    """Seconds before a call to igni gives up."""

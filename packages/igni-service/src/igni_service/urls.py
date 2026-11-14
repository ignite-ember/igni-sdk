"""URLs, written the one way igni writes them, and the paths the wire fixes."""

from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit


class ServiceUrl:
    """A service's own URL as igni normalises it.

    A person's token for a service names the service's URL as its
    audience, and igni compares it as a string: it normalises the
    `client_uri` a service registers — lower-case scheme and host, no
    trailing slash, no query or fragment — and puts exactly that in every
    token. So the service normalises its own URL the same way before it
    registers it and before it compares against it.
    """

    @staticmethod
    def normalise(url: str) -> str:
        """`scheme://host[:port][/path]`. Raises `ValueError` for anything else.

        Args:
            url: The service's own URL, as it was given: lower-case scheme
                and host, no trailing slash, and no query or fragment.
        """
        parts = urlsplit((url or "").strip())
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            raise ValueError(f"{url!r} is not an absolute http(s) URL")
        if parts.query or parts.fragment:
            raise ValueError(f"{url!r} must not have a query or a fragment")
        host = parts.hostname.lower()
        if ":" in host:
            # An IPv6 address is written in brackets; without them the port
            # cannot be told from the address.
            host = f"[{host}]"
        netloc = f"{host}:{parts.port}" if parts.port is not None else host
        return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), "", ""))


class IgniPaths:
    """The paths igni serves, spelled once."""

    DISCOVERY = "/.well-known/openid-configuration"
    """igni's OpenID Connect discovery document."""
    JWKS = "/.well-known/jwks.json"
    """igni's public keys, which people's tokens are checked against."""
    CLIENTS = "/v1/clients"
    """Client registration (RFC 7591), and each client's extension under it."""
    TOKEN = "/v1/oauth/token"  # noqa: S105 — an endpoint path, not a secret
    """The token endpoint: service tokens, and sign-in to the service's pages."""
    REVOKE = "/v1/oauth/revoke"
    """The revocation endpoint (RFC 7009): a sign-out ends the sign-in there."""
    DIRECTORY = "/v1/directory"
    """The directory: an organisation and its members."""
    NOTIFICATIONS = "/v1/service-notifications"
    """Where a service sends notifications."""
    SERVICE_EVENTS = "/v1/service-events"
    """Waking a producer's agent with an event (service-identity §15)."""
    SERVICE_ITEMS = "/v1/service-items"
    """Any item for a producer's agent: an event, a message, a chat, an action."""
    SERVICE_ATTACHMENTS = "/v1/service-attachments"
    """A file an item then names."""
    REVOCATIONS = "/v1/revocations"
    """What igni has revoked in an organisation (service-identity §21)."""
    SERVED = "/v1/organisations/served"
    """Every organisation this service serves (service-identity §21)."""
    SERVICE_VM_PROFILE = "/v1/service-vm-profile"
    """A service's extension's VM profile request in one organisation (service-identity §12)."""
    APPS = "/v1/apps"
    """An app, acting as itself (service-identity §11.1, §17)."""

    @staticmethod
    def _segment(value: str) -> str:
        """`value` as one path segment: a slash, a dot-dot or a question mark cannot leave it."""
        escaped = quote(value, safe="")
        return escaped.replace(".", "%2E") if escaped in (".", "..") else escaped

    @classmethod
    def app_vm_profile_request(cls, app_id: str) -> str:
        """An app's own request for what its VM needs.

        Args:
            app_id: The app's id, as an org admin registered it: whose
                request for a VM profile this is.
        """
        return f"{cls.APPS}/{cls._segment(app_id)}/vm-profile-request"

    @classmethod
    def app_vm_profile(cls, app_id: str) -> str:
        """The profile an app's VM gets now.

        Args:
            app_id: The app's id, as an org admin registered it: whose VM's
                profile this is.
        """
        return f"{cls.APPS}/{cls._segment(app_id)}/vm-profile"

    @classmethod
    def service_event(cls, event_id: str) -> str:
        """What became of one item this service sent.

        Args:
            event_id: The id of the item to report on, as igni gave it when
                it accepted it.
        """
        return f"{cls.SERVICE_EVENTS}/{cls._segment(event_id)}"

    @classmethod
    def extension(cls, client_id: str) -> str:
        """Where igni holds `client_id`'s extension bundle.

        Args:
            client_id: The client id this service registered with, as igni
                gave it: whose extension this is.
        """
        return f"{cls.CLIENTS}/{cls._segment(client_id)}/extension"

    @classmethod
    def extension_asset(cls, client_id: str, sha256: str) -> str:
        """Where igni holds one asset of `client_id`'s extension, by its SHA-256.

        Args:
            client_id: The client id this service registered with, as igni
                gave it: whose extension the asset belongs to.
            sha256: The asset's SHA-256 digest: which asset of the bundle
                this is.
        """
        return f"{cls.CLIENTS}/{cls._segment(client_id)}/extension/assets/{cls._segment(sha256)}"

    SUBJECTS = "/v1/igni/subjects"
    """Where igni calls a service about one person (erasure, export)."""
    ORGANISATIONS = "/v1/igni/organisations"
    """Where igni tells a service that an organisation was deleted."""

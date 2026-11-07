"""Registrations, as igni keeps them: services that registered, and apps an admin did.

A service registers itself (`POST /v1/clients`, RFC 7591): the same key
again finds the same registration. An app is registered by an org admin
pasting its public key on the portal (`add_app`). A test plays a super
admin with `approve` and `revoke`.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

import httpx
from pydantic import BaseModel, ValidationError

from igni_service.crypto import Jwk, RsaKeyPair
from igni_service.registration import ClientMetadata
from igni_service.testing_wire import OAuthError, RoutedCall
from igni_service.urls import ServiceUrl


class ClientState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REVOKED = "revoked"


class ClientKind(StrEnum):
    SERVICE = "service"
    APP = "app"


class RegistrationResponse(BaseModel):
    """What igni answers a registration with (RFC 7591 §3.2.1, plus its state)."""

    client_id: str
    client_id_issued_at: int = 0
    client_name: str
    client_uri: str
    kind: ClientKind
    redirect_uris: list[str]
    token_endpoint_auth_method: str = "private_key_jwt"  # noqa: S105 — an RFC 7591 auth method, not a secret
    state: ClientState
    thumbprint: str


class FakeClient(BaseModel):
    """A registration, as igni keeps it."""

    client_id: str
    client_name: str
    client_uri: str
    kind: ClientKind
    redirect_uris: list[str]
    state: ClientState = ClientState.PENDING
    thumbprint: str
    jwk: Jwk
    #: An app's organisation; empty for a service.
    org_id: str = ""

    @property
    def is_revoked(self) -> bool:
        return self.state is ClientState.REVOKED

    @property
    def is_approved(self) -> bool:
        return self.state is ClientState.APPROVED

    def registration_response(self) -> RegistrationResponse:
        return RegistrationResponse(
            client_id=self.client_id,
            client_name=self.client_name,
            client_uri=self.client_uri,
            kind=self.kind,
            redirect_uris=self.redirect_uris,
            state=self.state,
            thumbprint=self.thumbprint,
        )


class FakeClientRegistry:
    """Every client igni knows, by client id."""

    def __init__(self) -> None:
        self.clients: dict[str, FakeClient] = {}

    def register(self, call: RoutedCall) -> httpx.Response:
        """`POST /v1/clients`: the same public key again is the same registration."""
        try:
            metadata = ClientMetadata.model_validate_json(call.seen.body)
        except ValidationError as exc:
            return self._invalid(str(exc))
        keys = metadata.jwks.keys
        if len(keys) != 1 or "d" in (keys[0].model_extra or {}):
            return self._invalid("exactly one public key is required")
        try:
            client_uri = ServiceUrl.normalise(metadata.client_uri)
            kind = ClientKind(metadata.kind)
        except ValueError as exc:
            return self._invalid(str(exc))
        existing = self.owner_of_thumbprint(keys[0].kid)
        if existing is None:
            existing = FakeClient(
                client_id=str(uuid.uuid4()),
                client_name=metadata.client_name,
                client_uri=client_uri,
                kind=kind,
                redirect_uris=metadata.redirect_uris,
                thumbprint=keys[0].kid,
                jwk=keys[0],
            )
            self.clients[existing.client_id] = existing
        return httpx.Response(201, json=existing.registration_response().model_dump(mode="json"))

    def add_app(self, app_id: str, org_id: str, name: str, pair: RsaKeyPair) -> FakeClient:
        """An app an org admin registered by pasting `pair`'s public half: approved by that act."""
        client = FakeClient(
            client_id=app_id,
            client_name=name or app_id,
            client_uri="",
            kind=ClientKind.APP,
            redirect_uris=[],
            state=ClientState.APPROVED,
            thumbprint=pair.thumbprint(),
            jwk=pair.public_jwk(),
            org_id=org_id,
        )
        self.clients[app_id] = client
        return client

    def get(self, client_id: str) -> FakeClient | None:
        return self.clients.get(client_id)

    def approve(self, client_id: str | None = None) -> None:
        """Play a super admin approving one client, or every one."""
        for client in self._matching(client_id):
            client.state = ClientState.APPROVED

    def revoke(self, client_id: str | None = None) -> None:
        """Play a super admin revoking one client, or every one."""
        for client in self._matching(client_id):
            client.state = ClientState.REVOKED

    @property
    def registration(self) -> FakeClient | None:
        """The one registration, when there is one."""
        return next(iter(self.clients.values()), None)

    def owner_of_thumbprint(self, thumbprint: str) -> FakeClient | None:
        return next((c for c in self.clients.values() if c.thumbprint == thumbprint), None)

    def _matching(self, client_id: str | None) -> list[FakeClient]:
        return [c for c in self.clients.values() if client_id is None or c.client_id == client_id]

    @staticmethod
    def _invalid(description: str) -> httpx.Response:
        return OAuthError(
            error="invalid_client_metadata", error_description=description
        ).to_response()


__all__ = [
    "ClientKind",
    "ClientState",
    "FakeClient",
    "FakeClientRegistry",
    "RegistrationResponse",
]

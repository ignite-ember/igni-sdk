"""Extension bundles and their assets, as igni takes them from a service, over the wire.

A service uploads each asset its manifest declares, signed (`PUT
/v1/clients/{id}/extension/assets/{sha256}`), then the bundle, signed
(`PUT /v1/clients/{id}/extension`). igni checks each signature against
the client's registered key, the bytes against what was signed, the
manifest against the signed claim, that every asset is already there,
and that no other approved service ships the same extension. With
`hold(reason)`, a new version from an approved service is held for a
super admin instead of replacing the one machines receive.
"""

from __future__ import annotations

import hashlib
from typing import TypeVar

import httpx
import jwt
from jwt.api_jws import PyJWS
from pydantic import BaseModel, ConfigDict, ValidationError

from igni_service.crypto import ALGORITHM, AssetClaim, BundleClaim, Jwk
from igni_service.registration import PublishedExtension
from igni_service.testing_bundles import HeldExtension, UploadedManifest
from igni_service.testing_clients import FakeClient, FakeClientRegistry
from igni_service.testing_wire import DetailError, RoutedCall
from igni_service.urls import IgniPaths

Claim = TypeVar("Claim", bound=BaseModel)

NOT_SIGNED = "not signed by this client's registered key"
OTHER_BYTES = "the signature is for other bytes"


class SignedBody(BaseModel):
    """Bytes a client uploaded, and the JWS header that says what they are."""

    signature: str
    body: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    def verify(self, jwk: Jwk, claim: type[Claim]) -> Claim | DetailError:
        """The signed claim, when `jwk` signed it."""
        try:
            payload = PyJWS().decode(self.signature, jwk.public_key(), algorithms=[ALGORITHM])
            return claim.model_validate_json(payload)
        except (jwt.PyJWTError, ValidationError, ValueError):
            return DetailError(detail=NOT_SIGNED)


class ClientPath(BaseModel):
    """`/v1/clients/{client_id}/extension[/assets/{sha256}]`."""

    client_id: str
    #: The asset's digest; `None` for the bundle itself.
    sha256: str | None = None

    @classmethod
    def parse(cls, path: str) -> ClientPath | None:
        client_id, _, rest = path.removeprefix(f"{IgniPaths.CLIENTS}/").partition("/")
        if rest == "extension":
            return cls(client_id=client_id)
        if rest.startswith("extension/assets/"):
            return cls(client_id=client_id, sha256=rest.removeprefix("extension/assets/"))
        return None


class AssetKey(BaseModel):
    """An uploaded asset: whose, and its digest."""

    model_config = ConfigDict(frozen=True)

    client_id: str
    sha256: str


class AssetStored(BaseModel):
    """What igni answers an asset upload with."""

    sha256: str
    size: int


class FakeExtensionStore:
    """Every client's bundle and assets, and the versions held for a super admin."""

    def __init__(self, clients: FakeClientRegistry) -> None:
        self.clients = clients
        self.extensions: dict[str, HeldExtension] = {}
        #: Uploads held for a super admin (`hold`), by client.
        self.held: dict[str, HeldExtension] = {}
        self.assets: dict[AssetKey, bytes] = {}
        #: When set, an upload replacing an approved service's extension is
        #: **held** with this reason, as igni holds a version that asks for
        #: more than the approved one (service-identity §8.1).
        self.hold_uploads: str | None = None

    def hold(self, reason: str) -> None:
        """Hold every new version from an approved service, for `reason`."""
        self.hold_uploads = reason

    def release(self) -> None:
        """Stop holding new versions; those already held stay held."""
        self.hold_uploads = None

    def reset(self) -> None:
        self.release()
        self.held.clear()

    def shipped(self, client_id: str) -> HeldExtension | None:
        """The bundle machines receive for `client_id`."""
        return self.extensions.get(client_id)

    def latest(self, client_id: str) -> HeldExtension:
        """The last bundle `client_id` uploaded: held, or else shipped."""
        return self.held.get(client_id) or self.extensions[client_id]

    # ── Routes ──────────────────────────────────────────────────────

    def route(self, call: RoutedCall) -> httpx.Response:
        """Everything under `/v1/clients/{client_id}/`."""
        path = ClientPath.parse(call.seen.path)
        if path is None:
            return DetailError(detail="Not Found", status=404).to_response()
        if path.sha256 is None:
            return self._extension(call, path.client_id)
        return self._asset(call, path.client_id, path.sha256)

    def _extension(self, call: RoutedCall, client_id: str) -> httpx.Response:
        if call.seen.method == "GET":
            return self._published(client_id)
        client = self.clients.get(client_id)
        if client is None:
            return DetailError(detail="no such client", status=404).to_response()
        if client.is_revoked:
            return DetailError(detail="revoked", status=403).to_response()
        uploaded = self._checked(client, call)
        if isinstance(uploaded, DetailError):
            return uploaded.to_response()
        if self.hold_uploads and client.is_approved and client_id in self.extensions:
            self.held[client_id] = uploaded
            return self._answer(uploaded.published(self._hold_reason()))
        self.extensions[client_id] = uploaded
        return self._answer(uploaded.published())

    def _published(self, client_id: str) -> httpx.Response:
        waiting = self.held.get(client_id)
        if waiting is not None:
            return self._answer(waiting.published(self._hold_reason()))
        shipped = self.extensions.get(client_id)
        if shipped is None:
            return DetailError(detail="Nothing uploaded for this client", status=404).to_response()
        return self._answer(shipped.published())

    def _checked(self, client: FakeClient, call: RoutedCall) -> HeldExtension | DetailError:
        """The upload, after every check igni makes of a bundle."""
        signed = SignedBody(
            signature=call.seen.headers.get("x-igni-bundle-signature", ""), body=call.seen.body
        )
        claim = signed.verify(client.jwk, BundleClaim)
        if isinstance(claim, DetailError):
            return claim
        if claim.sha256 != signed.sha256:
            return DetailError(detail=OTHER_BYTES)
        manifest = UploadedManifest.from_archive(signed.body)
        if isinstance(manifest, DetailError):
            return manifest
        if manifest.id != claim.extension or manifest.version != claim.version:
            return DetailError(detail="the manifest is not what was signed")
        missing = [
            asset.name
            for asset in manifest.assets
            if AssetKey(client_id=client.client_id, sha256=asset.sha256) not in self.assets
        ]
        if missing:
            return DetailError(detail=f"assets not uploaded first: {', '.join(missing)}")
        if self._shipped_elsewhere(claim.extension, client.client_id):
            return DetailError(detail="another service ships this extension", status=409)
        return HeldExtension(
            client_id=client.client_id,
            extension_id=claim.extension,
            version=claim.version,
            sha256=claim.sha256,
            archive=signed.body,
            manifest=manifest,
        )

    def _shipped_elsewhere(self, extension_id: str, client_id: str) -> bool:
        return any(
            shipped.extension_id == extension_id and other != client_id
            for other, shipped in self.extensions.items()
            if self.clients.clients[other].is_approved
        )

    def _asset(self, call: RoutedCall, client_id: str, sha256: str) -> httpx.Response:
        key = AssetKey(client_id=client_id, sha256=sha256)
        if call.seen.method == "HEAD":
            return httpx.Response(200 if key in self.assets else 404)
        client = self.clients.get(client_id)
        if client is None:
            return DetailError(detail="no such client", status=404).to_response()
        signed = SignedBody(
            signature=call.seen.headers.get("x-igni-asset-signature", ""), body=call.seen.body
        )
        claim = signed.verify(client.jwk, AssetClaim)
        if isinstance(claim, DetailError):
            return claim.to_response()
        if claim.asset != sha256 or signed.sha256 != sha256:
            return DetailError(detail=OTHER_BYTES).to_response()
        if claim.size != len(signed.body):
            return DetailError(detail="the size is not what was signed").to_response()
        self.assets[key] = signed.body
        stored = AssetStored(sha256=sha256, size=len(signed.body))
        return httpx.Response(200, json=stored.model_dump())

    def _hold_reason(self) -> str:
        return f"held for a super admin: {self.hold_uploads}"

    @staticmethod
    def _answer(published: PublishedExtension) -> httpx.Response:
        return httpx.Response(200, json=published.model_dump())


__all__ = ["AssetKey", "AssetStored", "ClientPath", "FakeExtensionStore", "SignedBody"]

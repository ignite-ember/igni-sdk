"""The fake's extension store: every check igni makes of a bundle and an asset, and what it holds.

Driven at the store with signed uploads built by hand, so each refusal is
seen as igni's own words and not through the SDK that signs correctly.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile

import httpx
import pytest

from igni_service.crypto import AssetClaim, BundleClaim, RsaKeyPair
from igni_service.testing import FakeIgni
from igni_service.testing_clients import ClientState, FakeClient, FakeClientRegistry
from igni_service.testing_extensions import (
    NOT_SIGNED,
    OTHER_BYTES,
    AssetKey,
    ClientPath,
    FakeExtensionStore,
    SignedBody,
)
from igni_service.testing_wire import DetailError, RoutedCall, SeenRequest
from igni_service.urls import IgniPaths

BUNDLE_SIGNATURE = "x-igni-bundle-signature"
ASSET_SIGNATURE = "x-igni-asset-signature"


class Scene:
    """A registry with one approved client, and the store over it."""

    def __init__(self) -> None:
        self.registry = FakeClientRegistry()
        self.store = FakeExtensionStore(self.registry)
        self.pair = RsaKeyPair.generate()
        self.client = self.registry.add_app("c-1", "org-acme", "Tickets", self.pair)

    def other(self, client_id: str = "c-2") -> tuple[FakeClient, RsaKeyPair]:
        pair = RsaKeyPair.generate()
        return self.registry.add_app(client_id, "org-acme", client_id, pair), pair

    def call(
        self,
        method: str,
        client_id: str,
        *,
        asset: str | None = None,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> RoutedCall:
        path = f"{IgniPaths.CLIENTS}/{client_id}/extension"
        if asset is not None:
            path += f"/assets/{asset}"
        return RoutedCall(
            seen=SeenRequest(method=method, path=path, headers=headers or {}, body=body)
        )

    def put_asset(
        self, data: bytes, *, client_id: str = "c-1", pair: RsaKeyPair | None = None
    ) -> int:
        digest = hashlib.sha256(data).hexdigest()
        signature = (pair or self.pair).sign_asset(AssetClaim(asset=digest, size=len(data)))
        return self.store.route(
            self.call(
                "PUT",
                client_id,
                asset=digest,
                body=data,
                headers={ASSET_SIGNATURE: signature},
            )
        ).status_code

    def put_bundle(
        self,
        archive: bytes,
        *,
        client_id: str = "c-1",
        pair: RsaKeyPair | None = None,
        extension: str = "tickets",
        version: str = "1.0.0",
        sha256: str | None = None,
        signature: str | None = None,
    ) -> httpx.Response:
        claim = BundleClaim(
            extension=extension,
            version=version,
            sha256=sha256 or hashlib.sha256(archive).hexdigest(),
        )
        headers = {BUNDLE_SIGNATURE: (pair or self.pair).sign_bundle(claim)}
        if signature is not None:
            headers[BUNDLE_SIGNATURE] = signature
        return self.store.route(self.call("PUT", client_id, body=archive, headers=headers))


def archive(manifest: object = None, *, name: str = "manifest.json", **fields: object) -> bytes:
    body = (
        json.dumps(manifest)
        if manifest is not None
        else json.dumps({"id": "tickets", "version": "1.0.0", **fields})
    )
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        info = tarfile.TarInfo(name)
        data = body.encode()
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


def detail(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["detail"]


# ── Paths and the signed body ───────────────────────────────────────


def test_a_client_path_is_the_bundle_or_one_of_its_assets_and_nothing_else() -> None:
    assert ClientPath.parse("/v1/clients/c-1/extension") == ClientPath(client_id="c-1")
    assert ClientPath.parse("/v1/clients/c-1/extension/assets/abc") == ClientPath(
        client_id="c-1", sha256="abc"
    )
    for other in (
        "/v1/clients/c-1",
        "/v1/clients/c-1/extension/",
        "/v1/clients/c-1/extensions",
        "/v1/clients/c-1/extension/other/abc",
        "/v1/clients/c-1/other",
        "/v2/clients/c-1/extension",
        "/v1/clients",
    ):
        assert ClientPath.parse(other) is None


def test_a_signed_body_knows_its_digest_and_what_its_key_signed() -> None:
    pair = RsaKeyPair.generate()
    claim = AssetClaim(asset="a" * 64, size=3)
    body = SignedBody(signature=pair.sign_asset(claim), body=b"abc")

    assert body.sha256 == hashlib.sha256(b"abc").hexdigest()
    assert body.verify(pair.public_jwk(), AssetClaim) == claim


@pytest.mark.parametrize("signature", ["", "garbage", "a.b.c"])
def test_a_signature_that_is_missing_or_garbage_is_not_signed_by_the_key(signature: str) -> None:
    refused = SignedBody(signature=signature, body=b"").verify(
        RsaKeyPair.generate().public_jwk(), AssetClaim
    )

    assert isinstance(refused, DetailError)
    assert (refused.status, refused.detail) == (400, NOT_SIGNED)


def test_a_signature_by_another_key_or_over_another_claim_is_refused() -> None:
    mine, theirs = RsaKeyPair.generate(), RsaKeyPair.generate()
    signed = mine.sign_asset(AssetClaim(asset="a", size=1))

    wrong_key = SignedBody(signature=signed, body=b"").verify(theirs.public_jwk(), AssetClaim)
    wrong_claim = SignedBody(signature=signed, body=b"").verify(mine.public_jwk(), BundleClaim)

    assert wrong_key == DetailError(detail=NOT_SIGNED)
    assert wrong_claim == DetailError(detail=NOT_SIGNED)


# ── Assets ──────────────────────────────────────────────────────────


def test_an_asset_signed_by_its_client_is_stored_and_answered_with_digest_and_size() -> None:
    scene = Scene()
    data = b"asset bytes"
    digest = hashlib.sha256(data).hexdigest()
    signature = scene.pair.sign_asset(AssetClaim(asset=digest, size=len(data)))

    answer = scene.store.route(
        scene.call("PUT", "c-1", asset=digest, body=data, headers={ASSET_SIGNATURE: signature})
    )

    assert answer.status_code == 200
    assert answer.json() == {"sha256": digest, "size": len(data)}
    assert scene.store.assets == {AssetKey(client_id="c-1", sha256=digest): data}


def test_head_on_an_asset_says_whether_this_client_holds_it() -> None:
    scene = Scene()
    scene.other()
    data = b"asset"
    digest = hashlib.sha256(data).hexdigest()
    scene.put_asset(data)

    held = scene.store.route(scene.call("HEAD", "c-1", asset=digest))
    elsewhere = scene.store.route(scene.call("HEAD", "c-2", asset=digest))
    unknown = scene.store.route(scene.call("HEAD", "c-9", asset=digest))
    absent = scene.store.route(scene.call("HEAD", "c-1", asset="0" * 64))

    assert [r.status_code for r in (held, elsewhere, unknown, absent)] == [200, 404, 404, 404]


def test_an_asset_upload_for_an_unknown_client_is_not_found() -> None:
    scene = Scene()

    answer = scene.store.route(scene.call("PUT", "c-9", asset="a" * 64, body=b"x"))

    assert detail(answer) == (404, "no such client")


@pytest.mark.parametrize("signature", [None, "garbage"])
def test_an_asset_without_a_valid_signature_is_not_stored(signature: str | None) -> None:
    scene = Scene()
    data = b"asset"
    digest = hashlib.sha256(data).hexdigest()
    headers = {} if signature is None else {ASSET_SIGNATURE: signature}

    answer = scene.store.route(scene.call("PUT", "c-1", asset=digest, body=data, headers=headers))

    assert detail(answer) == (400, NOT_SIGNED)
    assert scene.store.assets == {}


def test_an_asset_signed_by_another_clients_key_is_refused() -> None:
    scene = Scene()
    _, theirs = scene.other()

    assert scene.put_asset(b"asset", client_id="c-1", pair=theirs) == 400
    assert scene.store.assets == {}


def test_an_asset_whose_bytes_are_not_what_was_signed_is_refused_in_both_ways() -> None:
    scene = Scene()
    data = b"asset"
    digest = hashlib.sha256(data).hexdigest()
    other = hashlib.sha256(b"other").hexdigest()

    path_for_other_bytes = scene.store.route(
        scene.call(
            "PUT",
            "c-1",
            asset=other,
            body=data,
            headers={ASSET_SIGNATURE: scene.pair.sign_asset(AssetClaim(asset=other, size=5))},
        )
    )
    claim_for_other_bytes = scene.store.route(
        scene.call(
            "PUT",
            "c-1",
            asset=digest,
            body=data,
            headers={ASSET_SIGNATURE: scene.pair.sign_asset(AssetClaim(asset=other, size=5))},
        )
    )

    assert detail(path_for_other_bytes) == (400, OTHER_BYTES)
    assert detail(claim_for_other_bytes) == (400, OTHER_BYTES)
    assert scene.store.assets == {}


def test_an_asset_whose_size_is_not_the_signed_size_is_refused() -> None:
    scene = Scene()
    data = b"asset"
    digest = hashlib.sha256(data).hexdigest()

    answer = scene.store.route(
        scene.call(
            "PUT",
            "c-1",
            asset=digest,
            body=data,
            headers={ASSET_SIGNATURE: scene.pair.sign_asset(AssetClaim(asset=digest, size=99))},
        )
    )

    assert detail(answer) == (400, "the size is not what was signed")
    assert scene.store.assets == {}


def test_an_empty_asset_is_stored_when_signed_for_nothing() -> None:
    scene = Scene()

    assert scene.put_asset(b"") == 200
    assert AssetKey(client_id="c-1", sha256=hashlib.sha256(b"").hexdigest()) in scene.store.assets


# ── Bundles ─────────────────────────────────────────────────────────


def test_a_signed_bundle_is_shipped_and_answered_as_published() -> None:
    scene = Scene()

    answer = scene.put_bundle(archive())

    assert answer.status_code == 200
    assert answer.json() == {
        "extension_id": "tickets",
        "version": "1.0.0",
        "sha256": hashlib.sha256(archive()).hexdigest(),
        "held": False,
        "reason": None,
        "added": [],
    }
    shipped = scene.store.shipped("c-1")
    assert shipped is not None
    assert (shipped.client_id, shipped.extension_id, shipped.version) == ("c-1", "tickets", "1.0.0")
    assert shipped.archive == archive()
    assert scene.store.latest("c-1") is shipped


def test_a_bundle_for_an_unknown_client_is_not_found_and_for_a_revoked_one_forbidden() -> None:
    scene = Scene()
    scene.registry.revoke("c-1")

    unknown = scene.put_bundle(archive(), client_id="c-9")
    revoked = scene.put_bundle(archive())

    assert detail(unknown) == (404, "no such client")
    assert detail(revoked) == (403, "revoked")
    assert scene.store.shipped("c-1") is None


@pytest.mark.parametrize("signature", [None, "garbage", ""])
def test_a_bundle_without_a_valid_signature_is_refused(signature: str | None) -> None:
    scene = Scene()
    call = scene.call(
        "PUT",
        "c-1",
        body=archive(),
        headers={} if signature is None else {BUNDLE_SIGNATURE: signature},
    )

    assert detail(scene.store.route(call)) == (400, NOT_SIGNED)
    assert scene.store.shipped("c-1") is None


def test_a_bundle_signed_by_another_key_is_refused() -> None:
    scene = Scene()
    _, theirs = scene.other()

    assert detail(scene.put_bundle(archive(), pair=theirs)) == (400, NOT_SIGNED)


def test_a_bundle_whose_digest_is_not_the_signed_one_is_refused() -> None:
    scene = Scene()

    answer = scene.put_bundle(archive(), sha256="0" * 64)

    assert detail(answer) == (400, OTHER_BYTES)


@pytest.mark.parametrize(
    "garbage",
    [b"not an archive", b""],
)
def test_a_bundle_that_is_no_archive_is_refused_in_igni_words_not_a_python_error(
    garbage: bytes,
) -> None:
    scene = Scene()

    answer = scene.put_bundle(garbage)

    assert detail(answer) == (400, "no manifest.json at the bundle's root")
    assert scene.store.shipped("c-1") is None


def test_a_bundle_with_no_manifest_at_its_root_is_refused_in_igni_words() -> None:
    scene = Scene()

    answer = scene.put_bundle(archive(name="nested/manifest.json"))

    assert detail(answer) == (400, "no manifest.json at the bundle's root")


def test_a_manifest_that_is_not_an_object_or_not_laid_out_as_igni_reads_it_is_refused() -> None:
    scene = Scene()

    not_object = scene.put_bundle(archive(["tickets"]))
    bad_assets = scene.put_bundle(archive({"id": "tickets", "version": "1.0.0", "assets": 3}))

    assert detail(not_object) == (400, "no manifest.json at the bundle's root")
    assert detail(bad_assets) == (400, "the manifest is not what was signed")


def test_a_manifest_that_differs_from_the_signed_id_or_version_is_refused() -> None:
    scene = Scene()

    other_id = scene.put_bundle(archive(), extension="notes")
    other_version = scene.put_bundle(archive(), version="2.0.0")

    for answer in (other_id, other_version):
        assert detail(answer) == (400, "the manifest is not what was signed")
    assert scene.store.shipped("c-1") is None


def test_every_asset_the_manifest_names_must_be_uploaded_first_by_this_client() -> None:
    scene = Scene()
    scene.other()
    data = b"asset"
    digest = hashlib.sha256(data).hexdigest()
    bundle = archive(assets=[{"name": "a.bin", "sha256": digest}, {"name": "b.bin", "sha256": "f"}])
    scene.put_asset(data, client_id="c-1")
    scene.store.assets[AssetKey(client_id="c-2", sha256="f")] = b"theirs"

    refused = scene.put_bundle(bundle)
    scene.store.assets[AssetKey(client_id="c-1", sha256="f")] = b"mine"
    accepted = scene.put_bundle(bundle)

    assert detail(refused) == (400, "assets not uploaded first: b.bin")
    assert accepted.status_code == 200


def test_another_approved_service_shipping_the_extension_is_a_conflict() -> None:
    scene = Scene()
    other, pair = scene.other()
    assert scene.put_bundle(archive(), client_id="c-2", pair=pair).status_code == 200

    answer = scene.put_bundle(archive())

    assert detail(answer) == (409, "another service ships this extension")
    scene.registry.revoke(other.client_id)
    assert scene.put_bundle(archive()).status_code == 200


def test_a_service_that_is_not_yet_approved_does_not_block_the_extension() -> None:
    scene = Scene()
    _, pair = scene.other()
    scene.put_bundle(archive(), client_id="c-2", pair=pair)
    scene.registry.clients["c-2"].state = ClientState.PENDING

    assert scene.put_bundle(archive()).status_code == 200


def test_a_new_version_replaces_the_shipped_one_when_nothing_is_held() -> None:
    scene = Scene()
    scene.put_bundle(archive())

    scene.put_bundle(archive(version="2.0.0"), version="2.0.0")

    shipped = scene.store.shipped("c-1")
    assert shipped is not None
    assert shipped.version == "2.0.0"


# ── Holding ─────────────────────────────────────────────────────────


def test_a_first_upload_and_an_unapproved_client_ship_directly_even_when_holding() -> None:
    scene = Scene()
    scene.store.hold("asks for more")
    first = scene.put_bundle(archive())
    _, pair = scene.other()
    scene.registry.clients["c-2"].state = ClientState.PENDING

    second = scene.put_bundle(archive(id="notes"), client_id="c-2", pair=pair, extension="notes")

    assert first.json()["held"] is False
    assert second.json()["held"] is False
    assert scene.store.held == {}


def test_a_new_version_from_a_service_not_yet_approved_ships_even_when_holding() -> None:
    scene = Scene()
    scene.registry.clients["c-1"].state = ClientState.PENDING
    scene.put_bundle(archive())
    scene.store.hold("asks for more")

    answer = scene.put_bundle(archive(version="2.0.0"), version="2.0.0")

    assert answer.json()["held"] is False
    assert scene.store.held == {}
    assert scene.store.latest("c-1").version == "2.0.0"


def test_a_new_version_from_an_approved_service_is_held_and_machines_keep_the_old() -> None:
    scene = Scene()
    scene.put_bundle(archive())
    scene.store.hold("asks for more")

    answer = scene.put_bundle(archive(version="2.0.0"), version="2.0.0")

    assert answer.json()["held"] is True
    assert answer.json()["reason"] == "held for a super admin: asks for more"
    shipped, latest = scene.store.shipped("c-1"), scene.store.latest("c-1")
    assert shipped is not None
    assert (shipped.version, latest.version) == ("1.0.0", "2.0.0")
    assert latest is scene.store.held["c-1"]


def test_a_second_held_upload_replaces_the_first() -> None:
    scene = Scene()
    scene.put_bundle(archive())
    scene.store.hold("why")
    scene.put_bundle(archive(version="2.0.0"), version="2.0.0")

    scene.put_bundle(archive(version="3.0.0"), version="3.0.0")

    assert scene.store.latest("c-1").version == "3.0.0"
    assert len(scene.store.held) == 1


def test_getting_the_extension_answers_the_held_version_with_its_reason_else_the_shipped() -> None:
    scene = Scene()
    scene.put_bundle(archive())
    shipped = scene.store.route(scene.call("GET", "c-1"))
    scene.store.hold("why")
    scene.put_bundle(archive(version="2.0.0"), version="2.0.0")

    waiting = scene.store.route(scene.call("GET", "c-1"))

    assert (shipped.json()["version"], shipped.json()["held"]) == ("1.0.0", False)
    assert (waiting.json()["version"], waiting.json()["held"]) == ("2.0.0", True)
    assert waiting.json()["reason"] == "held for a super admin: why"


def test_getting_what_was_never_uploaded_is_not_found_for_known_and_unknown_clients() -> None:
    scene = Scene()

    known = scene.store.route(scene.call("GET", "c-1"))
    unknown = scene.store.route(scene.call("GET", "c-9"))

    for answer in (known, unknown):
        assert detail(answer) == (404, "Nothing uploaded for this client")


def test_a_revoked_client_may_still_read_its_extension() -> None:
    scene = Scene()
    scene.put_bundle(archive())
    scene.registry.revoke("c-1")

    assert scene.store.route(scene.call("GET", "c-1")).status_code == 200


def test_release_stops_holding_but_keeps_what_is_held_and_reset_clears_it() -> None:
    scene = Scene()
    scene.put_bundle(archive())
    scene.store.hold("why")
    scene.put_bundle(archive(version="2.0.0"), version="2.0.0")

    scene.store.release()
    assert scene.store.hold_uploads is None
    assert "c-1" in scene.store.held
    shipped_after_release = scene.put_bundle(archive(version="3.0.0"), version="3.0.0")
    assert shipped_after_release.json()["held"] is False

    scene.store.hold("again")
    scene.store.reset()
    assert scene.store.hold_uploads is None
    assert scene.store.held == {}
    assert scene.store.shipped("c-1") is not None


def test_latest_prefers_the_held_upload_and_raises_when_there_is_nothing() -> None:
    scene = Scene()

    with pytest.raises(KeyError):
        scene.store.latest("c-1")


def test_a_path_the_store_does_not_serve_is_not_found() -> None:
    scene = Scene()
    call = RoutedCall(
        seen=SeenRequest(method="GET", path=f"{IgniPaths.CLIENTS}/c-1/other", headers={}, body=b"")
    )

    assert detail(scene.store.route(call)) == (404, "Not Found")


def test_the_fakes_extension_store_and_notifications_stand_on_its_one_client_registry() -> None:
    fake = FakeIgni()

    assert fake.extensions.clients is fake.clients
    assert fake.notifications.extensions is fake.extensions
    assert fake.notifications.directory is fake.directory

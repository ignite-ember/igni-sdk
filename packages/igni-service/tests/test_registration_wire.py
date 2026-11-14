"""What the registration says to igni and does with every answer: its bodies, refusals, retries and uploads.

`ServiceRegistration` is driven directly against a stub igni that answers
what each test tells it to and keeps every request it was sent. The
stub is a fake of igni, not of the code under audit.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from igni_service import MemoryKeyStore
from igni_service.assets import BundleLayout
from igni_service.bundle.archive import BundleArchive
from igni_service.errors import BundleError, IgniUnavailable
from igni_service.registration import (
    ASSET_SIGNATURE_HEADER,
    SIGNATURE_HEADER,
    AssetBody,
    ClientMetadata,
    ExtensionBundle,
    ExtensionRefused,
    PublishedExtension,
    Registration,
    ServiceRegistration,
)
from igni_service.server import IgniServer
from igni_service.signing import SigningKey
from igni_service.urls import IgniPaths

Answer = httpx.Response | Exception


class Igni:
    """igni's registration and extension endpoints, with what each was asked."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.bodies: list[bytes] = []
        self.answers: dict[str, Callable[[httpx.Request], Answer]] = {
            "POST": lambda r: httpx.Response(
                201, json={"client_id": "c1", "client_uri": "https://svc.test", "state": "pending"}
            ),
            "GET": lambda r: httpx.Response(404),
            "HEAD": lambda r: httpx.Response(404),
            "PUT": lambda r: httpx.Response(200, json=self.published()),
        }

    @staticmethod
    def published(**fields: Any) -> dict[str, Any]:
        return {"extension_id": "acme.example", "version": "1.0.0", "sha256": "ab", **fields}

    def answer(self, method: str, answer: Answer) -> None:
        self.answers[method] = lambda r: answer

    def sent(self, method: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        self.requests.append(request)
        self.bodies.append(body)
        await asyncio.sleep(0)
        outcome = self.answers[request.method](request)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def igni() -> Igni:
    return Igni()


def registration_for(igni: Igni, bundle_path: str = "", **options: Any) -> ServiceRegistration:
    server = IgniServer(
        base_url="http://igni.test",
        own_url="https://svc.test/",
        http=httpx.AsyncClient(transport=httpx.MockTransport(igni.handle)),
    )
    return ServiceRegistration(
        server,
        SigningKey(MemoryKeyStore()),
        service_name="Acme",
        bundle_path=bundle_path,
        **options,
    )


@pytest.fixture
def registration(igni: Igni) -> ServiceRegistration:
    return registration_for(igni)


def asset_entry(body: bytes, name: str = "model", **overrides: Any) -> dict[str, Any]:
    return {
        "name": name,
        "platform": "any",
        "file": f"{name}.bin",
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "source": f"https://downloads.test/{name}.bin",
        **overrides,
    }


def build(
    tmp_path: Path,
    *,
    manifest: dict[str, Any] | None = None,
    assets: dict[str, bytes] | None = None,
) -> Path:
    """A bundle archive and the `.assets` directory the builder leaves beside it."""
    staging = tmp_path / "staging"
    staging.mkdir(exist_ok=True)
    declared = manifest if manifest is not None else {"id": "acme.example", "version": "1.0.0"}
    (staging / "manifest.json").write_text(json.dumps(declared))
    out = tmp_path / "extension-bundle.tar.gz"
    BundleArchive.write(staging, out)
    if assets:
        beside = BundleLayout.assets_dir(out)
        beside.mkdir(exist_ok=True)
        for digest, body in assets.items():
            (beside / digest).write_bytes(body)
    return out


MODEL = b"the model's weights"
MODEL_SHA = hashlib.sha256(MODEL).hexdigest()


def with_model(tmp_path: Path, **overrides: Any) -> Path:
    manifest = {
        "id": "acme.example",
        "version": "1.0.0",
        "assets": [asset_entry(MODEL, **overrides)],
    }
    return build(tmp_path, manifest=manifest, assets={MODEL_SHA: MODEL})


class TestTheBundle:
    def test_it_reads_its_manifest_digest_and_claim_without_unpacking(self, tmp_path: Path) -> None:
        path = build(tmp_path, manifest={"id": "acme.example", "version": 7})

        bundle = ExtensionBundle.at(path)

        assert bundle is not None
        assert (bundle.extension_id, bundle.version) == ("acme.example", "7")
        assert bundle.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        assert bundle.archive == path.read_bytes()
        assert bundle.assets == []
        claim = bundle.claim
        assert (claim.extension, claim.version, claim.sha256) == (
            "acme.example",
            "7",
            bundle.sha256,
        )
        assert bundle.assets_dir == tmp_path / "extension-bundle.assets"

    def test_no_path_a_directory_or_a_missing_file_is_no_bundle(self, tmp_path: Path) -> None:
        assert ExtensionBundle.at("") is None
        assert ExtensionBundle.at(tmp_path) is None
        assert ExtensionBundle.at(tmp_path / "nothing.tar.gz") is None

    @pytest.mark.parametrize(
        "manifest",
        [{"version": "1"}, {"id": "a"}, {}, {"id": "a", "version": "1", "assets": [{"name": "x"}]}],
        ids=["no id", "no version", "empty", "bad asset"],
    )
    def test_a_manifest_that_does_not_say_what_it_is_is_a_bundle_error(
        self, tmp_path: Path, manifest: dict[str, Any]
    ) -> None:
        with pytest.raises(BundleError, match="manifest is unreadable"):
            ExtensionBundle.at(build(tmp_path, manifest=manifest))

    def test_a_file_that_is_not_an_archive_is_a_bundle_error(self, tmp_path: Path) -> None:
        broken = tmp_path / "extension-bundle.tar.gz"
        broken.write_bytes(b"not a tarball")

        with pytest.raises(BundleError, match="unreadable"):
            ExtensionBundle.at(broken)

    def test_an_asset_file_is_returned_only_with_the_size_and_digest_the_manifest_pins(
        self, tmp_path: Path
    ) -> None:
        bundle = ExtensionBundle.at(with_model(tmp_path))
        assert bundle is not None
        (asset,) = bundle.assets
        assert bundle.asset_file(asset) == tmp_path / "extension-bundle.assets" / MODEL_SHA

        held = tmp_path / "extension-bundle.assets" / MODEL_SHA
        held.write_bytes(b"x" * len(MODEL))  # the right size, the wrong bytes
        with pytest.raises(BundleError, match="build the bundle again"):
            bundle.asset_file(asset)
        held.write_bytes(MODEL + b"!")  # the wrong size
        with pytest.raises(BundleError, match="model"):
            bundle.asset_file(asset)
        held.unlink()
        with pytest.raises(BundleError, match="SHA-256"):
            bundle.asset_file(asset)

    def test_a_bundle_made_from_bytes_has_no_assets_directory_to_read_from(
        self, tmp_path: Path
    ) -> None:
        path = with_model(tmp_path)
        bundle = ExtensionBundle(path.read_bytes())

        with pytest.raises(BundleError, match="build the bundle again"):
            bundle.asset_file(bundle.assets[0])

    async def test_an_asset_body_is_streamed_in_one_mebibyte_chunks(self, tmp_path: Path) -> None:
        big = tmp_path / "big"
        big.write_bytes(b"a" * (2 * 1024 * 1024 + 5))

        chunks = [chunk async for chunk in AssetBody(big)]

        assert [len(chunk) for chunk in chunks] == [1024 * 1024, 1024 * 1024, 5]
        empty = tmp_path / "empty"
        empty.write_bytes(b"")
        assert [chunk async for chunk in AssetBody(empty)] == []


class TestTheWireModels:
    def test_a_registration_names_a_service_with_a_private_key_unless_told_otherwise(self) -> None:
        metadata = ClientMetadata.model_validate(
            {"client_name": "Acme", "client_uri": "https://svc.test", "jwks": {"keys": []}}
        )

        assert metadata.kind == "service"
        assert metadata.token_endpoint_auth_method == "private_key_jwt"
        assert metadata.redirect_uris == []

    def test_an_answer_with_only_a_client_id_is_a_registration_and_one_without_is_not(self) -> None:
        bare = Registration.model_validate({"client_id": "c1"})

        assert (bare.client_uri, bare.state, bare.thumbprint) == ("", "", "")
        with pytest.raises(ValueError):
            Registration.model_validate({"state": "approved"})

    def test_a_published_extension_is_not_held_unless_igni_says_so(self) -> None:
        published = PublishedExtension.model_validate(Igni.published())

        assert published.held is False
        assert published.reason is None and published.added == []

    def test_the_documented_constants_are_what_the_backoff_and_uploads_run_on(self) -> None:
        assert ServiceRegistration.RETRY_MIN == 5.0
        assert ServiceRegistration.RETRY_MAX == 300.0
        assert ServiceRegistration.UPLOAD_TIMEOUT == 120.0
        assert ServiceRegistration.ASSET_UPLOAD_TIMEOUT == 900.0
        assert AssetBody.CHUNK == 1024 * 1024
        assert SIGNATURE_HEADER == "X-Igni-Bundle-Signature"
        assert ASSET_SIGNATURE_HEADER == "X-Igni-Asset-Signature"


class TestRegistering:
    async def test_the_body_is_the_services_rfc_7591_metadata_with_its_public_key(
        self, igni: Igni
    ) -> None:
        registration = registration_for(igni)
        registration._redirect_uris.append("https://svc.test/callback")  # noqa: SLF001

        await registration.register()

        (request,) = igni.sent("POST")
        assert request.url.path == IgniPaths.CLIENTS
        body = json.loads(igni.bodies[0])
        assert body["client_name"] == "Acme"
        assert body["client_uri"] == "https://svc.test"
        assert body["kind"] == "service"
        assert body["redirect_uris"] == ["https://svc.test/callback"]
        assert body["token_endpoint_auth_method"] == "private_key_jwt"
        (key,) = body["jwks"]["keys"]
        assert key["kty"] == "RSA" and "d" not in key

    async def test_igni_s_answer_is_held_and_the_registered_event_is_set(
        self, igni: Igni, registration: ServiceRegistration
    ) -> None:
        assert registration.current is None
        assert not registration.registered.is_set()

        held = await registration.register()

        assert held.client_id == "c1" and registration.current is held
        assert registration.registered.is_set()
        assert await registration.client_id() == "c1"

    @pytest.mark.parametrize("status", [200, 201])
    async def test_both_success_statuses_are_accepted(self, igni: Igni, status: int) -> None:
        igni.answer("POST", httpx.Response(status, json={"client_id": "c1"}))

        assert (await registration_for(igni).register()).client_id == "c1"

    async def test_register_posts_again_each_time_and_ensure_only_once(self, igni: Igni) -> None:
        registration = registration_for(igni)

        await registration.ensure()
        await registration.ensure()
        await registration.client_id()
        assert len(igni.sent("POST")) == 1

        await registration.register()
        assert len(igni.sent("POST")) == 2

    async def test_many_callers_at_once_send_one_registration(self, igni: Igni) -> None:
        registration = registration_for(igni)

        found = await asyncio.gather(*(registration.ensure() for _ in range(6)))

        assert len(igni.sent("POST")) == 1
        assert all(item is found[0] for item in found)

    async def test_a_refusal_says_the_status_and_the_body_and_is_retried_by_the_next_call(
        self, igni: Igni
    ) -> None:
        igni.answer("POST", httpx.Response(403, text="who are you"))
        registration = registration_for(igni)

        with pytest.raises(IgniUnavailable, match="refused the registration: 403 who are you"):
            await registration.ensure()

        assert registration.current is None and not registration.registered.is_set()
        igni.answer("POST", httpx.Response(200, json={"client_id": "c2"}))
        assert (await registration.ensure()).client_id == "c2"

    @pytest.mark.parametrize(
        "answer",
        [
            httpx.Response(500, text="boom"),
            httpx.Response(204),
            httpx.Response(200, text="<html>"),
            httpx.Response(200, json=["c1"]),
            httpx.Response(200, json={"state": "pending"}),
        ],
        ids=["500", "204", "not json", "wrong shape", "no client id"],
    )
    async def test_an_answer_that_is_not_a_registration_is_igni_unavailable(
        self, igni: Igni, answer: httpx.Response
    ) -> None:
        igni.answer("POST", answer)
        registration = registration_for(igni)

        with pytest.raises(IgniUnavailable):
            await registration.register()

        assert registration.current is None and not registration.registered.is_set()

    async def test_a_network_error_is_igni_unavailable(self, igni: Igni) -> None:
        igni.answer("POST", httpx.ConnectTimeout("slow"))

        with pytest.raises(IgniUnavailable, match="ConnectTimeout"):
            await registration_for(igni).register()


class TestAskingWhatIgniHolds:
    async def test_no_extension_is_none_and_a_held_one_is_read(self, igni: Igni) -> None:
        registration = registration_for(igni)
        assert await registration.published() is None
        assert igni.sent("GET")[0].url.path == IgniPaths.extension("c1")

        igni.answer("GET", httpx.Response(200, json=Igni.published(held=True, added=["x"])))
        published = await registration.published()
        assert published is not None and published.held and published.added == ["x"]

    @pytest.mark.parametrize(
        "answer",
        [
            httpx.Response(500),
            httpx.Response(403),
            httpx.Response(204),
            httpx.Response(200, text="nope"),
            httpx.Response(200, json={"version": "1"}),
            httpx.ReadError("cut"),
        ],
        ids=["500", "403", "204", "not json", "wrong shape", "network"],
    )
    async def test_anything_else_is_igni_unavailable(self, igni: Igni, answer: Answer) -> None:
        igni.answer("GET", answer)

        with pytest.raises(IgniUnavailable):
            await registration_for(igni).published()

    async def test_an_asset_is_held_or_not_by_a_head_request(self, igni: Igni) -> None:
        registration = registration_for(igni)
        assert await registration.holds_asset("d1") is False
        assert igni.sent("HEAD")[0].url.path == IgniPaths.extension_asset("c1", "d1")

        igni.answer("HEAD", httpx.Response(200))
        assert await registration.holds_asset("d1") is True

    @pytest.mark.parametrize(
        "answer", [httpx.Response(500), httpx.Response(401), httpx.ReadError("cut")]
    )
    async def test_an_asset_question_igni_cannot_answer_is_igni_unavailable(
        self, igni: Igni, answer: Answer
    ) -> None:
        igni.answer("HEAD", answer)

        with pytest.raises(IgniUnavailable):
            await registration_for(igni).holds_asset("d1")


class TestShippingAnAsset:
    async def test_it_is_streamed_signed_with_its_length_and_a_long_timeout(
        self, igni: Igni, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        registration = registration_for(igni)
        bundle = ExtensionBundle.at(with_model(tmp_path))
        assert bundle is not None

        with caplog.at_level(logging.INFO, logger="igni_service"):
            shipped = await registration.ship_asset(bundle, bundle.assets[0])

        assert shipped is True
        (put,) = igni.sent("PUT")
        assert put.url.path == IgniPaths.extension_asset("c1", MODEL_SHA)
        assert igni.bodies[-1] == MODEL
        assert put.headers["content-length"] == str(len(MODEL))
        assert put.headers["content-type"] == "application/octet-stream"
        assert put.headers[ASSET_SIGNATURE_HEADER]
        assert put.extensions["timeout"]["read"] == ServiceRegistration.ASSET_UPLOAD_TIMEOUT
        assert "uploaded asset model (any) of acme.example" in caplog.text

    async def test_one_igni_holds_is_not_sent_again(self, igni: Igni, tmp_path: Path) -> None:
        igni.answer("HEAD", httpx.Response(200))
        bundle = ExtensionBundle.at(with_model(tmp_path))
        assert bundle is not None

        assert await registration_for(igni).ship_asset(bundle, bundle.assets[0]) is False

        assert igni.sent("PUT") == []

    async def test_a_damaged_file_is_a_bundle_error_and_nothing_is_sent(
        self, igni: Igni, tmp_path: Path
    ) -> None:
        path = with_model(tmp_path)
        (tmp_path / "extension-bundle.assets" / MODEL_SHA).write_bytes(b"short")
        bundle = ExtensionBundle.at(path)
        assert bundle is not None

        with pytest.raises(BundleError):
            await registration_for(igni).ship_asset(bundle, bundle.assets[0])

        assert igni.sent("PUT") == []

    @pytest.mark.parametrize("status", [400, 401, 403, 409, 413, 422])
    async def test_a_4xx_is_a_refusal_naming_the_asset_and_what_igni_said(
        self, igni: Igni, tmp_path: Path, status: int
    ) -> None:
        igni.answer("PUT", httpx.Response(status, text="no thanks"))
        bundle = ExtensionBundle.at(with_model(tmp_path))
        assert bundle is not None

        with pytest.raises(ExtensionRefused) as refused:
            await registration_for(igni).ship_asset(bundle, bundle.assets[0])

        message = str(refused.value)
        assert "asset model (any) of acme.example 1.0.0" in message
        assert f"{status} no thanks" in message

    @pytest.mark.parametrize(
        "answer",
        [
            httpx.Response(500, text="down"),
            httpx.Response(503),
            httpx.Response(204),
            httpx.Response(302),
            httpx.WriteError("cut"),
        ],
        ids=["500", "503", "204", "302", "network"],
    )
    async def test_anything_else_that_is_not_a_200_is_igni_unavailable(
        self, igni: Igni, tmp_path: Path, answer: Answer
    ) -> None:
        igni.answer("PUT", answer)
        bundle = ExtensionBundle.at(with_model(tmp_path))
        assert bundle is not None

        with pytest.raises(IgniUnavailable):
            await registration_for(igni).ship_asset(bundle, bundle.assets[0])


class TestShippingTheBundle:
    async def test_its_assets_go_first_and_the_bundle_after_them_signed(
        self, igni: Igni, tmp_path: Path
    ) -> None:
        bundle = ExtensionBundle.at(with_model(tmp_path))
        assert bundle is not None

        assert await registration_for(igni).ship(bundle) is True

        puts = igni.sent("PUT")
        assert [p.url.path for p in puts] == [
            IgniPaths.extension_asset("c1", MODEL_SHA),
            IgniPaths.extension("c1"),
        ]
        assert puts[1].headers["content-type"] == "application/gzip"
        assert puts[1].headers[SIGNATURE_HEADER]
        assert igni.bodies[-1] == bundle.archive
        assert puts[1].extensions["timeout"]["read"] == ServiceRegistration.UPLOAD_TIMEOUT

    async def test_the_timeout_is_never_shorter_than_the_servers_own(
        self, igni: Igni, tmp_path: Path
    ) -> None:
        bundle = ExtensionBundle.at(build(tmp_path))
        assert bundle is not None
        server = IgniServer(
            base_url="http://igni.test",
            timeout=500.0,
            http=httpx.AsyncClient(transport=httpx.MockTransport(igni.handle)),
        )
        registration = ServiceRegistration(
            server, SigningKey(MemoryKeyStore()), service_name="Acme"
        )

        await registration.ship(bundle)

        assert igni.sent("PUT")[0].extensions["timeout"]["read"] == 500.0

    async def test_bytes_igni_already_holds_are_not_sent_and_it_is_said(
        self, igni: Igni, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        bundle = ExtensionBundle.at(with_model(tmp_path))
        assert bundle is not None
        igni.answer("GET", httpx.Response(200, json=Igni.published(sha256=bundle.sha256)))

        with caplog.at_level(logging.INFO, logger="igni_service"):
            assert await registration_for(igni).ship(bundle) is False

        assert igni.sent("PUT") == [] and igni.sent("HEAD") == []
        assert f"already holds extension acme.example 1.0.0 ({bundle.sha256})" in caplog.text

    async def test_different_bytes_are_sent_even_when_the_version_is_the_same(
        self, igni: Igni, tmp_path: Path
    ) -> None:
        bundle = ExtensionBundle.at(build(tmp_path))
        assert bundle is not None
        igni.answer("GET", httpx.Response(200, json=Igni.published(sha256="other")))

        assert await registration_for(igni).ship(bundle) is True

    async def test_held_bytes_say_so_and_are_not_sent(
        self, igni: Igni, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        bundle = ExtensionBundle.at(build(tmp_path))
        assert bundle is not None
        igni.answer(
            "GET",
            httpx.Response(
                200,
                json=Igni.published(
                    sha256=bundle.sha256,
                    held=True,
                    reason="held for a super admin: it asks for the network",
                    added=["net", "disk"],
                ),
            ),
        )

        with caplog.at_level(logging.INFO, logger="igni_service"):
            assert await registration_for(igni).ship(bundle) is False

        assert igni.sent("PUT") == []
        assert "is held for a super admin (it asks for the network; it adds net, disk)" in (
            caplog.text
        )

    async def test_a_hold_with_no_reason_and_no_grants_says_the_default(
        self, igni: Igni, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        bundle = ExtensionBundle.at(build(tmp_path))
        assert bundle is not None
        igni.answer("PUT", httpx.Response(200, json=Igni.published(held=True)))

        with caplog.at_level(logging.INFO, logger="igni_service"):
            assert await registration_for(igni).ship(bundle) is True

        assert "(it asks for more than the approved version)" in caplog.text
        assert "it adds" not in caplog.text

    async def test_an_upload_that_is_taken_but_unreadable_still_counts_as_uploaded(
        self, igni: Igni, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        bundle = ExtensionBundle.at(build(tmp_path))
        assert bundle is not None
        igni.answer("PUT", httpx.Response(200, text="ok"))

        with caplog.at_level(logging.INFO, logger="igni_service"):
            assert await registration_for(igni).ship(bundle) is True

        assert "uploaded extension acme.example 1.0.0" in caplog.text
        assert "held for a super admin" not in caplog.text

    @pytest.mark.parametrize("status", [401, 403, 409, 422])
    async def test_a_4xx_is_a_refusal_with_the_status_and_igni_s_words(
        self, igni: Igni, tmp_path: Path, status: int
    ) -> None:
        bundle = ExtensionBundle.at(build(tmp_path))
        assert bundle is not None
        igni.answer("PUT", httpx.Response(status, text="bad signature"))

        with pytest.raises(ExtensionRefused, match=f"acme.example 1.0.0: {status} bad signature"):
            await registration_for(igni).ship(bundle)

    @pytest.mark.parametrize(
        "answer",
        [httpx.Response(500, text="down"), httpx.Response(204), httpx.WriteTimeout("slow")],
        ids=["500", "204", "network"],
    )
    async def test_anything_else_that_is_not_a_200_is_igni_unavailable(
        self, igni: Igni, tmp_path: Path, answer: Answer
    ) -> None:
        bundle = ExtensionBundle.at(build(tmp_path))
        assert bundle is not None
        igni.answer("PUT", answer)

        with pytest.raises(IgniUnavailable):
            await registration_for(igni).ship(bundle)

    async def test_a_refused_asset_stops_the_bundle_from_being_sent(
        self, igni: Igni, tmp_path: Path
    ) -> None:
        bundle = ExtensionBundle.at(with_model(tmp_path))
        assert bundle is not None
        igni.answer("PUT", httpx.Response(422, text="too big"))

        with pytest.raises(ExtensionRefused):
            await registration_for(igni).ship(bundle)

        assert len(igni.sent("PUT")) == 1


class TestStartingUp:
    async def test_an_empty_bundle_path_means_no_extension_and_says_nothing_about_one(
        self, igni: Igni, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="igni_service"):
            started = await registration_for(igni).start()

        assert started.client_id == "c1"
        assert igni.sent("GET") == [] and igni.sent("PUT") == []
        assert "no extension bundle" not in caplog.text

    async def test_a_bundle_path_with_nothing_there_is_a_warning_and_the_registration_stands(
        self, igni: Igni, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        missing = str(tmp_path / "gone.tar.gz")

        with caplog.at_level(logging.INFO, logger="igni_service"):
            started = await registration_for(igni, missing).start()

        assert started.client_id == "c1"
        assert f"no extension bundle at {missing}; nothing uploaded" in caplog.text
        assert igni.sent("PUT") == []

    async def test_the_banner_shows_the_identity_and_falls_back_to_the_services_own_url(
        self, igni: Igni, caplog: pytest.LogCaptureFixture
    ) -> None:
        igni.answer("POST", httpx.Response(201, json={"client_id": "c1", "state": "pending"}))
        registration = registration_for(igni)

        with caplog.at_level(logging.INFO, logger="igni_service"):
            await registration.start()

        assert "client id:   c1" in caplog.text
        assert "state:       pending" in caplog.text
        assert "URL:         https://svc.test\n" in caplog.text
        assert f"thumbprint:  {await registration._key.thumbprint()}" in caplog.text  # noqa: SLF001

    async def test_an_asset_damaged_beside_the_bundle_is_logged_and_the_registration_stands(
        self, igni: Igni, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = with_model(tmp_path)
        (tmp_path / "extension-bundle.assets" / MODEL_SHA).unlink()

        with caplog.at_level(logging.INFO, logger="igni_service"):
            started = await registration_for(igni, str(path)).start()

        assert started.client_id == "c1"
        assert "nothing more uploaded" in caplog.text
        assert igni.sent("PUT") == []

    async def test_a_refused_bundle_is_logged_and_igni_being_down_is_raised(
        self, igni: Igni, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = build(tmp_path)
        igni.answer("PUT", httpx.Response(422, text="no"))
        with caplog.at_level(logging.INFO, logger="igni_service"):
            assert (await registration_for(igni, str(path)).start()).client_id == "c1"
        assert "refused extension acme.example" in caplog.text

        igni.answer("PUT", httpx.Response(503))
        with pytest.raises(IgniUnavailable):
            await registration_for(igni, str(path)).start()


class TestNextSteps:
    def test_each_known_state_has_its_own_guidance_indented_under_the_banner(self) -> None:
        pending = ServiceRegistration.next_step("pending")
        approved = ServiceRegistration.next_step("approved")
        revoked = ServiceRegistration.next_step("revoked")

        assert "A super admin approves this service in igni's portal under" in pending
        assert "Approved. Its extension reaches a person's igni once" in approved
        assert "Revoked by a super admin" in revoked
        assert all(line.startswith("  ") for line in pending.split("\n"))
        assert len({pending, approved, revoked}) == 3

    @pytest.mark.parametrize("state", ["suspended", "", "PENDING"])
    def test_a_state_igni_has_not_documented_is_echoed(self, state: str) -> None:
        assert ServiceRegistration.next_step(state) == (
            f"  igni answered state {state!r}; see igni's portal under Services."
        )


class TestKeepingTrying:
    async def test_it_returns_the_registration_when_the_first_try_works(self, igni: Igni) -> None:
        found = await registration_for(igni).keep_trying()

        assert found is not None and found.client_id == "c1"

    async def test_a_stop_set_before_the_first_try_asks_igni_nothing(self, igni: Igni) -> None:
        stop = asyncio.Event()
        stop.set()

        assert await registration_for(igni).keep_trying(stop) is None
        assert igni.requests == []

    async def test_a_stop_during_the_wait_ends_it_at_once(self, igni: Igni) -> None:
        igni.answer("POST", httpx.Response(503))
        registration = registration_for(igni, retry_min=60.0, retry_max=60.0)
        stop = asyncio.Event()
        task = asyncio.create_task(registration.keep_trying(stop))
        await asyncio.sleep(0.05)
        assert not task.done()

        stop.set()

        assert await asyncio.wait_for(task, timeout=2) is None
        assert len(igni.sent("POST")) == 1

    async def test_the_wait_doubles_after_each_failure_up_to_the_cap(self, igni: Igni) -> None:
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        times: list[float] = []

        def refuse(request: httpx.Request) -> Answer:
            times.append(loop.time())
            if len(times) == 5:
                stop.set()
            return httpx.Response(503)

        igni.answers["POST"] = refuse
        registration = registration_for(igni, retry_min=0.05, retry_max=0.2)

        assert await asyncio.wait_for(registration.keep_trying(stop), timeout=5) is None

        gaps = [later - earlier for earlier, later in zip(times, times[1:], strict=False)]
        assert len(gaps) == 4
        assert 0.05 <= gaps[0] < 0.1
        assert 0.1 <= gaps[1] < 0.2
        assert 0.2 <= gaps[2] < 0.35
        assert 0.2 <= gaps[3] < 0.35  # held at the cap, not doubled to 0.4

"""The edges of assets: what a fetch leaves behind, what the network may do, what is refused."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from igni_service import BundleError
from igni_service.assets import (
    MAX_ASSET_BYTES,
    AssetFetcher,
    AssetPlatform,
    BundleAsset,
    BundleAssets,
    BundleLayout,
    FileDigest,
)

BODY = b"the asset's bytes"
SOURCE = "https://downloads.test/a/file.bin"


def asset(body: bytes = BODY, **overrides: object) -> BundleAsset:
    fields: dict[str, object] = {
        "name": "model",
        "platform": "any",
        "file": "file.bin",
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "source": SOURCE,
        **overrides,
    }
    return BundleAsset.model_validate(fields)


def fetcher(handler: Callable[[httpx.Request], httpx.Response]) -> AssetFetcher:
    return AssetFetcher(transport=httpx.MockTransport(handler))


def serves(body: bytes) -> AssetFetcher:
    return fetcher(lambda request: httpx.Response(200, content=body))


def only(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


class TestAFetchLeavesNothingBehind:
    @pytest.mark.parametrize(
        ("served", "message"),
        [
            (BODY + b"!", "larger than"),
            (BODY[:-1], "pins"),
            (b"x" * len(BODY), "pins"),
            (b"", "pins"),
        ],
    )
    def test_a_download_of_the_wrong_size_or_digest_leaves_no_file(
        self, tmp_path: Path, served: bytes, message: str
    ) -> None:
        with pytest.raises(BundleError, match=message):
            serves(served).fetch(asset(), tmp_path)

        assert only(tmp_path) == []

    def test_a_refused_status_leaves_no_file(self, tmp_path: Path) -> None:
        with pytest.raises(BundleError, match="answered 503"):
            fetcher(lambda request: httpx.Response(503)).fetch(asset(), tmp_path)

        assert only(tmp_path) == []

    @pytest.mark.parametrize(
        "error",
        [
            httpx.ConnectError("dns failure"),
            httpx.ReadTimeout("too slow"),
            httpx.RemoteProtocolError("cut off"),
        ],
    )
    def test_a_network_failure_is_a_bundle_error_that_names_the_asset(
        self, tmp_path: Path, error: httpx.HTTPError
    ) -> None:
        def fail(request: httpx.Request) -> httpx.Response:
            raise error

        with pytest.raises(BundleError, match=r"model \(any\).*could not be fetched") as raised:
            fetcher(fail).fetch(asset(), tmp_path)

        assert raised.value.__cause__ is error
        assert SOURCE in str(raised.value)
        assert only(tmp_path) == []

    def test_a_download_that_stops_halfway_leaves_no_file(self, tmp_path: Path) -> None:
        class Cut(httpx.SyncByteStream):
            def __iter__(self):  # type: ignore[no-untyped-def]
                yield BODY[:5]
                raise httpx.ReadError("connection lost")

        with pytest.raises(BundleError, match="could not be fetched"):
            fetcher(lambda request: httpx.Response(200, stream=Cut())).fetch(asset(), tmp_path)

        assert only(tmp_path) == []

    def test_a_redirect_to_plain_http_is_refused(self, tmp_path: Path) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.scheme == "https":
                return httpx.Response(302, headers={"Location": "http://mirror.test/file.bin"})
            return httpx.Response(200, content=BODY)

        with pytest.raises(BundleError, match="redirected to http://mirror.test/file.bin"):
            fetcher(handle).fetch(asset(), tmp_path)

        assert only(tmp_path) == []

    def test_a_redirect_that_stays_on_https_is_followed(self, tmp_path: Path) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.host == "downloads.test":
                return httpx.Response(302, headers={"Location": "https://mirror.test/file.bin"})
            return httpx.Response(200, content=BODY)

        path = fetcher(handle).fetch(asset(), tmp_path)

        assert path.read_bytes() == BODY


class TestWhatIsAlreadyThere:
    def test_a_file_of_the_right_size_and_the_wrong_digest_is_fetched_again(
        self, tmp_path: Path
    ) -> None:
        wanted = asset()
        (tmp_path / wanted.sha256).write_bytes(b"x" * len(BODY))

        path = serves(BODY).fetch(wanted, tmp_path)

        assert path.read_bytes() == BODY

    @pytest.mark.parametrize("held", [b"", b"short", BODY + b"more"])
    def test_a_file_of_the_wrong_size_is_fetched_again(self, tmp_path: Path, held: bytes) -> None:
        wanted = asset()
        (tmp_path / wanted.sha256).write_bytes(held)

        assert serves(BODY).fetch(wanted, tmp_path).read_bytes() == BODY

    def test_a_good_file_is_returned_without_any_request(self, tmp_path: Path) -> None:
        wanted = asset()
        (tmp_path / wanted.sha256).write_bytes(BODY)

        def nothing(request: httpx.Request) -> httpx.Response:
            raise AssertionError("asked the network")

        assert fetcher(nothing).fetch(wanted, tmp_path) == tmp_path / wanted.sha256

    def test_a_failed_refetch_leaves_the_corrupt_file_and_no_partial(self, tmp_path: Path) -> None:
        wanted = asset()
        (tmp_path / wanted.sha256).write_bytes(b"corrupt")

        with pytest.raises(BundleError):
            fetcher(lambda request: httpx.Response(500)).fetch(wanted, tmp_path)

        assert only(tmp_path) == [wanted.sha256]

    def test_a_missing_directory_is_made_with_its_parents(self, tmp_path: Path) -> None:
        into = tmp_path / "a" / "b" / "assets"

        path = serves(BODY).fetch(asset(), into)

        assert path == into / asset().sha256 and path.read_bytes() == BODY
        assert only(into) == [asset().sha256]


class TestTheDigest:
    def test_a_file_bigger_than_one_chunk_is_read_whole(self, tmp_path: Path) -> None:
        body = bytes(range(256)) * (3 * 1024 * 1024 // 256 + 1)
        file = tmp_path / "big"
        file.write_bytes(body)

        assert FileDigest.of(file) == hashlib.sha256(body).hexdigest()

    @pytest.mark.parametrize("held", [BODY, BODY + b"x", b"x" * len(BODY)])
    def test_a_match_is_the_declared_size_and_digest_of_a_file(
        self, tmp_path: Path, held: bytes
    ) -> None:
        file = tmp_path / "f"
        file.write_bytes(held)

        assert FileDigest.matches(file, asset()) is (held == BODY)

    def test_nothing_and_a_directory_never_match(self, tmp_path: Path) -> None:
        assert FileDigest.matches(tmp_path / "absent", asset()) is False
        assert FileDigest.matches(tmp_path, asset()) is False


class TestTheDeclaration:
    def test_the_digests_are_every_one_declared(self) -> None:
        other = b"another"
        assets = BundleAssets(assets=[asset(), asset(other, name="other", file="o.bin")])

        assert assets.digests() == {
            hashlib.sha256(BODY).hexdigest(),
            hashlib.sha256(other).hexdigest(),
        }
        assert BundleAssets().digests() == set()

    def test_the_same_name_twice_for_any_platform_is_refused(self) -> None:
        twice = [asset(platform="any"), asset(platform="any", file="again.bin")]

        with pytest.raises(ValidationError, match="must be one file"):
            BundleAssets(assets=twice)

    @pytest.mark.parametrize("repeated", AssetPlatform.specific())
    def test_the_same_name_twice_for_one_platform_is_refused_beside_the_others(
        self, repeated: AssetPlatform
    ) -> None:
        every = [asset(platform=str(p), file=f"{p}.bin") for p in AssetPlatform.specific()]
        repeat = asset(platform=str(repeated), file="again.bin")

        BundleAssets(assets=every)
        with pytest.raises(ValidationError, match="must be one file"):
            BundleAssets(assets=[*every, repeat])

    def test_a_manifest_with_no_assets_is_fine(self) -> None:
        assert BundleAssets.model_validate({}).assets == []
        assert BundleAssets(assets=[]).for_platform(AssetPlatform.LINUX_X86_64) == []

    def test_the_specific_platforms_are_the_three_igni_runs_on(self) -> None:
        assert AssetPlatform.specific() == (
            AssetPlatform.MACOS_ARM64,
            AssetPlatform.LINUX_X86_64,
            AssetPlatform.WINDOWS_X86_64,
        )
        assert [str(p) for p in AssetPlatform] == [
            "any",
            "macos-arm64",
            "linux-x86_64",
            "windows-x86_64",
        ]

    @pytest.mark.parametrize("name", ["model", "a", "0-9", "a" * 64])
    def test_a_name_may_be_lowercase_letters_digits_and_dashes(self, name: str) -> None:
        asset(name=name)

    @pytest.mark.parametrize("name", ["", "Model", "-model", "a_b", "a/b", ".hidden", "a" * 65])
    def test_any_other_name_is_refused(self, name: str) -> None:
        with pytest.raises(ValidationError):
            asset(name=name)

    @pytest.mark.parametrize("file", ["a", "model-1.2+x.bin", "Model.ONNX"])
    def test_a_file_is_one_plain_name(self, file: str) -> None:
        asset(file=file)

    @pytest.mark.parametrize(
        "file", ["", ".hidden", "..", "../x", "a/b", "/abs", "a b", "a\\b", "x" * 201]
    )
    def test_a_file_that_is_not_one_plain_name_is_refused(self, file: str) -> None:
        with pytest.raises(ValidationError):
            asset(file=file)

    def test_the_size_is_one_byte_up_to_the_most_igni_takes(self) -> None:
        asset(size=1)
        asset(size=MAX_ASSET_BYTES)
        for size in (0, -1, MAX_ASSET_BYTES + 1):
            with pytest.raises(ValidationError):
                asset(size=size)

    @pytest.mark.parametrize(
        "source",
        ["http://x.test/f", "https://", "https://x.test/a b", "ftp://x.test/f", "x.test/f"],
    )
    def test_a_source_that_is_not_one_https_address_is_refused(self, source: str) -> None:
        with pytest.raises(ValidationError):
            asset(source=source)

    @pytest.mark.parametrize("digest", ["", "a" * 63, "a" * 65, "A" * 64, "g" * 64])
    def test_a_digest_is_sixty_four_lowercase_hex_characters(self, digest: str) -> None:
        with pytest.raises(ValidationError):
            asset(sha256=digest)

    @pytest.mark.parametrize("file", ["a.tar.gz", "a.tgz", "a.zip"])
    def test_an_archive_can_be_unpacked(self, file: str) -> None:
        assert asset(file=file, unpack=True).unpack is True

    @pytest.mark.parametrize("file", ["a.bin", "a.tar", "a.gz", "tgz"])
    def test_anything_else_cannot(self, file: str) -> None:
        with pytest.raises(ValidationError, match="can be unpacked"):
            asset(file=file, unpack=True)
        assert asset(file=file).unpack is False

    def test_an_unknown_member_is_refused_and_a_declaration_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            asset(extra="x")
        with pytest.raises(ValidationError):
            asset().name = "other"


class TestTheLayout:
    @pytest.mark.parametrize(
        ("bundle", "assets"),
        [
            ("b.tar.gz", "b.assets"),
            ("b.tgz", "b.assets"),
            ("b", "b.assets"),
            ("b.zip", "b.zip.assets"),
            ("b.tar.gz.tar.gz", "b.tar.gz.assets"),
        ],
    )
    def test_the_assets_directory_sits_beside_the_bundle_named_without_its_suffix(
        self, bundle: str, assets: str
    ) -> None:
        assert BundleLayout.assets_dir(Path("/out") / bundle) == Path("/out") / assets

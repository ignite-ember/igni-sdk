"""What the fake holds of an uploaded bundle, and how `upload` makes one from a path.

`UploadedManifest` reads a manifest only as far as igni does, `HeldExtension`
is what igni answers about it, and `BundleSource` makes a bundle of an
extension's directory or its built archive.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest

from igni_service import IgniService
from igni_service.bundle.archive import BundleArchive
from igni_service.testing import FakeIgni, HeldExtension
from igni_service.testing_bundles import BundleSource, UploadedManifest
from igni_service.testing_wire import DetailError


def gzipped_tar(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def archive_of(manifest: dict[str, Any]) -> bytes:
    return gzipped_tar({"manifest.json": json.dumps(manifest).encode()})


def names_in(archive: bytes) -> set[str]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        return {member.name for member in tar if member.isfile()}


def extension_dir(root: Path, **files: str) -> Path:
    """An extension's directory holding `manifest.json` and the files given by path."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps({"id": "acme.example", "version": "1"}))
    for name, text in files.items():
        target = root / name.replace("__", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return root


class TestTheManifestIgniReads:
    def test_a_manifest_is_read_as_far_as_igni_reads_it(self) -> None:
        manifest = UploadedManifest.from_archive(
            archive_of(
                {
                    "id": "acme.example",
                    "version": "1.2.3",
                    "name": "Acme",
                    "assets": [{"name": "a.whl", "sha256": "ab", "platform": "linux"}],
                    "contributes": {"pages": [{"kind": "panel"}, {"kind": "settings", "x": 1}]},
                    "vm": {"memoryMib": 2048},
                }
            )
        )

        assert isinstance(manifest, UploadedManifest)
        assert (manifest.id, manifest.version, manifest.name) == ("acme.example", "1.2.3", "Acme")
        assert [(a.name, a.sha256) for a in manifest.assets] == [("a.whl", "ab")]
        assert manifest.pages == ["panel", "settings"]
        assert manifest.vm == {"memoryMib": 2048}

    def test_a_stand_in_manifest_with_nothing_but_an_id_is_taken(self) -> None:
        manifest = UploadedManifest.from_archive(archive_of({"id": "a", "something": "new"}))

        assert isinstance(manifest, UploadedManifest)
        assert (manifest.version, manifest.name, manifest.assets, manifest.vm) == (
            "",
            None,
            [],
            None,
        )
        assert manifest.pages == []
        assert manifest.model_extra == {"something": "new"}

    def test_an_empty_manifest_is_taken_with_nothing_in_it(self) -> None:
        manifest = UploadedManifest.from_archive(archive_of({}))

        assert manifest == UploadedManifest()

    @pytest.mark.parametrize(
        "manifest",
        [
            {"assets": "not a list"},
            {"contributes": []},
            {"contributes": {"pages": "panel"}},
            {"vm": 3},
            {"id": 7},
        ],
    )
    def test_a_manifest_with_the_wrong_kind_of_field_is_not_what_was_signed(
        self, manifest: dict[str, Any]
    ) -> None:
        refused = UploadedManifest.from_archive(archive_of(manifest))

        assert refused == DetailError(detail="the manifest is not what was signed")

    @pytest.mark.parametrize(
        "archive",
        [
            pytest.param(b"", id="empty"),
            pytest.param(b"not a tarball", id="not-a-tarball"),
            pytest.param(gzipped_tar({}), id="empty-tar"),
            pytest.param(gzipped_tar({"plugin/manifest.json": b"{}"}), id="not-at-the-root"),
            pytest.param(gzipped_tar({"manifest.json": b"{not json"}), id="not-json"),
            pytest.param(gzipped_tar({"manifest.json": b"[1]"}), id="not-an-object"),
        ],
    )
    def test_a_bundle_whose_manifest_cannot_be_read_has_none_at_its_root(
        self, archive: bytes
    ) -> None:
        refused = UploadedManifest.from_archive(archive)

        assert refused == DetailError(detail="no manifest.json at the bundle's root")

    def test_a_manifest_under_dot_slash_is_at_the_root(self) -> None:
        archive = gzipped_tar({"./manifest.json": b'{"id": "a"}'})

        manifest = UploadedManifest.from_archive(archive)

        assert isinstance(manifest, UploadedManifest) and manifest.id == "a"


class TestWhatIgniHolds:
    def held(self, **manifest: Any) -> HeldExtension:
        return HeldExtension(
            client_id="c-1",
            extension_id="acme.example",
            version="1.0.0",
            sha256="ab" * 32,
            archive=b"bytes",
            manifest=UploadedManifest.model_validate(manifest),
        )

    def test_a_bundle_with_no_reason_is_published(self) -> None:
        published = self.held().published()

        assert (published.extension_id, published.version, published.sha256) == (
            "acme.example",
            "1.0.0",
            "ab" * 32,
        )
        assert (published.held, published.reason) == (False, None)

    def test_a_bundle_with_a_reason_is_held_for_a_super_admin(self) -> None:
        published = self.held().published("it asks for more")

        assert (published.held, published.reason) == (True, "it asks for more")

    def test_an_empty_reason_still_holds_it(self) -> None:
        published = self.held().published("")

        assert (published.held, published.reason) == (True, "")

    def test_its_pages_are_the_manifests(self) -> None:
        held = self.held(contributes={"pages": [{"kind": "panel"}, {"kind": "chat"}]})

        assert held.pages == ["panel", "chat"]
        assert self.held().pages == []


class TestMakingABundle:
    def test_a_directory_is_archived_with_what_igni_reads_and_no_wheelhouse(
        self, tmp_path: Path
    ) -> None:
        directory = extension_dir(
            tmp_path / "ext",
            **{
                "README.md": "# Acme",
                "plugin__main.py": "x = 1",
                "ui__index.html": "<!doctype html>",
                "wheelhouse__a.whl": "wheel",
                "notes.txt": "not shipped",
            },
        )

        bundle = BundleSource(path=directory).bundle()

        assert (bundle.extension_id, bundle.version) == ("acme.example", "1")
        assert names_in(bundle.archive) == {
            "manifest.json",
            "README.md",
            "plugin/main.py",
            "ui/index.html",
        }

    def test_a_directory_with_only_a_manifest_makes_a_bundle_of_it(self, tmp_path: Path) -> None:
        bundle = BundleSource(path=extension_dir(tmp_path / "ext")).bundle()

        assert names_in(bundle.archive) == {"manifest.json"}

    def test_the_manifest_s_own_path_stands_for_its_directory(self, tmp_path: Path) -> None:
        directory = extension_dir(tmp_path / "ext", **{"ui__index.html": "<!doctype html>"})

        bundle = BundleSource(path=directory / "manifest.json").bundle()

        assert names_in(bundle.archive) == {"manifest.json", "ui/index.html"}

    def test_a_directory_s_bundle_is_the_same_bytes_every_time(self, tmp_path: Path) -> None:
        source = BundleSource(path=extension_dir(tmp_path / "ext", **{"ui__a.html": "a"}))

        assert source.bundle().archive == source.bundle().archive

    def test_a_built_archive_is_the_bundle_as_it_is(self, tmp_path: Path) -> None:
        staging = extension_dir(tmp_path / "staging")
        built = tmp_path / "extension-bundle.tar.gz"
        written = BundleArchive.write(staging, built)

        bundle = BundleSource(path=built).bundle()

        assert bundle.archive == written
        assert bundle.extension_id == "acme.example"

    def test_a_path_that_is_not_there_is_not_an_extension(self, tmp_path: Path) -> None:
        missing = tmp_path / "nothing"

        with pytest.raises(ValueError, match=f"^{missing} has no manifest.json$"):
            BundleSource(path=missing).bundle()

    def test_a_directory_without_a_manifest_is_not_an_extension(self, tmp_path: Path) -> None:
        (tmp_path / "ui").mkdir()

        with pytest.raises(ValueError, match=f"^{tmp_path} has no manifest.json$"):
            BundleSource(path=tmp_path).bundle()

    def test_a_manifest_path_in_a_directory_without_one_is_not_an_extension(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="has no manifest.json"):
            BundleSource(path=tmp_path / "manifest.json").bundle()

    @pytest.mark.parametrize("content", [b"", b"not a tarball", b'{"id": "a"}'])
    def test_a_file_that_is_not_a_bundle_is_a_value_error_naming_it(
        self, tmp_path: Path, content: bytes
    ) -> None:
        elsewhere = tmp_path / "other.tar.gz"
        elsewhere.write_bytes(content)

        with pytest.raises(ValueError, match=f"^{elsewhere} is not an extension bundle"):
            BundleSource(path=elsewhere).bundle()

    def test_a_tarball_with_no_manifest_is_not_a_bundle(self, tmp_path: Path) -> None:
        built = tmp_path / "bundle.tar.gz"
        built.write_bytes(gzipped_tar({"ui/index.html": b"x"}))

        with pytest.raises(ValueError, match="is not an extension bundle"):
            BundleSource(path=built).bundle()


class TestUploadingAPath:
    async def test_a_file_that_is_not_a_bundle_is_refused_before_anything_is_sent(
        self, fake: FakeIgni, igni: IgniService, tmp_path: Path
    ) -> None:
        junk = tmp_path / "junk.tar.gz"
        junk.write_bytes(b"junk")

        with pytest.raises(ValueError, match="is not an extension bundle"):
            await fake.upload(junk, igni)

        assert fake.traffic.seen == []

    async def test_a_path_that_is_not_an_extension_is_refused_before_anything_is_sent(
        self, fake: FakeIgni, igni: IgniService, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="has no manifest.json"):
            await fake.upload(tmp_path, igni)

        assert fake.traffic.seen == []

    async def test_an_upload_answers_what_the_fake_now_holds_with_its_manifest(
        self, fake: FakeIgni, igni: IgniService, tmp_path: Path
    ) -> None:
        directory = extension_dir(tmp_path / "ext")
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "id": "acme.example",
                    "version": "3",
                    "contributes": {"pages": [{"kind": "panel"}]},
                }
            )
        )

        held = await fake.upload(directory, igni)

        assert held.pages == ["panel"]
        assert held.version == "3"
        assert held.client_id == await igni.registration.client_id()
        assert held.archive == BundleSource(path=directory).bundle().archive

    async def test_an_extension_the_fake_holds_back_is_published_with_its_reason(
        self, fake: FakeIgni, igni: IgniService, tmp_path: Path
    ) -> None:
        fake.extensions.hold("it asks for more")

        held = await fake.upload(extension_dir(tmp_path / "ext"), igni)

        published = held.published("it asks for more")
        assert published.held is True

"""What igni holds of an extension bundle: its manifest, as far as igni reads it.

`UploadedManifest` is laxer than the bundle builder's `BundleManifest`,
as igni is: a stand-in bundle in a test has no `python` section and no
assets for every platform. `HeldExtension` is one uploaded bundle;
`BundleSource` makes one from a built archive or an extension's
directory, for `FakeIgni.upload`.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from igni_service.bundle.archive import BundleArchive
from igni_service.errors import BundleError
from igni_service.registration import ExtensionBundle, PublishedExtension
from igni_service.testing_wire import DetailError


class ManifestAsset(BaseModel):
    """One asset a manifest declares; igni reads its name and digest."""

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)

    name: str = ""
    """The asset's name."""
    sha256: str = ""
    """Its SHA-256, hex."""


class PageRef(BaseModel):
    """One page a manifest contributes; igni reads its kind."""

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)

    kind: str = ""
    """The page's kind."""


class Contributes(BaseModel):
    """A manifest's `contributes` section: what the extension adds to igni."""

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)

    pages: list[PageRef] = Field(default_factory=list)
    """The pages it contributes."""


class UploadedManifest(BaseModel):
    """An uploaded bundle's `manifest.json`, read only as far as igni reads it.

    Laxer than `BundleManifest`, which the bundle builder checks: a
    stand-in bundle in a test has no `python` section and no assets for
    every platform, and igni takes it.
    """

    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)

    id: str = ""
    """The extension's id."""
    version: str = ""
    """Its version."""
    name: str | None = None
    """Its display name."""
    assets: list[ManifestAsset] = Field(default_factory=list)
    """The assets it declares."""
    contributes: Contributes = Field(default_factory=Contributes)
    """What it adds to igni: its pages, among others."""
    vm: dict[str, object] | None = None
    """Its `vm` section: the VM profile it asks for, if any."""

    @classmethod
    def from_archive(cls, archive: bytes) -> UploadedManifest | DetailError:
        """The manifest, or igni's refusal: none it can read, or one that is not what was signed.

        Args:
            archive: The bundle's bytes: the gzipped tar to read the
                manifest out of.
        """
        try:
            manifest = BundleArchive.read_manifest(archive)
        except BundleError:
            return DetailError(detail="no manifest.json at the bundle's root")
        try:
            return cls.model_validate(manifest)
        except ValidationError:
            return DetailError(detail="the manifest is not what was signed")

    @property
    def pages(self) -> list[str]:
        """The kind of each page it contributes."""
        return [page.kind for page in self.contributes.pages]


class HeldExtension(BaseModel):
    """A bundle igni holds for a client."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    client_id: str
    """The service that uploaded it."""
    extension_id: str
    """Its manifest `id`."""
    version: str
    """Its manifest `version`."""
    sha256: str
    """The SHA-256 of the archive, hex."""
    archive: bytes
    """The bundle's bytes, as uploaded."""
    manifest: UploadedManifest = Field(default_factory=UploadedManifest)
    """What the fake read from its manifest."""

    @property
    def pages(self) -> list[str]:
        """The kind of each page its manifest contributes."""
        return self.manifest.pages

    def published(self, reason: str | None = None) -> PublishedExtension:
        """What igni answers about it; held for a super admin when there is a `reason`.

        Args:
            reason: Why the bundle is held for a super admin; no reason
                publishes it.
        """
        return PublishedExtension(
            extension_id=self.extension_id,
            version=self.version,
            sha256=self.sha256,
            held=reason is not None,
            reason=reason,
        )


class BundleSource(BaseModel):
    """A built bundle, or an extension's directory to archive as one."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    path: Path

    def bundle(self) -> ExtensionBundle:
        """The bundle: `manifest.json`, `README.md`, `plugin/` and `ui/`, with no wheelhouse.

        Raises `ValueError` when the path is a file that is not a bundle, or
        a directory with no `manifest.json`.
        """
        path = self.path
        if path.is_file() and path.name != "manifest.json":
            try:
                found = ExtensionBundle.at(path)
            except BundleError as exc:
                raise ValueError(f"{path} is not an extension bundle: {exc}") from exc
            if found is None:
                raise ValueError(f"{path} is not an extension bundle")
            return found
        directory = path.parent if path.is_file() else path
        if not (directory / "manifest.json").is_file():
            raise ValueError(f"{directory} has no manifest.json")
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp) / "bundle"
            staging.mkdir()
            for name in ("manifest.json", "README.md", "plugin", "ui"):
                source = directory / name
                if source.is_dir():
                    shutil.copytree(source, staging / name)
                elif source.is_file():
                    shutil.copy2(source, staging / name)
            return ExtensionBundle(BundleArchive.write(staging, Path(tmp) / "bundle.tar.gz"))


__all__ = [
    "BundleSource",
    "Contributes",
    "HeldExtension",
    "ManifestAsset",
    "PageRef",
    "UploadedManifest",
]

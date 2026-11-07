"""One extension directory into a bundle.

The extension's own files are staged, its wheelhouse filled
(`wheelhouse`), `permissions.tools` written from or held to the code
(`permissions_tools`), and the lot archived (`archive`). Beside the
archive, in `<out>.assets/`, every asset the manifest declares — fetched
from its pinned `source` and held to its pinned size and SHA-256, one
file per digest (`igni_service.assets`).
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from igni_service.assets import AssetFetcher, BundleAsset, BundleLayout
from igni_service.bundle.archive import BundleArchive
from igni_service.bundle.code_tools import CodeTools, CodeToolsRead
from igni_service.bundle.manifest import BundleManifest
from igni_service.bundle.permissions_tools import PermissionsTools
from igni_service.bundle.platforms import PLATFORMS, Platform
from igni_service.bundle.project import ExtensionProject
from igni_service.bundle.requirements import Requirement
from igni_service.bundle.runner import CommandRunner
from igni_service.bundle.sources import PackageSources
from igni_service.bundle.wheelhouse import Wheelhouse


class BundleReport(BaseModel):
    """What was built, and what was said about it."""

    out: Path
    extension_id: str
    version: str
    sha256: str
    size: int
    wheels: list[str] = Field(default_factory=list)
    #: `<out>.assets`, where every declared asset was written by digest.
    assets_dir: Path
    assets: list[BundleAsset] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BundleBuilder:
    """Builds one extension directory into a bundle."""

    #: What goes into the bundle from the extension directory, besides the
    #: wheelhouse. Sources travel inside the extension's wheel; tests do not
    #: travel at all.
    SHIPPED = ("manifest.json", "README.md", "plugin", "ui")

    def __init__(
        self,
        extension_dir: Path,
        *,
        allow_sdist: Iterable[str] = (),
        find_links: Iterable[Path] = (),
        no_index: bool = False,
        build_isolation: bool = True,
        platforms: Sequence[Platform] = PLATFORMS,
        runner: CommandRunner | None = None,
        fetcher: AssetFetcher | None = None,
        code_tools: CodeTools | None = None,
    ) -> None:
        self._dir = extension_dir.resolve()
        runner = runner or CommandRunner()
        self._code_tools = code_tools or CodeTools(runner)
        self._fetcher = fetcher or AssetFetcher()
        self._project = ExtensionProject.read(self._dir)
        self._wheelhouse = Wheelhouse(
            self._dir,
            sources=PackageSources(
                find_links=tuple(path.resolve() for path in find_links),
                no_index=no_index,
                build_isolation=build_isolation,
            ),
            runner=runner,
            platforms=platforms,
            allow_sdist={Requirement.normalise(name) for name in allow_sdist}
            | self._project.sdist_only(),
        )

    def manifest(self) -> BundleManifest:
        return BundleManifest.read(self._dir / "manifest.json")

    def build(self, out: Path) -> BundleReport:
        manifest = self.manifest()
        self._project.check_package(manifest.python)
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            staging = self._stage(scratch)
            wheels = staging / manifest.python.wheels
            wheels.mkdir(parents=True)
            self._wheelhouse.add_extension(manifest.python.package, wheels, scratch)
            notes = self._wheelhouse.platform_notes()
            notes += self._wheelhouse.fill(wheels, scratch)
            notes += self._tools(manifest, staging / "manifest.json", wheels)
            archive = BundleArchive.write(staging, out)
            built = sorted(path.name for path in wheels.glob("*.whl"))
        assets_dir = self._assets(manifest, out)
        return BundleReport(
            out=out,
            extension_id=manifest.id,
            version=manifest.version,
            sha256=hashlib.sha256(archive).hexdigest(),
            size=len(archive),
            wheels=built,
            assets_dir=assets_dir,
            assets=manifest.assets,
            notes=notes,
        )

    def _stage(self, scratch: Path) -> Path:
        staging = scratch / "bundle"
        staging.mkdir()
        for name in self.SHIPPED:
            source, target = self._dir / name, staging / name
            if source.is_dir():
                shutil.copytree(
                    source,
                    target,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
                )
            elif source.is_file():
                shutil.copy2(source, target)
        return staging

    def _tools(self, manifest: BundleManifest, staged: Path, wheels: Path) -> list[str]:
        """Write `permissions.tools` into the staged manifest, or check it, from the code."""
        module = self._project.module_of(manifest.python.entry)
        read = (
            self._code_tools.read(wheels, manifest.python.package, module)
            if module
            else CodeToolsRead()
        )
        outcome = PermissionsTools(manifest).against(read)
        if outcome.written is not None:
            staged.write_text(manifest.with_tools(outcome.written).to_json())
        return outcome.notes

    def _assets(self, manifest: BundleManifest, out: Path) -> Path:
        """Every declared asset in `<out>.assets/<sha256>`, and nothing else there.

        Made even when the manifest declares none, so an image copies the
        same two paths whatever the extension ships.
        """
        where = BundleLayout.assets_dir(out)
        where.mkdir(parents=True, exist_ok=True)
        for asset in manifest.assets:
            self._fetcher.fetch(asset, where)
        wanted = {asset.sha256 for asset in manifest.assets}
        for stale in where.iterdir():
            if stale.name not in wanted:
                stale.unlink()
        return where

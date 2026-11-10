"""The wheelhouse: the extension's wheel and every dependency's, for each platform.

**A requirement with no usable wheel stops the build**, by name and
platform, unless the extension declares it sdist-only (in
`[tool.igni.bundle]`, or with `--allow-sdist`). An allowed one is built
from its sdist and must come out pure Python (`py3-none-any`); anything
else still stops the build. Nothing is skipped silently.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from igni_service.bundle.downloads import PipDownloader
from igni_service.bundle.platforms import PLATFORMS, Platform
from igni_service.bundle.requirements import HashedRequirements, Requirement
from igni_service.bundle.resolver import Resolver
from igni_service.bundle.runner import CommandRunner
from igni_service.bundle.sources import PackageSources
from igni_service.errors import BundleError


class Wheelhouse:
    """Fills one directory with every wheel the extension needs on each platform."""

    def __init__(
        self,
        extension_dir: Path,
        *,
        sources: PackageSources,
        runner: CommandRunner,
        platforms: Sequence[Platform],
        allow_sdist: set[str],
    ) -> None:
        self._dir = extension_dir
        self._sources = sources
        self._runner = runner
        self._platforms = tuple(platforms)
        self._allow_sdist = allow_sdist
        self._resolver = Resolver(extension_dir, sources, runner)

    def platform_notes(self) -> list[str]:
        if set(self._platforms) == set(PLATFORMS):
            return []
        names = ", ".join(platform.name for platform in self._platforms)
        return [
            f"wheels for {names} only: a machine on any other platform cannot install this bundle"
        ]

    def add_extension(self, package: str, into: Path, scratch: Path) -> Path:
        """Build the extension's own wheel into `into`; it must be `package`'s."""
        dist = scratch / "dist"
        built = self._runner.run(
            [
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                str(dist),
                *self._sources.index_flags(),
                *self._sources.uv_isolation_flags(),
                str(self._dir),
            ]
        )
        if built.returncode != 0:
            raise BundleError(f"could not build the extension's wheel:\n{built.stderr}")
        wheels = sorted(dist.glob("*.whl"))
        if len(wheels) != 1:
            raise BundleError(f"expected one extension wheel, found {[w.name for w in wheels]}")
        [wheel] = wheels
        if Requirement.of_wheel(wheel.name) != Requirement.normalise(package):
            raise BundleError(f"the extension built {wheel.name}, not {package}")
        return Path(shutil.copy2(wheel, into / wheel.name))

    def fill(self, into: Path, scratch: Path) -> list[str]:
        """Fill `into` with every dependency's wheel. Returns what was said about it."""
        pip = PipDownloader.find(self._sources, self._runner)
        missing: dict[str, list[str]] = {}
        for platform in self._platforms:
            requirements = self._resolver.requirements(platform, scratch)
            for requirement in pip.download(requirements, platform, into):
                missing.setdefault(requirement, []).append(platform.name)
        notes: list[str] = []
        unresolved: list[str] = []
        for requirement, platforms in sorted(missing.items()):
            bare, where = HashedRequirements.bare(requirement), ", ".join(platforms)
            if Requirement.name_of(requirement) not in self._allow_sdist:
                unresolved.append(f"{bare}: no cp312/abi3/pure wheel for {where}")
                continue
            built = pip.wheel_from_sdist(requirement, into, scratch)
            notes.append(
                f"{bare}: no wheel for {where}; built {built.name} "
                "from its sdist (declared sdist-only)"
            )
        if unresolved:
            raise BundleError(
                "dependencies with no usable wheel:\n  "
                + "\n  ".join(unresolved)
                + "\nA pure-Python dependency that publishes only an sdist can be declared in "
                "pyproject.toml under [tool.igni.bundle] sdist-only = [...]."
            )
        return notes

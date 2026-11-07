"""Resolving an extension's dependencies for one platform.

With `uv pip compile --python-platform … --python-version 3.12`, so
markers such as `sys_platform == 'win32'` are evaluated for the target,
not for the machine building.
"""

from __future__ import annotations

import re
from pathlib import Path

from igni_service.bundle.platforms import PYTHON_VERSION, Platform
from igni_service.bundle.requirements import HashedRequirements
from igni_service.bundle.runner import CommandRunner
from igni_service.bundle.sources import PackageSources
from igni_service.errors import BundleError


class Resolver:
    """Pins every dependency of one extension, by hash, for a platform."""

    #: What to do while the SDKs are not on PyPI. Said when a resolution
    #: fails because one of them cannot be found.
    CHECKOUT_HINT = """\
The igni SDKs are not on PyPI yet. Build them from an igni-sdk checkout and
point the builder at the wheels:

  uv build --wheel --out-dir ./sdk-wheels <igni-sdk checkout>/packages/igni-extension
  igni-service-bundle --extension extension --out extension-bundle.tar.gz --find-links ./sdk-wheels"""

    #: The SDKs a resolution may fail to find before they are published.
    SDKS = ("igni-extension", "igni-service")

    def __init__(self, extension_dir: Path, sources: PackageSources, runner: CommandRunner) -> None:
        self._dir = extension_dir
        self._sources = sources
        self._runner = runner

    def requirements(self, platform: Platform, scratch: Path) -> list[str]:
        """Every pinned requirement, its hashes on the same line."""
        out = scratch / f"requirements-{platform.uv}.txt"
        compiled = self._runner.run(
            [
                "uv",
                "pip",
                "compile",
                str(self._dir / "pyproject.toml"),
                "--python-version",
                PYTHON_VERSION,
                "--python-platform",
                platform.uv,
                "--no-header",
                "--no-annotate",
                "--quiet",
                # A bundle is resolved as a machine with no checkout will
                # install it: from wheels and indexes only. An enclosing
                # uv workspace's path sources would otherwise turn the
                # SDKs into editable paths that exist only here.
                "--no-sources",
                # Every file is pinned by hash, so the download takes
                # exactly what this resolution chose, from whichever index
                # serves it. A same-named package published anywhere else
                # cannot match — that is what keeps a public look-alike of
                # an igni package out of a bundle.
                "--generate-hashes",
                *self._sources.index_flags(),
                *self._sources.uv_isolation_flags(),
                "-o",
                str(out),
            ],
            extra_env=platform.uv_env,
        )
        if compiled.returncode != 0:
            raise BundleError(
                f"could not resolve the dependencies for {platform.name}:\n"
                f"{compiled.stderr}{self._hint(compiled.stderr)}"
            )
        return HashedRequirements.parse(out.read_text())

    def _hint(self, stderr: str) -> str:
        missing_sdk = any(
            re.search(rf"\b{sdk}\b.*(not found|was not found|no versions)", stderr)
            for sdk in self.SDKS
        )
        return f"\n{self.CHECKOUT_HINT}" if missing_sdk else ""

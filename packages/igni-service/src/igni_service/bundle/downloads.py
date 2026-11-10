"""Downloading pinned requirements as wheels, and building one from an sdist.

Each pinned requirement is downloaded with `pip download
--only-binary=:all: --platform …`, hashes required. A requirement with
no usable wheel is answered back to the caller, which decides whether it
may be built from its sdist; one that is must come out pure Python.

A requirement the find-links directories already hold is taken from
there rather than downloaded: the file the resolution pinned is the one
the bundle must carry, and pip, left to itself, fetches the same-named
file from the index instead — a different build of the same version —
which the hash check then refuses.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sys
from pathlib import Path

from igni_service.bundle.platforms import PYTHON_VERSION, Platform
from igni_service.bundle.requirements import HashedRequirements, Requirement
from igni_service.bundle.runner import CommandRunner
from igni_service.bundle.sources import PackageSources
from igni_service.errors import BundleError


def _sha256(path: Path) -> str:
    """The digest of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PipDownloader:
    """pip, found once, downloading wheels and building them from sdists."""

    def __init__(self, pip: list[str], sources: PackageSources, runner: CommandRunner) -> None:
        self._pip = pip
        self._sources = sources
        self._runner = runner

    @classmethod
    def find(cls, sources: PackageSources, runner: CommandRunner) -> PipDownloader:
        """pip, from this interpreter if it has one, otherwise through uv."""
        if runner.run([sys.executable, "-m", "pip", "--version"]).returncode == 0:
            return cls([sys.executable, "-m", "pip"], sources, runner)
        return cls(["uvx", "--from", "pip", "pip"], sources, runner)

    def download(self, requirements: list[str], platform: Platform, into: Path) -> list[str]:
        """Download what has a wheel for `platform`; answer with what has none.

        One pip run for the lot. pip stops at the first requirement it
        cannot satisfy and names it, so that one is set aside and the rest
        asked for again until pip is satisfied.
        """
        remaining = list(requirements)
        missing: list[str] = []
        self._take_local_wheels(remaining, into)
        while remaining:
            listed = into.parent / f"want-{platform.uv}.txt"
            listed.write_text("\n".join(remaining) + "\n")
            done = self._runner.run([*self._download_command(platform, into), "-r", str(listed)])
            listed.unlink()
            if done.returncode == 0:
                return missing
            named = re.search(r"No matching distribution found for (\S+)", done.stderr)
            wanted = Requirement.name_of(named.group(1)) if named else None
            culprit = next((r for r in remaining if Requirement.name_of(r) == wanted), None)
            if culprit is None:
                raise BundleError(f"pip download failed for {platform.name}:\n{done.stderr}")
            missing.append(culprit)
            remaining.remove(culprit)
        return missing

    def _take_local_wheels(self, requirements: list[str], into: Path) -> None:
        """Take the wheels the find-links directories already hold.

        The resolution pins every dependency by hash, and the file it
        chose is often right here: the SDKs' wheels, built from a
        checkout or taken from a release. pip, left to itself, fetches
        the same-named file from the index instead — a different build of
        the same version — and the hash check then stops the build. The
        local file is taken when its bytes are the ones the resolution
        pinned, so the bundle carries what was resolved.
        """
        local = self._local_wheels()
        for requirement in list(requirements):
            for digest in HashedRequirements.hashes_of(requirement):
                path = local.get(digest)
                if path is None:
                    continue
                shutil.copy2(path, into / path.name)
                requirements.remove(requirement)
                break

    def _local_wheels(self) -> dict[str, Path]:
        """Every wheel in the find-links directories, by the digest of its bytes."""
        found: dict[str, Path] = {}
        for directory in self._sources.find_links:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.whl")):
                found.setdefault(_sha256(path), path)
        return found

    def wheel_from_sdist(self, requirement: str, into: Path, scratch: Path) -> Path:
        """Build `requirement` from its sdist into `into`; it must come out pure Python."""
        built = scratch / "sdist-wheels"
        built.mkdir(exist_ok=True)
        name = Requirement.name_of(requirement)
        # Through a requirements file, so the sdist is held to its hash too.
        pinned = scratch / f"sdist-{name}.txt"
        pinned.write_text(requirement + "\n")
        made = self._runner.run(
            [
                *self._pip,
                "wheel",
                "--quiet",
                "--disable-pip-version-check",
                "--no-deps",
                "--no-binary",
                ":all:",
                *self._sources.index_flags(),
                *self._sources.pip_isolation_flags(),
                "--require-hashes",
                "-w",
                str(built),
                "-r",
                str(pinned),
            ]
        )
        if made.returncode != 0:
            raise BundleError(
                f"{requirement}: could not build a wheel from its sdist:\n{made.stderr}"
            )
        for wheel in sorted(built.glob("*.whl")):
            if Requirement.of_wheel(wheel.name) != name:
                continue
            if not wheel.name.endswith("-none-any.whl"):
                raise BundleError(
                    f"{requirement}: built {wheel.name} from its sdist, which is not pure Python "
                    "and so would install on one platform only"
                )
            return Path(shutil.copy2(wheel, into / wheel.name))
        raise BundleError(f"{requirement}: building its sdist produced no wheel")

    def _download_command(self, platform: Platform, into: Path) -> list[str]:
        return [
            *self._pip,
            "download",
            "--quiet",
            "--disable-pip-version-check",
            "--no-deps",
            "--require-hashes",
            "--only-binary=:all:",
            "--python-version",
            PYTHON_VERSION,
            "--implementation",
            "cp",
            "--abi",
            "cp312",
            "--abi",
            "abi3",
            "--abi",
            "none",
            *platform.pip_flags(),
            *self._sources.index_flags(),
            "--dest",
            str(into),
        ]

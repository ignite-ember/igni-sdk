"""The bundle archive: a deterministic gzipped tar, manifest at its root.

Sorted members, zero mtimes and owners, a zero gzip timestamp — so the
same inputs give the same SHA-256, and the service uploads only when the
bundle really changed.
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
from pathlib import Path

from igni_service.errors import BundleError


class BundleArchive:
    """A deterministic gzipped tar of a directory, manifest at its root."""

    @staticmethod
    def write(staging: Path, out: Path) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for path in sorted(staging.rglob("*")):
                if path.is_dir():
                    continue
                info = tarfile.TarInfo(path.relative_to(staging).as_posix())
                info.size = path.stat().st_size
                info.mtime = 0
                info.mode = 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                with path.open("rb") as handle:
                    tar.addfile(info, handle)
        zipped = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=zipped, mtime=0) as gz:
            gz.write(buffer.getvalue())
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(zipped.getvalue())
        return zipped.getvalue()

    @staticmethod
    def read_manifest(archive: bytes) -> dict[str, object]:
        """The `manifest.json` at an archive's root, read without unpacking it.

        Left as the JSON object it is: each reader validates it into its
        own model. Raises `BundleError` when the archive is unreadable, has
        no manifest at its root, or its manifest is not a JSON object.
        """
        try:
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                for member in tar:
                    if member.isfile() and member.name.removeprefix("./") == "manifest.json":
                        extracted = tar.extractfile(member)
                        if extracted is None:
                            break
                        manifest = json.loads(extracted.read())
                        if not isinstance(manifest, dict):
                            raise ValueError("manifest.json is not an object")
                        return manifest
        except (tarfile.TarError, OSError, EOFError, ValueError) as exc:
            raise BundleError(f"the extension bundle is unreadable: {exc}") from exc
        raise BundleError("the extension bundle has no manifest.json at its root")

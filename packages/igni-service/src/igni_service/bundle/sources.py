"""Where uv and pip find packages, and whether they build in isolation.

A machine that cannot reach PyPI hands the builder the SDKs' wheels with
`--find-links`: from igni-sdk's GitHub release, or built from a checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class PackageSources(BaseModel):
    """The index flags and build isolation every uv and pip run shares."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    find_links: tuple[Path, ...] = ()
    no_index: bool = False
    build_isolation: bool = True

    def index_flags(self) -> list[str]:
        flags = ["--no-index"] if self.no_index else []
        for path in self.find_links:
            flags += ["--find-links", str(path)]
        return flags

    def uv_isolation_flags(self) -> list[str]:
        """uv builds with this interpreter's packages when isolation is off."""
        if self.build_isolation:
            return []
        return ["--no-build-isolation", "--python", sys.executable]

    def pip_isolation_flags(self) -> list[str]:
        return [] if self.build_isolation else ["--no-build-isolation"]

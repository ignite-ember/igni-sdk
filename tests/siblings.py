"""Where igni-core is, for the tests that hold this repository to it.

igni-sdk builds against copies of what igni-core publishes (``contracts/``).
The test that those copies are still igni-core's runs against a checkout of
it: ``IGNI_CORE_DIR``, by default ``../igni-core`` beside this repository.
Without one it skips; under CI it fails instead, since CI checks igni-core
out.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

__all__ = ["IGNI_CORE", "REPO", "needs_core"]

REPO = Path(__file__).resolve().parent.parent
#: The igni-core checkout.
IGNI_CORE = (
    Path(os.environ.get("IGNI_CORE_DIR") or REPO.parent / "igni-core").expanduser().resolve()
)


def _under_ci() -> bool:
    return bool(os.environ.get("CI"))


needs_core = pytest.mark.skipif(
    not (IGNI_CORE / "docs").is_dir() and not _under_ci(),
    reason=f"no igni-core checkout at {IGNI_CORE} (set IGNI_CORE_DIR)",
)

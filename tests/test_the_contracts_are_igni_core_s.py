"""The contracts this repository builds against are igni-core's, unchanged.

igni-core publishes the host schema and the manifest and theme schemas;
``contracts/`` holds copies, so this repository builds without importing
igni-core. A copy that drifts is an SDK built for an igni that does not
exist — refresh them with ``make contracts``.
"""

from __future__ import annotations

import pytest

from scripts.sync_contracts import COPIES
from tests.siblings import IGNI_CORE, REPO, needs_core


@needs_core
@pytest.mark.parametrize("copy", sorted(COPIES))
def test_the_copy_is_igni_core_s(copy: str) -> None:
    original = IGNI_CORE / COPIES[copy]
    assert (REPO / copy).read_text(encoding="utf-8") == original.read_text(encoding="utf-8"), (
        f"{copy} differs from igni-core's {COPIES[copy]}. Run `make contracts`."
    )


def test_every_copy_is_there() -> None:
    for copy in COPIES:
        assert (REPO / copy).is_file(), copy

"""Refresh the contracts igni-sdk copies from igni-core.

    python scripts/sync_contracts.py            # from ../igni-core, or IGNI_CORE_DIR
    python scripts/sync_contracts.py --check    # exit 1 if a copy differs

igni-core publishes them; this repository builds against its copies:

* ``contracts/host-schema.json`` — the host object model both SDKs'
  ``host`` objects are generated from (``make host-sdks`` after this);
* ``contracts/rpc-contract.json`` — every RPC method and message on igni's
  socket, which igni-client's typed models and methods are generated from
  (``make client-api`` after this);
* ``contracts/extension-manifest.schema.json`` and
  ``contracts/theme.schema.json`` — what an extension's manifest and theme
  are checked against.

``tools/host_spec.py`` is igni-core's grammar for the host schema, copied
by hand when that grammar changes: a test fails when it can no longer read
the published schema back.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = Path(os.environ.get("IGNI_CORE_DIR") or ROOT.parent / "igni-core").resolve()

#: Each copy here, and where igni-core keeps the original.
COPIES: dict[str, str] = {
    "contracts/host-schema.json": "docs/host-schema.json",
    "contracts/rpc-contract.json": "docs/rpc-contract.json",
    "contracts/extension-manifest.schema.json": "docs/extension-manifest.schema.json",
    "contracts/theme.schema.json": "docs/theme.schema.json",
}


def main(argv: list[str]) -> int:
    if not (CORE / "docs").is_dir():
        print(f"no igni-core checkout at {CORE} (set IGNI_CORE_DIR)", file=sys.stderr)
        return 2
    for original in COPIES.values():
        if not (CORE / original).is_file():
            print(f"igni-core at {CORE} has no {original}", file=sys.stderr)
            return 2
    stale = []
    for copy, original in COPIES.items():
        text = (CORE / original).read_text(encoding="utf-8")
        local = ROOT / copy
        if local.is_file() and local.read_text(encoding="utf-8") == text:
            continue
        stale.append(copy)
        if "--check" not in argv:
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(text, encoding="utf-8")
    for copy in stale:
        print(("stale: " if "--check" in argv else "refreshed: ") + copy)
    return 1 if stale and "--check" in argv else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

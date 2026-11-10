"""The npm packages, as a consumer outside a bundler sees them.

The packages ship their TypeScript source, which a bundler compiles. A
consumer that does not — a Node program, a tool that reads the types —
needs the build beside it: the JavaScript Node runs and the declarations
it reads.

This holds the packages to that. It packs them the way npm publishes
them, installs the tarballs into a scratch consumer that resolves the
way Node does (``moduleResolution: node16``), and type-checks and runs
a program against them. The script it calls is
``scripts/check_npm_consumers.py``; it is the same proof, run on its
own, so a failure says which step failed and why.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: The script that does the work.
SCRIPT = ROOT / "scripts" / "check_npm_consumers.py"


@pytest.mark.skipif(
    shutil.which("npm") is None or not (ROOT / "node_modules" / ".bin" / "tsc").exists(),
    reason="needs npm and the workspace's own dependencies",
)
def test_the_npm_packages_resolve_outside_a_bundler() -> None:
    """A consumer that is not a bundler can use the packages."""
    done = subprocess.run(  # noqa: S603 — our own script
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr

"""Running uv and pip."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path


class CommandRunner:
    """Runs uv and pip, with a fixed timestamp for anything they build."""

    SOURCE_DATE_EPOCH = "315532800"
    """Wheels built here carry this as every file's timestamp, so building
    the same source twice gives the same bytes.
    """

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        extra_env: Iterable[tuple[str, str]] = (),
    ) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "SOURCE_DATE_EPOCH": self.SOURCE_DATE_EPOCH, **dict(extra_env)}
        # uv and pip, with an argv list and no shell.
        return subprocess.run(  # noqa: S603
            list(command), cwd=cwd, env=env, capture_output=True, text=True, check=False
        )

"""The tools an `igni-extension` extension registers, read from its own code."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError

from igni_service.bundle.manifest import AgentTool
from igni_service.bundle.requirements import Requirement
from igni_service.bundle.runner import CommandRunner


class CodeToolsRead(BaseModel):
    """What reading the code's tools found.

    `tools` is `None` when nothing was read; `problem` then says why, when
    it is worth saying (an extension not built with `igni-extension` is
    not a problem).
    """

    tools: list[AgentTool] | None = None
    problem: str = ""


class ManifestListing(BaseModel):
    """What `python -m igni_extension.manifest` prints."""

    tools: list[AgentTool]


class CodeTools:
    """Reads the tools from the code with `python -m igni_extension.manifest <module>`.

    Runs in a throwaway environment installed from the wheelhouse only
    (`uv run --offline --no-index`), so it runs what the bundle ships and
    needs no network. Reads nothing when there is nothing to read: an
    extension not built with `igni-extension`, or a wheelhouse with
    nothing for this machine.
    """

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or CommandRunner()

    def read(self, wheels: Path, package: str, module: str) -> CodeToolsRead:
        if not any(Requirement.of_wheel(w.name) == "igni-extension" for w in wheels.glob("*.whl")):
            return CodeToolsRead()
        ran = self._runner.run(
            [
                "uv",
                "run",
                "--no-project",
                "--isolated",
                "--offline",
                "--no-index",
                "--find-links",
                str(wheels),
                "--python",
                sys.executable,
                "--with",
                package,
                "python",
                "-m",
                "igni_extension.manifest",
                module,
            ]
        )
        if ran.returncode != 0:
            return CodeToolsRead(problem=self._said(ran.stderr))
        try:
            listing = ManifestListing.model_validate(json.loads(ran.stdout))
        except (ValueError, ValidationError) as exc:
            return CodeToolsRead(problem=f"igni_extension.manifest answered something else: {exc}")
        return CodeToolsRead(tools=listing.tools)

    @staticmethod
    def _said(stderr: str) -> str:
        """The line of a failed run worth repeating."""
        lines = [line.strip() for line in stderr.strip().splitlines() if line.strip()]
        said = next(
            (line for line in lines if line.startswith(("error:", "×", "igni_extension"))),
            lines[-1] if lines else "no output",
        )
        return said.lstrip("× ").strip()

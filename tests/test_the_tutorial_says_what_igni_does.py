"""What docs/YOUR_FIRST_EXTENSION.md says igni and its scaffold do, they do.

Each test here is a sentence of the tutorial a reader followed and found
untrue, held against the thing it describes.
"""

from __future__ import annotations

import re

from tests.siblings import IGNI_CORE, REPO, needs_core

TUTORIAL = REPO / "docs" / "YOUR_FIRST_EXTENSION.md"


def _text() -> str:
    return " ".join(TUTORIAL.read_text(encoding="utf-8").split())


@needs_core
def test_step_0_says_how_a_scaffolded_project_finds_the_wheels() -> None:
    """It said the scaffold's pyproject.toml "installs from `--find-links
    wheels`"; the pyproject igni ext init writes names no wheel directory and
    tells you to pass --find-links yourself."""
    templates = (IGNI_CORE / "src/igni_core/cli/ext_scaffold_templates.py").read_text()
    (workspace,) = re.findall(r'SERVICE_WORKSPACE = """(.*?)"""', templates, re.S)
    tool_uv = workspace.split("[tool.uv]", 1)[1].split("\n[", 1)[0]

    assert "find-links" not in tool_uv, "the scaffold now names its wheels: say so here"
    assert "uv sync --find-links" in workspace
    assert "its `pyproject.toml` installs from `--find-links wheels`" not in _text()
    assert "says to run `uv sync --find-links <the directory holding them>`" in _text()

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


def _section(heading: str) -> str:
    text = TUTORIAL.read_text(encoding="utf-8")
    start = text.index(heading)
    return text[start : text.index("\n## ", start + 1)]


def test_step_7_s_headless_runs_cannot_stop_at_a_question() -> None:
    """ "Look ticket T-1002 up on the ticket service." ended with exit 1: the
    model went on to a shell command, and a headless run that meets a question
    pauses. `--read-only` lets the extension's read-only tools run and refuses
    the rest (checked against a real model)."""
    section = _section("## 7. Use it")
    runs = [line for line in section.splitlines() if re.match(r"igni\b.*\s-m\s", line)]

    assert len(runs) == 2
    assert all("--read-only" in line for line in runs), runs
    assert "Run paused for confirmation" in section

"""Every Python SDK, and this repository's tooling, keeps bandit's rules on.

``S`` is flake8-bandit, as in igni-core: a finding is fixed or carries a
``# noqa: S…`` saying why it is not one. Only ``S101`` (assert) is off, and
rules are relaxed for tests alone.
"""

from __future__ import annotations

import tomllib

import pytest

from tests.siblings import REPO

PYPROJECTS = [
    "pyproject.toml",
    *sorted(str(p.relative_to(REPO)) for p in (REPO / "packages").glob("*/pyproject.toml")),
]


def test_every_python_sdk_is_covered() -> None:
    assert {
        "packages/igni-service/pyproject.toml",
        "packages/igni-extension/pyproject.toml",
    } <= set(PYPROJECTS)


@pytest.mark.parametrize("pyproject", PYPROJECTS)
def test_bandit_rules_are_selected_and_only_assert_is_off(pyproject: str) -> None:
    lint = tomllib.loads((REPO / pyproject).read_text())["tool"]["ruff"]["lint"]
    assert "S" in lint["select"]
    assert [rule for rule in lint["ignore"] if rule.startswith("S")] == ["S101"]
    for path, rules in lint.get("per-file-ignores", {}).items():
        assert "tests" in path, f"{path}: bandit rules may be relaxed for tests only"
        assert "S" not in rules

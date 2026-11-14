"""What the SDK docs generator does with each input, not only what it wrote last time.

``test_the_sdk_docs_are_generated.py`` compares the checked-in pages with a
fresh run, which stays true however wrong the run is. These tests give the
generator small inputs and say what must come out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.client_codegen import Placement
from tools.sdk_docs import (
    DocsError,
    _npm_source,
    _Param,
    check_example,
)

ROOT = Path(__file__).resolve().parent.parent
CANCEL = Placement.of("cancel_scheduled_task", "session.scheduler.cancel")


def _check(code: str, *names: str) -> None:
    params = [_Param(name, "str", None) for name in names]
    check_example(CANCEL, params, code, False, None)  # type: ignore[arg-type]


def test_an_example_may_pass_as_many_positionals_as_the_method_has_parameters() -> None:
    _check("await session.scheduler.cancel('t1')\n", "task_id")
    _check("await session.scheduler.cancel('t1', 'x')\n", "task_id", "other")
    _check("await session.scheduler.cancel()\n")


def test_an_example_that_passes_a_positional_to_a_method_without_parameters_fails() -> None:
    with pytest.raises(DocsError, match="too many arguments"):
        _check("await session.scheduler.cancel('t1')\n")


def test_an_example_that_passes_more_positionals_than_parameters_fails() -> None:
    with pytest.raises(DocsError, match="too many arguments"):
        _check("await session.scheduler.cancel('a', 'b', 'c')\n", "task_id", "other")


def test_an_example_that_is_not_python_fails() -> None:
    with pytest.raises(DocsError, match=r"session\.scheduler\.cancel\(\) is not Python"):
        _check("await session.scheduler.cancel(\n")


def test_an_example_that_never_calls_its_method_fails() -> None:
    with pytest.raises(DocsError, match="does not call it"):
        _check("await session.scheduler.list()\n")


def test_an_example_that_passes_a_keyword_the_method_lacks_fails() -> None:
    with pytest.raises(DocsError, match="task="):
        _check("await session.scheduler.cancel(task='t1')\n", "task_id")
    _check("await session.scheduler.cancel(task_id='t1')\n", "task_id")


def test_an_example_may_spread_a_dict_of_keywords() -> None:
    _check("await session.scheduler.cancel(**options)\n", "task_id")


def test_a_parameter_the_page_does_not_show_is_not_one_the_example_may_pass() -> None:
    params = [_Param("task_id", "str", None), _Param("session_id", "", None)]
    with pytest.raises(DocsError, match="session_id="):
        check_example(
            CANCEL,
            params,
            "await session.scheduler.cancel(session_id='s')\n",
            False,
            None,  # type: ignore[arg-type]
        )


def test_an_npm_package_may_name_its_repository_as_a_string_or_not_at_all() -> None:
    assert _npm_source({"repository": "https://github.com/o/r"}) == "https://github.com/o/r"
    assert _npm_source({}) == ""
    assert _npm_source({"repository": {"type": "git"}}) == ""


def test_an_npm_repository_url_loses_its_git_prefix_and_suffix() -> None:
    assert _npm_source({"repository": {"url": "git+https://github.com/o/r.git"}}) == (
        "https://github.com/o/r"
    )
    assert _npm_source({"repository": {"url": "https://github.com/o/r"}}) == (
        "https://github.com/o/r"
    )
    assert _npm_source({"repository": {"url": "git+ssh://x/y.gitx"}}) == "ssh://x/y.gitx"

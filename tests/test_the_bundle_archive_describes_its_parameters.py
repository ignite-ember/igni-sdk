"""The bundle archive's two methods say what each parameter is.

The reference page for `igni_service.bundle` is generated from the
docstrings, so an `Args:` entry that names a parameter the method does
not take, or leaves one out, is a page that is wrong. `BundleArchive` is
not in `igni_service.__all__`, so the walk in
`test_every_parameter_is_documented.py` does not reach it.
"""

from __future__ import annotations

import inspect

import pytest
from igni_service.bundle.archive import BundleArchive

from tools.param_docs import python_args


@pytest.mark.parametrize(
    ("method", "parameters"),
    [(BundleArchive.write, ["staging", "out"]), (BundleArchive.read_manifest, ["archive"])],
)
def test_every_parameter_has_an_args_entry_and_no_other_has(
    method: object, parameters: list[str]
) -> None:
    taken = list(inspect.signature(method).parameters)  # type: ignore[arg-type]
    documented = python_args(inspect.getdoc(method) or "")  # type: ignore[arg-type]

    assert taken == parameters
    assert list(documented) == parameters
    assert all(meaning.strip() for meaning in documented.values())

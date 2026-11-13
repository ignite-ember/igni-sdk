"""`igni_extension`'s public surface: what `from igni_extension import X` gives."""

from __future__ import annotations

import types

import igni_extension


def _imported_names() -> set[str]:
    """What the package namespace holds that is a name an author would import."""
    return {
        name
        for name, value in vars(igni_extension).items()
        if not name.startswith("_") and not isinstance(value, types.ModuleType)
    }


def test_every_name_in_all_resolves() -> None:
    missing = [name for name in igni_extension.__all__ if not hasattr(igni_extension, name)]

    assert missing == []


def test_all_lists_each_name_once() -> None:
    names = igni_extension.__all__

    assert len(names) == len(set(names))


def test_all_is_exactly_what_the_package_imports() -> None:
    assert set(igni_extension.__all__) == _imported_names()


def test_star_import_gives_the_whole_surface() -> None:
    scope: dict[str, object] = {}

    exec("from igni_extension import *", scope)  # noqa: S102 — the point is what `*` brings in

    assert set(scope) - {"__builtins__"} == set(igni_extension.__all__)


def test_the_example_in_the_package_docstring_uses_names_it_exports() -> None:
    doc = igni_extension.__doc__ or ""

    for name in ("IgniExtension", "ToolHints"):
        assert name in doc
        assert name in igni_extension.__all__
    assert "ext.run()" in doc

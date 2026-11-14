"""`igni_service`'s public surface: what `from igni_service import X` gives."""

from __future__ import annotations

import types

import igni_service


def _imported_names() -> set[str]:
    """What the package namespace holds that is a name a service author would import."""
    return {
        name
        for name, value in vars(igni_service).items()
        if not name.startswith("_") and not isinstance(value, types.ModuleType)
    }


def test_every_name_in_all_resolves() -> None:
    missing = [name for name in igni_service.__all__ if not hasattr(igni_service, name)]

    assert missing == []


def test_all_lists_each_name_once() -> None:
    names = igni_service.__all__

    assert len(names) == len(set(names))


def test_all_is_exactly_what_the_package_imports() -> None:
    assert set(igni_service.__all__) == _imported_names()


def test_star_import_gives_the_whole_surface() -> None:
    scope: dict[str, object] = {}

    exec("from igni_service import *", scope)  # noqa: S102 — the point is what `*` brings in

    assert set(scope) - {"__builtins__"} == set(igni_service.__all__)


def test_the_agent_names_come_from_the_modules_that_define_them() -> None:
    from igni_service.agent_wire import Attachment, ItemStatus
    from igni_service.agents import Agent, Chat
    from igni_service.app import IgniApp

    assert igni_service.Agent is Agent and igni_service.Chat is Chat
    assert igni_service.Attachment is Attachment and igni_service.ItemStatus is ItemStatus
    assert igni_service.IgniApp is IgniApp

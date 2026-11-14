"""What `import igni_client` offers is what the package says it offers.

A user writes `from igni_client import Fleet, IgniClient, Person`; every name
in `__all__` must be the real object of its home module, every event and
error igni-client defines must be reachable from the top, and the names the
contract-typed rewrite removed must stay gone.
"""

from __future__ import annotations

import inspect
from types import ModuleType

import igni_client
from igni_client import access, approvals, calls, errors, events, models, replies, sessions


def test_every_name_in_all_resolves_and_star_import_works() -> None:
    namespace: dict[str, object] = {}
    exec("from igni_client import *", namespace)  # noqa: S102
    assert set(igni_client.__all__) <= set(namespace)
    assert len(set(igni_client.__all__)) == len(igni_client.__all__), "no name listed twice"
    for name in igni_client.__all__:
        assert getattr(igni_client, name) is namespace[name]


def test_the_exports_are_the_home_modules_objects() -> None:
    assert igni_client.Call is calls.Call
    assert igni_client.Decision is approvals.Decision
    assert igni_client.ApprovalRequested is approvals.ApprovalRequested
    assert igni_client.Reply is replies.Reply
    assert igni_client.Session is sessions.Session
    assert igni_client.Sessions is sessions.Sessions
    assert igni_client.ChatTurn is models.ChatTurn
    assert igni_client.SessionListEntry is models.SessionListEntry


def _defined_in(module: ModuleType, base: type | None = None) -> set[str]:
    return {
        name
        for name, obj in vars(module).items()
        if inspect.isclass(obj)
        and obj.__module__ == module.__name__
        and not name.startswith("_")
        and (base is None or issubclass(obj, base))
    }


def test_every_error_igni_client_defines_is_exported() -> None:
    defined = _defined_in(errors, Exception)
    assert defined, "found the error classes"
    assert defined <= set(igni_client.__all__)
    for name in defined:
        assert getattr(igni_client, name) is getattr(errors, name)


def test_every_event_a_user_receives_is_exported_as_the_events_object() -> None:
    names = [
        "Event", "RunEvent", "ContentDelta", "RunStarted", "ReasoningStarted", "ToolStarted",
        "ToolCompleted", "ToolError", "ModelCompleted", "StreamingDone", "RunCompleted",
        "RunError", "RunPaused", "Requirement", "RequirementDetails", "RequirementResolved",
        "TaskCreated", "TaskUpdated", "TaskStateUpdated", "StatusUpdate", "CommandResult",
        "InfoMessage", "ErrorMessage", "UserMessageReceived", "PushNotification", "Unknown",
    ]  # fmt: skip
    for name in names:
        assert name in igni_client.__all__
        assert getattr(igni_client, name) is getattr(events, name)
    assert issubclass(igni_client.Unknown, igni_client.Event)


def test_the_names_the_typed_rewrite_removed_stay_gone() -> None:
    for name in ("Models", "ModelCatalogue", "ModelEntry", "HistoryTurn"):
        assert not hasattr(igni_client, name)
        assert name not in igni_client.__all__
    assert not hasattr(igni_client.IgniClient, "rpc")


def test_the_typed_rewrite_added_its_calls_and_errors() -> None:
    added = {
        "Call",
        "ChatTurn",
        "AccessRefused",
        "UnknownMethod",
        "InvalidArguments",
        "UnexpectedAnswer",
        "MethodFailed",
    }
    assert added <= set(igni_client.__all__)
    assert issubclass(igni_client.AccessRefused, igni_client.NotAllowed)
    assert issubclass(igni_client.UnknownMethod, igni_client.RpcError)


def test_the_front_page_docstring_names_what_exists() -> None:
    doc = igni_client.__doc__ or ""
    assert "igni.rpc" not in doc
    for name in ("Fleet", "IgniClient", "Person", "Call", "Session"):
        assert name in doc
        assert hasattr(igni_client, name)
    assert hasattr(igni_client.Commands, "run")
    assert hasattr(igni_client.Person, "from_cli")
    assert access.__all__  # the module a user never imports directly still exports

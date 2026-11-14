"""The fake's directory and agent channel describe every parameter, and their models their fields.

The reference pages are generated from these docstrings, so a parameter
with no entry in `Args:` is a blank row there, and a model that does not
read attribute docstrings has fields with no words.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from types import ModuleType

import pytest
from pydantic import BaseModel

from igni_service import testing_directory, testing_items, testing_notifications
from igni_service.testing_items import FakeAgents, SentEvent, Upload
from igni_service.testing_notifications import Delivery, DeliveryKey, NotifyCall

from .test_host_keys_and_notifications_describe_every_parameter import _documented, _parameters


def _public_functions(module: ModuleType) -> Iterator[tuple[str, object, str]]:
    for class_name in module.__all__:
        klass = getattr(module, class_name)
        if not inspect.isclass(klass) or klass.__module__ != module.__name__:
            continue
        for name, member in klass.__dict__.items():
            if name.startswith("_"):
                continue
            function = member.__func__ if isinstance(member, staticmethod | classmethod) else member
            if inspect.isfunction(function):
                yield f"{class_name}.{name}", function, inspect.getdoc(function) or ""


def _surface() -> list[tuple[str, object, str]]:
    found = [*_public_functions(testing_directory), *_public_functions(testing_items)]
    found.append(("FakeAgents", FakeAgents.__init__, inspect.getdoc(FakeAgents) or ""))
    return found


@pytest.mark.parametrize(
    ("where", "function", "doc"), _surface(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_every_parameter_has_an_entry_in_args(where: str, function: object, doc: str) -> None:
    assert _documented(doc) == _parameters(function), where


def test_the_check_reads_the_functions_that_take_parameters() -> None:
    reads = {where for where, function, _ in _surface() if _parameters(function)}

    assert reads >= {
        "FakeAgents",
        "FakeAgents.settle",
        "FakeAgents.event",
        "FakeAgents.item",
        "FakeAgents.upload",
        "FakeAgents.status",
        "FakeDirectory.add_organisation",
        "FakeDirectory.ensure",
        "FakeDirectory.add_member",
        "FakeDirectory.delete_organisation",
        "FakeDirectory.member",
        "FakeDirectory.is_member",
        "FakeDirectory.claims_for",
        "FakeDirectory.served",
        "FakeDirectory.route",
        "FakeOrganisation.find",
        "FakeOrganisation.search",
        "FakeOrganisation.deactivate",
        "FakeOrganisation.claims_for",
        "MemberQuery.from_request",
        "OrganisationDeletion.send",
    }


MODELS: dict[type[BaseModel], list[str]] = {
    SentEvent: [
        "event_id",
        "org_id",
        "client_id",
        "producer",
        "kind",
        "type",
        "payload",
        "thread",
        "text",
        "title",
        "start_run",
        "action",
        "attachments",
        "event_key",
        "state",
        "created_at",
    ],
    Upload: ["attachment_id", "client_id", "filename", "content_type", "data", "event_id"],
    NotifyCall: ["org_id", "client_id", "notifications"],
    Delivery: ["org_id", "user_id", "source", "notification"],
    DeliveryKey: [],
    testing_directory.MemberQuery: [],
    testing_directory.FakeOrganisation: [],
    testing_directory.OrganisationDeletion: ["org_id", "path", "headers"],
}


@pytest.mark.parametrize("model", list(MODELS), ids=lambda m: m.__name__)
def test_a_model_reads_attribute_docstrings(model: type[BaseModel]) -> None:
    assert model.model_config.get("use_attribute_docstrings") is True


@pytest.mark.parametrize(
    ("model", "field"), [(m, f) for m, fields in MODELS.items() for f in fields]
)
def test_a_field_has_its_attribute_docstring_as_its_description(
    model: type[BaseModel], field: str
) -> None:
    description = model.model_fields[field].description

    assert description and description.strip() == description
    assert model.model_json_schema()["properties"][field]["description"] == description


def test_the_words_say_what_the_fields_are() -> None:
    assert "`event`, `message`, `chat` or `action`" in (
        SentEvent.model_fields["kind"].description or ""
    )
    assert "`Chat.queue` sends `False`" in (SentEvent.model_fields["start_run"].description or "")
    assert "once one does" in (Upload.model_fields["event_id"].description or "")


def test_reading_the_docstrings_changed_no_default_and_no_requiredness() -> None:
    assert SentEvent.model_fields["kind"].default == "event"
    assert SentEvent.model_fields["start_run"].default is True
    assert SentEvent.model_fields["state"].default == "pending"
    assert [n for n, f in SentEvent.model_fields.items() if f.is_required()] == [
        "event_id",
        "org_id",
        "client_id",
        "producer",
        "type",
        "created_at",
    ]
    assert [n for n, f in Upload.model_fields.items() if f.is_required()] == [
        "attachment_id",
        "client_id",
        "filename",
        "content_type",
        "data",
    ]
    assert testing_notifications.Delivery.model_config.get("frozen") is True

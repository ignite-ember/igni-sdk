"""The VM profile fake, the fake's wire types and the token endpoint describe every parameter and field.

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

from igni_service import testing_vm_profiles, testing_vm_rules, testing_wire, token_endpoint

from .test_host_keys_and_notifications_describe_every_parameter import _documented, _parameters

MODULES = [testing_vm_profiles, testing_vm_rules, testing_wire, token_endpoint]


def _classes(module: ModuleType) -> Iterator[type]:
    for _, klass in inspect.getmembers(module, inspect.isclass):
        ours = klass.__module__ == module.__name__ and not klass.__name__.startswith("_")
        if ours and not getattr(klass, "_is_protocol", False):
            yield klass


def _functions(module: ModuleType) -> Iterator[tuple[str, object, str]]:
    for klass in _classes(module):
        for name, member in klass.__dict__.items():
            if name.startswith("_") and name != "__init__":
                continue
            function = member.__func__ if isinstance(member, staticmethod | classmethod) else member
            if not inspect.isfunction(function):
                continue
            doc = inspect.getdoc(klass if name == "__init__" else function) or ""
            if name == "__init__" and "Args:" not in doc and not _parameters(function):
                continue
            yield f"{klass.__name__}.{name}", function, doc


def _surface() -> list[tuple[str, object, str]]:
    return [found for module in MODULES for found in _functions(module)]


@pytest.mark.parametrize(
    ("where", "function", "doc"), _surface(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_every_parameter_has_an_entry_in_args(where: str, function: object, doc: str) -> None:
    assert _documented(doc) == _parameters(function), where


def test_the_check_reads_the_functions_that_take_parameters() -> None:
    reads = {where for where, function, _ in _surface() if _parameters(function)}

    assert reads >= {
        "FakeVmProfiles.__init__",
        "FakeVmProfiles.request",
        "FakeVmProfiles.approve",
        "FakeVmProfiles.reject",
        "FakeVmProfiles.assign",
        "FakeVmProfiles.app_put",
        "FakeVmProfiles.app_get",
        "FakeVmProfiles.app_profile",
        "FakeVmProfiles.service",
        "NoVmProfileRequest.__init__",
        "VmProfileSubject.app",
        "VmProfileSubject.extension",
        "Resolved.of",
        "FakeProfile.default",
        "FakeCaps.refusal",
        "FakeCaps.serve",
        "IgniAddresses.reaches",
        "SeenRequest.of",
        "SeenRequest.json_model",
        "SeenRequest.first",
        "RecordedTraffic.record",
        "RecordedTraffic.failure_for",
        "RecordedTraffic.fail",
        "RecordedTraffic.requests_to",
        "OAuthRefusal.read",
        "GrantRefused.__init__",
        "TokenEndpoint.__init__",
        "TokenEndpoint.grant",
        "TokenEndpoint.revoke",
    }


MODELS = [
    cls
    for module in MODULES
    for cls in _classes(module)
    if issubclass(cls, BaseModel) and cls.model_fields
]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_a_model_reads_attribute_docstrings(model: type[BaseModel]) -> None:
    assert model.model_config.get("use_attribute_docstrings") is True


@pytest.mark.parametrize(
    ("model", "field"), [(m, f) for m in MODELS for f in m.model_fields], ids=lambda v: str(v)
)
def test_a_field_has_its_attribute_docstring_as_its_description(
    model: type[BaseModel], field: str
) -> None:
    description = model.model_fields[field].description

    assert description and description.strip() == description, f"{model.__name__}.{field}"

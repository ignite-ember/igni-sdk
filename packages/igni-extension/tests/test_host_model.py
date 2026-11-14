"""`igni_extension.host_model`: the generated models and objects, held to igni's schema.

The file is written by `tools/host_codegen.py` from `contracts/host-schema.json`
(`tests/test_the_host_sdks_are_generated.py` holds the file to the generator).
These are about what an extension author gets from it: the models carry the
schema's field words so the reference pages can show them, a payload that omits
what the schema requires is refused, a newer igni's fields are kept, and every
method parameter is described in `Args:`.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from igni_extension import host_model
from igni_extension.members import HostObject

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "host-schema.json").read_text("utf-8")
)
TYPES = {spec["name"]: spec for spec in SCHEMA["types"]}


def _args(doc: str) -> dict[str, str]:
    """The `Args:` entries of a docstring, name to meaning (continuation lines joined)."""
    lines = (doc or "").splitlines()
    if "Args:" not in [line.strip() for line in lines]:
        return {}
    start = next(i for i, line in enumerate(lines) if line.strip() == "Args:")
    base = len(lines[start]) - len(lines[start].lstrip())
    out: dict[str, str] = {}
    name = ""
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base:
            break
        if indent == base + 4 and ": " in line:
            name, _, meaning = line.strip().partition(": ")
            out[name] = meaning
        elif name:
            out[name] += " " + line.strip()
    return out


def test_the_models_are_the_schemas_types_with_their_words() -> None:
    assert set(TYPES) <= set(vars(host_model))
    for name, spec in TYPES.items():
        model = getattr(host_model, name)
        if not (inspect.isclass(model) and issubclass(model, BaseModel)):
            continue  # a union or alias, not a model
        if model.__module__ != host_model.__name__:
            continue  # hand-written, held to the schema elsewhere
        assert model.__doc__ and model.__doc__.strip() == spec["doc"].strip(), name
        assert list(model.model_fields) == [f["name"] for f in spec["fields"]], name
        for field in spec["fields"]:
            info = model.model_fields[field["name"]]
            assert info.is_required() is (not field.get("optional", False)), (name, field["name"])
            # use_attribute_docstrings: the docstring under a field is its description
            assert (info.description or "") == field.get("doc", "").strip(), (name, field["name"])


def test_every_model_keeps_what_a_newer_igni_adds_and_documents_its_fields() -> None:
    models = [
        value
        for value in vars(host_model).values()
        if inspect.isclass(value)
        and issubclass(value, BaseModel)
        and value.__module__ == host_model.__name__
    ]
    assert len(models) > 50
    for model in models:
        assert model.model_config.get("extra") == "allow", model.__name__
        assert model.model_config.get("use_attribute_docstrings") is True, model.__name__


def test_a_newer_igni_s_extra_field_is_kept_on_the_model() -> None:
    change = host_model.Change.model_validate({"path": "a.b", "value": 1, "since": "9"})
    assert change.path == "a.b" and change.window is None
    assert change.model_dump()["since"] == "9"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (host_model.Toast, {"id": "t", "text": "hi", "kind": "info"}),
        (host_model.Dialog, {"id": "d", "spec": {}}),
    ],
)
def test_a_toast_or_dialog_without_its_type_is_refused(model: Any, payload: dict[str, Any]) -> None:
    assert model.model_fields["type"].is_required()
    with pytest.raises(ValidationError) as refused:
        model.model_validate(payload)
    assert [error["loc"] for error in refused.value.errors()] == [("type",)]
    assert model.model_validate({**payload, "type": "x"}).type == "x"


def test_a_payload_of_the_wrong_type_or_missing_a_required_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        host_model.Change.model_validate({"value": 1})
    with pytest.raises(ValidationError):
        host_model.Display.model_validate(
            {"verbose": "yes", "output_style": "", "output_styles": [], "color_theme": "auto"}
        )


def test_the_schema_version_is_the_schemas() -> None:
    assert host_model.SCHEMA_VERSION == SCHEMA["version"] == "1.13.0"


def _host_methods() -> list[tuple[str, str, Any, list[dict[str, Any]]]]:
    by_path = {spec["path"]: spec for spec in SCHEMA["objects"]}
    out = []
    for name in host_model.__all__:
        cls = getattr(host_model, name)
        if not (inspect.isclass(cls) and issubclass(cls, HostObject)) or cls is HostObject:
            continue
        spec = by_path[cls.PATH]
        for method in spec["methods"]:
            out.append((name, method["name"], vars(cls)[method["name"]], method.get("params", [])))
    return out


def test_every_method_parameter_is_described_in_args() -> None:
    methods = _host_methods()
    assert len(methods) > 80
    parameters = 0
    for cls, name, function, params in methods:
        written = [p for p in inspect.signature(function).parameters if p != "self"]
        assert written == [p["name"] for p in params], (cls, name)
        args = _args(inspect.getdoc(function) or "")
        assert list(args) == written, (cls, name)
        for param in params:
            parameters += 1
            assert args[param["name"]].strip(), (cls, name, param["name"])
            if param.get("doc"):
                # the schema's own words, verbatim
                assert args[param["name"]].startswith(param["doc"].strip()), (
                    cls,
                    name,
                    param["name"],
                )
    assert parameters >= 111


def test_the_public_names_are_every_model_object_and_the_version() -> None:
    public = {
        name
        for name, value in vars(host_model).items()
        if not name.startswith("_")
        and getattr(value, "__module__", None) == host_model.__name__
        and (inspect.isclass(value))
    }
    assert public <= set(host_model.__all__)
    assert "SCHEMA_VERSION" in host_model.__all__ and "Host" in host_model.__all__
    assert len(host_model.__all__) == len(set(host_model.__all__))
    for name in host_model.__all__:
        assert hasattr(host_model, name), name

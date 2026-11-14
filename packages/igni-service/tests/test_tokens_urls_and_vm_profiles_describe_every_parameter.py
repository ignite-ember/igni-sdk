"""Every parameter of the token verifier, the URL helpers and the VM profile reader is described in an Args block.

The reference pages are generated from the docstrings, so a parameter with no
entry in `Args:` is a blank row on the page, and an entry for a parameter that
no longer exists is a lie. A class docstring documents its constructor.
"""

from __future__ import annotations

import inspect
import re

import pytest
from pydantic import BaseModel

from igni_service import tokens, urls, vm_profiles


def _documented(doc: str) -> list[str]:
    """The parameter names an `Args:` block lists, each with a non-empty description."""
    lines = doc.splitlines()
    if "Args:" not in [line.strip() for line in lines]:
        return []
    start = next(i for i, line in enumerate(lines) if line.strip() == "Args:")
    indent = len(lines[start]) - len(lines[start].lstrip())
    names: list[str] = []
    for line in lines[start + 1 :]:
        if not line.strip():
            if names:
                break
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        match = re.match(rf"^\s{{{indent + 4}}}(\w+): (\S.*)$", line)
        if match:
            names.append(match.group(1))
    return names


def _surface() -> list[tuple[str, object, str]]:
    surface: list[tuple[str, object, str]] = []
    for built in (tokens.TokenVerifier, vm_profiles.ServiceVmProfiles):
        surface.append((built.__name__, built.__init__, inspect.getdoc(built) or ""))
    classes: tuple[type, ...] = (
        tokens.CallerKind,
        tokens.TokenRefused,
        tokens.Person,
        tokens.App,
        tokens.Space,
        tokens.TokenVerifier,
        urls.ServiceUrl,
        urls.IgniPaths,
        vm_profiles.VmProfileRequest,
        vm_profiles.VmProfileRequestRecord,
        vm_profiles.ServiceVmProfiles,
    )
    for klass in classes:
        for name, member in klass.__dict__.items():
            if name.startswith("_"):
                continue
            function = member.__func__ if isinstance(member, staticmethod | classmethod) else member
            if inspect.isfunction(function):
                surface.append(
                    (f"{klass.__name__}.{name}", function, inspect.getdoc(function) or "")
                )
    surface.append(("refusal", vm_profiles.refusal, inspect.getdoc(vm_profiles.refusal) or ""))
    return surface


def _parameters(function: object) -> list[str]:
    return [
        name
        for name in inspect.signature(function).parameters  # type: ignore[arg-type]
        if name not in ("self", "cls")
    ]


@pytest.mark.parametrize(
    ("where", "function", "doc"), _surface(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_every_parameter_has_an_entry_in_args(where: str, function: object, doc: str) -> None:
    assert _documented(doc) == _parameters(function), where


def test_the_check_reads_the_methods_that_take_parameters() -> None:
    reads = {where for where, function, _ in _surface() if _parameters(function)}
    assert reads >= {
        "TokenVerifier",
        "TokenVerifier.claims",
        "TokenVerifier.person",
        "TokenVerifier.caller",
        "TokenVerifier.igni_call",
        "ServiceUrl.normalise",
        "IgniPaths.app_vm_profile",
        "IgniPaths.extension_asset",
        "ServiceVmProfiles",
        "ServiceVmProfiles.of",
        "Person.from_claims",
        "refusal",
    }


def test_the_args_reader_tells_a_missing_entry_from_a_present_one() -> None:
    doc = "Summary.\n\nArgs:\n    first: One.\n        More of one.\n    second: Two.\n"
    assert _documented(doc) == ["first", "second"]
    assert _documented("Summary.") == []


def _models() -> list[type[BaseModel]]:
    found: list[type[BaseModel]] = []
    for module in (tokens, vm_profiles):
        for value in vars(module).values():
            if (
                inspect.isclass(value)
                and issubclass(value, BaseModel)
                and value.__module__ == module.__name__
            ):
                found.append(value)
    return found


def test_the_check_reads_the_models_of_both_modules() -> None:
    names = {model.__name__ for model in _models()}
    assert names >= {"Person", "App", "Space", "IgniCall", "VmProfileRequest", "ServiceVmProfile"}


@pytest.mark.parametrize("model", _models(), ids=lambda m: m.__name__)
def test_every_field_of_a_model_says_what_it_is(model: type[BaseModel]) -> None:
    blank = [
        name for name, field in model.model_fields.items() if not (field.description or "").strip()
    ]

    assert blank == []

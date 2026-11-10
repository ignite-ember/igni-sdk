"""Every parameter of every public method says what it is.

The reference pages show a table of a method's parameters: the name,
the type, the default, and what it means. The meaning is read from the
method's own docstring — an ``Args:`` section, one indented line a
parameter, the way igni-core writes them.

Two things are wrong when that does not happen, and this test holds
both to the code:

* a parameter no docstring documents — the page would show it as
  undocumented, and a reader would be left guessing;
* a documented ``Args:`` entry naming a parameter the method does not
  take — the docstring has drifted from the code, and the page would
  document a parameter that is not there.

The inventory is read from the packages themselves, with ``inspect``,
so it cannot drift from what the packages publish.
"""

from __future__ import annotations

import dataclasses
import enum
import inspect
from typing import Any

import igni_extension
import igni_extension.testing
import igni_service
import igni_service.testing
import pytest

from tools.param_docs import python_args

#: The modules the reference reads: each package, and its testing module.
MODULES = (igni_service, igni_service.testing, igni_extension, igni_extension.testing)


def _own_doc(cls: type) -> str:
    """A class's own docstring — not the one it inherits."""
    doc = cls.__dict__.get("__doc__")
    return inspect.cleandoc(doc) if isinstance(doc, str) else ""


def _own_members(cls: type) -> list[tuple[str, Any]]:
    """A class's own public methods and properties, as the code defines them."""
    out: list[tuple[str, Any]] = []
    for name, value in vars(cls).items():
        if name.startswith("_") or name.startswith("model_"):
            continue
        if isinstance(value, staticmethod | classmethod | property) or inspect.isfunction(value):
            out.append((name, value))
    return out


def _parameter_names(obj: Any, *, bound: bool = False) -> list[str]:
    """The names of the parameters a callable takes.

    ``bound`` says the callable is a method read off the class, where
    the first parameter is the instance and is not one a caller writes.
    """
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return []
    names = [param.name for param in sig.parameters.values()]
    if bound and names and names[0] in ("self", "cls"):
        names = names[1:]
    return names


def _shows_a_field_table(cls: type) -> bool:
    """Whether the class is shown as a table of its fields.

    A model — a pydantic one, a dataclass — says what each of its
    fields is in the field's own right, and the reference shows that
    table. What its constructor takes is then those fields, and each of
    them says what it is already.
    """
    return isinstance(getattr(cls, "model_fields", None), dict) or dataclasses.is_dataclass(cls)


def _is_an_enumeration(cls: type) -> bool:
    """Whether the class is an enumeration or an exception.

    Neither is built: an enumeration's members are its values, and an
    exception's are its arguments. The reference shows neither a
    constructor's parameters nor a table of them.
    """
    return issubclass(cls, enum.Enum | BaseException)


def _public_callables() -> list[tuple[str, Any, list[str], str, bool]]:
    """Every public callable the packages publish, and what it says.

    Each is: the name a reader would look for, the callable, the names
    of the parameters it takes, its docstring, and whether the
    reference shows a table of those parameters at all.
    """
    out: list[tuple[str, Any, list[str], str, bool]] = []
    seen: set[tuple[str, str]] = set()
    for module in MODULES:
        for name in module.__all__:
            obj = getattr(module, name)
            if inspect.isclass(obj):
                key = (obj.__module__, obj.__qualname__)
                if key not in seen:
                    seen.add(key)
                    out.append(
                        (
                            f"{name}.__init__",
                            obj,
                            _parameter_names(obj),
                            _own_doc(obj),
                            not _is_an_enumeration(obj) and not _shows_a_field_table(obj),
                        )
                    )
                for member_name, member in _own_members(obj):
                    if isinstance(member, property):
                        continue
                    func = (
                        member.__func__
                        if isinstance(member, staticmethod | classmethod)
                        else member
                    )
                    out.append(
                        (
                            f"{name}.{member_name}",
                            func,
                            _parameter_names(func, bound=True),
                            inspect.getdoc(func) or "",
                            True,
                        )
                    )
            elif inspect.isfunction(obj):
                out.append((name, obj, _parameter_names(obj), inspect.getdoc(obj) or "", True))
    return out


CALLABLES = _public_callables()


def test_the_packages_publish_the_methods_the_test_looks_at() -> None:
    """The inventory is not empty, and holds the packages' own methods.

    A test that found nothing to check would pass whatever the code
    said. This says what it found, so that a change in the packages'
    surface is a change in the test's inventory too.
    """
    names = {name for name, _, _, _, _ in CALLABLES}
    assert any(name.startswith("IgniService.") for name in names), sorted(names)[:20]
    assert any(name.startswith("IgniExtension.") for name in names), sorted(names)[:20]
    assert len(CALLABLES) > 100, len(CALLABLES)


@pytest.mark.parametrize("name,obj,parameters,doc,shown", CALLABLES, ids=lambda v: str(v)[:80])
def test_every_parameter_of_a_public_method_is_documented(
    name: str, obj: Any, parameters: list[str], doc: str, shown: bool
) -> None:
    """Every parameter a public method takes is documented.

    A parameter no docstring documents is one the reference shows as
    undocumented. The message names the method and the parameter, so
    that whoever writes the docstring knows which one is missing.
    """
    if not shown:
        return
    meanings = python_args(doc)
    missing = [param for param in parameters if param not in meanings]
    assert not missing, (
        f"{name}: these parameters have no documented meaning. Add an `Args:` "
        f"section to its docstring, one indented line a parameter: "
        f"{', '.join(missing)}"
    )


@pytest.mark.parametrize("name,obj,parameters,doc,shown", CALLABLES, ids=lambda v: str(v)[:80])
def test_a_documented_argument_is_one_the_method_takes(
    name: str, obj: Any, parameters: list[str], doc: str, shown: bool
) -> None:
    """A documented ``Args:`` entry names a parameter the method has.

    The docstring has drifted from the code: the entry documents a
    parameter the method does not take, and the page would show it as
    one it does.
    """
    meanings = python_args(doc)
    extra = [argument for argument in meanings if argument not in parameters]
    assert not extra, (
        f"{name}: the docstring documents {', '.join(extra)}, which the method "
        f"does not take. It takes: {', '.join(parameters) or 'nothing'}."
    )

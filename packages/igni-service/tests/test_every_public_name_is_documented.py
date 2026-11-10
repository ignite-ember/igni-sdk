"""Every public name of igni_service, and what it leads to, says what it is.

The SDK's reference pages are generated from its docstrings and its
Pydantic fields' descriptions, so a name without one is a blank on the
page. This walks `__all__` of `igni_service` and `igni_service.testing` —
every class, its bases and the classes its fields and public signatures
name; each method, property, classmethod, enum member, class constant,
instance attribute set in `__init__`, and Pydantic field — and fails on
any that says nothing.

A docstring is a function's or class's own, or the one an override
inherits from a base of this package (as `inspect.getdoc` reads it). A
constant, an attribute or an enum member is documented by a string
literal right after its assignment, which is also how a Pydantic field
gets its description (`use_attribute_docstrings=True`).
"""

from __future__ import annotations

import ast
import enum
import functools
import importlib
import inspect
import sys
import types
import typing
from typing import Any

from pydantic import BaseModel

MODULES = ["igni_service", "igni_service.testing"]
EXEMPT: frozenset[str] = frozenset()


class SourceDocs:
    """Attribute docstrings — a string literal right after an assignment — read from source."""

    @staticmethod
    @functools.cache
    def _module_tree(path: str) -> ast.Module:
        with open(path, encoding="utf-8") as handle:
            return ast.parse(handle.read())

    @staticmethod
    def _documented(body: list[ast.stmt], *, self_attrs: bool = False) -> set[str]:
        names: set[str] = set()
        for stmt, after in zip(body, body[1:], strict=False):
            if not (
                isinstance(after, ast.Expr)
                and isinstance(after.value, ast.Constant)
                and isinstance(after.value.value, str)
                and after.value.value.strip()
            ):
                continue
            targets: list[ast.expr] = []
            if isinstance(stmt, ast.Assign):
                targets = list(stmt.targets)
            elif isinstance(stmt, ast.AnnAssign):
                targets = [stmt.target]
            elif isinstance(stmt, ast.TypeAlias):
                targets = [stmt.name]
            for target in targets:
                if isinstance(target, ast.Name) and not self_attrs:
                    names.add(target.id)
                elif (
                    self_attrs
                    and isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    names.add(target.attr)
        return names

    @classmethod
    def module(cls, module: types.ModuleType) -> set[str]:
        path = getattr(module, "__file__", None)
        return cls._documented(cls._module_tree(path).body) if path else set()

    @classmethod
    def klass(cls, klass: type) -> tuple[set[str], set[str], set[str]]:
        """Its documented class attributes, its documented `self.` attributes, every `self.` attribute."""
        node = cls._class_node(klass)
        if node is None:
            return set(), set(), set()
        documented = cls._documented(node.body)
        documented_self: set[str] = set()
        assigned_self: set[str] = set()
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef) and stmt.name == "__init__":
                for sub in ast.walk(stmt):
                    for field in ("body", "orelse", "finalbody"):
                        block = getattr(sub, field, None)
                        if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                            documented_self |= cls._documented(block, self_attrs=True)
                for sub in ast.walk(stmt):
                    targets = (
                        sub.targets
                        if isinstance(sub, ast.Assign)
                        else [sub.target]
                        if isinstance(sub, ast.AnnAssign)
                        else []
                    )
                    for target in targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            assigned_self.add(target.attr)
        return documented, documented_self, assigned_self

    @classmethod
    def _class_node(cls, klass: type) -> ast.ClassDef | None:
        module = sys.modules.get(klass.__module__)
        path = getattr(module, "__file__", None)
        if not path:
            return None
        found: ast.ClassDef | None = None
        for node in ast.walk(cls._module_tree(path)):
            if isinstance(node, ast.ClassDef) and node.name == klass.__name__:
                found = node
                break
        return found


class Undocumented:
    """The public names of `package` (and the modules listed) that say nothing about themselves."""

    def __init__(self, package: str, modules: list[str]) -> None:
        self.package = package
        self.modules = [importlib.import_module(name) for name in modules]
        self.classes = 0
        """How many classes `gaps` read: a guard against checking nothing."""
        self.all_modules = [
            module
            for name, module in sorted(sys.modules.items())
            if module is not None and (name == package or name.startswith(package + "."))
        ]

    def ours(self, obj: Any) -> bool:
        module = getattr(obj, "__module__", "") or ""
        return module == self.package or module.startswith(self.package + ".")

    def gaps(self) -> list[str]:
        """Every undocumented public name, method, property, attribute and field."""
        found: list[str] = []
        seen_classes: set[type] = set()
        for module in self.modules:
            documented_here = SourceDocs.module(module)
            for name in getattr(module, "__all__", []):
                obj = getattr(module, name)
                where = f"{module.__name__}.{name}"
                if inspect.isclass(obj):
                    if self.ours(obj):
                        found += self._class(obj, seen_classes)
                elif inspect.isfunction(obj) or inspect.isbuiltin(obj):
                    if not (obj.__doc__ or "").strip():
                        found.append(where)
                elif isinstance(obj, types.ModuleType):
                    continue
                elif name not in documented_here and not self._constant_documented(name):
                    found.append(where)
        return sorted(set(found))

    def _constant_documented(self, name: str) -> bool:
        return any(name in SourceDocs.module(module) for module in self.all_modules)

    def _class(self, cls: type, seen: set[type]) -> list[str]:
        """`cls`, its bases of ours, and every class of ours its fields and
        public signatures name — what a reader of its page follows."""
        found: list[str] = []
        todo = [cls]
        while todo:
            for klass in todo.pop().__mro__:
                if klass in seen or not self.ours(klass):
                    continue
                seen.add(klass)
                found += self._own(klass)
                todo += [named for named in self._named(klass) if named not in seen]
        return found

    def _named(self, klass: type) -> list[type]:
        hints: list[Any] = []
        if issubclass(klass, BaseModel):
            hints += [
                field.annotation for field in klass.__dict__.get("__pydantic_fields__", {}).values()
            ]
        for name, value in klass.__dict__.items():
            if name.startswith("_"):
                continue
            target = getattr(value, "wrapped", value)
            if isinstance(target, staticmethod | classmethod):
                target = target.__func__
            if isinstance(target, property):
                target = target.fget
            if inspect.isfunction(target):
                try:
                    hints += list(typing.get_type_hints(target).values())
                except Exception:  # noqa: S112 — a hint this process cannot resolve
                    continue
        found: list[type] = []
        while hints:
            hint = hints.pop()
            if inspect.isclass(hint) and self.ours(hint):
                found.append(hint)
            hints += list(typing.get_args(hint))
        return found

    def _inherited_doc(self, klass: type, name: str) -> bool:
        """Whether a base of ours documents `name`, as `inspect.getdoc` reads an override."""
        for base in klass.__mro__[1:]:
            if not self.ours(base) or name not in base.__dict__:
                continue
            value = getattr(base.__dict__[name], "wrapped", base.__dict__[name])
            if isinstance(value, staticmethod | classmethod):
                value = value.__func__
            if isinstance(value, property):
                value = value.fget
            if (getattr(value, "__doc__", None) or "").strip():
                return True
        return False

    def _own(self, klass: type) -> list[str]:
        self.classes += 1
        where = f"{klass.__module__}.{klass.__qualname__}"
        found: list[str] = []
        if not (klass.__dict__.get("__doc__") or "").strip():
            found.append(where)
        documented, documented_self, assigned_self = SourceDocs.klass(klass)
        is_model = issubclass(klass, BaseModel)
        fields = klass.__dict__.get("__pydantic_fields__", {}) if is_model else {}
        own_fields = (
            set(klass.__annotations__)
            if is_model and "__annotations__" in klass.__dict__
            else set()
        )
        for name in sorted(own_fields & set(fields)):
            if name.startswith("_"):
                continue
            if not (fields[name].description or "").strip():
                found.append(f"{where}.{name} (field)")
        members: dict[str, Any] = (
            dict(klass.__members__) if isinstance(klass, enum.EnumMeta) else {}
        )
        for name in members:
            if name in klass.__dict__.get("_member_names_", []) and name not in documented:
                found.append(f"{where}.{name} (member)")
        for name, value in klass.__dict__.items():
            if name.startswith("_") or name in members or name in own_fields:
                continue
            if name in {"model_config", "model_fields", "model_computed_fields"}:
                continue
            target = getattr(value, "wrapped", value)
            if isinstance(target, staticmethod | classmethod):
                target = target.__func__
            if isinstance(target, property):
                target = target.fget
            if isinstance(target, functools.cached_property):
                target = target.func
            if inspect.isfunction(target):
                if not (target.__doc__ or "").strip() and not self._inherited_doc(klass, name):
                    found.append(f"{where}.{name}")
            elif inspect.isclass(target):
                continue
            elif name not in documented:
                found.append(f"{where}.{name} (attribute)")
        for name in sorted(assigned_self - documented_self):
            if name.startswith("_") or name in klass.__dict__ or name in own_fields:
                continue
            found.append(f"{where}.{name} (instance attribute)")
        return found


def test_every_public_name_is_documented() -> None:
    gaps = [gap for gap in Undocumented("igni_service", MODULES).gaps() if gap not in EXEMPT]
    assert gaps == [], "undocumented:\n  " + "\n  ".join(gaps)


def test_the_check_reads_the_whole_api() -> None:
    checked = Undocumented("igni_service", MODULES)
    checked.gaps()
    assert checked.classes >= 100


def test_a_field_s_docstring_is_its_description() -> None:
    from igni_service import Person

    assert (
        Person.model_fields["user_id"].description
        == "The person's igni user id (the token's `sub`)."
    )

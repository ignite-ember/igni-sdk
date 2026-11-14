"""How one of igni's methods is typed in Python: its parameters, signature and result."""

from __future__ import annotations

import re

from pydantic import BaseModel

from tools.client_contract import RpcContract
from tools.client_names import OWN_SESSION_ARG, SELF_MADE
from tools.client_plan import Placement, Plan
from tools.client_python import ContractError, Imports, field_name, pascal
from tools.client_types import Types

#: Capitalised names in an annotation that are not igni_client.models' classes.
_NOT_MODELS = frozenset({"Literal", "Annotated", "JsonValue", "None", "Field"})


class Param(BaseModel):
    """One parameter of a generated method."""

    name: str
    #: Empty for an argument igni-client fills in itself, which the signature omits.
    annotation: str
    default: str | None
    #: How the argument goes into the args model, when not as itself.
    value: str


class MethodSignatures:
    """Each method's parameters, signature and result type, as the generated code spells them.

    Records, as it goes, which of ``igni_client.models``' classes the
    signatures name (``models``) and what else they need imported (``imports``).
    """

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.contract: RpcContract = plan.contract
        self.types: Types = plan.types
        self.imports = Imports()
        self.models: set[str] = set()

    def _use(self, annotation: str) -> str:
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", annotation):
            if token[0].isupper() and token not in _NOT_MODELS:
                self.models.add(token)
        return annotation

    @staticmethod
    def adapter_name(wire: str) -> str:
        return f"_{wire.upper()}"

    def event_alias(self, wire: str) -> str:
        return pascal(wire) + "Event"

    def result_type(self, wire: str) -> str:
        return self._use(self.types.annotation(self.contract.methods[wire].result, self.imports))

    def params(self, placement: Placement) -> tuple[list[Param], str]:
        """The method's parameters, and its args model's class."""
        method = self.contract.methods[placement.wire]
        args_def = self.contract.ref_name(method.args)
        if args_def is None:
            raise ContractError(f"{placement.wire}: args is not a def")
        model = self._use(self.types.class_name(args_def))
        schema = self.contract.defs[args_def]
        required = set(schema.get("required", []))
        params: list[Param] = []
        for prop, prop_schema in schema.get("properties", {}).items():
            python = field_name(prop)
            if (
                placement.owner == "session"
                and placement.wire in OWN_SESSION_ARG
                and prop == "session_id"
            ):
                params.append(
                    Param(name=python, annotation="", default=None, value="self._caller.session_id")
                )
                continue
            annotation = self._use(self.types.annotation(prop_schema, self.imports))
            value = python
            default: str | None = None
            if "default" in prop_schema:
                raw = prop_schema["default"]
                if isinstance(raw, list | dict):
                    if not annotation.endswith("| None"):
                        annotation += " | None"
                    default = "None"
                    empty = "[]" if isinstance(raw, list) else "{}"
                    value = f"({empty} if {python} is None else {python})"
                else:
                    default = repr(raw)
            elif prop not in required:
                if not annotation.endswith("| None"):
                    annotation += " | None"
                default = "None"
                kind = prop_schema.get("type")
                if kind in ("object", "array"):
                    empty = "{}" if kind == "object" else "[]"
                    value = f"({empty} if {python} is None else {python})"
            params.append(Param(name=python, annotation=annotation, default=default, value=value))
        self._fill(placement.wire, params)
        return params, model

    def _fill(self, wire: str, params: list[Param]) -> None:
        """Fill in the arguments igni-client makes for itself.

        A run's id, the writer's own name for a change: igni echoes them
        back on the call's own events, so that they can be told from
        another call's. The caller may give their own; one is made when
        they do not.
        """
        for name, expression in SELF_MADE.get(wire, {}).items():
            for param in params:
                if param.name != name:
                    continue
                if param.default is None:
                    raise ContractError(f"{wire}: {name} is required; it cannot be made")
                param.value = f"{param.name} or {expression}"

    def signature(self, placement: Placement, params: list[Param]) -> str:
        """``self``, then a lone required argument by position, then the rest by keyword.

        A method of one argument takes it by position too, required or not:
        ``session.plan.approve(run_id)``, ``session.command(text)``.
        """
        shown = [p for p in params if p.annotation]
        required = [p for p in shown if p.default is None]
        if len(shown) == 1:
            required = shown
        parts = ["self"]
        if len(required) == 1:
            lone = required[0]
            default = f" = {lone.default}" if lone.default is not None else ""
            parts.append(f"{lone.name}: {lone.annotation}{default}")
            rest = [p for p in shown if p is not lone]
        else:
            rest = shown
        if rest:
            parts.append("*")
            for p in sorted(rest, key=lambda p: p.default is not None):
                default = f" = {p.default}" if p.default is not None else ""
                parts.append(f"{p.name}: {p.annotation}{default}")
        return ", ".join(parts)


__all__ = ["MethodSignatures", "Param"]

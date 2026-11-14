"""JSON Schema → Python annotations, over igni-core's RPC contract's defs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel

from tools.client_contract import RpcContract
from tools.client_names import CLASS_NAMES, UNION_NAMES
from tools.client_python import ContractError, Imports

#: The JSON types igni-core's ``JsonValue`` def allows: any JSON value.
_JSON_TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})

#: The JSON types that are one Python type whatever else the schema says.
_SCALARS: Mapping[str, str] = MappingProxyType(
    {"integer": "int", "number": "float", "boolean": "bool", "null": "None"}
)


class NamedUnion(BaseModel):
    """A union of defs the contract uses, under its name in ``UNION_NAMES``."""

    #: The property whose value tells the members apart; empty when none does.
    told_by: str
    members: list[str]


class Types:
    """JSON Schema → Python annotations, over the contract's defs."""

    def __init__(self, contract: RpcContract) -> None:
        self.contract = contract
        self.unions: dict[str, NamedUnion] = {}
        self._readers: Mapping[str, Callable[[dict[str, Any], Imports], str]] = MappingProxyType(
            {"string": self._string, "array": self._array, "object": self._object}
        )

    def class_name(self, def_name: str) -> str:
        return CLASS_NAMES.get(def_name, def_name)

    def is_enum(self, def_name: str) -> bool:
        schema = self.contract.defs[def_name]
        return "enum" in schema and "properties" not in schema

    def is_json_value(self, schema: dict[str, Any]) -> bool:
        return self.contract.ref_name(schema) == "JsonValue" or (
            isinstance(schema.get("type"), list) and set(schema["type"]) == _JSON_TYPES
        )

    def annotation(self, schema: dict[str, Any], imports: Imports) -> str:
        """The Python type ``schema`` describes."""
        if not schema or self.is_json_value(schema):
            imports.pydantic.add("JsonValue")
            return "JsonValue"
        ref = self.contract.ref_name(schema)
        if ref is not None:
            return self.class_name(ref)
        if "const" in schema:
            imports.typing.add("Literal")
            return f"Literal[{schema['const']!r}]"
        if "enum" in schema:
            imports.typing.add("Literal")
            return "Literal[" + ", ".join(repr(v) for v in schema["enum"]) + "]"
        if "anyOf" in schema or "oneOf" in schema:
            members = schema.get("anyOf") or schema["oneOf"]
            told_by = (schema.get("discriminator") or {}).get("propertyName")
            return self._union(members, imports, told_by)
        kind = schema.get("type")
        if isinstance(kind, list):
            return self._union([{"type": k} for k in kind], imports)
        if not isinstance(kind, str):
            raise ContractError(f"a schema this generator cannot read: {schema}")
        if kind in _SCALARS:
            return _SCALARS[kind]
        reader = self._readers.get(kind)
        if reader is None:
            raise ContractError(f"a schema this generator cannot read: {schema}")
        return reader(schema, imports)

    def _string(self, schema: dict[str, Any], imports: Imports) -> str:
        if schema.get("format") == "date-time":
            imports.datetime = True
            return "datetime"
        return "str"

    def _array(self, schema: dict[str, Any], imports: Imports) -> str:
        if "prefixItems" in schema:
            items = [self.annotation(s, imports) for s in schema["prefixItems"]]
            return "tuple[" + ", ".join(items) + "]"
        return f"list[{self.annotation(schema.get('items', {}), imports)}]"

    def _object(self, schema: dict[str, Any], imports: Imports) -> str:
        if "properties" in schema:
            raise ContractError(f"an object defined in place, not as a def: {schema}")
        extra = schema.get("additionalProperties", {})
        value = self.annotation(extra if isinstance(extra, dict) else {}, imports)
        return f"dict[str, {value}]"

    def _union(
        self, members: list[dict[str, Any]], imports: Imports, told_by: str | None = None
    ) -> str:
        nullable = any(m.get("type") == "null" for m in members)
        rest = [m for m in members if m.get("type") != "null"]
        refs = [self.contract.ref_name(m) for m in rest]
        if len(rest) > 1 and all(r is not None for r in refs):
            names = [r for r in refs if r is not None]
            body = self._named_union(names, told_by)
        else:
            parts: list[str] = []
            for member in rest:
                rendered = self.annotation(member, imports)
                if rendered not in parts:
                    parts.append(rendered)
            body = " | ".join(parts)
        if nullable:
            return f"{body} | None" if body else "None"
        return body

    def _named_union(self, names: list[str], told_by: str | None) -> str:
        key = frozenset(names)
        alias = UNION_NAMES.get(key)
        if alias is None:
            raise ContractError(
                f"a union of {sorted(names)} has no name; add one to UNION_NAMES "
                "in tools/client_names.py"
            )
        self.unions[alias] = NamedUnion(
            told_by=told_by or self.discriminator(names) or "", members=names
        )
        return alias

    def discriminator(self, names: list[str]) -> str | None:
        """The property every member fixes to its own value, if there is one."""
        candidates: set[str] | None = None
        for name in names:
            props = self.contract.defs[name].get("properties", {})
            fixed = {key for key, value in props.items() if "const" in value}
            candidates = fixed if candidates is None else candidates & fixed
        for key in sorted(candidates or ()):
            values = [self.contract.defs[n]["properties"][key]["const"] for n in names]
            if len(set(values)) == len(values):
                return key
        return None


__all__ = ["NamedUnion", "Types"]

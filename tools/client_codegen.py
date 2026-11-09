"""Generate igni-client's typed models and methods from igni-core's RPC contract.

igni-core publishes ``docs/rpc-contract.json``; this repository keeps a copy
in ``contracts/rpc-contract.json`` (``make contracts``), and this writes

* ``packages/igni-client/src/igni_client/models.py`` — a Pydantic model for
  every type the contract defines that a client sends or reads, every
  message on igni's socket among them, with the contract's descriptions as
  docstrings;
* ``packages/igni-client/src/igni_client/api.py`` — every method a client
  calls, as a typed Python method on ``IgniClient`` (scope ``igni``) or on
  ``Session`` (scope ``session``), grouped by namespace, with the contract's
  documentation as its docstring; and the table that says, per method, who
  may call it, how igni answers and what it streams;
* the API reference in ``packages/igni-client/README.md``, between its
  ``<!-- api-reference:start -->`` and ``<!-- api-reference:end -->``
  markers — igni-client's PyPI page.

Neither Python file is edited by hand, nor is the README between the
markers. ``tests/test_the_client_api_is_generated.py`` regenerates all three
in memory and fails when what is checked in differs; ``make client-api``
writes them. What a method is called in Python is the one decision made by
hand, in ``tools/client_names.py``; the generator refuses a contract with a
method that table does not place.

The Python is formatted with the repository's ``ruff``, so what is checked in
passes the package's own ``ruff format --check``.
"""

from __future__ import annotations

import keyword
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.client_contract import CONTRACT_FILE, PUSH_PREFIX, PushChannelContract, RpcContract
from tools.client_names import (
    CLASS_NAMES,
    FOLLOWED,
    HAND_WRITTEN_NAMESPACES,
    MESSAGE_METHODS,
    MESSAGES_NOT_SENT,
    MESSAGES_SENT_BY_HAND,
    METHODS,
    NAMESPACES,
    NOT_FOR_CLIENTS,
    OWN_SESSION_ARG,
    SCOPE_EXCEPTIONS,
    UNFOLLOWED,
    UNION_NAMES,
)

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path("packages/igni-client")
MODELS_OUTPUT = PACKAGE / "src/igni_client/models.py"
API_OUTPUT = PACKAGE / "src/igni_client/api.py"
README = PACKAGE / "README.md"
README_START = "<!-- api-reference:start -->"
README_END = "<!-- api-reference:end -->"

_BANNER = (
    "GENERATED from igni-core's RPC contract (version {version}) by igni-sdk's "
    "tools/client_codegen.py — do not edit. Run `make client-api` after refreshing "
    "contracts/rpc-contract.json."
)

#: The JSON types igni-core's ``JsonValue`` def allows: any JSON value.
_JSON_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
#: Fields every message carries, which the bases in ``igni_client.wire`` declare.
_ENVELOPE = ("type", "id", "session_id", "event_seq")
#: Fields a run's events carry besides: the base ``RunEvent`` declares them.
_RUN_FIELDS = ("run_id", "parent_run_id")


class ContractError(ValueError):
    """The contract says something this generator cannot turn into Python."""


def snake(name: str) -> str:
    """``activeForm`` → ``active_form``."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


#: What a field may not be called in a Pydantic model: `BaseModel`'s own names.
_RESERVED = frozenset(
    {
        "json",
        "dict",
        "copy",
        "schema",
        "schema_json",
        "construct",
        "validate",
        "fields",
        "parse_obj",
        "parse_raw",
        "parse_file",
        "from_orm",
        "update_forward_refs",
    }
)


def field_name(prop: str) -> str:
    """The Python name of the wire field ``prop``: snake case, clear of keywords and
    of `BaseModel`'s own names (``json`` → ``json_``)."""
    python = snake(prop)
    if keyword.iskeyword(python) or python in _RESERVED:
        python += "_"
    return python


def pascal(name: str) -> str:
    """``read_process_tail`` → ``ReadProcessTail``."""
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[_.]", name) if part)


def docstring(text: str, indent: str) -> list[str]:
    """``text`` as a docstring at ``indent``, escaped so any text is valid Python."""
    body = text.strip().replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    if not body:
        return []
    lines = body.splitlines()
    if len(lines) == 1:
        closing = " " if body.endswith('"') else ""
        return [f'{indent}"""{body}{closing}"""']
    out = [f'{indent}"""{lines[0]}']
    out += [f"{indent}{line}" if line.strip() else "" for line in lines[1:]]
    out.append(f'{indent}"""')
    return out


# ── Where things are ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Placement:
    """Where one method lives in Python: ``igni.processes.tail``."""

    wire: str
    owner: str
    namespace: str
    name: str

    @classmethod
    def of(cls, wire: str, path: str) -> Placement:
        parts = path.split(".")
        if parts[0] not in ("igni", "session") or len(parts) not in (2, 3):
            raise ContractError(f"{wire}: {path!r} is not igni.<ns>.<name> or session.<ns>.<name>")
        namespace = parts[1] if len(parts) == 3 else ""
        return cls(wire=wire, owner=parts[0], namespace=namespace, name=parts[-1])

    @property
    def path(self) -> str:
        return ".".join(p for p in (self.owner, self.namespace, self.name) if p)

    @property
    def group(self) -> str:
        """``igni.processes``, or ``igni`` for a method on the client itself."""
        return ".".join(p for p in (self.owner, self.namespace) if p)


def class_for_group(group: str) -> str:
    """``igni.processes`` → ``IgniProcesses``; ``session`` → ``SessionApi``."""
    if "." not in group:
        return pascal(group) + "Api"
    return pascal(group)


# ── Types ─────────────────────────────────────────────────────────────


@dataclass
class Imports:
    """What the generated module must import."""

    typing: set[str] = field(default_factory=set)
    pydantic: set[str] = field(default_factory=set)
    datetime: bool = False


class Types:
    """JSON Schema → Python annotations, over the contract's defs."""

    def __init__(self, contract: RpcContract) -> None:
        self.contract = contract
        self.unions: dict[str, tuple[str, list[str]]] = {}

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
        if kind == "string":
            if schema.get("format") == "date-time":
                imports.datetime = True
                return "datetime"
            return "str"
        if kind == "integer":
            return "int"
        if kind == "number":
            return "float"
        if kind == "boolean":
            return "bool"
        if kind == "null":
            return "None"
        if kind == "array":
            if "prefixItems" in schema:
                items = [self.annotation(s, imports) for s in schema["prefixItems"]]
                return "tuple[" + ", ".join(items) + "]"
            return f"list[{self.annotation(schema.get('items', {}), imports)}]"
        if kind == "object":
            if "properties" in schema:
                raise ContractError(f"an object defined in place, not as a def: {schema}")
            extra = schema.get("additionalProperties", {})
            value = self.annotation(extra if isinstance(extra, dict) else {}, imports)
            return f"dict[str, {value}]"
        raise ContractError(f"a schema this generator cannot read: {schema}")

    def _union(
        self, members: list[dict[str, Any]], imports: Imports, told_by: str | None = None
    ) -> str:
        nullable = any(m.get("type") == "null" for m in members)
        rest = [m for m in members if m.get("type") != "null"]
        refs = [self.contract.ref_name(m) for m in rest]
        if len(rest) > 1 and all(r is not None for r in refs):
            names = [r for r in refs if r is not None]
            body = self._named_union(names, imports, told_by)
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

    def _named_union(self, names: list[str], imports: Imports, told_by: str | None) -> str:
        key = frozenset(names)
        alias = UNION_NAMES.get(key)
        if alias is None:
            raise ContractError(
                f"a union of {sorted(names)} has no name; add one to UNION_NAMES "
                "in tools/client_names.py"
            )
        self.unions[alias] = (told_by or self.discriminator(names) or "", names)
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


# ── What is generated ─────────────────────────────────────────────────


def hoisted(contract: RpcContract) -> RpcContract:
    """``contract`` with every object it defines in place made a def of its own.

    A push channel's payload is sometimes written out where it is used,
    titled but not in ``defs``; as a def it becomes a class like any other.
    """
    contract = contract.model_copy(deep=True)

    def lift(node: Any) -> Any:
        if isinstance(node, list):
            return [lift(n) for n in node]
        if not isinstance(node, dict):
            return node
        node = {k: (v if k in ("default", "const", "enum") else lift(v)) for k, v in node.items()}
        if node.get("type") == "object" and "properties" in node and "title" in node:
            name = node["title"]
            if contract.defs.get(name, node) != node:
                # A def of that title is the broadcast; this is its payload, without `channel`.
                name = name.removesuffix("Event") + "Payload"
                if contract.defs.get(name, node) != node:
                    raise ContractError(f"{node['title']} is defined twice, differently")
            contract.defs[name] = node
            return {"$ref": f"#/defs/{name}"}
        return node

    for name, channel in list(contract.push_channels.items()):
        contract.push_channels[name] = PushChannelContract.model_validate(
            {"doc": channel.doc, "schema": lift(channel.schema_)}
        )
    return contract


class Plan:
    """Which methods and defs are generated, and where each method goes."""

    def __init__(self, contract: RpcContract) -> None:
        self.contract = hoisted(contract)
        self.types = Types(self.contract)
        contract = self.contract
        self._check_placement()
        self.placements = {
            wire: Placement.of(wire, METHODS[wire])
            for wire in sorted(contract.methods)
            if wire not in NOT_FOR_CLIENTS
        }
        self._check_messages()
        self.defs_in, self.defs_out = self._reachable()

    def _check_placement(self) -> None:
        wires = set(self.contract.methods)
        unplaced = wires - set(METHODS) - set(NOT_FOR_CLIENTS)
        if unplaced:
            raise ContractError(
                f"methods with no name in tools/client_names.py: {sorted(unplaced)}"
            )
        gone = (set(METHODS) | set(NOT_FOR_CLIENTS)) - wires
        if gone:
            raise ContractError(f"tools/client_names.py names methods igni lacks: {sorted(gone)}")
        both = set(METHODS) & set(NOT_FOR_CLIENTS)
        if both:
            raise ContractError(f"both named and not for clients: {sorted(both)}")
        for wire, path in METHODS.items():
            method = self.contract.methods[wire]
            if method.access in ("page", "platform"):
                raise ContractError(f"{wire} is a {method.access} call; list it in NOT_FOR_CLIENTS")
            if path.split(".")[0] != method.scope and wire not in SCOPE_EXCEPTIONS:
                raise ContractError(
                    f"{wire} has scope {method.scope} but is placed at {path}; "
                    "place it by its scope or say why in SCOPE_EXCEPTIONS"
                )
        streaming = {w for w, m in self.contract.methods.items() if m.streams} - set(
            NOT_FOR_CLIENTS
        )
        decided = set(FOLLOWED) | set(UNFOLLOWED)
        if streaming != decided:
            raise ContractError(
                "every method that streams is either followed or says why not: "
                f"undecided {sorted(streaming - decided)}, not streaming {sorted(decided - streaming)}"
            )
        paths = [Placement.of(w, p).path for w, p in METHODS.items()]
        clashes = {p for p in paths if paths.count(p) > 1}
        if clashes:
            raise ContractError(f"two methods share a name: {sorted(clashes)}")

    def _check_messages(self) -> None:
        sent = {t for t, m in self.contract.messages.items() if m.direction in ("to_igni", "both")}
        decided = set(MESSAGE_METHODS) | set(MESSAGES_NOT_SENT) | set(MESSAGES_SENT_BY_HAND)
        if sent != decided:
            raise ContractError(
                "every message a client may send is a method, sent by hand, or says why "
                f"not: undecided {sorted(sent - decided)}, unknown {sorted(decided - sent)}"
            )

    def _reachable(self) -> tuple[set[str], set[str]]:
        """The defs a client sends (``in``) and reads (``out``)."""
        inputs: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []
        for wire in self.placements:
            method = self.contract.methods[wire]
            inputs.append(method.args)
            outputs.append(method.result)
        for message in self.contract.messages.values():
            if message.direction in ("to_igni", "both"):
                inputs.append(message.schema_)
            if message.direction in ("to_client", "both"):
                outputs.append(message.schema_)
        for channel in self.contract.push_channels.values():
            outputs.append(channel.schema_)
        return self._closure(inputs), self._closure(outputs)

    def _closure(self, roots: Iterable[dict[str, Any]]) -> set[str]:
        found: set[str] = set()
        stack: list[Any] = list(roots)
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                ref = self.contract.ref_name(node)
                if ref is not None and ref not in found:
                    found.add(ref)
                    stack.append(self.contract.defs[ref])
                stack.extend(v for k, v in node.items() if k not in ("default", "const", "enum"))
            elif isinstance(node, list):
                stack.extend(node)
        found.discard("JsonValue")
        return found

    # ── Messages ──

    def message_of_def(self) -> dict[str, str]:
        """Def name → the wire type of the message it is."""
        return {self.contract.message_def(t): t for t in self.contract.messages}

    def stream_classes(self, wire: str) -> list[str]:
        """The classes of what ``wire`` streams, in the contract's order."""
        out: list[str] = []
        for stream in self.contract.methods[wire].streams:
            if stream.startswith(PUSH_PREFIX):
                channel = stream.removeprefix(PUSH_PREFIX)
                name = (
                    push_class(channel)
                    if channel in self.contract.push_channels
                    else "PushNotification"
                )
            else:
                name = self.types.class_name(self.contract.message_def(stream))
            if name not in out:
                out.append(name)
        return out


def push_class(channel: str) -> str:
    """The class of a typed push: ``process_line`` → ``ProcessLinePush``."""
    return pascal(channel) + "Push"


# ── models.py ─────────────────────────────────────────────────────────


class ModelsGenerator:
    """Every def a client sends or reads, as a Pydantic model or a type alias."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.contract = plan.contract
        self.types = plan.types
        self.imports = Imports()
        self.messages = plan.message_of_def()

    def generate(self) -> str:
        names = sorted(self.plan.defs_in | self.plan.defs_out)
        enums = [n for n in names if self.types.is_enum(n)]
        classes = [n for n in names if not self.types.is_enum(n)]
        body: list[str] = []
        for name in enums:
            body += self._enum(name)
        for name in classes:
            body += self._class(name)
        for channel in sorted(self.contract.push_channels):
            body += self._push(channel)
        for wire in self.plan.placements:
            # A method's result may be a union the models do not use: name it here.
            self.types.annotation(self.contract.methods[wire].result, Imports())
        unions: list[str] = []
        for alias in sorted(self.types.unions):
            unions += self._union(alias)
        tables = self._tables()
        head = self._head()
        return "\n".join([*head, *body, *unions, *tables]) + "\n"

    def _head(self) -> list[str]:
        out = [
            '"""Every type igni-client sends or reads, as igni-core\'s RPC contract defines it.',
            "",
            _BANNER.format(version=self.contract.version),
            "",
            "Messages a client reads are `Event`s (a run's, `RunEvent`s); messages it",
            "sends are `Frame`s; arguments are `Args`; everything else is a `Model`.",
            'A model a client reads keeps a field a newer igni adds (`extra="allow"`).',
            '"""',
            "",
            "from __future__ import annotations",
            "",
        ]
        if self.imports.datetime:
            out.append("from datetime import datetime")
        typing = sorted(self.imports.typing)
        if typing:
            out.append(f"from typing import {', '.join(typing)}")
        out.append("")
        pydantic = sorted(self.imports.pydantic)
        if pydantic:
            out.append(f"from pydantic import {', '.join(pydantic)}")
            out.append("")
        bases = sorted(self.bases_used)
        out.append(f"from igni_client.wire import {', '.join(bases)}")
        out.append("")
        return out

    @property
    def bases_used(self) -> set[str]:
        return getattr(self, "_bases", set())

    def _use_base(self, base: str) -> str:
        if not hasattr(self, "_bases"):
            self._bases: set[str] = set()
        self._bases.add(base)
        return base

    def _enum(self, name: str) -> list[str]:
        schema = self.contract.defs[name]
        self.imports.typing.add("Literal")
        values = ", ".join(repr(v) for v in schema["enum"])
        out = ["", ""]
        described = schema.get("description") or f"The values of {name}."
        out += [f"#: {line}".rstrip() for line in described.strip().splitlines()]
        out.append(f"type {self.types.class_name(name)} = Literal[{values}]")
        return out

    def _base(self, name: str, props: dict[str, Any]) -> str:
        wire = self.messages.get(name)
        if wire is not None:
            direction = self.contract.messages[wire].direction
            if direction == "to_igni":
                return self._use_base("Frame")
            if all(f in props for f in _RUN_FIELDS):
                return self._use_base("RunEvent")
            return self._use_base("Event")
        if name in self.plan.defs_out:
            return self._use_base("Model")
        return self._use_base("Args")

    def _class(self, name: str) -> list[str]:
        schema = self.contract.defs[name]
        props: dict[str, Any] = schema.get("properties", {})
        required = set(schema.get("required", []))
        cls = self.types.class_name(name)
        base = self._base(name, props)
        wire = self.messages.get(name)
        doc = (
            schema.get("description")
            or (self.contract.messages[wire].doc if wire else "")
            or f"{schema.get('title', name)}."
        )
        if wire is not None:
            doc = f"{doc.rstrip()}\n\nOn the wire: ``{wire}``."
        out = ["", "", f"class {cls}({base}):"]
        out += docstring(doc, "    ")
        aliased = any(field_name(p) != p for p in props)
        if aliased:
            self.imports.pydantic.add("ConfigDict")
            out += [
                "",
                "    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)",
            ]
        if props:
            out.append("")
        for prop in props:
            out += self._field(prop, props[prop], prop in required)
        return out

    def _field(self, prop: str, schema: dict[str, Any], required: bool) -> list[str]:
        python = field_name(prop)
        annotation = self.types.annotation(schema, self.imports)
        kwargs: list[str] = []
        default: str | None = None
        if "default" in schema:
            value = schema["default"]
            if isinstance(value, list | dict) and value:
                ref = self.contract.ref_name(schema)
                maker = f"{self.types.class_name(ref)}.model_validate" if ref else ""
                kwargs.append(f"default_factory=lambda: {maker}({value!r})")
            elif isinstance(value, list):
                kwargs.append("default_factory=list")
            elif isinstance(value, dict):
                kwargs.append("default_factory=dict")
            else:
                default = repr(value)
        elif not required:
            kind = schema.get("type")
            if kind == "object":
                kwargs.append("default_factory=dict")
            elif kind == "array":
                kwargs.append("default_factory=list")
            else:
                if not annotation.endswith("| None") and annotation != "None":
                    annotation += " | None"
                default = "None"
        if python != prop:
            kwargs.append(f"alias={prop!r}")
        if "minLength" in schema:
            kwargs.append(f"min_length={schema['minLength']}")
        if kwargs:
            self.imports.pydantic.add("Field")
            if default is not None:
                kwargs.insert(0, f"default={default}")
            line = f"    {python}: {annotation} = Field({', '.join(kwargs)})"
        elif default is not None:
            line = f"    {python}: {annotation} = {default}"
        else:
            line = f"    {python}: {annotation}"
        out = [line]
        if schema.get("description"):
            out += docstring(schema["description"], "    ")
        return out

    def _push(self, channel: str) -> list[str]:
        spec = self.contract.push_channels[channel]
        payload = self.types.annotation(spec.schema_, self.imports)
        self.imports.typing.add("Literal")
        doc = spec.doc or f"A push on ``{channel}``."
        doc = f"{doc.rstrip()}\n\nOn the wire: ``push_notification`` on the channel ``{channel}``."
        out = ["", "", f"class {push_class(channel)}(PushNotification):"]
        out += docstring(doc, "    ")
        out += [
            "",
            f"    channel: Literal[{channel!r}] = {channel!r}",
            f"    payload: {payload}  # type: ignore[assignment]",
        ]
        return out

    def _union(self, alias: str) -> list[str]:
        discriminator, names = self.types.unions[alias]
        members = " | ".join(self.types.class_name(n) for n in names)
        out = ["", ""]
        if discriminator:
            self.imports.typing.add("Annotated")
            self.imports.pydantic.add("Field")
            out.append(f"#: One of {len(names)} kinds, told apart by ``{discriminator}``.")
            out.append(
                f'type {alias} = Annotated[{members}, Field(discriminator="{discriminator}")]'
            )
        else:
            out.append(
                f"#: One of {len(names)} kinds. Nothing in the contract tells them apart: "
                "the one that fits best is taken."
            )
            out.append(f"type {alias} = {members}")
        return out

    def _tables(self) -> list[str]:
        events: list[str] = []
        frames: list[str] = []
        for wire_type in sorted(self.contract.messages):
            message = self.contract.messages[wire_type]
            cls = self.types.class_name(self.contract.message_def(wire_type))
            if message.direction in ("to_client", "both"):
                events.append(f"    {wire_type!r}: {cls},")
            if message.direction in ("to_igni", "both"):
                frames.append(f"    {wire_type!r}: {cls},")
        pushes = [f"    {c!r}: {push_class(c)}," for c in sorted(self.contract.push_channels)]
        return [
            "",
            "",
            "#: Every message igni sends, by its wire `type`.",
            "EVENT_TYPES: dict[str, type[Event]] = {",
            *events,
            "}",
            "",
            "#: Every message a client sends, by its wire `type`.",
            "FRAME_TYPES: dict[str, type[Frame | Event]] = {",
            *frames,
            "}",
            "",
            "#: Every push channel the contract types, by channel.",
            "PUSH_TYPES: dict[str, type[PushNotification]] = {",
            *pushes,
            "}",
        ]


# ── api.py ────────────────────────────────────────────────────────────


@dataclass
class Param:
    name: str
    annotation: str
    default: str | None
    #: How the argument goes into the args model, when not as itself.
    value: str


class ApiGenerator:
    """Every method a client calls, on the class its placement names."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.contract = plan.contract
        self.types = plan.types
        self.imports = Imports()
        self.models: set[str] = set()

    def generate(self) -> str:
        groups: dict[str, list[Placement]] = {}
        for placement in self.plan.placements.values():
            groups.setdefault(placement.group, []).append(placement)
        for name, (_, path) in MESSAGE_METHODS.items():
            placement = Placement.of(name, path)
            groups.setdefault(placement.group, []).append(placement)
        results = self._results()
        events = self._event_aliases()
        classes: list[str] = []
        for group in sorted(groups, key=lambda g: (g.count("."), g)):
            if "." in group:
                classes += self._namespace(group, groups[group])
        for owner in ("igni", "session"):
            classes += self._owner(owner, groups.get(owner, []), groups)
        table = self._table()
        head = self._head()
        return "\n".join([*head, *results, *events, *table, *classes]) + "\n"

    def _head(self) -> list[str]:
        out = [
            '"""Every method a client calls, typed: igni\'s RPC methods by namespace.',
            "",
            _BANNER.format(version=self.contract.version),
            "",
            "`IgniApi` is what `IgniClient` adds for igni as a whole, and `SessionApi`",
            "what `Session` adds for one session. A method that streams returns a",
            "`Call`: await it for the result, or `async with` it to follow its events too.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
        ]
        if getattr(self, "builtins", False):
            out.append("import builtins")
        if self.imports.datetime:
            out.append("from datetime import datetime")
        typing = sorted(self.imports.typing)
        if typing:
            out.append(f"from typing import {', '.join(typing)}")
        out.append("")
        pydantic = sorted({"TypeAdapter", *self.imports.pydantic})
        out.append(f"from pydantic import {', '.join(pydantic)}")
        out.append("")
        out.append("from igni_client.calls import Call, Caller, MethodSpec")
        models = sorted(self.models)
        out.append("from igni_client.models import (")
        out += [f"    {m}," for m in models]
        out.append(")")
        out.append("")
        return out

    def _use(self, annotation: str) -> str:
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", annotation):
            if token[0].isupper() and token not in (
                "Literal",
                "Annotated",
                "JsonValue",
                "None",
                "Field",
            ):
                self.models.add(token)
        return annotation

    @staticmethod
    def adapter_name(wire: str) -> str:
        return f"_{wire.upper()}"

    def result_type(self, wire: str) -> str:
        return self._use(self.types.annotation(self.contract.methods[wire].result, self.imports))

    def _results(self) -> list[str]:
        out = ["", "# What each method answers, read with these."]
        for wire in sorted(self.plan.placements):
            annotation = self.result_type(wire)
            out.append(
                f"{self.adapter_name(wire)}: TypeAdapter[{annotation}] = TypeAdapter({annotation})"
            )
        for name, (_, _path) in sorted(MESSAGE_METHODS.items()):
            reply = MESSAGE_METHODS[name][0]
            if reply:
                cls = self._use(self.types.class_name(self.contract.message_def(reply)))
                out.append(f"{self.adapter_name(name)}: TypeAdapter[{cls}] = TypeAdapter({cls})")
        return out

    def event_alias(self, wire: str) -> str:
        return pascal(wire) + "Event"

    def _event_aliases(self) -> list[str]:
        out = ["", "", "# What each method that is followed streams."]
        for wire in sorted(FOLLOWED):
            classes = [self._use(c) for c in self.plan.stream_classes(wire)]
            out.append(f"type {self.event_alias(wire)} = {' | '.join(classes)}")
        return out

    def _table(self) -> list[str]:
        out = [
            "",
            "#: Every method a client calls, by wire name: who may call it, how igni",
            "#: answers it, and what it streams.",
            "METHODS: dict[str, MethodSpec] = {",
        ]
        for wire in sorted(self.plan.placements):
            m = self.contract.methods[wire]
            placement = self.plan.placements[wire]
            streams = "".join(f"{s!r}, " for s in m.streams)
            out.append(
                f"    {wire!r}: MethodSpec(wire={wire!r}, python={placement.path!r}, "
                f"scope={m.scope!r}, access={m.access!r}, reply={m.reply!r}, "
                f"streams=({streams}), followed={wire in FOLLOWED}),"
            )
        out.append("}")
        out += [
            "",
            "#: igni's methods a client never calls, and why.",
            "NOT_FOR_CLIENTS: dict[str, str] = {",
        ]
        out += [f"    {w!r}: {r!r}," for w, r in sorted(NOT_FOR_CLIENTS.items())]
        out.append("}")
        out += [
            "",
            "#: Methods that stream, but whose events igni gives a client nothing to",
            "#: tell apart from another call's: they return their result only.",
            "UNFOLLOWED: dict[str, str] = {",
        ]
        out += [f"    {w!r}: {r!r}," for w, r in sorted(UNFOLLOWED.items())]
        out.append("}")
        return out

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
                params.append(Param(python, "", None, "self._caller.session_id"))
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
            params.append(Param(python, annotation, default, value))
        return params, model

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

    def _method(self, placement: Placement) -> list[str]:
        if placement.wire in MESSAGE_METHODS:
            return self._message_method(placement)
        method = self.contract.methods[placement.wire]
        params, model = self.params(placement)
        result = self.result_type(placement.wire)
        values = ", ".join(f"{p.name!r}: {p.value}" for p in params)
        adapter = self.adapter_name(placement.wire)
        doc = method.doc
        if placement.wire in FOLLOWED:
            doc += "\n\n" + FOLLOWED[placement.wire]
        elif placement.wire in UNFOLLOWED:
            doc += "\n\nNot followed: " + UNFOLLOWED[placement.wire]
        if method.access != "client":
            doc += "\n\n" + ACCESS_NOTES[method.access]
        sig = self.signature(placement, params)
        if placement.wire in FOLLOWED:
            out = [
                "",
                f"    def {placement.name}({sig}) -> Call[{result}, {self.event_alias(placement.wire)}]:",
            ]
            out += docstring(doc, "        ")
            out.append(
                f"        return self._caller.follow({placement.wire!r}, {model}, {{{values}}}, {adapter})"
            )
            return out
        out = ["", f"    async def {placement.name}({sig}) -> {result}:"]
        out += docstring(doc, "        ")
        out.append(
            f"        return await self._caller.rpc({placement.wire!r}, {model}, {{{values}}}, {adapter})"
        )
        return out

    def _message_method(self, placement: Placement) -> list[str]:
        wire_type = placement.wire
        reply, _ = MESSAGE_METHODS[wire_type]
        message = self.contract.messages[wire_type]
        def_name = self.contract.message_def(wire_type)
        cls = self._use(self.types.class_name(def_name))
        schema = self.contract.defs[def_name]
        params: list[Param] = []
        for prop, prop_schema in schema.get("properties", {}).items():
            if prop in _ENVELOPE:
                continue
            if prop == "client_id":
                params.append(Param(prop, "", None, "self._caller.client_id"))
                continue
            annotation = self._use(self.types.annotation(prop_schema, self.imports))
            default = repr(prop_schema["default"]) if "default" in prop_schema else None
            params.append(Param(prop, annotation, default, prop))
        values = ", ".join(f"{p.name!r}: {p.value}" for p in params)
        sig = self.signature(placement, params)
        doc = MESSAGE_DOCS.get(wire_type, message.doc)
        doc += f"\n\nSent as igni's ``{wire_type}`` message."
        if reply:
            result = self._use(self.types.class_name(self.contract.message_def(reply)))
            doc += f" igni answers with ``{reply}``."
            out = ["", f"    async def {placement.name}({sig}) -> {result}:"]
            out += docstring(doc, "        ")
            out.append(
                f"        return await self._caller.request({cls}, {{{values}}}, "
                f"{self.adapter_name(wire_type)})"
            )
            return out
        out = ["", f"    async def {placement.name}({sig}) -> None:"]
        out += docstring(doc, "        ")
        out.append(f"        await self._caller.send({cls}, {{{values}}})")
        return out

    def _namespace(self, group: str, members: list[Placement]) -> list[str]:
        cls = class_for_group(group)
        doc = NAMESPACES.get(group)
        if doc is None:
            raise ContractError(f"namespace {group} has no description in NAMESPACES")
        out = ["", "", f"class {cls}:"]
        doc_text = doc
        if group in HAND_WRITTEN_NAMESPACES:
            doc_text += (
                f"\n\nThe generated base of ``{HAND_WRITTEN_NAMESPACES[group]}``, "
                f"which is ``{group}``."
            )
        out += docstring(doc_text, "    ")
        out += [
            "",
            "    def __init__(self, caller: Caller) -> None:",
            "        self._caller = caller",
        ]
        for placement in sorted(members, key=lambda p: p.name):
            out += self._method(placement)
        if any(p.name == "list" for p in members):
            out = self._builtin_list(out)
        return out

    def _builtin_list(self, lines: list[str]) -> list[str]:
        """In a class with a method named ``list``, ``list[...]`` in a signature is that method."""
        self.builtins = True
        return [
            re.sub(r"(?<![\w.])list\[", "builtins.list[", line)
            if line.lstrip().startswith(("def ", "async def "))
            else line
            for line in lines
        ]

    def _owner(
        self, owner: str, members: list[Placement], groups: dict[str, list[Placement]]
    ) -> list[str]:
        cls = class_for_group(owner)
        doc = OWNER_DOCS[owner]
        out = ["", "", f"class {cls}:"]
        out += docstring(doc, "    ")
        namespaces = sorted(g for g in groups if g.startswith(owner + "."))
        out += [""]
        for group in namespaces:
            if group in HAND_WRITTEN_NAMESPACES:
                continue
            attr = group.split(".", 1)[1]
            out.append(f"    {attr}: {class_for_group(group)}")
            ns_doc = NAMESPACES[group]
            out += docstring(ns_doc, "    ")
        out += [
            "",
            "    def __init__(self, caller: Caller) -> None:",
            "        self._caller = caller",
        ]
        for group in namespaces:
            if group in HAND_WRITTEN_NAMESPACES:
                continue
            attr = group.split(".", 1)[1]
            out.append(f"        self.{attr} = {class_for_group(group)}(caller)")
        for placement in sorted(members, key=lambda p: p.name):
            out += self._method(placement)
        return out


#: What a method reached only by some connections says about it.
ACCESS_NOTES = {
    "approver": (
        "Access: ``approver``. Through Fleet's gateway every connection stands as igni's "
        "window and makes this call. On the desktop, a program needs an approver token the "
        "window minted (``Local(approver_token=...)``); with the lockfile's token it gets "
        "``AccessRefused``."
    ),
    "window": (
        "Access: ``window``. Through Fleet's gateway every connection stands as igni's "
        "window and makes this call. On the desktop only the app's own window does: a "
        "program — with the lockfile's token or an approver token — gets ``AccessRefused``."
    ),
}

OWNER_DOCS = {
    "igni": "The methods igni answers for igni as a whole; `IgniClient` is one.",
    "session": "The methods igni answers for one session; `Session` is one.",
}

#: Fuller docstrings than the contract's for the messages sent as methods.
MESSAGE_DOCS = {
    "command": (
        "Run a slash command in this session, as typed in igni's composer: ``/help``, "
        "``/compact``, ``/model``.\n\n``text`` is the command line, its leading ``/`` "
        "optional. Returns igni's ``command_result``: its ``kind`` (``markdown``, ``info``, "
        "``error`` or ``action``), the ``content`` to show and the ``action`` the command "
        "asks a client to take. The commands that switch approvals off, change what igni "
        "loads or whom it signs in to (``/bypass``, ``/accept``, ``/plugin``, ``/eject``, "
        "``/login``, ``/logout``) answer an ``error`` to anything but igni's window."
    ),
    "cancel_login": (
        "Cancel the sign-in to igni server that ``igni.auth.login()`` started.\n\n"
        "igni answers nothing; the sign-in's ``login_result`` push says it ended."
    ),
    "typing": (
        "Show what this client is typing to every other client of this session.\n\n"
        "``text`` is the whole draft, not a change to it; empty clears it. igni relays it "
        "to every client attached, this one included, as a ``Typing`` event."
    ),
}


# ── The README's API reference ────────────────────────────────────────


class ReferenceGenerator:
    """The README's API reference: every namespace and method, from the contract."""

    def __init__(self, plan: Plan, api: ApiGenerator) -> None:
        self.plan = plan
        self.api = api
        self.contract = plan.contract

    def generate(self) -> str:
        groups: dict[str, list[Placement]] = {}
        for placement in self.plan.placements.values():
            groups.setdefault(placement.group, []).append(placement)
        for name, (_, path) in MESSAGE_METHODS.items():
            placement = Placement.of(name, path)
            groups.setdefault(placement.group, []).append(placement)
        order = sorted(groups, key=lambda g: (g.split(".")[0] != "igni", g.count("."), g))
        out = [
            README_START,
            "",
            "<!-- Generated by tools/client_codegen.py from contracts/rpc-contract.json. "
            "Do not edit by hand: run `make client-api`. -->",
            "",
        ]
        if self.contract.access:
            out += ["#### Who may call what", "", self._md(self.contract.access), ""]
        out.append("| Namespace | Methods |")
        out.append("|---|---|")
        for group in order:
            names = ", ".join(f"`{p.name}`" for p in sorted(groups[group], key=lambda p: p.name))
            out.append(f"| [`{group}`](#{self.anchor(group)}) | {names} |")
        out.append("")
        for group in order:
            out += self._group(group, groups[group])
        out += self._not_for_clients()
        out.append(README_END)
        return "\n".join(out)

    @staticmethod
    def anchor(group: str) -> str:
        return re.sub(r"[^a-z0-9 -]", "", group.lower()).replace(" ", "-")

    def _group(self, group: str, members: list[Placement]) -> list[str]:
        title = group
        doc = NAMESPACES.get(group) or OWNER_DOCS[group].replace("`", "`")
        out = [f"#### {title}", "", doc, ""]
        for placement in sorted(members, key=lambda p: p.name):
            out += self._method(placement)
        return out

    def _method(self, placement: Placement) -> list[str]:
        if placement.wire in MESSAGE_METHODS:
            return self._message(placement)
        method = self.contract.methods[placement.wire]
        params, _ = self.api.params(placement)
        sig = self.api.signature(placement, params).removeprefix("self").lstrip(", ")
        result = self.api.result_type(placement.wire)
        if placement.wire in FOLLOWED:
            returns = f"Call[{result}, {self.api.event_alias(placement.wire)}]"
        else:
            returns = result
        prefix = "" if placement.wire in FOLLOWED else "await "
        out = [
            "<details>",
            f"<summary><code>{prefix}{placement.path}({self._html(sig)})</code> → "
            f"<code>{self._html(returns)}</code></summary>",
            "",
            f"Wire method `{placement.wire}` · access `{method.access}`"
            + (f" · streams {self._streams(method.streams)}" if method.streams else ""),
            "",
            self._md(method.doc),
            "",
        ]
        if placement.wire in FOLLOWED:
            out += [f"Followed: {self._md(FOLLOWED[placement.wire])}", ""]
        elif placement.wire in UNFOLLOWED:
            out += [f"Not followed: {self._md(UNFOLLOWED[placement.wire])}", ""]
        if method.access != "client":
            out += [self._md(ACCESS_NOTES[method.access]), ""]
        out += ["</details>", ""]
        return out

    def _message(self, placement: Placement) -> list[str]:
        reply, _ = MESSAGE_METHODS[placement.wire]
        def_name = self.contract.message_def(placement.wire)
        schema = self.contract.defs[def_name]
        params = [
            p for p in schema.get("properties", {}) if p not in _ENVELOPE and p != "client_id"
        ]
        returns = self.plan.types.class_name(self.contract.message_def(reply)) if reply else "None"
        doc = MESSAGE_DOCS.get(placement.wire, self.contract.messages[placement.wire].doc)
        return [
            "<details>",
            f"<summary><code>await {placement.path}({', '.join(params)})</code> → "
            f"<code>{returns}</code></summary>",
            "",
            f"Message `{placement.wire}`" + (f", answered by `{reply}`" if reply else ""),
            "",
            self._md(doc),
            "",
            "</details>",
            "",
        ]

    def _not_for_clients(self) -> list[str]:
        out = ["#### Not for clients", "", "| Wire method | Why |", "|---|---|"]
        for wire, reason in sorted(NOT_FOR_CLIENTS.items()):
            out.append(f"| `{wire}` | {reason} |")
        out += ["", "| Message | Why a client does not send it |", "|---|---|"]
        for wire, reason in sorted(MESSAGES_NOT_SENT.items()):
            out.append(f"| `{wire}` | {reason} |")
        out.append("")
        return out

    @staticmethod
    def _streams(streams: list[str]) -> str:
        return ", ".join(f"`{s.removeprefix(PUSH_PREFIX)}`" for s in streams)

    @staticmethod
    def _html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _md(text: str) -> str:
        """igni-core's reStructuredText-flavoured docstrings, as Markdown."""
        text = re.sub(r":(?:class|meth|func|attr|data|mod):`~?([^`]+)`", r"`\1`", text)
        return text.replace("``", "`")


# ── Writing and checking ──────────────────────────────────────────────


def ruff_format(text: str, path: Path) -> str:
    """``text`` as the package's ``ruff`` leaves it: imports sorted, then formatted."""
    for command in (["check", "--select", "I", "--fix", "--quiet"], ["format"]):
        done = subprocess.run(  # noqa: S603 — this interpreter's ruff, on our own output
            [sys.executable, "-m", "ruff", *command, "--stdin-filename", str(path), "-"],
            input=text,
            capture_output=True,
            text=True,
            check=False,
            cwd=path.parent,
        )
        if done.returncode != 0:
            raise ContractError(f"ruff could not format the generated {path.name}: {done.stderr}")
        text = done.stdout
    return text


class ClientApi:
    """The generated files, and whether what is on disk is current."""

    def __init__(self, root: Path = ROOT, contract: RpcContract | None = None) -> None:
        self.root = root
        self.contract = contract or RpcContract.read(root / CONTRACT_FILE.relative_to(ROOT))

    def outputs(self) -> dict[Path, str]:
        plan = Plan(self.contract)
        models = ModelsGenerator(plan).generate()
        api_gen = ApiGenerator(plan)
        api = api_gen.generate()
        reference = ReferenceGenerator(plan, api_gen).generate()
        readme_path = self.root / README
        readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
        return {
            self.root / MODELS_OUTPUT: ruff_format(models, self.root / MODELS_OUTPUT),
            self.root / API_OUTPUT: ruff_format(api, self.root / API_OUTPUT),
            readme_path: self.splice(readme, reference),
        }

    @staticmethod
    def splice(readme: str, reference: str) -> str:
        """``readme`` with its API reference replaced by ``reference``."""
        start, end = readme.find(README_START), readme.find(README_END)
        if start < 0 or end < start:
            raise ContractError(
                f"{README} has no {README_START} … {README_END} section to write the reference into"
            )
        return readme[:start] + reference + readme[end + len(README_END) :]

    def write(self) -> list[Path]:
        written: list[Path] = []
        for path, text in self.outputs().items():
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8")
                written.append(path)
        return written

    def stale(self) -> list[Path]:
        return [
            path
            for path, text in self.outputs().items()
            if not path.exists() or path.read_text(encoding="utf-8") != text
        ]


def main() -> int:
    for path in ClientApi().write():
        print("wrote", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "API_OUTPUT",
    "MODELS_OUTPUT",
    "README",
    "ApiGenerator",
    "ClientApi",
    "ContractError",
    "ModelsGenerator",
    "Plan",
    "ReferenceGenerator",
]

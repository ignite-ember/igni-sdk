"""Generate ``@ignite-ember/igni-client``'s TypeScript models and methods from the RPC contract.

This is the TypeScript half of :mod:`tools.client_codegen`. The Python client's
models and methods are generated from ``contracts/rpc-contract.json``; so are
the TypeScript client's, from the same file and the same :class:`~tools.client_plan.Plan`,
so the two clients cannot drift on the wire. The precedent is
``tools/host_codegen.py``, which already emits TypeScript (the extension bridge's
host model) beside Python.

It writes

* ``packages/igni-client/src/models.generated.ts`` — an ``interface`` for every
  type the contract defines, a string-literal union for every enum, a push
  interface per typed channel, the discriminated unions, and the runtime sets
  of which wire ``type``\\ s and push channels this client knows; and
* ``packages/igni-client/src/api.generated.ts`` — every method a client calls,
  as a typed method on a per-namespace class, and the ``METHODS`` table that
  says, per method, who may call it, how igni answers and what it streams.

Neither file is edited by hand. ``tests/test_the_ts_client_api_is_generated.py``
regenerates both in memory and fails when what is checked in differs;
``make client-api`` writes them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.client_contract import Correlation, RpcContract
from tools.client_names import (
    ACCESS_NOTES,
    CLASS_NAMES,
    FOLLOWED,
    MESSAGE_DOCS,
    MESSAGE_METHODS,
    NAMESPACES,
    NOT_FOR_CLIENTS,
    OWN_SESSION_ARG,
    OWNER_DOCS,
    SELF_MADE,
    UNION_NAMES,
    WAITING_ACCESS_NOTES,
)
from tools.client_plan import Placement, Plan, class_for_group, push_class
from tools.client_python import ENVELOPE, ContractError, pascal

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path("packages/igni-client")
MODELS_OUTPUT = PACKAGE / "src/models.generated.ts"
API_OUTPUT = PACKAGE / "src/api.generated.ts"

_BANNER = (
    "GENERATED from igni-core's RPC contract (version {version}) by igni-sdk's "
    "tools/client_ts.py — do not edit. Run `make client-api` after refreshing "
    "contracts/rpc-contract.json."
)

#: The JSON types igni-core's ``JsonValue`` def allows: any JSON value.
_JSON_TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})

#: What a JSON scalar type is in TypeScript.
_SCALARS: dict[str, str] = {
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "null": "null",
}

#: Words a generated parameter may not be named in TypeScript; one that would
#: be is suffixed with ``_`` and its wire name kept in the arguments object.
_RESERVED = frozenset(
    {
        "default",
        "function",
        "class",
        "new",
        "delete",
        "typeof",
        "instanceof",
        "void",
        "return",
        "in",
        "of",
        "for",
        "while",
        "const",
        "let",
        "var",
        "case",
        "switch",
        "this",
        "super",
        "extends",
        "import",
        "export",
        "enum",
        "yield",
        "await",
    }
)


def param_name(prop: str) -> str:
    """The TypeScript name of a parameter for the wire field ``prop``."""
    return f"{prop}_" if prop in _RESERVED else prop


def _literal(value: Any) -> str:
    """A JSON value as a TypeScript literal type."""
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return repr(value)


def _quote(text: str) -> str:
    """``text`` as a double-quoted TypeScript string literal."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def jsdoc(text: str, indent: str) -> list[str]:
    """``text`` as a JSDoc comment at ``indent``; empty for empty text."""
    body = text.strip()
    if not body:
        return []
    safe = [line.replace("*/", "*\\/").rstrip() for line in body.splitlines()]
    if len(safe) == 1:
        return [f"{indent}/** {safe[0]} */"]
    out = [f"{indent}/**"]
    out += [f"{indent} * {line}".rstrip() for line in safe]
    out.append(f"{indent} */")
    return out


class TsTypes:
    """JSON Schema → TypeScript annotations, over the contract's defs.

    A parallel of :class:`tools.client_types.Types`, emitting TypeScript where
    that emits Python. Named unions are recorded as they are met, under the
    same names in :data:`tools.client_names.UNION_NAMES`, so the two clients
    name the same unions.
    """

    def __init__(self, contract: RpcContract) -> None:
        self.contract = contract
        #: Alias → (member class names, the property that tells them apart).
        self.unions: dict[str, tuple[list[str], str]] = {}
        #: Model class names an annotation named, for the importing module.
        self.referenced: set[str] = set()

    def class_name(self, def_name: str) -> str:
        return CLASS_NAMES.get(def_name, def_name)

    def is_enum(self, def_name: str) -> bool:
        schema = self.contract.defs[def_name]
        return "enum" in schema and "properties" not in schema

    def is_json_value(self, schema: dict[str, Any]) -> bool:
        return self.contract.ref_name(schema) == "JsonValue" or (
            isinstance(schema.get("type"), list) and set(schema["type"]) == _JSON_TYPES
        )

    def annotation(self, schema: dict[str, Any]) -> str:
        """The TypeScript type ``schema`` describes."""
        if not schema or self.is_json_value(schema):
            self.referenced.add("JsonValue")
            return "JsonValue"
        ref = self.contract.ref_name(schema)
        if ref is not None:
            name = self.class_name(ref)
            self.referenced.add(name)
            return name
        if "const" in schema:
            return _literal(schema["const"])
        if "enum" in schema:
            return " | ".join(_literal(v) for v in schema["enum"])
        if "anyOf" in schema or "oneOf" in schema:
            members = schema.get("anyOf") or schema["oneOf"]
            told_by = (schema.get("discriminator") or {}).get("propertyName")
            return self._union(members, told_by)
        kind = schema.get("type")
        if isinstance(kind, list):
            return self._union([{"type": k} for k in kind])
        if not isinstance(kind, str):
            raise ContractError(f"a schema this generator cannot read: {schema}")
        if kind in _SCALARS:
            return _SCALARS[kind]
        if kind == "string":
            return "string"
        if kind == "array":
            return self._array(schema)
        if kind == "object":
            return self._object(schema)
        raise ContractError(f"a schema this generator cannot read: {schema}")

    def _array(self, schema: dict[str, Any]) -> str:
        if "prefixItems" in schema:
            items = [self.annotation(s) for s in schema["prefixItems"]]
            return "[" + ", ".join(items) + "]"
        inner = self.annotation(schema.get("items", {}))
        return f"Array<{inner}>" if " " in inner or "|" in inner else f"{inner}[]"

    def _object(self, schema: dict[str, Any]) -> str:
        if "properties" in schema:
            raise ContractError(f"an object defined in place, not as a def: {schema}")
        extra = schema.get("additionalProperties", {})
        value = self.annotation(extra if isinstance(extra, dict) else {})
        return f"Record<string, {value}>"

    def _union(self, members: list[dict[str, Any]], told_by: str | None = None) -> str:
        nullable = any(m.get("type") == "null" for m in members)
        rest = [m for m in members if m.get("type") != "null"]
        refs = [self.contract.ref_name(m) for m in rest]
        if len(rest) > 1 and all(r is not None for r in refs):
            names = [r for r in refs if r is not None]
            body = self._named_union(names, told_by)
        else:
            parts: list[str] = []
            for member in rest:
                rendered = self.annotation(member)
                if rendered not in parts:
                    parts.append(rendered)
            body = " | ".join(parts)
        if nullable:
            return f"{body} | null" if body else "null"
        return body

    def _named_union(self, names: list[str], told_by: str | None) -> str:
        alias = UNION_NAMES.get(frozenset(names))
        if alias is None:
            raise ContractError(
                f"a union of {sorted(names)} has no name; add one to UNION_NAMES "
                "in tools/client_names.py"
            )
        self.unions[alias] = (
            [self.class_name(n) for n in names],
            told_by or self._discriminator(names) or "",
        )
        for name in names:
            self.referenced.add(self.class_name(name))
        self.referenced.add(alias)
        return alias

    def _discriminator(self, names: list[str]) -> str | None:
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


class TsModelsGenerator:
    """``models.generated.ts``: every def a client sends or reads, as a TypeScript type."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.contract = plan.contract
        self.types = TsTypes(self.contract)
        self.messages = plan.message_of_def()

    def generate(self) -> str:
        names = sorted(self.plan.defs_in | self.plan.defs_out)
        enums = [n for n in names if self.types.is_enum(n)]
        classes = [n for n in names if not self.types.is_enum(n)]
        body: list[str] = []
        for name in enums:
            body += self._enum(name)
        for name in classes:
            body += self._interface(name)
        for channel in sorted(self.contract.push_channels):
            body += self._push(channel)
        # Name a method's result union even when no model uses it, as Python does.
        for wire in self.plan.placements:
            self.types.annotation(self.contract.methods[wire].result)
        unions: list[str] = []
        for alias in sorted(self.types.unions):
            unions += self._union(alias)
        return "\n".join([*self._head(), *body, *unions, *self._tables()]) + "\n"

    def _head(self) -> list[str]:
        return [
            f"// {_BANNER.format(version=self.contract.version)}",
            "//",
            "// Every type igni-client sends or reads, as igni-core's RPC contract",
            "// defines it. Messages a client reads keep a field a newer igni adds.",
            "",
            "/** Any JSON value. */",
            "export type JsonValue =",
            "  | null",
            "  | boolean",
            "  | number",
            "  | string",
            "  | JsonValue[]",
            "  | { [key: string]: JsonValue };",
            "",
        ]

    def _enum(self, name: str) -> list[str]:
        schema = self.contract.defs[name]
        values = " | ".join(_literal(v) for v in schema["enum"])
        described = schema.get("description") or f"The values of {name}."
        return ["", *jsdoc(described, ""), f"export type {self.types.class_name(name)} = {values};"]

    def _interface(self, name: str) -> list[str]:
        schema = self.contract.defs[name]
        props: dict[str, Any] = schema.get("properties", {})
        required = set(schema.get("required", []))
        cls = self.types.class_name(name)
        wire = self.messages.get(name)
        doc = (
            schema.get("description")
            or (self.contract.messages[wire].doc if wire else "")
            or f"{schema.get('title', name)}."
        )
        if wire is not None:
            doc = f"{doc.rstrip()}\n\nOn the wire: `{wire}`."
        out = ["", *jsdoc(doc, ""), f"export interface {cls} {{"]
        for prop, prop_schema in props.items():
            out += self._field(prop, prop_schema, prop in required)
        out.append("}")
        return out

    def _field(self, prop: str, schema: dict[str, Any], required: bool) -> list[str]:
        annotation = self.types.annotation(schema)
        optional = "" if required else "?"
        out = jsdoc(schema.get("description", ""), "  ")
        out.append(f"  {_member(prop)}{optional}: {annotation};")
        return out

    def _push(self, channel: str) -> list[str]:
        spec = self.contract.push_channels[channel]
        payload = self.types.annotation(spec.schema_)
        doc = spec.doc or f"A push on `{channel}`."
        doc = f"{doc.rstrip()}\n\nOn the wire: `push_notification` on the channel `{channel}`."
        return [
            "",
            *jsdoc(doc, ""),
            f'export interface {push_class(channel)} extends Omit<PushNotification, "channel" | "payload"> {{',
            f"  channel: {_quote(channel)};",
            f"  payload: {payload};",
            "}",
        ]

    def _union(self, alias: str) -> list[str]:
        members, told_by = self.types.unions[alias]
        kinds = len(members)
        note = (
            f"One of {kinds} kinds, told apart by `{told_by}`."
            if told_by
            else f"One of {kinds} kinds. Nothing in the contract tells them apart."
        )
        return ["", *jsdoc(note, ""), f"export type {alias} = {' | '.join(members)};"]

    def _tables(self) -> list[str]:
        events: list[str] = []
        frames: list[str] = []
        read_classes: list[str] = []
        for wire_type in sorted(self.contract.messages):
            message = self.contract.messages[wire_type]
            cls = self.types.class_name(self.contract.message_def(wire_type))
            if message.direction in ("to_client", "both"):
                events.append(f"  {_quote(wire_type)},")
                if cls not in read_classes:
                    read_classes.append(cls)
            if message.direction in ("to_igni", "both"):
                frames.append(f"  {_quote(wire_type)},")
        pushes = [f"  {_quote(c)}," for c in sorted(self.contract.push_channels)]
        members = " | ".join(sorted(read_classes))
        return [
            "",
            "/** Every message igni may send, by its `type` discriminant. */",
            f"export type ServerEvent = {members};",
            "",
            "/** Every wire `type` igni sends that this client knows. */",
            "export const EVENT_TYPES: ReadonlySet<string> = new Set([",
            *events,
            "]);",
            "",
            "/** Every wire `type` a client sends. */",
            "export const FRAME_TYPES: ReadonlySet<string> = new Set([",
            *frames,
            "]);",
            "",
            "/** Every push channel the contract types. */",
            "export const PUSH_CHANNELS: ReadonlySet<string> = new Set([",
            *pushes,
            "]);",
        ]


def _member(prop: str) -> str:
    """A property name as an interface member: quoted when it is not an identifier."""
    if prop.isidentifier():
        return prop
    return _quote(prop)


class TsApiGenerator:
    """``api.generated.ts``: every method a client calls, on the class its placement names."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.contract = plan.contract
        self.types = TsTypes(self.contract)

    def generate(self) -> str:
        groups = self.plan.groups()
        events = self._event_aliases()
        classes: list[str] = []
        for group in sorted(groups, key=lambda g: (g.count("."), g)):
            if "." in group:
                classes += self._namespace(group, groups[group])
        for owner in ("igni", "session"):
            classes += self._owner(owner, groups.get(owner, []), groups)
        table = self._table()
        return "\n".join([*self._head(), *events, *table, *classes]) + "\n"

    def _head(self) -> list[str]:
        # Collected after the body is generated; placeholder replaced in generate order
        # is awkward, so collect references first by generating the body into memory.
        return []  # filled by _assemble

    def _assemble(self, body: list[str]) -> str:
        imports = sorted(self.types.referenced)
        head = [
            f"// {_BANNER.format(version=self.contract.version)}",
            "//",
            "// Every method a client calls, typed, by namespace. `IgniApi` is what",
            "// `IgniClient` adds for igni as a whole, and `SessionApi` what `Session`",
            "// adds for one session. A method that streams returns a `Call`.",
            "",
            'import type { Caller } from "./calls.js";',
            'import { Call } from "./calls.js";',
            'import type { Correlation, MethodSpec } from "./methodSpec.js";',
        ]
        if imports:
            head.append("import type {")
            head += [f"  {name}," for name in imports]
            head.append('} from "./models.generated.js";')
        head.append("")
        return "\n".join([*head, *body]) + "\n"

    def _event_aliases(self) -> list[str]:
        out = ["", "// What each followed method causes."]
        for wire in sorted(FOLLOWED):
            classes = self.plan.event_classes(wire)
            for name in classes:
                self.types.referenced.add(name)
            out.append(f"export type {pascal(wire)}Event = {' | '.join(classes)};")
        return out

    @staticmethod
    def _correlation(correlation: Correlation | None) -> str:
        if correlation is None:
            return "null"
        parts = [f"by: {_quote(correlation.by)}"]
        if correlation.source:
            parts.append(f"source: {_quote(correlation.source)}")
        if correlation.equals:
            parts.append(f"equals: {_quote(correlation.equals)}")
        return "{ " + ", ".join(parts) + " }"

    def _table(self) -> list[str]:
        out = [
            "",
            "/**",
            " * Every method a client calls, by wire name: who may call it, how igni",
            " * answers it, how long it takes, and what it streams.",
            " */",
            "export const METHODS: Record<string, MethodSpec> = {",
        ]
        for wire in sorted(self.plan.placements):
            m = self.contract.methods[wire]
            placement = self.plan.placements[wire]
            streams = ", ".join(_quote(s) for s in m.streams)
            may = ", ".join(_quote(s) for s in m.may_stream)
            timeout = "null" if m.timeout_seconds is None else str(m.timeout_seconds)
            out.append(
                f"  {_quote(wire)}: {{ wire: {_quote(wire)}, python: {_quote(placement.path)}, "
                f"scope: {_quote(m.scope)}, access: {_quote(m.access)}, reply: {_quote(m.reply)}, "
                f"streams: [{streams}], mayStream: [{may}], duration: {_quote(m.duration)}, "
                f"timeoutSeconds: {timeout}, correlate: {self._correlation(m.correlate)}, "
                f"followed: {str(wire in FOLLOWED).lower()} }},"
            )
        out.append("};")
        out += [
            "",
            "/** igni's methods a client never sends: an extension page's and the platform's. */",
            "export const NOT_FOR_CLIENTS: ReadonlySet<string> = new Set([",
        ]
        out += [f"  {_quote(w)}," for w in sorted(NOT_FOR_CLIENTS)]
        out.append("]);")
        return out

    def _namespace(self, group: str, members: list[Placement]) -> list[str]:
        cls = class_for_group(group)
        doc = NAMESPACES.get(group)
        if doc is None:
            raise ContractError(f"namespace {group} has no description in NAMESPACES")
        out = ["", *jsdoc(doc, ""), f"export class {cls} {{"]
        out.append("  constructor(readonly caller: Caller) {}")
        for placement in sorted(members, key=lambda p: p.name):
            out += self._method(placement)
        out.append("}")
        return out

    def _owner(
        self, owner: str, members: list[Placement], groups: dict[str, list[Placement]]
    ) -> list[str]:
        cls = class_for_group(owner)
        namespaces = [g for g in sorted(groups) if g.startswith(owner + ".")]
        out = ["", *jsdoc(OWNER_DOCS[owner], ""), f"export class {cls} {{"]
        for group in namespaces:
            attr = group.split(".", 1)[1]
            out += jsdoc(NAMESPACES[group], "  ")
            out.append(f"  readonly {attr}: {class_for_group(group)};")
        out.append("")
        out.append("  constructor(readonly caller: Caller) {")
        for group in namespaces:
            attr = group.split(".", 1)[1]
            out.append(f"    this.{attr} = new {class_for_group(group)}(caller);")
        out.append("  }")
        for placement in sorted(members, key=lambda p: p.name):
            out += self._method(placement)
        out.append("}")
        return out

    def _method(self, placement: Placement) -> list[str]:
        if placement.wire in MESSAGE_METHODS:
            return self._message_method(placement)
        method = self.contract.methods[placement.wire]
        params, values, model_props = self._params(placement)
        result = self.types.annotation(method.result)
        doc = method.doc
        if placement.wire in FOLLOWED:
            doc += "\n\n" + FOLLOWED[placement.wire]
        if method.access != "client":
            doc += "\n\n" + ACCESS_NOTES[method.access]
        if placement.wire in WAITING_ACCESS_NOTES:
            doc += "\n\n" + WAITING_ACCESS_NOTES[placement.wire]
        signature = ", ".join(params)
        values_obj = "{ " + ", ".join(values) + " }" if values else "{}"
        out = ["", *jsdoc(doc, "  ")]
        if placement.wire in FOLLOWED:
            event = f"{pascal(placement.wire)}Event"
            out.append(f"  {placement.name}({signature}): Call<{result}, {event}> {{")
            out.append(
                f"    return this.caller.follow<{result}, {event}>("
                f"{_quote(placement.wire)}, {values_obj});"
            )
            out.append("  }")
            return out
        out.append(f"  {placement.name}({signature}): Promise<{result}> {{")
        out.append(f"    return this.caller.rpc<{result}>({_quote(placement.wire)}, {values_obj});")
        out.append("  }")
        return out

    def _params(self, placement: Placement) -> tuple[list[str], list[str], set[str]]:
        """A method's TypeScript parameters, and the arguments object it builds.

        Required parameters come first, then optional ones, as TypeScript needs.
        A ``session_id`` the session owns, a ``client_id`` and a self-made id are
        filled in by the client and left out of the signature.
        """
        method = self.contract.methods[placement.wire]
        args_def = self.contract.ref_name(method.args)
        if args_def is None:
            raise ContractError(f"{placement.wire}: args is not a def")
        schema = self.contract.defs[args_def]
        required = set(schema.get("required", []))
        made = SELF_MADE.get(placement.wire, {})
        required_params: list[str] = []
        optional_params: list[str] = []
        values: list[str] = []
        for prop, prop_schema in schema.get("properties", {}).items():
            if (
                placement.owner == "session"
                and placement.wire in OWN_SESSION_ARG
                and prop == "session_id"
            ):
                values.append(f"{_member(prop)}: this.caller.sessionId")
                continue
            annotation = self.types.annotation(prop_schema)
            name = param_name(prop)
            is_required = prop in required and "default" not in prop_schema
            if prop in made:
                values.append(f"{_member(prop)}: {name} ?? {_self_made(made[prop])}")
                optional_params.append(f"{name}?: {annotation}")
                continue
            values.append(f"{_member(prop)}: {name}")
            if is_required:
                required_params.append(f"{name}: {annotation}")
            else:
                optional_params.append(f"{name}?: {annotation}")
        return [*required_params, *optional_params], values, set()

    def _message_method(self, placement: Placement) -> list[str]:
        wire_type = placement.wire
        reply, _ = MESSAGE_METHODS[wire_type]
        message = self.contract.messages[wire_type]
        def_name = self.contract.message_def(wire_type)
        schema = self.contract.defs[def_name]
        required = set(schema.get("required", []))
        required_params: list[str] = []
        optional_params: list[str] = []
        values: list[str] = []
        for prop, prop_schema in schema.get("properties", {}).items():
            if prop in ENVELOPE:
                continue
            if prop == "client_id":
                values.append(f"{_member(prop)}: this.caller.clientId")
                continue
            annotation = self.types.annotation(prop_schema)
            name = param_name(prop)
            values.append(f"{_member(prop)}: {name}")
            if prop in required and "default" not in prop_schema:
                required_params.append(f"{name}: {annotation}")
            else:
                optional_params.append(f"{name}?: {annotation}")
        signature = ", ".join([*required_params, *optional_params])
        values_obj = "{ " + ", ".join(values) + " }" if values else "{}"
        doc = MESSAGE_DOCS.get(wire_type, message.doc)
        doc += f"\n\nSent as igni's `{wire_type}` message."
        out = ["", *jsdoc(doc, "  ")]
        if reply:
            result = self.types.annotation(self.contract.messages[reply].schema_)
            doc += f" igni answers with `{reply}`."
            out = ["", *jsdoc(doc, "  ")]
            out.append(f"  {placement.name}({signature}): Promise<{result}> {{")
            out.append(
                f"    return this.caller.request<{result}>({_quote(wire_type)}, {values_obj});"
            )
            out.append("  }")
            return out
        out.append(f"  {placement.name}({signature}): Promise<void> {{")
        out.append(f"    return this.caller.sendMessage({_quote(wire_type)}, {values_obj});")
        out.append("  }")
        return out


def _self_made(expression: str) -> str:
    """``self._caller.new_id('run')`` → ``this.caller.newId("run")``."""
    inner = expression.split("(", 1)[1].rstrip(")")
    prefix = inner.strip().strip("'\"")
    return f'this.caller.newId("{prefix}")'


def models_ts(plan: Plan) -> str:
    return TsModelsGenerator(plan).generate()


def api_ts(plan: Plan) -> str:
    generator = TsApiGenerator(plan)
    body = generator.generate()
    return generator._assemble(body.splitlines())


def outputs(root: Path = ROOT, contract: RpcContract | None = None) -> dict[Path, str]:
    """The two generated TypeScript files, by path."""
    from tools.client_contract import CONTRACT_FILE

    contract = contract or RpcContract.read(root / CONTRACT_FILE.relative_to(ROOT))
    plan = Plan(contract)
    return {root / MODELS_OUTPUT: models_ts(plan), root / API_OUTPUT: api_ts(plan)}


def stale(root: Path = ROOT) -> list[Path]:
    return [
        path
        for path, text in outputs(root).items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]


def write(root: Path = ROOT) -> list[Path]:
    written: list[Path] = []
    for path, text in outputs(root).items():
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            written.append(path)
    return written


def main() -> int:
    for path in write(ROOT):
        print("wrote", path.relative_to(ROOT))
    return 0


__all__ = [
    "API_OUTPUT",
    "MODELS_OUTPUT",
    "TsApiGenerator",
    "TsModelsGenerator",
    "TsTypes",
    "api_ts",
    "models_ts",
    "main",
    "outputs",
    "stale",
    "write",
]


if __name__ == "__main__":
    raise SystemExit(main())

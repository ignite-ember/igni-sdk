"""Generate both SDKs' ``host`` objects from igni-core's host schema.

``docs/HOST_OBJECT_MODEL.md`` (igni-core): "One schema, two SDKs." igni-core
describes the model once and publishes it as ``docs/host-schema.json``; this
repository keeps a copy in ``contracts/host-schema.json``, and this writes

* ``packages/igni-extension/src/igni_extension/host_model.py`` — the
  Python SDK's ``ext.host``: a typed Pydantic model per value type and a
  class per object, whose properties, signals and methods travel over
  the extension process's loopback socket;
* ``packages/extension-bridge/src/hostModel.generated.ts`` — the same
  for a page, as ``bridge.host``, over the bridge.

Neither file is edited by hand. ``tests/test_the_host_sdks_are_generated.py``
regenerates both in memory and fails when what is checked in differs. Run
``make host-sdks`` after refreshing the copy (``make contracts``).

Names are the schema's in both languages — ``bridge.host.chat.run_completed``,
not ``runCompleted`` — so a member is spelled one way everywhere it is
written down.
"""

from __future__ import annotations

from pathlib import Path

from tools.host_spec import HostSchema, MethodSpec, ObjectSpec, TypeExpr

#: igni-core's host schema, as this repository has it.
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "contracts" / "host-schema.json"
HOST_SCHEMA = HostSchema.model_validate_json(SCHEMA_FILE.read_text(encoding="utf-8"))

#: Where the generated files live, relative to the repository root.
PYTHON_OUTPUT = Path("packages/igni-extension/src/igni_extension/host_model.py")
TYPESCRIPT_OUTPUT = Path("packages/extension-bridge/src/hostModel.generated.ts")

_BANNER = (
    "GENERATED from the igni host schema {version} by "
    "igni-sdk's tools/host_codegen.py — do not edit. "
    "Run `make host-sdks` after refreshing contracts/host-schema.json."
)

#: What a parameter the schema does not describe is. The schema owns
#: the shape of the model; these are the words for the parameters it
#: leaves to the SDKs, taken from igni-core's own implementation.
#:
#: The key is the object path, the method's name and the parameter's
#: name — the schema's own names, in one place. A parameter the schema
#: does describe is documented from the schema; this table is for the
#: ones it leaves out, and a parameter in neither is left undocumented
#: rather than given a meaning the contract does not have.
PARAM_MEANINGS: dict[tuple[str, str, str], str] = {
    ("", "decide", "questions"): ("The questions to ask, each with its own text and answer type."),
    ("", "decide_batch", "contexts"): "The contexts to ask about, one decision each, in order.",
    ("", "decide_batch", "questions"): "The questions to ask of every context.",
    ("app", "set_verbose", "on"): "Whether routing detail is shown.",
    ("app", "set_output_style", "name"): "The output style to switch to, by its name.",
    ("app.state", "get", "key"): "The key to read the value of.",
    ("app.state", "set", "key"): "The key to store the value under.",
    ("app.state", "set", "value"): "The value to store.",
    ("app.state", "delete", "key"): "The key to remove.",
    ("ui", "open_panel", "params"): (
        "The panel's own parameters: what the panel shows, in the panel's own shape."
    ),
    ("ui", "set_sidebar", "open"): "Whether the sidebar is open.",
    ("ui", "open_preview", "path"): "The file to preview, by its path in the project.",
    ("ui", "select", "selection"): (
        "What is selected: a message, text or a file; the parts left out are cleared."
    ),
    ("ui", "set_composer", "text"): "The draft to put in the composer.",
    ("ui", "toast", "text"): "The toast's first line.",
    ("ui", "dismiss_toast", "toast_id"): "The toast to take away, by its id.",
    ("ui", "show_dialog", "spec"): ("The dialog to show: its title, body, buttons and input."),
    (
        "ui",
        "scroll_to",
        "message_id",
    ): "The message to scroll to, named by the run it belongs to; `bottom` for the newest.",
    ("sessions", "open", "session_id"): "The session to open, by its id.",
    ("sessions", "create", "project_dir"): (
        "The folder the new session works in; this project when left out."
    ),
    ("sessions", "attach", "session_id"): "The session to make live, by its id.",
    ("sessions", "attach", "project_dir"): (
        "The folder the session works in; it must belong to that session."
    ),
    ("chat", "post", "text"): "The message to post, labelled as this extension's.",
    ("chat", "queue", "text"): "The message to queue for the next turn.",
    ("chat", "append", "title"): "The view's title, as it is shown in the transcript.",
    ("chat", "replace", "view_id"): "The view to replace, by the id `append` returned.",
    ("chat", "replace", "view"): "The new json-render spec: `{root, elements}`.",
    ("chat", "replace", "title"): "The view's new title.",
    ("chat", "search", "query"): "The text to find in the transcript.",
    ("chat", "cancel_agent", "run_id"): "The sub-agent's run to stop, by its id.",
    ("chat", "truncate", "run_id"): "The run to remove, with every run after it.",
    ("chat", "extract_learnings", "user_msg"): "The turn's message, the one the person wrote.",
    ("chat", "extract_learnings", "assistant_msg"): "The turn's answer, the one the agent gave.",
    ("chat", "discard_interrupted", "message_id"): (
        "The interrupted run to forget, named by the message that started it."
    ),
    ("chat", "upload", "filename"): "The file's name, made safe for the disk.",
    ("chat", "upload", "content_base64"): "The file's bytes, base64-encoded.",
    ("chat.approvals", "answer", "requirement_id"): "The waiting request to answer, by its id.",
    ("chat.approvals", "answer_all", "answers"): "The answers to give, one per waiting request.",
    ("chat.views", "dispatch", "view_id"): "The view the action was used on, by its id.",
    ("chat.views", "dispatch", "action"): "The control's action name.",
    ("chat.views", "dispatch", "params"): "The values the view attached to the action.",
    ("plan", "approve", "run_id"): "The run that submitted the plan.",
    ("plan", "dismiss", "run_id"): "The run that submitted the plan.",
    ("agents", "promote_ephemeral", "name"): "The agent to keep, by its name.",
    ("agents", "discard_ephemeral", "name"): "The agent to drop, by its name.",
    ("workflows", "run", "name"): "The workflow to start, by its name.",
    ("workflows", "run", "input"): "The workflow's input, a JSON object it reads as it defines.",
    ("workflows", "cancel", "workflow_run_id"): "The run to stop, by its id.",
    ("scheduler", "run_now", "task_id"): "The scheduled task to run now, by its id.",
    ("scheduler", "cancel", "task_id"): "The scheduled task to cancel, by its id.",
    ("processes", "tail", "pid"): "The shell to read the last lines of, by its process id.",
    ("processes", "stop", "pid"): "The shell to stop, by its process id.",
    ("processes", "run", "command"): "The command line to run in the project.",
    ("workspace", "read", "path"): "The file to read, by its path in the project.",
    ("workspace", "list", "dir"): (
        "The directory to list, by its path in the project; the project itself when left out."
    ),
    ("workspace", "complete", "prefix"): "The path typed so far after `@`.",
    ("workspace", "search", "query"): "The text to search the code for.",
    ("mcp", "connect", "name"): "The server to connect, by its name in the MCP configuration.",
    (
        "mcp",
        "disconnect",
        "name",
    ): "The server to disconnect, by its name in the MCP configuration.",
    ("mcp", "set_tool_enabled", "server"): "The server the tool belongs to, by its name.",
    ("mcp", "set_tool_enabled", "tool"): "The tool to offer or withhold, by its name.",
    ("mcp", "set_tool_enabled", "on"): "Whether the tool is offered.",
    ("plugins", "contents", "name"): "The installed plugin to describe, by its name.",
    ("plugins", "preview", "source"): "The plugin's git URL, optionally followed by a subfolder.",
    ("plugins", "preview", "branch"): (
        "The branch, tag or commit to read; the default branch when left out."
    ),
    ("plugins", "preview", "subdir"): (
        "The plugin's folder inside the repository, which wins over one in `source`."
    ),
    ("plugins", "install", "ref"): "The plugin to install: a git URL or `@<marketplace>/<plugin>`.",
    ("plugins", "install", "install_ref"): (
        "The branch, tag or commit to check out; the marketplace's, or the default "
        "branch, when left out."
    ),
    ("plugins", "update", "name"): "The installed plugin to move, by its name.",
    ("plugins", "update", "install_ref"): (
        "The branch, tag or commit to move to; the remote's default branch when left out."
    ),
    ("plugins", "remove", "name"): "The installed plugin to remove, by its name.",
    ("plugins", "set_enabled", "name"): "The installed plugin to switch on or off, by its name.",
    ("plugins", "set_enabled", "on"): "Whether the plugin is enabled.",
    ("plugins", "add_marketplace", "url"): "The marketplace's git URL.",
    ("plugins", "remove_marketplace", "name"): "The marketplace to forget, by its name.",
    ("plugins", "refresh_marketplaces", "name"): (
        "The marketplace to fetch again; every one of them when left out."
    ),
    ("extensions", "set_settings", "values"): "The settings to change, as key to value.",
    ("permissions", "check", "tool_name"): "The tool the call would use, by its name.",
    ("permissions", "check", "func_name"): "The function of that tool the call would reach.",
    ("permissions", "check", "tool_args"): (
        "The call's arguments, which argument rules match against."
    ),
    ("permissions", "save_rule", "rule"): "The rule to save: `Bash(git status)`, a tool name.",
    ("notifications", "notify", "notification"): "What to tell the person at this machine.",
    ("notifications", "mark_read", "ids"): "The notifications to mark read, by their ids.",
    ("notifications", "mark_read", "source"): (
        "The source whose notifications to mark read; every one of them when left out."
    ),
    ("self", "busy", "reason"): "Why the extension is working inside igni's process.",
    ("self", "done", "reason"): "The reason the lease was taken for.",
}


#: What the two accessors the schema does not carry take: the id of
#: the window or the session the object is for. The schema has no
#: member for them — they are how an object reaches another window's
#: or another session's model.
ACCESSOR_MEANINGS: dict[str, str] = {
    "window_id": "The window to reach, by its id.",
    "session_id": "The session to reach, by its id.",
}


def param_meaning(path: str, method: str, name: str, doc: str = "") -> str:
    """What a parameter is: the schema's own words, or the table's.

    The schema describes a parameter or does not. A parameter it
    describes is documented from it; one it leaves out is documented
    from :data:`PARAM_MEANINGS`, and one in neither is left
    undocumented rather than given a meaning the contract does not
    have.
    """
    described = (doc or "").strip()
    if described:
        return described
    return PARAM_MEANINGS.get((path, method, name), "")


class ObjectNaming:
    """Class names and the tree of objects, shared by both generators."""

    def __init__(self, schema: HostSchema) -> None:
        self.schema = schema

    @staticmethod
    def class_name(path: str) -> str:
        if not path:
            return "Host"
        return "Host" + "".join(part.title().replace("_", "") for part in path.split("."))

    def children(self, path: str) -> list[ObjectSpec]:
        """Objects one level below ``path``, in schema order."""
        depth = 0 if not path else path.count(".") + 1
        out: list[ObjectSpec] = []
        for spec in self.schema.objects:
            if not spec.path or spec.path == path:
                continue
            if spec.path.count(".") != depth:
                continue
            if path and not spec.path.startswith(path + "."):
                continue
            out.append(spec)
        return out

    @staticmethod
    def attribute(spec: ObjectSpec) -> str:
        return spec.path.rpartition(".")[2]

    def per_window(self) -> list[ObjectSpec]:
        return [o for o in self.schema.objects if o.per_window]

    def per_session(self) -> list[ObjectSpec]:
        """Objects a session owns whose parent it does not: ``host.sessions.chat(id)``.

        Their children follow them, as ``chat.approvals`` follows ``chat``.
        """
        owned = {o.path for o in self.schema.objects if o.per_session}
        return [
            o
            for o in self.schema.objects
            if o.per_session and o.path.rpartition(".")[0] not in owned
        ]

    def check(self) -> None:
        """No child object, nor ``host.sessions``' handle of one, may share a
        name with a member of the object it hangs from."""
        for spec in self.schema.objects:
            names = {m.name for g in (spec.properties, spec.signals, spec.methods) for m in g}
            for child in self.children(spec.path):
                if self.attribute(child) in names:
                    raise ValueError(
                        f"{child.path}: its name collides with a member of "
                        f"{spec.path or 'the root'}"
                    )
            if spec.path == "sessions":
                children = {self.attribute(c) for c in self.children(spec.path)}
                for target in self.per_session():
                    if self.attribute(target) in names | children:
                        raise ValueError(
                            f"sessions.{self.attribute(target)}(id): collides with a member "
                            "of sessions"
                        )

    def ordered(self) -> list[ObjectSpec]:
        """Deepest first, so a class is defined before its parent uses it."""
        return sorted(self.schema.objects, key=lambda o: -(o.path.count(".") + 1 if o.path else 0))


# ── Python ────────────────────────────────────────────────────────


class PythonGenerator:
    """``igni_extension.host_model``."""

    #: Schema types the Python SDK already has, hand-written with the
    #: limits igni enforces, and used rather than generated: an author
    #: who wrote ``LocalNotification`` before the model existed keeps
    #: writing it. ``tests/test_the_host_sdks_are_generated.py`` holds
    #: their fields to the schema's.
    EXTERNAL: dict[str, tuple[str, str]] = {
        "LocalNotification": ("igni_extension.notifications", "LocalNotification"),
        "NotificationTarget": ("igni_extension.notifications", "Target"),
    }

    def __init__(self, schema: HostSchema = HOST_SCHEMA) -> None:
        self.schema = schema
        self.naming = ObjectNaming(schema)

    def type(self, expression: str) -> str:
        return self._render(TypeExpr.parse(expression))

    def _render(self, expr: TypeExpr) -> str:
        if expr.kind == "scalar":
            return "JsonValue" if expr.name == "json" else expr.name
        if expr.kind == "named":
            return expr.name
        assert expr.item is not None
        inner = self._render(expr.item)
        if expr.kind == "list":
            return f"list[{inner}]"
        if expr.kind == "dict":
            return f"dict[str, {inner}]"
        return f"{inner} | None"

    def _default(self, expression: str) -> str:
        expr = TypeExpr.parse(expression)
        if expr.kind == "optional" or (expr.kind == "scalar" and expr.name == "json"):
            return "None"
        if expr.kind == "list":
            return "Field(default_factory=list)"
        if expr.kind == "dict":
            return "Field(default_factory=dict)"
        if expr.kind == "scalar":
            return {"str": '""', "int": "0", "float": "0.0", "bool": "False"}.get(expr.name, "None")
        return "None"

    @staticmethod
    def _doc(text: str, indent: str) -> list[str]:
        text = text.replace('"""', "'''").strip()
        if not text:
            return []
        return [f'{indent}"""{text}"""']

    def _doc_with_args(self, text: str, args: list[tuple[str, str]], indent: str) -> list[str]:
        """A docstring: what it does, and what each of its parameters is.

        The parameters are the ones that have a meaning: the schema's
        own words, or the table's. One with neither is left out rather
        than given a meaning the contract does not have.
        """
        text = text.replace('"""', "'''").strip()
        out: list[str] = []
        if text:
            out.append(f'{indent}"""{text}')
        if args:
            if text:
                out.append("")
            out.append(f"{indent}Args:")
            for name, meaning in args:
                out.append(f"{indent}    {name}: {meaning}")
        out.append(f'{indent}"""')
        return out

    def generate(self) -> str:
        self.naming.check()
        lines: list[str] = [
            f'"""{_BANNER.format(version=self.schema.version)}',
            "",
            "`ext.host` as an extension's process sees it. Read",
            "`docs/HOST_OBJECT_MODEL.md` in igni for what each object is.",
            '"""',
            "",
            "# ruff: noqa: E501",
            "",
            "from __future__ import annotations",
            "",
            "from typing import cast",
            "",
            "from pydantic import BaseModel, ConfigDict, Field",
            "",
            "from igni_extension.members import (",
            "    NO_RESULT,",
            "    HostLink,",
            "    HostObject,",
            "    JsonValue,",
            "    Property,",
            "    Signal,",
            ")",
        ]
        modules: dict[str, list[str]] = {}
        for module, name in self.EXTERNAL.values():
            modules.setdefault(module, []).append(name)
        for module, names in sorted(modules.items()):
            lines.append(f"from {module} import {', '.join(sorted(names))}")
        lines += [
            "",
            f'SCHEMA_VERSION = "{self.schema.version}"',
            '"""The version of igni\'s host object model this SDK was generated from."""',
            "",
        ]
        for schema_name, (_, name) in sorted(self.EXTERNAL.items()):
            if schema_name != name:
                lines.append(f"{schema_name} = {name}")
        for spec in self.schema.types:
            if spec.name in self.EXTERNAL:
                continue
            lines += ["", f"class {spec.name}(BaseModel):"]
            lines += self._doc(spec.doc, "    ")
            lines += [
                "",
                '    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)',
                "",
            ]
            for f in spec.fields:
                annotation = self.type(f.type)
                if f.optional:
                    lines.append(f"    {f.name}: {annotation} = {self._default(f.type)}")
                else:
                    lines.append(f"    {f.name}: {annotation}")
                lines += self._doc(f.doc, "    ")
            lines.append("")
        for obj in self.naming.ordered():
            lines += self._object(obj)
        lines += [
            "",
            "__all__ = [",
            *sorted(
                [f'    "{t.name}",' for t in self.schema.types]
                + [f'    "{self.naming.class_name(o.path)}",' for o in self.schema.objects]
                + ['    "SCHEMA_VERSION",']
            ),
            "]",
            "",
        ]
        return "\n".join(lines)

    def _object(self, spec: ObjectSpec) -> list[str]:
        name = self.naming.class_name(spec.path)
        out = ["", f"class {name}(HostObject):"]
        out += self._doc_with_args(
            spec.doc,
            [
                ("link", "The link this object talks to the host through."),
                (
                    "window",
                    "The window it was reached through, or None for the one the extension is in.",
                ),
                (
                    "session",
                    "The session it was reached through, or None for the one on screen.",
                ),
            ],
            "    ",
        )
        out += [
            "",
            f'    PATH = "{spec.path}"',
            *self._doc(
                f"Where this object is in the host model: `host.{spec.path}`."
                if spec.path
                else "Where this object is in the host model: the root, `host`.",
                "    ",
            ),
            "",
            "    def __init__(",
            "        self, link: HostLink, window: str | None = None, session: str | None = None",
            "    ) -> None:",
            "        super().__init__(link, window, session)",
        ]
        for child in self.naming.children(spec.path):
            out.append(
                f"        self.{self.naming.attribute(child)} = "
                f"{self.naming.class_name(child.path)}(link, window, session)"
            )
            out += self._doc(f"`host.{child.path}`. {child.doc}", "        ")
        for p in spec.properties:
            out.append(
                f"        self.{p.name}: Property[{self.type(p.type)}] = Property("
                f'self, "{p.name}", {self.type(p.type)}, writable={p.writable})'
            )
            out += self._doc(p.doc, "        ")
        for s in spec.signals:
            wire = self.schema.wire_name(spec, s)
            out.append(
                f"        self.{s.name}: Signal[{self.type(s.type)}] = Signal("
                f'"{wire}", {self.type(s.type)})'
            )
            out += self._doc(s.doc, "        ")
        for m in spec.methods:
            out += self._method(spec, m)
        if spec.path == "windows":
            per_window = self.naming.per_window()
            for target in per_window:
                cls = self.naming.class_name(target.path)
                attr = self.naming.attribute(target)
                out += [
                    "",
                    f"    def {attr}(self, window_id: str) -> {cls}:",
                ]
                out += self._doc_with_args(
                    f"`host.{target.path}` of one window, by its id.",
                    [("window_id", ACCESSOR_MEANINGS["window_id"])],
                    "        ",
                )
                out += [
                    f"        return {cls}(self._link, window_id)",
                ]
        if spec.path == "sessions":
            for target in self.naming.per_session():
                cls = self.naming.class_name(target.path)
                attr = self.naming.attribute(target)
                out += [
                    "",
                    f"    def {attr}(self, session_id: str) -> {cls}:",
                ]
                out += self._doc_with_args(
                    f"`host.{target.path}` of any session of this project, by its id, "
                    "without showing it. The session on screen's id is "
                    f"`host.{target.path}` itself.",
                    [("session_id", ACCESSOR_MEANINGS["session_id"])],
                    "        ",
                )
                out += [
                    f"        return {cls}(self._link, None, session_id)",
                ]
        return out

    def _method(self, spec: ObjectSpec, m: MethodSpec) -> list[str]:
        params = ["self"]
        body_args: list[str] = []
        for p in m.params:
            annotation = self.type(p.type)
            if p.optional:
                if TypeExpr.parse(p.type).kind != "optional":
                    annotation = f"{annotation} | None"
                params.append(f"{p.name}: {annotation} = None")
            else:
                params.append(f"{p.name}: {annotation}")
            body_args.append(f'"{p.name}": {p.name}')
        result = self.type(m.result)
        signature = f"    async def {m.name}({', '.join(params)}) -> {result}:"
        call_args = "{" + ", ".join(body_args) + "}"
        out = ["", signature]
        out += self._doc_with_args(
            m.doc,
            [
                (p.name, param_meaning(spec.path, m.name, p.name, p.doc))
                for p in m.params
                if param_meaning(spec.path, m.name, p.name, p.doc)
            ],
            "        ",
        )
        if m.result == "None":
            out.append(f'        await self._call("{m.name}", {call_args}, NO_RESULT)')
        else:
            out.append(
                f'        return cast({result}, await self._call("{m.name}", {call_args}, {result}))'
            )
        return out


# ── TypeScript ────────────────────────────────────────────────────


class TypeScriptGenerator:
    """``hostModel.generated.ts`` in ``@ignite-ember/extension-bridge``."""

    def __init__(self, schema: HostSchema = HOST_SCHEMA) -> None:
        self.schema = schema
        self.naming = ObjectNaming(schema)

    def type(self, expression: str) -> str:
        return self._render(TypeExpr.parse(expression))

    def _render(self, expr: TypeExpr) -> str:
        if expr.kind == "scalar":
            return {
                "str": "string",
                "int": "number",
                "float": "number",
                "bool": "boolean",
                "None": "null",
                "json": "JsonValue",
            }[expr.name]
        if expr.kind == "named":
            return expr.name
        assert expr.item is not None
        inner = self._render(expr.item)
        if expr.kind == "list":
            return f"({inner})[]" if " " in inner else f"{inner}[]"
        if expr.kind == "dict":
            return f"Record<string, {inner}>"
        return f"{inner} | null"

    @staticmethod
    def _doc(text: str, indent: str) -> list[str]:
        text = text.replace("*/", "*\\/").strip()
        if not text:
            return []
        return [f"{indent}/** {text} */"]

    def _method_doc(self, path: str, m: MethodSpec, indent: str) -> list[str]:
        """A method's JSDoc: what it does, and what each of its parameters is.

        A parameter is documented from the schema when the schema
        describes it, and from the table when it does not; one with
        neither is left undocumented rather than given a meaning the
        contract does not have.
        """
        text = m.doc.replace("*/", "*\\/").strip()
        params = [
            (p.name, param_meaning(path, m.name, p.name, p.doc))
            for p in m.params
            if param_meaning(path, m.name, p.name, p.doc)
        ]
        if not params:
            return self._doc(m.doc, indent)
        lines = [f"{indent}/**"]
        if text:
            for line in text.split("\n"):
                lines.append(f"{indent} * {line}".rstrip())
        lines.append(f"{indent} *")
        for name, meaning in params:
            lines.append(f"{indent} * @param {name} — {meaning}")
        lines.append(f"{indent} */")
        return lines

    def generate(self) -> str:
        self.naming.check()
        lines = [
            f"// {_BANNER.format(version=self.schema.version)}",
            "//",
            "// `bridge.host` as an extension's page sees it. Read",
            "// `docs/HOST_OBJECT_MODEL.md` in igni for what each object is.",
            "",
            # The `.js` extension is what Node resolves: the package is ESM, and
            # a compiled `dist/` has to find its neighbours by their file names.
            'import { HostObject, Property, Signal, type HostLink, type JsonValue } from "./hostModel.js";',
            "",
            "/**",
            " * The version of igni's host schema this file was generated from.",
            " *",
            " * It moves when igni's host model moves. The bridge carries it on the",
            " * wire, so a host and a page can say which model they are speaking.",
            " */",
            f'export const SCHEMA_VERSION = "{self.schema.version}";',
            "",
        ]
        for spec in self.schema.types:
            lines += self._doc(spec.doc, "")
            lines.append(f"export interface {spec.name} {{")
            for f in spec.fields:
                lines += self._doc(f.doc, "  ")
                optional = "?" if f.optional else ""
                lines.append(f"  {f.name}{optional}: {self.type(f.type)};")
            lines += ["}", ""]
        for obj in self.naming.ordered():
            lines += self._object(obj)
        return "\n".join(lines) + "\n"

    def _object(self, spec: ObjectSpec) -> list[str]:
        name = self.naming.class_name(spec.path)
        out = self._doc(spec.doc, "")
        out.append(f"export class {name} extends HostObject {{")
        out.append(f'  static readonly PATH = "{spec.path}";')
        children = self.naming.children(spec.path)
        for child in children:
            out += self._doc(f"`host.{child.path}`. {child.doc}", "  ")
            out.append(
                f"  readonly {self.naming.attribute(child)}: {self.naming.class_name(child.path)};"
            )
        for p in spec.properties:
            out += self._doc(p.doc, "  ")
            out.append(f"  readonly {p.name}: Property<{self.type(p.type)}>;")
        for s in spec.signals:
            out += self._doc(s.doc, "  ")
            out.append(f"  readonly {s.name}: Signal<{self.type(s.type)}>;")
        out += [
            "",
            "  /**",
            "   * The object igni hands a page, bound to a host and to the window",
            "   * or session it was reached through.",
            "   *",
            "   * A page never builds one of these: `bridge.host` is already the",
            "   * right one, and a second would be a second conversation.",
            "   *",
            "   * @param link — The link this object talks to the host through.",
            "   * @param window — The window it was reached through, or null for",
            "   *   the one the page is in.",
            "   * @param session — The session it was reached through, or null for",
            "   *   the one on screen.",
            "   */",
            "  constructor(",
            "    link: HostLink,",
            "    window: string | null = null,",
            "    session: string | null = null,",
            "  ) {",
            f'    super(link, "{spec.path}", window, session);',
        ]
        for child in children:
            out.append(
                f"    this.{self.naming.attribute(child)} = new "
                f"{self.naming.class_name(child.path)}(link, window, session);"
            )
        for p in spec.properties:
            out.append(
                f'    this.{p.name} = new Property(this, "{p.name}", {str(p.writable).lower()});'
            )
        for s in spec.signals:
            wire = self.schema.wire_name(spec, s)
            out.append(f'    this.{s.name} = new Signal("{wire}");')
        out.append("  }")
        for m in spec.methods:
            out += self._method(spec, m)
        if spec.path == "windows":
            for target in self.naming.per_window():
                cls = self.naming.class_name(target.path)
                attr = self.naming.attribute(target)
                out += [
                    "",
                    "  /**",
                    f"   * `host.{target.path}` of one window, by its id.",
                    "   *",
                    f"   * @param windowId — {ACCESSOR_MEANINGS['window_id']}",
                    "   */",
                    f"  {attr}(windowId: string): {cls} {{",
                    f"    return new {cls}(this.link, windowId);",
                    "  }",
                ]
        if spec.path == "sessions":
            for target in self.naming.per_session():
                cls = self.naming.class_name(target.path)
                attr = self.naming.attribute(target)
                out += [
                    "",
                    "  /**",
                    f"   * `host.{target.path}` of any session of this project, by its id, "
                    "without showing it. The session on screen's id is "
                    f"`host.{target.path}` itself.",
                    "   *",
                    f"   * @param sessionId — {ACCESSOR_MEANINGS['session_id']}",
                    "   */",
                    f"  {attr}(sessionId: string): {cls} {{",
                    f"    return new {cls}(this.link, null, sessionId);",
                    "  }",
                ]
        out += ["}", ""]
        return out

    def _method(self, spec: ObjectSpec, m: MethodSpec) -> list[str]:
        params: list[str] = []
        names: list[str] = []
        for p in m.params:
            ts = self.type(p.type)
            if p.optional:
                params.append(f"{p.name}?: {ts}")
            else:
                params.append(f"{p.name}: {ts}")
            names.append(p.name)
        result = "void" if m.result == "None" else self.type(m.result)
        args = "{ " + ", ".join(names) + " }" if names else "{}"
        out = [""]
        out += self._method_doc(spec.path, m, "  ")
        out.append(f"  {m.name}({', '.join(params)}): Promise<{result}> {{")
        out.append(f'    return this.call<{result}>("{m.name}", {args});')
        out.append("  }")
        return out


class HostSdks:
    """Both generated files, and whether what is on disk is current."""

    def __init__(self, root: Path, schema: HostSchema = HOST_SCHEMA) -> None:
        self.root = root
        self.schema = schema

    def outputs(self) -> dict[Path, str]:
        return {
            self.root / PYTHON_OUTPUT: PythonGenerator(self.schema).generate(),
            self.root / TYPESCRIPT_OUTPUT: TypeScriptGenerator(self.schema).generate(),
        }

    def write(self) -> list[Path]:
        written: list[Path] = []
        for path, text in self.outputs().items():
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8")
                written.append(path)
        return written

    def stale(self) -> list[Path]:
        """Generated files that do not match the schema."""
        return [
            path
            for path, text in self.outputs().items()
            if not path.exists() or path.read_text(encoding="utf-8") != text
        ]


__all__ = [
    "ACCESSOR_MEANINGS",
    "HOST_SCHEMA",
    "PARAM_MEANINGS",
    "PYTHON_OUTPUT",
    "SCHEMA_FILE",
    "TYPESCRIPT_OUTPUT",
    "HostSdks",
    "ObjectNaming",
    "PythonGenerator",
    "TypeScriptGenerator",
    "param_meaning",
]

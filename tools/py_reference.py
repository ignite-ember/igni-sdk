"""A Python package's public names, read from the package itself, as reference pages.

igni-service and igni-extension are written by hand, so their reference on
the site (``tools/sdk_docs.py``) is read from them: every name in a module's
``__all__``, its signature as ``inspect`` reports it, its docstring, and, for
a class, its fields and its own public methods and properties. Nothing is
added that the code does not say; a name with no docstring is shown with its
signature alone.

Under every signature is the table of its parameters: what each one is
called, what type it is, what it defaults to, and what it means. The
meaning is read from the docstring's own ``Args:`` section
(``tools/param_docs.py``); a parameter no docstring documents is said to be
undocumented, because a reference that guesses what a parameter is would be
wrong rather than useful.

Which page a name is on is decided by the module that defines it, through a
table of areas the caller gives; a public name no area takes is an error.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import importlib
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.markdown_pages import plain, signature, site_id
from tools.param_docs import UNDOCUMENTED, code, python_args, strip_python_args, table
from tools.reference_area import Area


class ReferenceError_(ValueError):
    """A public name has no page, or a page names a module with no public name."""


@dataclass
class Entry:
    name: str
    obj: Any
    #: The ``__all__`` it is exported from: ``igni_service``, ``igni_service.testing``.
    exported_from: str


def stable_repr(value: Any) -> str:
    """``repr(value)``, the same on every run: sets sorted, no addresses."""
    if isinstance(value, frozenset | set):
        items = ", ".join(sorted(stable_repr(v) for v in value))
        name = type(value).__name__
        return f"{name}({{{items}}})" if items else f"{name}()"
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    text = re.sub(r" at 0x[0-9a-fA-F]+", "", repr(value))
    # `igni_service.tokens.Person | …` reads as `Person | …`, as the code spells it.
    return re.sub(r"\b[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+\.(?=[A-Z])", "", text)


def annotation_text(annotation: Any) -> str:
    """An annotation as its source spells it, where ``from __future__`` kept it a string."""
    if annotation is inspect.Parameter.empty:
        return ""
    if isinstance(annotation, str):
        return annotation
    if isinstance(annotation, type):
        return annotation.__qualname__
    return re.sub(r"\b(typing|collections\.abc|builtins)\.", "", repr(annotation))


def signature_text(obj: Any, *, skip_self: bool = False) -> tuple[str, str]:
    """``(parameters, return annotation)`` of ``obj``, or ``("…", "")`` when unknowable."""
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return "…", ""
    parts: list[str] = []
    seen_keyword_only = False
    params = list(sig.parameters.values())
    for index, param in enumerate(params):
        if skip_self and index == 0 and param.name in ("self", "cls"):
            continue
        if param.kind is param.KEYWORD_ONLY and not seen_keyword_only:
            parts.append("*")
            seen_keyword_only = True
        if param.kind is param.VAR_POSITIONAL:
            seen_keyword_only = True
            prefix = "*"
        elif param.kind is param.VAR_KEYWORD:
            prefix = "**"
        else:
            prefix = ""
        text = prefix + param.name
        ann = annotation_text(param.annotation)
        if ann:
            text += f": {ann}"
        if param.default is not inspect.Parameter.empty:
            text += f" = {stable_repr(param.default)}" if ann else f"={stable_repr(param.default)}"
        parts.append(text)
        if param.kind is param.POSITIONAL_ONLY and (
            index + 1 == len(params) or params[index + 1].kind is not param.POSITIONAL_ONLY
        ):
            parts.append("/")
    return ", ".join(parts), annotation_text(sig.return_annotation)


def docstring_markdown(doc: str | None) -> str:
    """A docstring as Markdown: reST roles and double backticks as code, indented
    examples as Python blocks."""
    if not doc:
        return ""
    text = re.sub(r":(?:class|meth|func|attr|data|mod|exc|obj):`~?([^`]+)`", r"`\1`", doc)
    text = text.replace("``", "`")
    lines = text.split("\n")
    out: list[str] = []
    block: list[str] = []

    def flush() -> None:
        if not block:
            return
        while block and not block[-1].strip():
            block.pop()
        indent = min(len(b) - len(b.lstrip()) for b in block if b.strip())
        out.append("```python")
        out.extend(b[indent:] if b.strip() else "" for b in block)
        out.append("```")
        out.append("")
        block.clear()

    previous_blank = True
    for line in lines:
        indented = line.startswith("    ") and line.strip()
        if block:
            if indented or not line.strip():
                block.append(line)
                continue
            flush()
        if indented and previous_blank and not _in_list(out):
            block.append(line)
            continue
        out.append(line)
        previous_blank = not line.strip()
    flush()
    return "\n".join(out).strip()


def _in_list(out: list[str]) -> bool:
    """Whether the last paragraph is a list item, whose indented lines continue it."""
    for line in reversed(out):
        if not line.strip():
            continue
        return bool(re.match(r"\s*([-*+]|\d+\.)\s", line))
    return False


def _own_members(cls: type) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for name, value in vars(cls).items():
        if name.startswith("_") or name.startswith("model_"):
            continue
        member = isinstance(value, staticmethod | classmethod | property | functools_cached())
        if member or inspect.isfunction(value):
            out.append((name, value))
    return out


def parameters_of(obj: Any, *, skip_self: bool = False) -> list[inspect.Parameter]:
    """The parameters a callable takes, as ``inspect`` reports them."""
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return []
    params = list(sig.parameters.values())
    if skip_self and params and params[0].name in ("self", "cls"):
        return params[1:]
    return params


def parameter_table(params: list[inspect.Parameter], meanings: dict[str, str]) -> list[str]:
    """The table of a callable's parameters, as the reference pages show it.

    The meaning of each parameter is what the docstring's ``Args:`` section
    says of it. A parameter the docstring does not document is said to be
    undocumented: the generator does not guess.
    """
    rows: list[tuple[str, str, str, str]] = []
    for param in params:
        annotation = annotation_text(param.annotation)
        variadic = param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD)
        default = (
            "—"
            if variadic
            else "required"
            if param.default is inspect.Parameter.empty
            else code(stable_repr(param.default))
        )
        prefix = "*" if param.kind is param.VAR_POSITIONAL else "**" if variadic else ""
        rows.append(
            (
                prefix + param.name,
                code(annotation) if annotation else "—",
                default,
                meanings.get(param.name) or UNDOCUMENTED,
            )
        )
    return table(rows)


def functools_cached() -> type:
    import functools

    return functools.cached_property


class PythonReference:
    """The reference pages of one package's public names."""

    def __init__(
        self,
        package: str,
        modules: tuple[str, ...],
        areas: list[Area],
        link: Callable[[str], str | None],
    ) -> None:
        #: ``igni_service``.
        self.package = package
        #: The modules whose ``__all__`` is public: the package and its ``testing``.
        self.modules = modules
        self.areas = areas
        #: The page and anchor of a documented name, for links between them.
        self.link = link
        self.entries = self._entries()
        self.placed = self._place()

    def _entries(self) -> list[Entry]:
        out: list[Entry] = []
        seen: set[str] = set()
        for module_name in self.modules:
            module = importlib.import_module(module_name)
            for name in module.__all__:
                key = f"{module_name}:{name}"
                if key in seen:
                    continue
                seen.add(key)
                out.append(Entry(name, getattr(module, name), module_name))
        return out

    def home(self, entry: Entry) -> str:
        """The module that defines ``entry``, or ``module:Name`` for a constant."""
        obj = entry.obj
        if inspect.isclass(obj) or inspect.isfunction(obj):
            return str(obj.__module__)
        return f"{entry.exported_from}:{entry.name}"

    def _attribute_doc(self, entry: Entry) -> str:
        """A constant's docstring, read from the source.

        A module-level constant is documented the way PEP 258 says: a
        string literal right after the assignment. Python does not keep
        that anywhere at runtime — ``SCHEMA_VERSION.__doc__`` is the
        version, not the sentence — so it is read from the source the
        way the convention intends a tool to read it.

        The constant is looked for across the package, not only in the
        module that re-exports it: ``igni_extension.testing`` exports
        ``Minter``, which ``igni_extension.testing.token_endpoint``
        defines and documents.

        A constant with no such literal has no docstring, and the page
        says so rather than inventing one.
        """
        for source in self._sources():
            try:
                tree = ast.parse(Path(source).read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            body = tree.body
            for index, node in enumerate(body):
                if not isinstance(node, ast.Assign | ast.AnnAssign):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if not any(
                    isinstance(target, ast.Name) and target.id == entry.name for target in targets
                ):
                    continue
                following = body[index + 1] if index + 1 < len(body) else None
                if (
                    isinstance(following, ast.Expr)
                    and isinstance(following.value, ast.Constant)
                    and isinstance(following.value.value, str)
                ):
                    return inspect.cleandoc(following.value.value)
        return ""

    def _sources(self) -> list[str]:
        """Every source file of the package.

        The files are read, not imported: a module that does work at
        import time should not be made to do it because a document was
        being written about it.
        """
        out: list[str] = []
        seen: set[str] = set()
        for module_name in self.modules:
            module = importlib.import_module(module_name)
            path = getattr(module, "__file__", None)
            if path and path not in seen:
                seen.add(path)
                out.append(path)
            for root in getattr(module, "__path__", []):
                for source in sorted(Path(root).rglob("*.py")):
                    if str(source) not in seen:
                        seen.add(str(source))
                        out.append(str(source))
        return out

    def _place(self) -> dict[str, list[Entry]]:
        placed: dict[str, list[Entry]] = {area.slug: [] for area in self.areas}
        unplaced: list[str] = []
        for entry in self.entries:
            home = self.home(entry)
            found = None
            for area in self.areas:
                for source in area.sources:
                    if (
                        home == source
                        or home.startswith(source + ".")
                        or (":" in source and source == f"{entry.exported_from}:{entry.name}")
                    ):
                        found = area
                        break
                if found:
                    break
            if found is None:
                unplaced.append(f"{entry.exported_from}.{entry.name} ({home})")
                continue
            placed[found.slug].append(entry)
        if unplaced:
            raise ReferenceError_(f"public names no reference page takes: {unplaced}")
        empty = [slug for slug, entries in placed.items() if not entries]
        if empty:
            raise ReferenceError_(f"reference pages with no public name: {empty}")
        return placed

    def anchors(self) -> dict[str, tuple[str, str]]:
        """Every documented name → (page slug, anchor)."""
        out: dict[str, tuple[str, str]] = {}
        for slug, entries in self.placed.items():
            for entry in entries:
                out.setdefault(entry.name, (slug, site_id(self.title(entry))))
        return out

    def title(self, entry: Entry) -> str:
        obj = entry.obj
        if inspect.isfunction(obj):
            return f"{entry.name}()"
        return entry.name

    # ── Rendering ──

    def page(self, area: Area) -> tuple[str, int]:
        """The page's Markdown body (no title), and how many names on it have no docstring."""
        out: list[str] = []
        undocumented = 0
        entries = self.placed[area.slug]
        modules = sorted({self.home(e).split(":")[0] for e in entries})
        imports = sorted({e.exported_from for e in entries})
        out.append(
            "Read from the code: every public name below, its signature and its docstring. "
            "Import "
            + ", ".join(f"`{m}`" for m in imports)
            + " — defined in "
            + ", ".join(f"`{m}`" for m in modules)
            + "."
        )
        out.append("")
        out.append("| Name | What it is |")
        out.append("|---|---|")
        for entry in entries:
            obj = entry.obj
            summary = _summary(
                _own_doc(obj)
                if inspect.isclass(obj)
                else inspect.getdoc(obj)
                if inspect.isfunction(obj)
                else self._attribute_doc(entry)
            )
            out.append(f"| [`{entry.name}`](#{site_id(self.title(entry))}) | {summary or '—'} |")
        out.append("")
        for entry in entries:
            text, missing = self._entry(entry)
            out += text
            undocumented += missing
        return "\n".join(out), undocumented

    def _entry(self, entry: Entry) -> tuple[list[str], int]:
        obj = entry.obj
        out = [f"## {self.title(entry)}", ""]
        missing = 0
        if inspect.isclass(obj):
            out += self._class(entry.name, obj)
            if not _own_doc(obj):
                missing += 1
            for name, member in _own_members(obj):
                lines, has_doc = self._member(entry.name, name, member)
                out += lines
                missing += 0 if has_doc else 1
        elif inspect.isfunction(obj):
            params, returns = signature_text(obj)
            prefix = "async def" if inspect.iscoroutinefunction(obj) else "def"
            arrow = f" -> {returns}" if returns else ""
            out += ["```python", signature(f"{prefix} {entry.name}", params, arrow), "```", ""]
            text = inspect.getdoc(obj) or ""
            out += parameter_table(parameters_of(obj), python_args(text))
            doc = docstring_markdown(strip_python_args(text))
            out += [doc, ""] if doc else []
            missing += 0 if text else 1
        else:
            out += [
                "```python",
                f"{entry.name}: {_type_name(obj)} = {stable_repr(obj)}",
                "```",
                "",
            ]
            doc = docstring_markdown(self._attribute_doc(entry))
            if doc:
                out += [doc, ""]
            else:
                missing += 1
        return out, missing

    def _class(self, name: str, cls: type) -> list[str]:
        bases = [b for b in cls.__bases__ if b is not object]
        base_text = ", ".join(b.__name__ for b in bases)
        out: list[str] = []
        doc_text = _own_doc(cls)
        if issubclass(cls, enum.Enum | BaseException):
            out += ["```python", f"class {name}({base_text})", "```", ""]
        else:
            params, _ = signature_text(cls)
            head = f"class {name}({base_text})" if base_text else f"class {name}"
            out += ["```python", head, signature(name, params), "```", ""]
            if not self._fields(cls):
                # A class whose fields are not a table of their own: what
                # its constructor takes is what the caller needs to know.
                out += parameter_table(
                    parameters_of(vars(cls).get("__init__"), skip_self=True),
                    python_args(doc_text),
                )
        documented_bases = [b for b in bases if self.link(b.__name__)]
        if documented_bases:
            out.append(
                "Based on "
                + ", ".join(f"[`{b.__name__}`]({self.link(b.__name__)})" for b in documented_bases)
                + "."
            )
            out.append("")
        doc = docstring_markdown(strip_python_args(doc_text))
        if doc:
            out += [doc, ""]
        if issubclass(cls, enum.Enum):
            out += ["| Member | Value |", "|---|---|"]
            for member in cls:
                out.append(f"| `{member.name}` | `{stable_repr(member.value)}` |")
            out.append("")
        else:
            out += self._fields(cls)
        return out

    def _fields(self, cls: type) -> list[str]:
        rows: list[str] = []
        model_fields = getattr(cls, "model_fields", None)
        if isinstance(model_fields, dict):
            own = getattr(cls, "__annotations__", {})
            for fname, info in model_fields.items():
                if fname not in own:
                    continue
                default = (
                    "required"
                    if info.is_required()
                    else (
                        "factory"
                        if info.default_factory is not None
                        else f"`{stable_repr(info.default)}`"
                    )
                )
                desc = (info.description or "").replace("\n", " ").replace("|", "\\|")
                ann = annotation_text(own.get(fname, info.annotation)).replace("|", "\\|")
                rows.append(f"| `{fname}` | `{ann}` | {default} | {desc} |")
        elif dataclasses.is_dataclass(cls):
            for f in dataclasses.fields(cls):
                if f.name.startswith("_") or not f.init and f.repr is False:
                    continue
                if f.default is not dataclasses.MISSING:
                    default = f"`{stable_repr(f.default)}`"
                elif f.default_factory is not dataclasses.MISSING:
                    default = "factory"
                else:
                    default = "required"
                ann = annotation_text(f.type).replace("|", "\\|")
                rows.append(f"| `{f.name}` | `{ann}` | {default} | |")
        if not rows:
            return []
        if all(row.endswith("|  |") or row.endswith("| |") for row in rows):
            # No field says what it is: no column to say it in.
            rows = [row.rsplit("|", 2)[0].rstrip() + " |" for row in rows]
            return ["| Field | Type | Default |", "|---|---|---|", *rows, ""]
        return ["| Field | Type | Default | Description |", "|---|---|---|---|", *rows, ""]

    def _member(self, owner: str, name: str, member: Any) -> tuple[list[str], bool]:
        if isinstance(member, property | functools_cached()):
            getter = member.fget if isinstance(member, property) else member.func
            _, returns = signature_text(getter)
            heading = f"### {owner}.{name}"
            code = f"{name}: {returns}" if returns else name
            label = "property"
            doc_source = getter
            taken = parameters_of(getter, skip_self=True)
        else:
            func = member.__func__ if isinstance(member, staticmethod | classmethod) else member
            params, returns = signature_text(func, skip_self=not isinstance(member, staticmethod))
            prefix = "async def" if inspect.iscoroutinefunction(func) else "def"
            arrow = f" -> {returns}" if returns else ""
            heading = f"### {owner}.{name}()"
            code = signature(f"{prefix} {name}", params, arrow)
            label = (
                "classmethod"
                if isinstance(member, classmethod)
                else "staticmethod"
                if isinstance(member, staticmethod)
                else ""
            )
            doc_source = func
            taken = parameters_of(func, skip_self=not isinstance(member, staticmethod))
        out = [heading, "", "```python"]
        if label:
            out.append(f"@{label}")
        out += [code, "```", ""]
        text = inspect.getdoc(doc_source) or ""
        out += parameter_table(taken, python_args(text))
        doc = docstring_markdown(strip_python_args(text))
        if doc:
            out += [doc, ""]
        return out, bool(text)


def _own_doc(cls: type) -> str:
    doc = cls.__dict__.get("__doc__")
    return inspect.cleandoc(doc) if isinstance(doc, str) else ""


def _summary(doc: str | None) -> str:
    if not doc:
        return ""
    first = doc.strip().split("\n\n", 1)[0].replace("\n", " ")
    first = re.sub(r":(?:class|meth|func|attr|data|mod|exc|obj):`~?([^`]+)`", r"`\1`", first)
    first = first.replace("``", "`").replace("|", "\\|")
    return first if len(plain(first)) <= 200 else first[:200].rsplit(" ", 1)[0] + "…"


def _type_name(obj: Any) -> str:
    return annotation_text(type(obj)) if not hasattr(obj, "__origin__") else "type"


__all__ = ["Area", "PythonReference", "ReferenceError_", "docstring_markdown", "stable_repr"]

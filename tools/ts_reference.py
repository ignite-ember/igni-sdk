"""The npm SDKs' reference pages, read from their TypeScript.

The Python packages' reference is read from the code itself
(``tools/py_reference.py``: ``inspect`` for the signatures, the
docstrings for the words). The npm packages have no such runtime to
ask, so this reads their TypeScript source the same way: every exported
declaration, its signature, its members and the JSDoc above it.

The shape of a page matches the Python ones, so a reader sees one table
of names and then each name in full:

* a table — the name, what kind of thing it is, and the first line of
  its JSDoc;
* then the name itself — its signature in a fenced block, its JSDoc as
  Markdown, and its members (an interface's fields, a class's methods)
  in a table.

Nothing is written by hand: ``make sdk-docs`` writes these pages, and
``tests/test_the_sdk_docs_are_generated.py`` fails when what is checked
in differs from what the sources generate.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tools.param_docs import UNDOCUMENTED, code, jsdoc_params, strip_jsdoc_params, table
from tools.reference_area import Area


class ReferenceError_(ValueError):
    """A public name has no page, or a page names a module with no public name."""


@dataclass
class Member:
    """One member of an interface or a class."""

    name: str
    kind: str
    type: str
    doc: str
    #: Whether the member may be left out — a field written ``name?``.
    optional: bool = False


@dataclass
class Parameter:
    """One parameter of a TypeScript signature."""

    name: str
    type: str
    default: str
    optional: bool
    #: Whether the parameter takes the rest of what is left: ``...rest``.
    rest: bool = False


@dataclass
class Declaration:
    """One exported declaration."""

    name: str
    kind: str
    signature: str
    doc: str
    #: The declaration's own text: an interface's or a class's body.
    body: str = ""
    #: The parameters a function takes, as the source spells them.
    params: str = ""
    members: list[Member] = field(default_factory=list)
    exported_from: str = ""


#: An identifier: a name in a signature, and what it may be called.
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")

#: A member of an interface or a class: a name, and a ``(``, a ``<`` or a
#: ``:`` after it, at the start of a line.
_MEMBER_START = re.compile(
    r"^[ \t]*((?:(?:public|private|protected|readonly|static|abstract|declare|override"
    r"|async|get|set)\s+)*)"
    r"([A-Za-z_$][\w$]*)\s*\??\s*(?=[(:<])",
    re.M,
)


#: The characters a regular expression literal can follow: an expression
#: may start there, so a ``/`` after one opens a regex and not a division.
_REGEX_AFTER = set("(,=:[!&|?{};+-*%~^<>")
_REGEX_AFTER_WORDS = frozenset(
    {
        "await",
        "case",
        "delete",
        "do",
        "else",
        "in",
        "instanceof",
        "new",
        "of",
        "return",
        "throw",
        "typeof",
        "void",
        "yield",
    }
)


def _prev_significant(text: str, index: int) -> str:
    """The last character before ``index`` that is not a space or a comment."""
    position = index - 1
    while position >= 0:
        char = text[position]
        if char in " \t\n\r":
            position -= 1
            continue
        if char == "/" and position > 0 and text[position - 1] == "*":
            start = text.rfind("/*", 0, position)
            if start < 0:
                return char
            position = start - 1
            continue
        if char == "/" and position > 0 and text[position - 1] == "/":
            position = text.rfind("\n", 0, position)
            continue
        return char
    return ""


def _regex_end(text: str, index: int) -> int:
    """The index just past the regular expression literal at ``index``."""
    position = index + 1
    in_class = False
    while position < len(text):
        char = text[position]
        if char == "\\":
            position += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            return position + 1
        elif char == "\n":
            break
        position += 1
    return index + 1


def _is_regex_start(text: str, index: int) -> bool:
    """Whether the ``/`` at ``index`` opens a regular expression."""
    previous = _prev_significant(text, index)
    if not previous:
        return True
    if previous in _REGEX_AFTER:
        return True
    if previous.isalpha():
        word = re.search(r"[A-Za-z_$][\w$]*$", text[:index])
        if word is None:
            return False
        return word.group(0) in _REGEX_AFTER_WORDS
    return False


def _match_bracket(text: str, start: int, open_char: str, close_char: str) -> int:
    """The index just past the bracket that closes the one at ``start``.

    Strings, template literals, comments and regular expressions are
    skipped, so a bracket inside any of them does not count.
    """
    depth = 0
    index = start
    quote = ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "'\"`":
            quote = char
            index += 1
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "/":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "*":
            end = text.find("*/", index)
            index = len(text) if end < 0 else end + 2
            continue
        if char == "/" and _is_regex_start(text, index):
            index = _regex_end(text, index)
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise ReferenceError_("an unclosed bracket")


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\n\r":
        index += 1
    return index


def _statement_end(text: str, start: int) -> int:
    """The index just past the ``;`` (or the newline) that ends a statement."""
    index = start
    depth = 0
    quote = ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "'\"`":
            quote = char
            index += 1
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "/":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "*":
            end = text.find("*/", index)
            index = len(text) if end < 0 else end + 2
            continue
        if char == "/" and _is_regex_start(text, index):
            index = _regex_end(text, index)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == ";" and depth == 0:
            return index + 1
        elif char == "\n" and depth == 0:
            return index
        index += 1
    return len(text)


def _type_end(text: str, start: int) -> int:
    """The index just past the ``;`` that ends a type alias.

    A type alias runs over as many lines as it needs — a union, one
    member a line — so the newline does not end it.
    """
    index = start
    depth = 0
    quote = ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "'\"`":
            quote = char
            index += 1
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "/":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "*":
            end = text.find("*/", index)
            index = len(text) if end < 0 else end + 2
            continue
        if char == "/" and _is_regex_start(text, index):
            index = _regex_end(text, index)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == ";" and depth == 0:
            return index + 1
        index += 1
    return len(text)


def _generic(text: str, start: int) -> tuple[str, int]:
    """The ``<...>`` of a declaration's type parameters, and where it ends."""
    index = _skip_space(text, start)
    if index >= len(text) or text[index] != "<":
        return "", start
    end = _match_bracket(text, index, "<", ">")
    return text[index:end], end


def _jsdoc(doc: str) -> str:
    """A JSDoc comment as Markdown: the ``*`` of every line gone, the tags
    that are prose kept, the rest dropped."""
    if not doc:
        return ""
    body = doc.strip()
    if body.startswith("/**"):
        body = body[3:]
    if body.endswith("*/"):
        body = body[:-2]
    lines = []
    for line in body.split("\n"):
        line = re.sub(r"^\s*\* ?", "", line)
        lines.append(line.rstrip())
    text = "\n".join(lines).strip("\n")
    text = re.sub(r"\{@link\s+([^}]+)\}", r"`\1`", text)
    return text.strip()


def _is_internal(doc: str) -> bool:
    return "@internal" in doc


def _summary(doc: str) -> str:
    """A JSDoc's first paragraph, as one line: what a table cell shows."""
    text = _jsdoc(doc)
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("@"):
            break
        if stripped.startswith(("```", "---", "|")):
            break
        if not stripped:
            if lines:
                break
            continue
        lines.append(stripped)
    out = re.sub(r"\s+", " ", " ".join(lines)).strip()
    if len(out) <= 200:
        return out
    cut = out[:200]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return cut[: end + 1] if end > 60 else cut.rsplit(" ", 1)[0] + "…"


def _one_line(text: str) -> str:
    """A signature's text on one line, the way it is written in the source."""
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r",\s*\)", ")", text)
    text = re.sub(r",\s*,", ",", text)
    return text


def _tight_generics(text: str) -> str:
    """A type's generic lists on one line, without the spaces a line break leaves.

    Only for types: a value's text is left alone, so a string that
    happens to hold a ``<`` keeps it.
    """
    text = _one_line(text)
    text = re.sub(r"<\s+", "<", text)
    text = re.sub(r"\s+>", ">", text)
    return text


def _doc_before(text: str, index: int) -> str:
    """The JSDoc block that ends just before ``index``, if there is one."""
    head = text[:index].rstrip()
    if not head.endswith("*/"):
        return ""
    start = head.rfind("/**")
    if start < 0:
        return ""
    between = head[start + 3 : -2].strip()
    if not between.startswith("*") and "\n" not in between:
        # A one-line comment: `/** … */`
        return f"/** {between} */"
    return head[start:]


def _line_depths(text: str) -> list[int]:
    """The nesting depth at the start of every line.

    A member of an interface or a class is at the top level of its body:
    a parameter line is not, however much it looks like one.
    """
    depths: list[int] = []
    depth = 0
    quote = ""
    in_comment = False
    offset = 0
    for line in text.split("\n"):
        depths.append(depth)
        index = 0
        while index < len(line):
            char = line[index]
            if in_comment:
                if line.startswith("*/", index):
                    in_comment = False
                    index += 2
                    continue
                index += 1
                continue
            if quote:
                if char == "\\":
                    index += 2
                    continue
                if char == quote:
                    quote = ""
                index += 1
                continue
            if char in "'\"`":
                quote = char
                index += 1
                continue
            if line.startswith("//", index):
                break
            if line.startswith("/*", index):
                in_comment = True
                index += 2
                continue
            if char == "/" and _is_regex_start(text, offset + index):
                index += _regex_end(text, offset + index) - (offset + index)
                continue
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            index += 1
        offset += len(line) + 1
    return depths


#: A declaration at the top level of a file: nothing before it on its line.
#: A declaration inside a function body is indented, and is not one.
_DECL_AT_TOP = re.compile(
    r"(?m)^(?P<export>export\s+)?(?:(?P<declare>declare\s+))?"
    r"(?P<abstract>abstract\s+)?(?P<async>async\s+)?"
    r"(?P<kind>function|class|interface|type|enum|const|let|var)\s+"
)

#: An export list: ``export { A, B } from "./x"`` or ``export type { A }``.
_EXPORT_LIST = re.compile(r"(?m)^export\s+(?:type\s+)?\{")

#: A whole module exported: ``export * from "./x"``.
_EXPORT_STAR = re.compile(r"(?m)^export\s+\*\s+from\s+")


class Module:
    """One TypeScript source file: its declarations, and what it exports.

    A file exports in three ways: a declaration marked ``export``, a list
    (``export { A, B } from "./x"``) and a whole module (``export * from
    "./x"``). All three are read here, so a name the package's entry point
    re-exports is found in the file that declares it.
    """

    def __init__(self, path: Path, name: str) -> None:
        self.path = path
        self.name = name
        self.text = path.read_text(encoding="utf-8")
        #: Every declaration in the file, exported or not.
        self.declarations: dict[str, Declaration] = {}
        #: The names the file exports itself, in the order it declares them.
        #:
        #: A dict rather than a set, and the order matters: a set of
        #: strings iterates in whatever order the interpreter's hash
        #: seed gives it, which differs between two runs of the same
        #: program. The pages would then be written one way by
        #: ``make sdk-docs`` and another by the staleness test, and
        #: neither would be wrong — only different.
        self.exported: dict[str, None] = {}
        #: A name the file re-exports → the module it comes from ("" for its own).
        self.reexports: dict[str, str] = {}
        #: The modules the file exports whole.
        self.stars: list[str] = []
        self._parse()

    def _parse(self) -> None:
        text = self.text
        starts = list(_DECL_AT_TOP.finditer(text))
        for index, match in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
            chunk = text[match.start() : end]
            declaration = self._declaration(chunk, match, _doc_before(text, match.start()))
            if declaration is None:
                continue
            self.declarations[declaration.name] = declaration
            if match.group("export"):
                self.exported[declaration.name] = None
        self._export_lists()

    def _export_lists(self) -> None:
        text = self.text
        for match in _EXPORT_LIST.finditer(text):
            open_brace = text.index("{", match.start())
            close = _match_bracket(text, open_brace, "{", "}")
            inner = text[open_brace + 1 : close - 1]
            specifier = ""
            from_match = re.match(r"\s*from\s+['\"]([^'\"]+)['\"]", text[close:])
            if from_match:
                specifier = from_match.group(1)
            for item in inner.split(","):
                name = item.strip()
                if not name:
                    continue
                if name.startswith("type "):
                    name = name[len("type ") :].strip()
                # `A as B` exports B under B.
                name = name.split(" as ")[-1].strip()
                self.reexports[name] = specifier
                if not specifier:
                    self.exported[name] = None
        for match in _EXPORT_STAR.finditer(text):
            from_match = re.match(r"\s*['\"]([^'\"]+)['\"]", text[match.end() :])
            if from_match:
                self.stars.append(from_match.group(1))

    def _declaration(self, chunk: str, match: re.Match[str], doc: str) -> Declaration | None:
        kind = match.group("kind")
        rest = chunk[match.end("kind") - match.start() :].lstrip()
        name_match = re.match(r"([A-Za-z_$][\w$]*)", rest)
        if not name_match:
            return None
        name = name_match.group(1)
        after = rest[name_match.end() :]
        generics, generics_end = _generic(after, 0)
        generics = _tight_generics(generics)
        signature = ""
        members: list[Member] = []
        body = ""
        params_text = ""
        if kind == "function":
            open_paren = after.find("(")
            if open_paren < 0:
                return None
            params_end = _match_bracket(after, open_paren, "(", ")")
            params = after[open_paren + 1 : params_end - 1]
            params_text = _one_line(_strip_comments(params))
            tail = after[params_end:]
            returns = ""
            tail_match = re.match(r"\s*:\s*([^{;]+?)\s*(?=\{|;|\Z)", tail, re.S)
            if tail_match:
                returns = tail_match.group(1).strip()
            prefix = "async function" if match.group("async") else "function"
            signature = f"{prefix} {name}{generics}({params_text})"
            if returns:
                signature += f": {returns}"
        elif kind in ("interface", "class", "enum"):
            brace = after.find("{")
            if brace < 0:
                return None
            body_end = _match_bracket(after, brace, "{", "}")
            body = after[brace + 1 : body_end - 1]
            clause = _tight_generics(after[generics_end:brace].strip())
            signature = f"{kind} {name}{generics}"
            if clause:
                signature += f" {clause}"
            members = self._members(body) if kind != "enum" else _enum_members(body)
        elif kind == "type":
            end = _type_end(after, generics_end)
            value = after[generics_end:end].strip().lstrip("=").strip().rstrip(";").strip()
            signature = f"type {name}{generics} = {_one_line(value).lstrip('| ')}"
        else:
            end = _statement_end(after, 0)
            text = after[:end].strip().rstrip(";").strip()
            if text.startswith(":"):
                head, _, tail = text[1:].partition("=")
                signature = f"const {name}: {_one_line(head.strip())}"
                literal = _one_line(tail.strip())
                if literal and len(literal) <= 60:
                    signature += f" = {literal}"
            else:
                value = text.lstrip("=").strip()
                signature = f"const {name}"
                if value.startswith("{") and value.endswith("}"):
                    # An object literal: what it holds is its members.
                    body = value[1:-1]
                    members = self._members(body, statements=True)
                else:
                    literal = _one_line(value)
                    if literal and len(literal) <= 80:
                        signature += f" = {literal}"
        return Declaration(
            name=name,
            kind=kind,
            signature=signature,
            doc=doc,
            body=body.strip("\n"),
            params=params_text,
            members=members,
            exported_from=self.name,
        )

    def _members(self, body: str, statements: bool = False) -> list[Member]:
        """The members of an interface or a class body.

        A member starts at the top level of the body — a parameter line
        is inside one, however much it looks like a member — and runs to
        the next member.

        ``statements`` says the body is an object literal rather than a
        declaration: there a word like ``default`` is a statement of a
        ``switch`` and not a member. In a declaration it is a name —
        ``default`` is a field of igni's model registry, and a reserved
        word is a fine name for a field.
        """
        depths = _line_depths(body)
        starts: list[re.Match[str]] = []
        seen_lines: set[int] = set()
        for match in _MEMBER_START.finditer(body):
            line = body.count("\n", 0, match.start())
            if line in seen_lines:
                # One member a line: a parameter on the same line is part
                # of it, not a member of its own.
                continue
            if line < len(depths) and depths[line] != 0:
                continue
            seen_lines.add(line)
            starts.append(match)
        out: list[Member] = []
        for index, match in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(body)
            chunk = body[match.start() : end]
            doc = _doc_before(body, match.start())
            modifiers = match.group(1)
            name = match.group(2)
            if statements and name in _KEYWORDS:
                continue
            rest = chunk[match.end() - match.start() :]
            if _is_internal(doc):
                # Marked internal: not part of the surface a reader is
                # looking at, and nothing is owed about it.
                continue
            if re.search(r"(?:^|\s)(get|set)\s+$", modifiers):
                out.append(Member(name, "accessor", _accessor_type(rest, modifiers), doc))
            elif rest.lstrip().startswith("="):
                out.append(Member(name, "field", _arrow_type(rest), doc))
            elif rest.lstrip().startswith("(") or rest.lstrip().startswith("<"):
                out.append(Member(name, "method", _method_type(rest), doc))
            else:
                out.append(Member(name, "field", _field_type(rest), doc))
            out[-1].optional = "?" in match.group(0)
        return out


def _enum_members(body: str) -> list[Member]:
    """The members of an enum: a name and the value it is given."""
    out: list[Member] = []
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        # A member ends with its comma, and may be followed by a comment.
        stripped = _strip_comments(stripped).strip().rstrip(",").strip()
        match = re.match(r"([A-Za-z_$][\w$]*)\s*(?:=\s*(.+))?$", stripped)
        if match:
            out.append(Member(match.group(1), "member", match.group(2) or "", ""))
    return out


def _strip_comments(text: str) -> str:
    """A fragment without its comments — and with its strings intact."""
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in "'\"":
            quote = char
            out.append(char)
            index += 1
            while index < length:
                out.append(text[index])
                if text[index] == "\\":
                    index += 1
                    if index < length:
                        out.append(text[index])
                        index += 1
                    continue
                if text[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if char == "/" and index + 1 < length:
            following = text[index + 1]
            if following == "/":
                while index < length and text[index] != "\n":
                    index += 1
                continue
            if following == "*":
                end = text.find("*/", index + 2)
                index = length if end < 0 else end + 2
                out.append(" ")
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _field_type(rest: str) -> str:
    """A field's type: what is between its colon and its end."""
    text = rest.strip()
    if ":" not in text:
        return ""
    _, _, type_ = text.partition(":")
    type_ = _strip_comments(type_).strip()
    # The type ends at its semicolon, at the end of its line, or at the
    # ``=`` that gives it a value; what follows is the next member's
    # documentation.
    depth = 0
    for index, char in enumerate(type_):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif depth == 0 and char in ";=\n":
            if char == "=" and type_[index : index + 2] == "=>":
                # An arrow, not a value: the type goes on.
                continue
            type_ = type_[:index]
            break
    return _tight_generics(type_.strip())


#: Words that are not members of anything: a statement, not a declaration.
_KEYWORDS = frozenset(
    {
        "await",
        "break",
        "case",
        "catch",
        "class",
        "const",
        "continue",
        "default",
        "delete",
        "do",
        "else",
        "export",
        "extends",
        "finally",
        "for",
        "function",
        "if",
        "import",
        "in",
        "instanceof",
        "let",
        "new",
        "of",
        "return",
        "super",
        "switch",
        "this",
        "throw",
        "try",
        "typeof",
        "var",
        "void",
        "while",
        "yield",
    }
)


def _method_type(rest: str) -> str:
    """A method's type: its parameters and what it returns."""
    text = rest.strip()
    open_paren = text.find("(")
    if open_paren < 0:
        return ""
    try:
        params_end = _match_bracket(text, open_paren, "(", ")")
    except ReferenceError_:
        return ""
    params = text[open_paren + 1 : params_end - 1]
    tail = text[params_end:]
    returns = ""
    arrow = re.match(r"\s*=>\s*([^{;]+?)\s*(?=\{|;|\Z)", tail, re.S)
    if arrow:
        returns = arrow.group(1).strip()
    else:
        tail_match = re.match(r"\s*:\s*([^{;]+?)\s*(?=\{|;|\Z)", tail, re.S)
        if tail_match:
            returns = tail_match.group(1).strip()
    one = f"({_one_line(_strip_comments(params))})"
    return f"{one} => {returns}" if returns else one


def _arrow_type(rest: str) -> str:
    """A field's own arrow function: ``= (value: T) => void``."""
    text = rest.strip()
    if text.startswith("="):
        text = text[1:].strip()
    return _method_type(text)


def _accessor_type(rest: str, modifiers: str) -> str:
    """A getter's or a setter's type: what it reads, or what it is given."""
    text = rest.strip()
    open_paren = text.find("(")
    if open_paren < 0:
        return ""
    try:
        params_end = _match_bracket(text, open_paren, "(", ")")
    except ReferenceError_:
        return ""
    if re.search(r"(?:^|\s)set\s+$", modifiers):
        params = _strip_comments(text[open_paren + 1 : params_end - 1]).strip()
        return params
    tail = text[params_end:]
    tail_match = re.match(r"\s*:\s*([^{;]+?)\s*(?:\{|;|$)", tail, re.S)
    return tail_match.group(1).strip() if tail_match else ""


# ── Parameters ─────────────────────────────────────────────────────


def _skip_string(text: str, index: int) -> int:
    """The index just past the string that starts at ``index``."""
    quote = text[index]
    index += 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return index


def _top_level(text: str, separator: str) -> list[int]:
    """The indexes of every ``separator`` that is not inside a bracket.

    A bracket is a bracket of any kind, and a string is a string: the
    comma in ``Record<string, number>`` and the one in ``"a, b"`` are
    not separators.
    """
    out: list[int] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "'\"`":
            index = _skip_string(text, index)
            continue
        if text.startswith("=>", index):
            index += 2
            continue
        if char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth -= 1
        elif char == separator and depth == 0:
            out.append(index)
        index += 1
    return out


def _split_top_level(text: str, separator: str = ",") -> list[str]:
    """``text`` split on a separator that is not inside a bracket."""
    out: list[str] = []
    start = 0
    for index in _top_level(text, separator):
        out.append(text[start:index])
        start = index + 1
    out.append(text[start:])
    return out


def _partition_top_level(text: str, separator: str) -> tuple[str, str, str]:
    """``text`` at its first top-level ``separator``: before, it, after."""
    indexes = _top_level(text, separator)
    if not indexes:
        return text, "", ""
    index = indexes[0]
    return text[:index], separator, text[index + 1 :]


def object_pattern_properties(pattern: str) -> list[tuple[str, str, bool]]:
    """The properties an object pattern takes: its name, its default, its rest.

    A pattern renames as it binds: ``{ base: givenBase }`` takes the
    property ``base`` and calls it ``givenBase`` in the body. The table
    names the property, which is what a caller writes.
    """
    inner = pattern.strip()[1:-1]
    out: list[tuple[str, str, bool]] = []
    for part in _split_top_level(inner):
        part = part.strip()
        if not part:
            continue
        rest = part.startswith("...")
        if rest:
            part = part[3:].strip()
        head, sep, tail = _partition_top_level(part, "=")
        default = tail.strip() if sep else ""
        name, _, _local = _partition_top_level(head, ":")
        out.append((name.strip(), default, rest))
    return out


def signature_parameters(
    text: str, prop_types: dict[str, dict[str, tuple[str, bool]]] | None = None
) -> list[Parameter]:
    """The parameters a TypeScript signature's parentheses hold.

    A parameter is its name, its type, and the default it is given when
    the source writes one. A name with a ``?`` is optional: the caller
    may leave it out.

    A parameter written as a pattern — ``{ variant, size }`` — is a
    component's props. The props are what a caller writes, so the props
    are what the table lists; their types come from the interface the
    pattern is annotated with, when the module declares one.
    """
    out: list[Parameter] = []
    for part in _split_top_level(text):
        part = part.strip()
        if not part:
            continue
        head, _, tail = _partition_top_level(part, ":")
        head = head.strip()
        if head.startswith("{") and head.endswith("}"):
            known = (prop_types or {}).get(tail.strip(), {})
            for name, default, rest in object_pattern_properties(head):
                type_, optional = known.get(name, ("", not default))
                out.append(
                    Parameter(
                        name,
                        type_,
                        default,
                        optional=optional and not rest,
                        rest=rest,
                    )
                )
            continue
        # A parameter may carry several modifiers — ``protected readonly
        # link`` — and the name a caller writes is what is left once
        # every one of them is gone.
        name = re.sub(
            r"^(?:(?:public|private|protected|readonly|override|static|declare|async)\s+)+",
            "",
            head,
        ).strip()
        optional = name.endswith("?")
        name = name.rstrip("?").strip()
        if name.startswith("..."):
            name = name[3:].strip()
        type_, _, default = _partition_top_level(tail, "=")
        out.append(Parameter(name, type_.strip(), default.strip(), optional))
    return out


def member_parameters_text(member: Member) -> str:
    """The parameters of a member's signature, as its type spells them."""
    text = member.type.strip()
    if not text.startswith("("):
        return ""
    try:
        end = _match_bracket(text, 0, "(", ")")
    except ReferenceError_:
        return ""
    return text[1 : end - 1]


def parameter_table(params: list[Parameter], meanings: dict[str, str]) -> list[str]:
    """The table of a signature's parameters, as the reference pages show it.

    A parameter the JSDoc does not document is said to be undocumented:
    the generator does not guess what a parameter is.
    """
    rows: list[tuple[str, str, str, str]] = []
    for param in params:
        if param.default:
            default = code(param.default)
        elif param.optional or param.rest:
            default = "optional"
        else:
            default = "required"
        rows.append(
            (
                param.name,
                code(param.type) if param.type else "—",
                default,
                meanings.get(param.name) or UNDOCUMENTED,
            )
        )
    return table(rows)


class TsReference:
    """The reference pages of one npm package's public names.

    A name is documented where it is *declared*, not where it is
    re-exported: ``index.ts`` of ``@ignite-ember/ui-react`` re-exports
    sixty names from nine files, and each of them is read from the file
    that declares it.
    """

    def __init__(
        self,
        package: str,
        src: Path,
        areas: list[Area],
        link: Callable[[str], str | None] | None = None,
        entries: tuple[str, ...] = ("index.ts",),
    ) -> None:
        self.package = package
        self.src = src
        self.areas = areas
        self.link = link
        #: The package's entry points: the files whose exports are its
        #: public surface — the main one, and any subpath it publishes.
        self.entries = entries
        self.modules: dict[str, Module] = {}
        self.placed: dict[str, list[Declaration]] = {}
        #: Every documented name → (the area's slug, its anchor).
        self.anchors_of: dict[str, tuple[str, str]] = {}
        self._load()
        #: Every name the package publishes.
        self.public: set[str] = {name for entry in self.entries for name in self.entry_names(entry)}

    # ── Reading the sources ──

    def _load(self) -> None:
        pending: list[str] = list(self.entries)
        for area in self.areas:
            pending.extend(area.sources)
        while pending:
            name = pending.pop(0)
            if name in self.modules:
                continue
            path = self.src / name
            if not path.exists():
                raise ReferenceError_(f"{self.package}: no source file {name}")
            module = Module(path, name)
            self.modules[name] = module
            for specifier in [*module.stars, *module.reexports.values()]:
                if not specifier:
                    continue
                target = self.target(name, specifier)
                if target and target not in self.modules:
                    pending.append(target)

    def target(self, module_name: str, specifier: str) -> str:
        """The file a ``from "./x"`` names, relative to the package's ``src``.

        The source names its own neighbours the way Node will find them
        after the build — ``./bridge.js`` for ``bridge.ts`` — because the
        emitted JavaScript has to find its neighbours by name. The
        declarations are in the TypeScript, so that is what is looked
        for.
        """
        if not specifier.startswith("."):
            return ""
        base = Path(module_name).parent
        stem = (base / specifier[2:]).as_posix()
        if stem.endswith((".js", ".jsx")):
            stem = stem.rsplit(".", 1)[0]
        for candidate in (
            stem + ".ts",
            stem + ".tsx",
            stem + "/index.ts",
            stem + "/index.tsx",
        ):
            if (self.src / candidate).exists():
                return candidate
        return ""

    def exported_names(self, module: Module, seen: set[str] | None = None) -> list[str]:
        """The names a module exports, in the order it exports them.

        Two modules that export each other whole are a cycle, not a
        reason to recurse for ever: each is read once.
        """
        seen = seen if seen is not None else set()
        if module.name in seen:
            return []
        seen.add(module.name)
        out: list[str] = []
        for name in [*module.exported, *module.reexports]:
            if name not in out:
                out.append(name)
        for specifier in module.stars:
            target = self.target(module.name, specifier)
            if not target or target not in self.modules:
                continue
            for name in self.exported_names(self.modules[target], seen):
                if name not in out:
                    out.append(name)
        return out

    def entry_names(self, entry: str | None = None) -> list[str]:
        """The names an entry point exports: the package's own, or a subpath's."""
        module = self.modules.get(entry or self.entries[0])
        if module is None:
            return []
        return self.exported_names(module)

    def resolve(
        self, module: Module, name: str, seen: set[tuple[str, str]] | None = None
    ) -> Declaration | None:
        """The declaration of a name a module exports."""
        seen = seen if seen is not None else set()
        key = (module.name, name)
        if key in seen:
            return None
        seen.add(key)
        declaration = module.declarations.get(name)
        if declaration is not None:
            return declaration
        specifier = module.reexports.get(name)
        if specifier:
            target = self.target(module.name, specifier)
            if target and target in self.modules:
                return self.resolve(self.modules[target], name, seen)
            return None
        for star in module.stars:
            target = self.target(module.name, star)
            if target and target in self.modules:
                found = self.resolve(self.modules[target], name, seen)
                if found is not None:
                    return found
        return None

    # ── The pages ──

    def _visible(self) -> set[str]:
        """The public names that are documented: not marked ``@internal``."""
        out: set[str] = set()
        for entry in self.entries:
            module = self.modules.get(entry)
            if module is None:
                continue
            for name in self.exported_names(module):
                if name not in self.public:
                    continue
                declaration = self.resolve(module, name)
                if declaration is None or _is_internal(declaration.doc):
                    continue
                out.add(name)
        return out

    def place(self) -> dict[str, list[Declaration]]:
        """Every public name, and the area it is on.

        A public name no area takes is an error, and so is an area that
        takes none: the pages are then a description of the package that
        is true of all of it.
        """
        if self.placed:
            return self.placed
        placed = {area.slug: self.entries_of(area) for area in self.areas}
        covered = {entry.name for entries in placed.values() for entry in entries}
        unplaced = sorted(self._visible() - covered)
        if unplaced:
            raise ReferenceError_(f"public names no reference page takes: {unplaced}")
        empty = [slug for slug, entries in placed.items() if not entries]
        if empty:
            raise ReferenceError_(f"reference pages with no public name: {empty}")
        self.placed = placed
        self.anchors_of = {
            entry.name: (slug, self.anchor(entry.name))
            for slug, entries in placed.items()
            for entry in entries
        }
        return placed

    def anchors(self) -> dict[str, tuple[str, str]]:
        """Every documented name → (the area's slug, its anchor)."""
        self.place()
        return dict(self.anchors_of)

    def entries_of(self, area: Area) -> list[Declaration]:
        """The declarations on a page, in the order the modules export them.

        Only names the package publishes are on it: a module's own
        helper is not public just because it is exported.
        """
        out: list[Declaration] = []
        seen: set[str] = set()
        for source in area.sources:
            module = self.modules.get(source)
            if module is None:
                continue
            for name in self.exported_names(module):
                if name in seen or name not in self.public:
                    continue
                declaration = self.resolve(module, name)
                if declaration is None or _is_internal(declaration.doc):
                    continue
                seen.add(name)
                out.append(declaration)
        return out

    def page(self, area: Area) -> tuple[str, int]:
        """The Markdown of one area's page, and how many names it left undocumented."""
        self.place()
        entries = self.placed[area.slug]
        missing = sum(1 for entry in entries if not _summary(entry.doc))
        out: list[str] = []
        if area.note:
            out += [area.note, ""]
        out += [
            "Read from the source: every name below, its signature, its JSDoc, and — "
            "for a type or a class — its own members.",
            "",
        ]
        out += ["| Name | Kind | Defined in | What it is |", "|---|---|---|---|"]
        for entry in entries:
            summary = _summary(entry.doc) or "—"
            out.append(
                f"| [`{entry.name}`](#{self.anchor(entry.name)}) | {entry.kind} "
                f"| `{entry.exported_from}` | {summary} |"
            )
        out.append("")
        for entry in entries:
            out += self._entry(entry)
        return "\n".join(out), missing

    def anchor(self, name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    def _entry(self, entry: Declaration) -> list[str]:
        out = [f"## {entry.name}", ""]
        out += ["```typescript", entry.signature, "```", ""]
        out += parameter_table(
            signature_parameters(entry.params, self._prop_types(entry)), jsdoc_params(entry.doc)
        )
        doc = _jsdoc(strip_jsdoc_params(entry.doc))
        if doc:
            out += [doc, ""]
        out += self._also(entry)
        if entry.members:
            out += self._member_table(entry.members)
            out.append("")
            out += self._member_parameters(entry)
        return out

    def _prop_types(self, entry: Declaration) -> dict[str, dict[str, tuple[str, bool]]]:
        """The interfaces a declaration's module declares, and their fields.

        A component's props are written as a pattern, and a pattern says
        no type of its own: the type is the interface it is annotated
        with. This is where those types are read from.
        """
        module = self.modules.get(entry.exported_from)
        if module is None:
            return {}
        out: dict[str, dict[str, tuple[str, bool]]] = {}
        for name, declaration in module.declarations.items():
            if declaration.kind != "interface":
                continue
            out[name] = {
                member.name: (member.type, member.optional) for member in declaration.members
            }
        return out

    def _member_parameters(self, entry: Declaration) -> list[str]:
        """The parameters of a declaration's methods, a table each.

        A method's own JSDoc says what each of its parameters is; the
        table says it where a reader looks for it.
        """
        out: list[str] = []
        for member in entry.members:
            if member.kind != "method":
                continue
            params = signature_parameters(member_parameters_text(member), self._prop_types(entry))
            if not params:
                continue
            out += [f"### {entry.name}.{member.name}()", ""]
            out += parameter_table(params, jsdoc_params(member.doc))
        return out

    def _member_table(self, members: list[Member]) -> list[str]:
        """The table of a declaration's members.

        A column for what a member is, but only when a member says it:
        a table of dashes is a table that says nothing. The Python
        reference drops its description column the same way.
        """
        rows = []
        documented = False
        for member in members:
            type_ = f"`{member.type}`" if member.type else "—"
            summary = _summary(member.doc)
            if summary:
                documented = True
            rows.append(f"| `{member.name}` | {member.kind} | {type_} | {summary} |")
        if not documented:
            # No member says what it is: no column to say it in.
            rows = [row.rsplit("|", 2)[0].rstrip() + " |" for row in rows]
            return ["| Member | Kind | Type |", "|---|---|---|", *rows]
        return ["| Member | Kind | Type | What it is |", "|---|---|---|---|", *rows]

    def _also(self, entry: Declaration) -> list[str]:
        """The other public names this one's signature names, linked to where they are."""
        if self.link is None:
            return []
        out: list[tuple[str, str]] = []
        for name in _IDENT.findall(entry.signature):
            if name == entry.name or name in [n for n, _ in out]:
                continue
            target = self.link(name)
            if target is None:
                continue
            out.append((name, target))
        if not out:
            return []
        return ["**Also** " + ", ".join(f"[`{n}`]({t})" for n, t in out) + ".", ""]


__all__ = [
    "Area",
    "Declaration",
    "Member",
    "Module",
    "ReferenceError_",
    "TsReference",
]

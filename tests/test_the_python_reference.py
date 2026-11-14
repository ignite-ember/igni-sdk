"""``PythonReference`` reads a package into pages: pinned on a small package written here.

The checked-in pages only show that the two real packages come out as they did
last time. Each rule of the reader is pinned here on a package built to hold
exactly the case: the page a function, a class, an enum, an exception and a
constant each get, the tables under them, and the errors a package that does
not fit its areas raises.
"""

from __future__ import annotations

import enum
import importlib
import sys
import textwrap
import typing
from collections.abc import Iterator
from pathlib import Path

import pytest

from tools.py_reference import (
    PythonReference,
    ReferenceError_,
    annotation_text,
    docstring_markdown,
    signature_text,
    stable_repr,
)
from tools.reference_area import Area

CORE = '''
"""Core."""
from __future__ import annotations

import dataclasses
import enum
import functools
import typing
from typing import Literal

import pydantic


def run(a: int, b: str = "x", *args: int, flag: bool = False, **extra: str) -> str | None:
    """Run it.

    Args:
        a: The first one,
            over two lines.
        flag: Whether to flag it.

    Returns:
        Nothing worth a table.
    """


async def wait(seconds: float, /, label: str = "l") -> None:
    """Wait."""


def settle(a: int, _env_file: str | None = None, *, _cli_parse_args: bool = False, b: int = 0) -> None:
    """Settle.

    Args:
        a: The one.
        b: The other.
    """


class Store(typing.Protocol):
    """Where it is kept.

    Args:
        args: Taken by a concrete store's constructor.
    """

    def fetch(self, key: str) -> str:
        """Fetch."""
        ...


def bare(x):
    return x


class Plain:
    """A plain class.

    Args:
        size: How big.
    """

    def __init__(self, size: int, name: str = "n") -> None:
        pass

    def go(self, to: str) -> int:
        """Go.

        Args:
            to: Where.
        """

    async def later(self) -> None:
        """Later."""

    @property
    def width(self) -> int:
        """The width."""

    @functools.cached_property
    def height(self) -> int:
        """The height."""

    @classmethod
    def make(cls, size: int) -> Plain:
        """Make one."""

    @staticmethod
    def helper(x: int) -> int:
        """Help."""

    def undocumented(self) -> None:
        pass

    def _private(self) -> None:
        """Hidden."""


class Child(Plain):
    pass


class Model(pydantic.BaseModel):
    """A model."""

    name: str = pydantic.Field(description="The name\\nof it | really.")
    kind: Literal["a", "b"] = "a"
    items: list[int] = pydantic.Field(default_factory=list)
    required_one: int


class Quiet(pydantic.BaseModel):
    """No field says what it is."""

    one: int = 1
    two: str | None = None


class Sub(Model):
    """Adds one."""

    extra: int = 0


@dataclasses.dataclass
class Rec:
    """A record."""

    a: int
    b: str = "x"
    c: list[int] = dataclasses.field(default_factory=list)
    _hidden: int = 0
    d: int = dataclasses.field(default=0, init=False, repr=False)


class Mode(enum.Enum):
    """A mode."""

    FAST = "fast"
    SLOW = 2


class Boom(Exception):
    """It broke."""


class NoDoc:
    pass


LIMIT = 30
"""How many, at most."""

TAGS = frozenset({"b", "a"})
# "not a docstring": this is a comment
BARE = 1  # "neither is this"
'''

TESTING = '''
"""Testing."""
from pkg.minting import SECRET, Minter

__all__ = ["SECRET", "Minter"]
'''

MINTING = '''
class Minter:
    """Mints."""


SECRET: str = "s"
"""A typed constant, documented."""
'''

INIT = '''
"""Package."""
from pkg.core import (
    BARE, LIMIT, TAGS, Boom, Child, Mode, Model, NoDoc, Plain, Quiet, Rec, Store, Sub, bare, run, settle,
    wait,
)

__all__ = [
    "BARE", "LIMIT", "TAGS", "Boom", "Child", "Mode", "Model", "NoDoc", "Plain", "Quiet", "Rec",
    "Store", "Sub", "bare", "run", "settle", "wait", "run",
]
'''


@pytest.fixture(scope="module")
def package(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    root = tmp_path_factory.mktemp("pkgroot")
    pkg = root / "pkg"
    (pkg / "testing").mkdir(parents=True)
    (pkg / "__init__.py").write_text(textwrap.dedent(INIT), encoding="utf-8")
    (pkg / "core.py").write_text(textwrap.dedent(CORE), encoding="utf-8")
    (pkg / "minting.py").write_text(textwrap.dedent(MINTING), encoding="utf-8")
    (pkg / "testing" / "__init__.py").write_text(textwrap.dedent(TESTING), encoding="utf-8")
    sys.path.insert(0, str(root))
    try:
        yield "pkg"
    finally:
        sys.path.remove(str(root))
        for name in [m for m in sys.modules if m == "pkg" or m.startswith("pkg.")]:
            del sys.modules[name]
        importlib.invalidate_caches()


def reference(package: str, areas: list[Area] | None = None) -> PythonReference:
    areas = areas or [
        Area("everything", "Everything", ("pkg.core", "pkg:LIMIT", "pkg:TAGS", "pkg:BARE")),
        Area("minting", "Minting", ("pkg.minting", "pkg.testing:SECRET")),
    ]
    return PythonReference(
        package,
        ("pkg", "pkg.testing"),
        areas,
        lambda name: "/docs/plain" if name == "Plain" else None,
    )


@pytest.fixture(scope="module")
def page(package: str) -> str:
    ref = reference(package)
    body, _ = ref.page(ref.areas[0])
    return body


def section(page: str, heading: str) -> str:
    """What a page says under one ``##`` or ``###`` heading, up to the next one."""
    marker = f"\n{heading}\n"
    start = page.index(marker) + len(marker)
    ends = [i for i in (page.find("\n## ", start), page.find("\n### ", start)) if i != -1]
    return page[start : min(ends) if ends else len(page)]


# ── the errors of a package that does not fit its areas ──


def test_a_public_name_no_area_takes_is_an_error_that_names_it(package: str) -> None:
    with pytest.raises(ReferenceError_, match=r"pkg\.run \(pkg\.core\)"):
        reference(package, [Area("minting", "Minting", ("pkg.minting", "pkg.testing:SECRET"))])


def test_an_area_with_no_public_name_is_an_error_that_names_it(package: str) -> None:
    areas = [
        Area("everything", "Everything", ("pkg.core", "pkg:LIMIT", "pkg:TAGS", "pkg:BARE")),
        Area("minting", "Minting", ("pkg.minting", "pkg.testing:SECRET")),
        Area("ghost", "Ghost", ("pkg.nothing",)),
    ]
    with pytest.raises(ReferenceError_, match=r"no public name: \['ghost'\]"):
        reference(package, areas)


def test_an_area_names_a_module_by_prefix_but_not_by_a_shared_beginning(package: str) -> None:
    areas = [
        Area("everything", "Everything", ("pkg.cor", "pkg:LIMIT", "pkg:TAGS", "pkg:BARE")),
        Area("minting", "Minting", ("pkg.minting", "pkg.testing:SECRET")),
    ]
    with pytest.raises(ReferenceError_, match="no reference page takes"):
        reference(package, areas)


def test_a_name_exported_twice_by_one_module_is_one_name(package: str) -> None:
    ref = reference(package)
    names = [e.name for e in ref.entries if e.exported_from == "pkg"]
    assert names.count("run") == 1 and len(names) == len(set(names))


def test_anchors_name_the_page_and_the_heading_of_every_documented_name(package: str) -> None:
    anchors = reference(package).anchors()
    assert anchors["run"] == ("everything", "run")
    assert anchors["Plain"] == ("everything", "plain")
    assert anchors["Minter"] == ("minting", "minter")
    assert anchors["LIMIT"] == ("everything", "limit")


# ── the page: names table and a section a name ──


def test_the_page_opens_with_where_to_import_from_and_a_table_of_names(page: str) -> None:
    lines = page.split("\n")
    assert lines[0] == (
        "Read from the code: every public name below, its signature and its docstring. "
        "Import `pkg` — defined in `pkg`, `pkg.core`."
    )
    assert "| Name | What it is |" in lines
    assert "| [`run`](#run) | Run it. |" in lines
    assert "| [`Plain`](#plain) | A plain class. |" in lines
    assert "| [`LIMIT`](#limit) | How many, at most. |" in lines


def test_a_name_with_no_docstring_has_a_dash_and_is_counted(package: str) -> None:
    ref = reference(package)
    body, undocumented = ref.page(ref.areas[0])
    assert "| [`bare`](#bare) | — |" in body.split("\n")
    assert "| [`NoDoc`](#nodoc) | — |" in body.split("\n")
    # bare, Child, NoDoc, BARE, TAGS, Plain.undocumented
    assert undocumented == 6


def test_a_summary_is_the_first_paragraph_and_is_cut_at_two_hundred_characters() -> None:
    from tools.py_reference import _summary

    long = "word " * 80

    out = _summary("One :class:`~pkg.X` and ``y`` | z.\n\nSecond paragraph.")
    assert out == "One `pkg.X` and `y` \\| z."
    cut = _summary(long)
    assert cut.endswith("…") and len(cut) <= 201
    assert _summary(None) == "" and _summary("") == ""


# ── C6: a table of parameters under every signature, the meanings read from Args: ──


def rows(text: str) -> list[list[str]]:
    """The rows of the first table in ``text``: the cells, split on unescaped pipes."""
    lines = [line for line in text.strip().split("\n") if line.startswith("|")]
    return [[c.strip() for c in line.strip("|").replace("\\|", "\0").split("|")] for line in lines]


def test_a_function_has_a_parameter_table_with_type_default_and_the_meaning_from_args(
    page: str,
) -> None:
    table = rows(section(page, "## run()").split("```\n", 1)[1])
    assert table[0] == ["Parameter", "Type", "Default", "Meaning"]
    by_name = {row[0]: row for row in table[2:]}
    assert by_name["`a`"] == [
        "`a`",
        "`int`",
        "required",
        "The first one, over two lines.",
    ]
    assert by_name["`b`"][1:] == ["`str`", "`'x'`", "Not documented yet."]
    assert by_name["`flag`"][1:] == ["`bool`", "`False`", "Whether to flag it."]


def test_a_parameter_with_no_annotation_has_a_dash_for_its_type(page: str) -> None:
    table = rows(section(page, "## bare()").split("```\n", 1)[1])
    assert table[2] == ["`x`", "—", "required", "Not documented yet."]


def test_the_args_section_is_not_said_twice_but_the_rest_of_the_docstring_is(page: str) -> None:
    body = section(page, "## run()")
    assert "Args:" not in body
    assert body.count("The first one") == 1
    assert "Run it." in body and "Nothing worth a table." in body


def test_a_method_has_its_own_table_without_self_or_cls(page: str) -> None:
    go = rows(section(page, "### Plain.go()").split("```\n", 1)[1])
    assert [row[0] for row in go[2:]] == ["`to`"] and go[2][3] == "Where."
    make = rows(section(page, "### Plain.make()").split("```\n", 1)[1])
    assert [row[0] for row in make[2:]] == ["`size`"]
    helper = rows(section(page, "### Plain.helper()").split("```\n", 1)[1])
    assert [row[0] for row in helper[2:]] == ["`x`"]


def test_a_method_with_no_parameters_has_no_table(page: str) -> None:
    assert "| Parameter" not in section(page, "### Plain.later()")
    assert "| Parameter" not in section(page, "### Plain.undocumented()")


def test_a_class_with_no_field_table_gets_its_constructors_table_from_the_class_docstring(
    page: str,
) -> None:
    table = rows(section(page, "## Plain").split("```\n", 1)[1])
    assert table[2:] == [
        ["`size`", "`int`", "required", "How big."],
        ["`name`", "`str`", "`'n'`", "Not documented yet."],
    ]


def test_a_class_with_a_field_table_has_no_constructor_table(page: str) -> None:
    for name in ("Model", "Quiet", "Rec"):
        assert "| Parameter" not in section(page, f"## {name}")
        assert "| Field" in section(page, f"## {name}")


def test_a_star_parameter_is_shown_with_its_stars_and_is_not_required(page: str) -> None:
    by_name = {row[0]: row for row in rows(section(page, "## run()").split("```\n", 1)[1])[2:]}
    assert by_name["`*args`"][1:3] == ["`int`", "—"]
    assert by_name["`**extra`"][1:3] == ["`str`", "—"]
    assert "`args`" not in by_name and "`extra`" not in by_name


# ── C7: every name says what it is: fields, members and constants ──


def table_of(text: str) -> list[list[str]]:
    """The first table in a section, header and rows, unescaped."""
    return [[c.replace("\0", "|") for c in row] for row in rows(text)]


def test_a_pydantic_model_has_a_table_of_its_fields_with_their_descriptions(page: str) -> None:
    table = table_of(section(page, "## Model"))
    assert table[0] == ["Field", "Type", "Default", "Description"]
    assert table[2:] == [
        ["`name`", "`str`", "required", "The name of it | really."],
        ["`kind`", "`Literal['a', 'b']`", "`'a'`", ""],
        ["`items`", "`list[int]`", "factory", ""],
        ["`required_one`", "`int`", "required", ""],
    ]


def test_a_model_shows_only_the_fields_it_adds_not_the_ones_it_inherits(page: str) -> None:
    table = table_of(section(page, "## Sub"))
    assert [row[0] for row in table[2:]] == ["`extra`"]


def test_a_table_of_fields_none_of_which_says_what_it_is_has_no_description_column(
    page: str,
) -> None:
    table = table_of(section(page, "## Quiet"))
    assert table[0] == ["Field", "Type", "Default"]
    assert table[2:] == [["`one`", "`int`", "`1`"], ["`two`", "`str | None`", "`None`"]]


def test_a_dataclass_shows_its_public_fields_and_not_a_private_or_hidden_one(page: str) -> None:
    table = table_of(section(page, "## Rec"))
    assert table[2:] == [
        ["`a`", "`int`", "required"],
        ["`b`", "`str`", "`'x'`"],
        ["`c`", "`list[int]`", "factory"],
    ]


def test_an_enum_has_a_table_of_members_and_no_constructor(page: str) -> None:
    body = section(page, "## Mode")
    assert "class Mode(Enum)" in body and "Mode(" not in body.replace("class Mode(", "")
    assert table_of(body) == [
        ["Member", "Value"],
        ["---", "---"],
        ["`FAST`", "`'fast'`"],
        ["`SLOW`", "`2`"],
    ]


def test_an_exception_has_no_constructor_line_and_no_table(page: str) -> None:
    body = section(page, "## Boom")
    assert body.startswith("\n```python\nclass Boom(Exception)\n```\n") or body.startswith(
        "```python\nclass Boom(Exception)\n```\n"
    )
    assert "| " not in body
    assert "It broke." in body


def test_a_subclass_names_the_documented_base_it_links_to_and_not_the_others(page: str) -> None:
    assert "Based on [`Plain`](/docs/plain)." in section(page, "## Child")
    assert "Based on" not in section(page, "## Sub")  # Model has no link
    assert "Based on" not in section(page, "## Model")  # BaseModel has no link


def test_a_class_with_no_docstring_of_its_own_does_not_borrow_its_parents(page: str) -> None:
    child = section(page, "## Child")
    assert "A plain class" not in child
    assert "| [`Child`](#child) | — |" in page


def test_a_class_is_shown_with_its_own_public_members_labelled_by_what_they_are(
    page: str,
) -> None:
    assert "@property\nwidth: int" in section(page, "### Plain.width")
    assert "@property\nheight: int" in section(page, "### Plain.height")
    assert "@classmethod\ndef make(size: int) -> Plain" in section(page, "### Plain.make()")
    assert "@staticmethod\ndef helper(x: int) -> int" in section(page, "### Plain.helper()")
    assert "async def later() -> None" in section(page, "### Plain.later()")
    assert "def go(to: str) -> int" in section(page, "### Plain.go()")
    assert "_private" not in page and "Hidden" not in page


def test_a_member_with_no_docstring_is_shown_and_counted_but_not_invented(page: str) -> None:
    body = section(page, "### Plain.undocumented()")
    assert "def undocumented() -> None" in body
    assert body.strip().endswith("```")


def test_a_constant_is_its_name_type_and_value_with_the_docstring_that_follows_it(
    page: str,
) -> None:
    body = section(page, "## LIMIT")
    assert "LIMIT: int = 30" in body
    assert body.strip().endswith("How many, at most.")


def test_a_set_constant_is_shown_sorted(page: str) -> None:
    assert "TAGS: frozenset = frozenset({'a', 'b'})" in section(page, "## TAGS")


# ── C8: comments are comments, and a constant's docstring is found across the package ──


def test_a_constant_re_exported_from_testing_has_the_docstring_its_defining_module_gives(
    package: str,
) -> None:
    ref = reference(package)
    body, _ = ref.page(ref.areas[1])
    secret = section(body, "## SECRET")
    assert "SECRET: str = 's'" in secret
    assert secret.strip().endswith("A typed constant, documented.")
    assert "| [`SECRET`](#secret) | A typed constant, documented. |" in body.split("\n")


def test_a_string_in_a_comment_after_a_constant_is_not_its_docstring(page: str) -> None:
    assert section(page, "## TAGS").strip().endswith("```")
    assert section(page, "## BARE").strip().endswith("```")
    assert "not a docstring" not in page and "neither is this" not in page


def test_a_constant_with_no_docstring_is_counted_and_not_invented(package: str) -> None:
    ref = reference(package)
    _, undocumented = ref.page(ref.areas[0])
    _, documented_only = ref.page(ref.areas[1])
    assert undocumented >= 2 and documented_only == 0


def test_a_source_that_cannot_be_read_does_not_stop_the_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg = tmp_path / "docs_broken"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from docs_broken.zz import GOOD, PLAIN\n__all__ = ['GOOD', 'PLAIN']\n", encoding="utf-8"
    )
    (pkg / "a_syntax.py").write_text("def broken(:\n", encoding="utf-8")
    (pkg / "b_bytes.py").write_bytes(b"\xff\xfe\x00 not utf-8 \x80")
    (pkg / "zz.py").write_text(
        'GOOD = 1\n"""Found past two bad files."""\nPLAIN = 2\nb"bytes are not a docstring"\n',
        "utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        ref = PythonReference(
            "docs_broken",
            ("docs_broken",),
            [Area("only", "Only", ("docs_broken:GOOD", "docs_broken:PLAIN"))],
            lambda name: None,
        )
        body, undocumented = ref.page(ref.areas[0])
    finally:
        for name in [m for m in sys.modules if m.startswith("docs_broken")]:
            del sys.modules[name]
    assert "Found past two bad files." in section(body, "## GOOD")
    assert undocumented == 1


# ── the readers, on their own ──


class Colour(enum.Enum):
    RED = 1


def test_stable_repr_sorts_sets_and_never_prints_an_address() -> None:
    assert stable_repr({"b", "a"}) == "set({'a', 'b'})"
    assert stable_repr(frozenset({3, 1, 2})) == "frozenset({1, 2, 3})"
    many = {f"k{i}" for i in range(40)}
    items = sorted(repr(v) for v in many)
    assert stable_repr(many) == "set({" + ", ".join(items) + "})"
    assert stable_repr(set()) == "set()" and stable_repr(frozenset()) == "frozenset()"
    assert stable_repr(object).startswith("<class 'object'>")
    assert stable_repr(lambda: 0).startswith("<function ")
    assert " at 0x" not in stable_repr(lambda: 0)


def test_stable_repr_names_an_enum_member_by_type_and_name() -> None:
    assert stable_repr(Colour.RED) == "Colour.RED"


def test_stable_repr_drops_the_module_a_class_is_qualified_by() -> None:
    person = type("Person", (), {"__module__": "igni_service.tokens"})
    assert stable_repr(person) == "<class 'Person'>"
    assert stable_repr([person, 1]) == "[<class 'Person'>, 1]"
    assert stable_repr(Path) == "<class 'pathlib.Path'>"
    assert stable_repr("a.B") == "'a.B'"


def test_annotation_text_is_what_the_source_spells() -> None:
    assert annotation_text("list[int] | None") == "list[int] | None"
    assert annotation_text(int) == "int"
    assert annotation_text(Path) == "Path"
    assert annotation_text(typing.Optional[int]) == "Optional[int]"  # noqa: UP045
    assert annotation_text(typing.Literal["a"]) == "Literal['a']"
    assert annotation_text(list[int]) == "list[int]"
    assert annotation_text(__import__("inspect").Parameter.empty) == ""


def test_signature_text_marks_keyword_only_positional_only_and_star_parameters() -> None:
    def f(a, b: int = 1, /, c: str = "x", *args: int, d: bool, e: float = 0.5, **kw: str) -> None:  # type: ignore[no-untyped-def]
        pass

    params, returns = signature_text(f)
    assert (
        params == "a, b: int = 1, /, c: str = 'x', *args: int, d: bool, e: float = 0.5, **kw: str"
    )
    assert returns == "None"


def test_signature_text_puts_a_bare_star_before_keyword_only_parameters() -> None:
    def f(a: int, *, b: int = 2, c) -> int:  # type: ignore[no-untyped-def]
        return a

    assert signature_text(f) == ("a: int, *, b: int = 2, c", "int")


def test_signature_text_skips_self_or_cls_only_when_asked() -> None:
    class C:
        def m(self, x: int) -> None: ...

        @classmethod
        def k(cls, x: int) -> None: ...

    assert signature_text(C.m, skip_self=True) == ("x: int", "None")
    assert signature_text(C.m) == ("self, x: int", "None")
    assert signature_text(C.k.__func__, skip_self=True) == ("x: int", "None")  # type: ignore[attr-defined]


def test_signature_text_of_what_has_no_signature_is_an_ellipsis() -> None:
    assert signature_text(1) == ("…", "")


def test_a_default_without_an_annotation_is_written_without_spaces() -> None:
    def f(a=1, b: int = 2):  # type: ignore[no-untyped-def]
        pass

    assert signature_text(f)[0] == "a=1, b: int = 2"


def test_docstring_markdown_turns_roles_and_double_backticks_into_code() -> None:
    assert docstring_markdown("See :class:`~pkg.Thing` and :meth:`go` and ``x``.") == (
        "See `pkg.Thing` and `go` and `x`."
    )


def test_docstring_markdown_turns_an_indented_block_after_a_blank_line_into_python() -> None:
    doc = "Example:\n\n    x = 1\n\n    y = 2\n\nAfter."
    assert docstring_markdown(doc) == "Example:\n\n```python\nx = 1\n\ny = 2\n```\n\nAfter."


def test_docstring_markdown_leaves_an_indented_list_continuation_alone() -> None:
    doc = "Things:\n\n- one\n\n    continues here\n- two"
    assert docstring_markdown(doc) == doc
    assert "```" not in docstring_markdown("1. first\n\n    more of first\n2. second")


def test_docstring_markdown_of_nothing_is_nothing() -> None:
    assert docstring_markdown(None) == "" and docstring_markdown("") == ""


def test_a_parameter_named_with_a_leading_underscore_is_not_shown_in_a_signature_or_table(
    page: str,
) -> None:
    part = section(page, "## settle()")
    assert "_env_file" not in part and "_cli_parse_args" not in part
    assert "a: int, *, b: int = 0" in part
    assert [row[0] for row in rows(part.split("```\n", 1)[1])[2:]] == ["`a`", "`b`"]
    assert signature_text(lambda a, _b=1, **k: None)[0] == "a, **k"


def test_a_protocol_has_no_constructor_line_or_table(page: str) -> None:
    part = section(page, "## Store")
    assert "class Store(Protocol)" in part
    assert "Store(" not in part.replace("class Store(Protocol)", "")
    assert "| Parameter" not in part
    assert "### Store.fetch()" in page

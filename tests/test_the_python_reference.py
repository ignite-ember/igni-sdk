"""``PythonReference`` reads a package into pages: pinned on a small package written here.

The checked-in pages only show that the two real packages come out as they did
last time. Each rule of the reader is pinned here on a package built to hold
exactly the case: the page a function, a class, an enum, an exception and a
constant each get, the tables under them, and the errors a package that does
not fit its areas raises.
"""

from __future__ import annotations

import importlib
import sys
import textwrap
from collections.abc import Iterator

import pytest

from tools.py_reference import (
    PythonReference,
    ReferenceError_,
)
from tools.reference_area import Area

CORE = '''
"""Core."""
from __future__ import annotations

import dataclasses
import enum
import functools
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

    name: str = pydantic.Field(description="The  name\\nof it | really.")
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
    BARE, LIMIT, TAGS, Boom, Child, Mode, Model, NoDoc, Plain, Quiet, Rec, Sub, bare, run, wait,
)

__all__ = [
    "BARE", "LIMIT", "TAGS", "Boom", "Child", "Mode", "Model", "NoDoc", "Plain", "Quiet", "Rec",
    "Sub", "bare", "run", "wait", "run",
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

"""The Markdown helpers the site's pages are cut with, pinned on small inputs.

``tools/markdown_pages.py`` cuts a package README into pages and writes the
signatures of the reference. The checked-in pages only show that the real
READMEs come out the same as last time; these tests say what each helper does
to the input it is given, so a change that regenerates the pages cleanly is
still seen.
"""

from __future__ import annotations

from tools.markdown_pages import signature, split_params

# ── signatures: one line, or one parameter a line as black writes it ──


def test_split_params_cuts_at_top_level_commas_only() -> None:
    assert split_params("a: int, b: dict[str, int] = {}, c: tuple[int, ...] = (1, 2)") == [
        "a: int",
        "b: dict[str, int] = {}",
        "c: tuple[int, ...] = (1, 2)",
    ]


def test_split_params_keeps_a_comma_inside_a_quoted_default() -> None:
    assert split_params("a: str = 'x, y', b: str = \"p, q\"") == [
        "a: str = 'x, y'",
        'b: str = "p, q"',
    ]


def test_split_params_keeps_a_quote_escaped_inside_a_default() -> None:
    assert split_params(r"a: str = 'it\'s, ok', b: int = 1") == [
        r"a: str = 'it\'s, ok'",
        "b: int = 1",
    ]


def test_split_params_ignores_a_trailing_comma_and_empty_input() -> None:
    assert split_params("a, b,") == ["a", "b"]
    assert split_params("") == []
    assert split_params("   ") == []


def test_a_signature_that_fits_is_one_line() -> None:
    assert signature("def f", "a: int, b: int", " -> int") == "def f(a: int, b: int) -> int"
    assert signature("def f", "") == "def f()"


def test_a_signature_of_exactly_the_width_stays_on_one_line_and_one_more_wraps() -> None:
    head, tail = "def f", " -> None"
    params = "a" * (88 - len("def f()") - len(tail))
    on_line = signature(head, params, tail)
    assert len(on_line) == 88 and "\n" not in on_line
    wrapped = signature(head, params + "b", tail)
    assert wrapped == f"def f(\n    {params}b,\n) -> None"


def test_a_signature_that_is_too_long_has_one_parameter_a_line_and_trailing_commas() -> None:
    long = signature("def f", "first: int, second: dict[str, int] = {}, third: str = 'x'", "", 30)
    assert long == (
        "def f(\n    first: int,\n    second: dict[str, int] = {},\n    third: str = 'x',\n)"
    )


def test_a_signature_with_no_parameters_never_wraps() -> None:
    assert signature("def a_very_long_name_indeed", "", " -> a_very_long_return", 10) == (
        "def a_very_long_name_indeed() -> a_very_long_return"
    )

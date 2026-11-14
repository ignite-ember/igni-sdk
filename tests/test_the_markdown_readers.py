"""The Markdown helpers the site's pages are cut with, pinned on small inputs.

``tools/markdown_pages.py`` cuts a package README into pages and writes the
signatures of the reference. The checked-in pages only show that the real
READMEs come out the same as last time; these tests say what each helper does
to the input it is given, so a change that regenerates the pages cleanly is
still seen.
"""

from __future__ import annotations

import pytest

from tools.markdown_pages import (
    PageError,
    ReadmePages,
    fenced,
    signature,
    split_params,
    strip_comments,
)

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


# ── comments and heading-like lines are not markup ──


def test_a_comment_on_one_line_is_removed_and_the_text_around_it_stays() -> None:
    assert strip_comments("a <!-- x --> b\nc") == "a  b\nc"
    assert strip_comments("<!-- x --><!-- y -->z") == "z"


def test_a_comment_over_many_lines_is_removed_and_the_text_around_it_stays() -> None:
    text = "before\nlead <!-- one\n## Hidden\ntwo --> tail\nafter"
    assert strip_comments(text) == "before\nlead \n tail\nafter"


def test_a_comment_that_is_never_closed_swallows_the_rest() -> None:
    assert strip_comments("keep\n<!-- never\n## gone") == "keep"


def test_a_comment_inside_a_code_fence_is_code_and_stays() -> None:
    text = "```html\n<!-- kept -->\n```\nafter <!-- gone -->"
    assert strip_comments(text) == "```html\n<!-- kept -->\n```\nafter "


def test_a_heading_inside_a_comment_is_not_a_heading() -> None:
    pages = ReadmePages("# T\n\n<!--\n## Hidden\n-->\n\n## Real\n\nx\n", "p/README.md")
    assert [s.title for s in pages.sections] == ["Real"]
    assert [h.text for h in pages.headings] == ["T", "Real"]


def test_a_heading_like_line_inside_a_fence_is_not_a_heading() -> None:
    text = "# T\n\n## One\n\n```sh\n# a comment\n## nor this\n```\n\n~~~\n## nor this\n~~~\n"
    pages = ReadmePages(text, "p/README.md")
    assert [s.title for s in pages.sections] == ["One"]
    assert [h.text for h in pages.headings] == ["T", "One"]
    assert "## nor this" in pages.sections[0].lines


def test_fenced_says_which_lines_are_code_including_the_fences() -> None:
    lines = ["a", "```py", "b", "```", "c", "~~~", "d", "~~~", "e"]
    assert [code for _, code in fenced(lines)] == [
        False, True, True, True, False, True, True, True, False,
    ]  # fmt: skip


def test_a_fence_closes_only_on_the_same_character_and_at_least_as_long_with_nothing_after() -> (
    None
):
    lines = ["````", "```", "~~~~", "```not a close", "````", "after"]
    assert [code for _, code in fenced(lines)] == [True, True, True, True, True, False]
    lines = ["~~~", "```", "~~~", "out"]
    assert [code for _, code in fenced(lines)] == [True, True, True, False]


def test_a_fence_never_closed_swallows_the_rest_of_the_document() -> None:
    pages = ReadmePages("# T\n\n## A\n\n```\n## B\n\n## C\n", "p/README.md")
    assert [s.title for s in pages.sections] == ["A"]


def test_a_readme_with_no_title_is_an_error_that_names_the_file() -> None:
    for text in ("", "no heading\n\n## Section\n", "```\n# in code\n```\n"):
        with pytest.raises(PageError, match="packages/x/README.md has no `# title`"):
            ReadmePages(text, "packages/x/README.md")
    assert issubclass(PageError, ValueError)


def test_a_readme_is_cut_into_title_intro_sections_and_headings() -> None:
    text = "# Title\n\nIntro.\n\n## One\n\nA\n\n### Deep\n\nB\n\n## Two\n\nC\n"
    pages = ReadmePages(text, "p/README.md")
    assert pages.title == "Title"
    assert "Intro." in pages.intro and "A" not in pages.intro
    assert [s.title for s in pages.sections] == ["One", "Two"]
    assert "### Deep" in pages.sections[0].lines and "### Deep" not in pages.sections[1].lines
    assert [(h.level, h.text, h.section) for h in pages.headings] == [
        (1, "Title", None),
        (2, "One", "One"),
        (3, "Deep", "One"),
        (2, "Two", "Two"),
    ]


def test_a_second_h1_is_a_heading_of_the_section_it_is_in_not_a_new_title() -> None:
    pages = ReadmePages("# Title\n\n## One\n\n# Again\n", "p/README.md")
    assert pages.title == "Title"
    assert [(h.level, h.text, h.section) for h in pages.headings][-1] == (1, "Again", "One")


def test_trailing_hashes_of_a_heading_are_not_part_of_its_text() -> None:
    pages = ReadmePages("# Title #\n\n## One ##\n\n### Deep ###  \n", "p/README.md")
    assert pages.title == "Title"
    assert [h.text for h in pages.headings] == ["Title", "One", "Deep"]


def test_a_comment_closing_and_opening_again_on_one_line_is_all_removed() -> None:
    assert strip_comments("a <!-- x\ny --> b <!-- z --> c <!-- w\nv --> d") == "a \n b  c \n d"

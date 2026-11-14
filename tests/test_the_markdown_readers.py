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
    REPO_BLOB,
    PageError,
    ReadmePages,
    fenced,
    first_sentences,
    github_anchor,
    lift,
    plain,
    rewrite_links,
    signature,
    site_id,
    split_params,
    strip_comments,
    tidy,
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


def test_a_heading_that_ends_in_a_hash_keeps_it() -> None:
    pages = ReadmePages("# Title\n\n## Using C#\n\n### F# and C# ##\n", "p/README.md")
    assert [h.text for h in pages.headings] == ["Title", "Using C#", "F# and C#"]


# ── names of headings, as GitHub and the site give them ──


def test_plain_drops_links_backticks_and_bold_and_keeps_underscores() -> None:
    assert plain("**Bold** `check_for_update` [a link](http://x/y) ![img](p.png)") == (
        "Bold check_for_update a link img"
    )
    assert plain("  padded  ") == "padded"


def test_the_site_id_is_lowercase_hyphenated_and_trimmed() -> None:
    assert site_id("`Foo_Bar`: the (2nd) call!") == "foo-bar-the-2nd-call"
    assert site_id("--x--") == "x"
    assert site_id("[Link](#a) text") == "link-text"
    assert site_id("Über naïve") == "ber-na-ve"


def test_the_github_anchor_keeps_unicode_word_characters_and_drops_punctuation() -> None:
    assert github_anchor("Über naïve: C++ & more!") == "über-naïve-c--more"
    assert github_anchor("  A  B ") == "a--b"
    assert github_anchor("[Link](#a) text") == "link-text"
    assert github_anchor("snake_case-and-dash") == "snake_case-and-dash"


def test_duplicate_headings_are_numbered_for_github_and_nothing_else_changes() -> None:
    text = "# T\n\n## Same\n\n### Same\n\n### Same\n\n### Other\n"
    anchors = ReadmePages(text, "p/README.md").anchors()
    assert anchors == {
        "t": (None, ""),
        "same": ("Same", ""),
        "same-1": ("Same", "same"),
        "same-2": ("Same", "same"),
        "other": ("Same", "other"),
    }


# ── the first sentences of a page ──


def test_first_sentences_is_the_first_prose_paragraph_as_plain_text() -> None:
    text = (
        "# Title\n\n| a | b |\n|---|---|\n\n- item\n\nThe **first** `one`\nspans lines.\n\nSecond."
    )
    assert first_sentences(text) == "The first one spans lines."


def test_first_sentences_skips_code_and_finds_nothing_in_a_page_of_no_prose() -> None:
    assert first_sentences("```\nnot prose\n```\n\nProse.") == "Prose."
    assert first_sentences("# H\n\n| a |\n\n> quote\n") == ""
    assert first_sentences("") == ""


def test_first_sentences_returns_a_short_paragraph_whole() -> None:
    assert first_sentences("One. Two. Three.") == "One. Two. Three."
    assert first_sentences("x" * 220) == "x" * 220


def test_first_sentences_cuts_a_long_paragraph_at_a_sentence() -> None:
    first = "A" * 70 + "."
    text = first + " " + "b" * 40 + ". " + "c" * 200
    assert first_sentences(text) == first + " " + "b" * 40 + "."


def test_first_sentences_cuts_at_a_word_with_an_ellipsis_when_no_sentence_ends_late_enough() -> (
    None
):
    text = "short. " + "word " * 60
    out = first_sentences(text)
    assert out.endswith("word…") and len(out) <= 221 and "short." in out
    assert first_sentences("x" * 300) == "x" * 220 + "…"


# ── lifting headings and rewriting links ──


def test_lift_raises_headings_outside_code_and_never_below_the_page_title() -> None:
    lines = ["## A", "### B", "#### C", "```", "### code", "```", "text ### no"]
    assert lift(lines) == ["# A", "## B", "### C", "```", "### code", "```", "text ### no"]
    assert lift(lines, 2)[1:3] == ["# B", "## C"]


def test_a_link_to_a_heading_of_the_readme_goes_through_the_anchor_callback() -> None:
    out = rewrite_links(
        ["See [x](#one) and [y](#two)."], lambda a: f"/p#{a.upper()}", "a/README.md"
    )
    assert out == ["See [x](/p#ONE) and [y](/p#TWO)."]


def test_a_relative_link_becomes_a_link_to_the_repository_from_the_readmes_directory() -> None:
    out = rewrite_links(
        ["[a](LICENSE) [b](../x/y.md#frag) [c](sub/z.py#L1)"], str, "packages/pkg/README.md"
    )
    assert out == [
        f"[a]({REPO_BLOB}/packages/pkg/LICENSE) "
        f"[b]({REPO_BLOB}/packages/x/y.md#frag) "
        f"[c]({REPO_BLOB}/packages/pkg/sub/z.py#L1)"
    ]


def test_absolute_root_and_scheme_links_and_code_are_left_alone() -> None:
    lines = [
        "[a](https://x.dev/p) [b](mailto:me@x.dev) [c](/docs/sdk) [d](tel:1)",
        "```",
        "[e](rel.md) [f](#frag)",
        "```",
    ]
    assert rewrite_links(lines, lambda a: "BAD", "p/README.md") == lines


def test_tidy_collapses_blank_runs_and_ends_in_one_newline() -> None:
    assert tidy(["", "", "a", "", "", "", "b", "", ""]) == "a\n\nb\n"
    assert tidy(["a"]) == "a\n"
    assert tidy([]) == "\n"

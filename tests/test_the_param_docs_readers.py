"""What a parameter is, read from the docstring that documents it, on small inputs.

``tools/param_docs.py`` reads Google-style ``Args:`` sections and JSDoc
``@param`` lines into the tables of the reference pages. The pages only show
what the real docstrings came to; these tests say what each reader does with
the shapes a docstring can take.
"""

from __future__ import annotations

from tools.param_docs import (
    UNDOCUMENTED,
    cell,
    code,
    jsdoc_lines,
    jsdoc_params,
    python_args,
    strip_jsdoc_params,
    strip_python_args,
    table,
)

# ── Python: the Args: section ──


def test_args_says_what_each_parameter_is_and_joins_the_lines_a_meaning_runs_over() -> None:
    doc = "Does it.\n\nArgs:\n    a: The first.\n    b: The second,\n        over two lines.\n"
    assert python_args(doc) == {"a": "The first.", "b": "The second, over two lines."}


def test_args_reads_a_name_with_a_type_in_parentheses() -> None:
    doc = "Args:\n    n (int): How many.\n    m (dict[str, int] | None): The map.\n"
    assert python_args(doc) == {"n": "How many.", "m": "The map."}


def test_args_ignores_lines_that_are_not_a_name_and_a_colon() -> None:
    doc = "Args:\n    *args: Rest.\n    **kw: More.\n    a: Kept.\n        continued\n"
    assert python_args(doc) == {"a": "Kept. continued"}


def test_a_continuation_after_an_ignored_line_belongs_to_nothing() -> None:
    doc = "Args:\n    *args: Rest\n        goes on.\n    a: Kept.\n"
    assert python_args(doc) == {"a": "Kept."}


def test_args_with_the_same_name_twice_say_both() -> None:
    assert python_args("Args:\n    a: One.\n    a: Two.\n") == {"a": "One. Two."}


def test_args_reads_every_section_of_a_docstring_and_ends_at_the_next_heading() -> None:
    doc = "Args:\n    a: One.\n\nReturns:\n    b: Not an arg.\n\nArgs:\n    c: Three.\n"
    assert python_args(doc) == {"a": "One.", "c": "Three."}


def test_args_inside_an_indented_class_docstring_ends_at_its_own_indent() -> None:
    doc = "    Text.\n\n    Args:\n        a: One.\n\n    Other:\n        b: Not.\n"
    assert python_args(doc) == {"a": "One."}


def test_args_with_a_blank_line_inside_keeps_reading() -> None:
    assert python_args("Args:\n    a: One.\n\n    b: Two.\n") == {"a": "One.", "b": "Two."}


def test_a_docstring_with_no_args_or_an_empty_one_documents_nothing() -> None:
    assert python_args("") == {}
    assert python_args("Just text.\nArgs are not a section here.") == {}
    assert python_args("Args:\n\n\nText") == {}
    assert python_args("Args:") == {}


def test_a_meaning_may_be_empty_or_hold_unicode() -> None:
    assert python_args("Args:\n    a:\n    b: Größe — naïve.\n") == {"a": "", "b": "Größe — naïve."}


def test_stripping_args_leaves_the_rest_of_the_docstring() -> None:
    doc = "Does it.\n\nArgs:\n    a: One.\n    b: Two.\n\nReturns:\n    Something.\n"
    assert strip_python_args(doc) == "Does it.\n\nReturns:\n    Something."


def test_stripping_args_at_the_end_or_the_start_or_twice() -> None:
    assert strip_python_args("Does it.\n\nArgs:\n    a: One.\n") == "Does it."
    assert strip_python_args("Args:\n    a: One.\n\nAfter.") == "After."
    assert strip_python_args("A\n\nArgs:\n    a: 1\n\nB\n\nArgs:\n    b: 2\n\nC") == "A\n\nB\n\nC"
    assert strip_python_args("No section.\n") == "No section."
    assert strip_python_args("") == ""


def test_what_the_table_says_of_a_parameter_nothing_documents() -> None:
    assert UNDOCUMENTED == "Not documented yet."


# ── TypeScript: the @param lines ──


def test_jsdoc_lines_drop_the_comment_marks() -> None:
    doc = "/**\n * One.\n *\n * @param a — two.\n */"
    assert jsdoc_lines(doc) == ["", "One.", "", "@param a — two.", " "]
    assert jsdoc_lines("/* one */") == [" one "]
    assert jsdoc_lines("/** one") == [" one"]
    assert jsdoc_lines("bare\n * text") == ["bare", "text"]


def test_param_names_the_parameter_and_what_it_is_with_or_without_a_dash() -> None:
    doc = "/**\n * @param a — em dash.\n * @param b – en dash.\n * @param c - hyphen.\n * @param d none.\n */"
    assert jsdoc_params(doc) == {
        "a": "em dash.",
        "b": "en dash.",
        "c": "hyphen.",
        "d": "none.",
    }


def test_param_reads_a_type_and_names_with_dollars_and_underscores() -> None:
    doc = "/**\n * @param {string} $el - Element.\n * @param {Map<string, number>} _x - Map.\n */"
    assert jsdoc_params(doc) == {"$el": "Element.", "_x": "Map."}


def test_a_param_runs_over_until_a_blank_line_or_the_next_tag() -> None:
    doc = (
        "/**\n * @param a - one\n *   and two\n * @param b - three\n * @returns r\n"
        " * more of returns\n * @param c - four\n *\n * after blank\n */"
    )
    assert jsdoc_params(doc) == {"a": "one and two", "b": "three", "c": "four"}


def test_the_same_param_twice_says_both_and_a_doc_with_none_says_nothing() -> None:
    assert jsdoc_params("/** @param a - x\n * @param a - y */") == {"a": "x y"}
    assert jsdoc_params("/** Text only. */") == {}
    assert jsdoc_params("") == {}


def test_stripping_params_leaves_the_description_and_the_other_tags() -> None:
    doc = (
        "/**\n * Does it.\n *\n * @param a - one\n *   and more\n * @param b - two\n"
        " * @returns The result.\n */"
    )
    assert strip_jsdoc_params(doc) == "Does it.\n\n@returns The result."


def test_stripping_params_keeps_prose_after_a_blank_line() -> None:
    doc = "/**\n * Top.\n * @param a - one\n *\n * Later prose.\n */"
    assert strip_jsdoc_params(doc) == "Top.\n\nLater prose."


# ── the table ──


def test_a_cell_is_one_line_and_its_pipes_are_escaped() -> None:
    assert cell("a  b\n\tc | d") == "a b c \\| d"
    assert cell("") == ""


def test_code_is_backticked_and_its_pipes_escaped() -> None:
    assert code("str | None") == "`str \\| None`"
    assert code("int") == "`int`"


def test_a_table_has_a_header_and_a_row_a_parameter_and_none_without_rows() -> None:
    assert table([]) == []
    assert table([("a", "`int`", "required", "The  first\n| one.")]) == [
        "| Parameter | Type | Default | Meaning |",
        "|---|---|---|---|",
        "| `a` | `int` | required | The first \\| one. |",
        "",
    ]


def test_a_param_shows_an_inline_link_as_code_not_as_the_raw_tag() -> None:
    doc = "/**\n * @param a - one of the {@link Codes}s, or {@link x.y} text\n */"
    assert jsdoc_params(doc) == {"a": "one of the `Codes`s, or `x.y` text"}

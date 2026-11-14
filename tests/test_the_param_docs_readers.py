"""What a parameter is, read from the docstring that documents it, on small inputs.

``tools/param_docs.py`` reads Google-style ``Args:`` sections and JSDoc
``@param`` lines into the tables of the reference pages. The pages only show
what the real docstrings came to; these tests say what each reader does with
the shapes a docstring can take.
"""

from __future__ import annotations

from tools.param_docs import UNDOCUMENTED, python_args, strip_python_args

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

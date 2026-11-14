"""The stylesheet's reference is a reading of the CSS, and the reading is right.

``tools/css_reference.py`` reads ``igni-ui.css`` into the tokens page and
the classes page of the ui-css reference. The generated pages are checked
in, and a reader that misread the file would regenerate them to match —
so the reader is tested here on small sheets whose answer is known.
"""

from __future__ import annotations

import pytest

from tools.css_reference import CssError, CssReference, Stylesheet
from tools.param_docs import UNDOCUMENTED


def _tokens(sheet: str) -> list[tuple[str, str, str]]:
    return [(t.name, t.value, t.meaning) for t in Stylesheet(sheet).tokens()]


def _classes(sheet: str) -> list[tuple[str, str, tuple[str, ...], str]]:
    return [
        (section.title, rule.selector, rule.properties, rule.note)
        for section, rule in Stylesheet(sheet).classes()
    ]


def test_a_comment_above_a_custom_property_is_its_meaning_not_part_of_its_name() -> None:
    sheet = """/* ── Colour ── the palette */
:root {
  /* The page's background. */
  --bg: #111;
  /* The text colour,
   * on two lines. */
  --fg: #eee;
  --bare: 1px;
}"""
    assert _tokens(sheet) == [
        ("--bg", "#111", "The page's background."),
        ("--fg", "#eee", "The text colour, on two lines."),
        ("--bare", "1px", ""),
    ]


def test_an_apostrophe_in_a_comment_does_not_start_a_string() -> None:
    sheet = """/* ── A ── */
:root { /* the user's colour */ --a: red; }
/* don't read this as a string { */
.x { color: var(--a); }"""
    assert _tokens(sheet) == [("--a", "red", "the user's colour")]
    assert Stylesheet(sheet).users_of("--a") == ["x"]


def test_a_brace_in_a_comment_inside_a_rule_does_not_close_it() -> None:
    sheet = "/* ── A ── */ .x { /* } */ color: red; }"
    assert _classes(sheet) == [("A", ".x", ("color",), "")]


def test_a_comment_above_a_rule_is_its_note_and_a_section_marker_titles_the_section() -> None:
    sheet = """/* The sheet. */
/* ── Buttons ── how they look
 * and sit */
/* A plain button. */
.btn { color: red; }"""
    reading = Stylesheet(sheet)
    (section,) = reading.sections
    assert section.title == "Buttons"
    assert section.note == "how they look and sit"
    assert [(r.selector, r.note) for r in section.rules] == [(".btn", "A plain button.")]


def test_a_sheet_with_no_markers_has_one_section_named_for_its_header() -> None:
    # A later rule with no comment of its own does not erase the header.
    sheet = "/* The header. */\n:root { --a: 1; color: red; }\n.x { color: blue; }"
    assert [(s.title, s.note, s.rules) for s in Stylesheet(sheet).sections] == [
        ("The stylesheet", "The header.", [])
    ]


def test_a_semicolon_inside_a_string_or_a_url_is_part_of_the_value() -> None:
    sheet = """/* ── A ── */
:root { --f: "a;b"; --u: url(data:image/png;base64,xx); --after: 1; }
.x { background: url(data:image/png;base64,yy); content: ';'; color: red; }"""
    assert _tokens(sheet) == [
        ("--f", '"a;b"', ""),
        ("--u", "url(data:image/png;base64,xx)", ""),
        ("--after", "1", ""),
    ]
    ((_, _, properties, _),) = _classes(sheet)
    assert properties == ("background", "content", "color")


def test_users_of_a_token_are_the_classes_that_read_it_once_each() -> None:
    sheet = """/* ── A ── */
:root { --a: 1; --a-b: 2; --abc: 3; }
.x { color: var(--a); }
.x:hover { color: var( --a , red); }
.y.z { margin: calc(var(--a) + 1px); }
.w { color: var(--a-b); }
.v { color: var(--abc, var(--a-b)); }"""
    reading = Stylesheet(sheet)
    assert reading.users_of("--a") == ["x", "y", "z"]
    assert reading.users_of("--a-b") == ["w", "v"]
    assert reading.users_of("--abc") == ["v"]
    assert reading.users_of("--missing") == []


def test_the_tokens_page_lists_users_the_meaning_and_what_is_missing() -> None:
    users = "\n".join(f".c{n} {{ color: var(--a); }}" for n in range(8))
    sheet = f"""/* ── A ── the note */
:root {{
  /* What a is | for. */
  --a: 1;
  --unused: 2;
}}
{users}
"""
    page, count = CssReference("pkg", "a.css", sheet).tokens_page()
    assert count == 2
    rows = [line for line in page.split("\n") if line.startswith("| `--")]
    assert rows == [
        "| `--a` | `1` | `.c0`, `.c1`, `.c2`, `.c3`, `.c4`, `.c5` … | What a is \\| for. |",
        f"| `--unused` | `2` | nothing here | {UNDOCUMENTED} |",
    ]
    assert "## --a\n\n`1`\n\nWhat a is | for.\n\nthe note\n" in page
    assert "## --unused\n\n`2`\n\nthe note\n" in page


def test_exactly_six_users_show_no_ellipsis() -> None:
    users = "\n".join(f".c{n} {{ color: var(--a); }}" for n in range(6))
    page, _ = CssReference(
        "p", "a.css", f"/* ── A ── */ :root {{ --a: 1; }}\n{users}"
    ).tokens_page()
    assert "`.c5` |" in page
    assert "…" not in page


@pytest.mark.parametrize(
    "sheet",
    [
        '/* ── A ── */ .a[title="x',
        "/* ── A ── */ .a[title='x",
    ],
)
def test_a_string_that_is_never_closed_is_refused_as_a_css_error(sheet: str) -> None:
    with pytest.raises(CssError, match="string"):
        Stylesheet(sheet)

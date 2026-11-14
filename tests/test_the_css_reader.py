"""The stylesheet's reference is a reading of the CSS, and the reading is right.

``tools/css_reference.py`` reads ``igni-ui.css`` into the tokens page and
the classes page of the ui-css reference. The generated pages are checked
in, and a reader that misread the file would regenerate them to match —
so the reader is tested here on small sheets whose answer is known.
"""

from __future__ import annotations

from tools.css_reference import CssReference, Stylesheet
from tools.param_docs import UNDOCUMENTED


def _tokens(sheet: str) -> list[tuple[str, str, str]]:
    return [(t.name, t.value, t.meaning) for t in Stylesheet(sheet).tokens()]


def _classes(sheet: str) -> list[tuple[str, str, tuple[str, ...], str]]:
    return [
        (section.title, rule.selector, rule.properties, rule.note)
        for section, rule in Stylesheet(sheet).classes()
    ]


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

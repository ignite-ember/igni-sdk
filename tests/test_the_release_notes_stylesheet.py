"""The release-notes example's stylesheet styles what its UI renders.

``examples/release-notes/ui/panel.css`` holds the two rules the published
floor does not: the editor that fills its pane and the comment card. These
tests read it as CSS and check that the page loads it after the floor's
stylesheet, that ``panel.tsx`` uses exactly these class names, and that the
file sets no colour of its own (so it follows theme changes).
"""

from __future__ import annotations

import re
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "release-notes"
CSS = (EXAMPLE / "ui" / "panel.css").read_text()


def rules() -> dict[str, dict[str, str]]:
    body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    out: dict[str, dict[str, str]] = {}
    for selector, block in re.findall(r"([^{}]+)\{([^}]*)\}", body):
        decls = {}
        for line in block.split(";"):
            if ":" in line:
                name, value = line.split(":", 1)
                decls[name.strip()] = value.strip()
        out[selector.strip()] = decls
    return out


def test_only_the_editor_and_the_comment_are_styled():
    assert set(rules()) == {".note-editor", ".comment"}


def test_the_editor_fills_its_pane_in_a_monospace_face():
    editor = rules()[".note-editor"]
    assert editor["height"] == "100%"
    # height 100% collapses in a parent without a definite height; this
    # floor keeps the editor usable.
    assert editor["min-height"] == "24rem"
    assert editor["font-family"] == "var(--font-mono, ui-monospace, monospace)"
    assert editor["line-height"] == "1.6"


def test_a_comment_is_a_vertical_column_spaced_by_the_token():
    comment = rules()[".comment"]
    assert comment["display"] == "flex"
    assert comment["flex-direction"] == "column"
    # the fallback applies when the host does not push --space-3
    assert comment["gap"] == "var(--space-3, 6px)"


def test_the_stylesheet_sets_no_colour_of_its_own():
    for decls in rules().values():
        assert not [p for p in decls if "color" in p or p in {"background", "border"}]
    assert "#" not in re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def test_the_panel_uses_the_class_names_the_stylesheet_styles():
    # The UI is split across the example's modules; panel.tsx is the
    # entry point, and the one that imports the stylesheet.
    sources = sorted(p for p in (EXAMPLE / "src").glob("*.tsx") if not p.name.endswith(".test.tsx"))
    tsx = "\n".join(p.read_text() for p in sources)
    assert 'className="note-editor"' in tsx
    assert re.search(r'className="ui-card comment"', tsx)
    assert 'import "./panel.css";' in (EXAMPLE / "src" / "panel.tsx").read_text()


def test_the_page_loads_the_panel_stylesheet_after_the_floors():
    html = (EXAMPLE / "ui" / "index.html").read_text()
    links = re.findall(r'<link[^>]+href="([^"]+\.css)"', html)
    assert "./panel.css" in links and "./igni-ui.css" in links
    assert links.index("./igni-ui.css") < links.index("./panel.css")

"""What docs/YOUR_FIRST_EXTENSION.md says igni and its scaffold do, they do.

Each test here is a sentence of the tutorial a reader followed and found
untrue, held against the thing it describes.
"""

from __future__ import annotations

import re

from tests.siblings import IGNI_CORE, REPO, needs_core

TUTORIAL = REPO / "docs" / "YOUR_FIRST_EXTENSION.md"


def _text() -> str:
    return " ".join(TUTORIAL.read_text(encoding="utf-8").split())


@needs_core
def test_step_0_says_how_a_scaffolded_project_finds_the_wheels() -> None:
    """It said the scaffold's pyproject.toml "installs from `--find-links
    wheels`"; the pyproject igni ext init writes names no wheel directory and
    tells you to pass --find-links yourself."""
    templates = (IGNI_CORE / "src/igni_core/cli/ext_scaffold_templates.py").read_text()
    (workspace,) = re.findall(r'SERVICE_WORKSPACE = """(.*?)"""', templates, re.S)
    tool_uv = workspace.split("[tool.uv]", 1)[1].split("\n[", 1)[0]

    assert "find-links" not in tool_uv, "the scaffold now names its wheels: say so here"
    assert "uv sync --find-links" in workspace
    assert "its `pyproject.toml` installs from `--find-links wheels`" not in _text()
    assert "says to run `uv sync --find-links <the directory holding them>`" in _text()


def _section(heading: str) -> str:
    text = TUTORIAL.read_text(encoding="utf-8")
    start = text.index(heading)
    return text[start : text.index("\n## ", start + 1)]


def test_step_7_s_headless_runs_cannot_stop_at_a_question() -> None:
    """ "Look ticket T-1002 up on the ticket service." ended with exit 1: the
    model went on to a shell command, and a headless run that meets a question
    pauses. `--read-only` lets the extension's read-only tools run and refuses
    the rest (checked against a real model)."""
    section = _section("## 7. Use it")
    runs = [line for line in section.splitlines() if re.match(r"igni\b.*\s-m\s", line)]

    assert len(runs) == 2
    assert all("--read-only" in line for line in runs), runs
    assert "Run paused for confirmation" in section


def test_a_development_install_is_said_to_be_a_copy_refreshed_with_replace() -> None:
    """ "Faster loops" said a development install "runs a directory straight
    from disk"; it copies the directory into igni's store, and after a rebuild
    a second install is refused ("already installed ... Pass --replace")."""
    bridge = REPO / "packages" / "extension-bridge" / "README.md"
    loops = _section("## Changing it")

    assert "straight from disk" not in loops
    assert "igni ext install --replace extension" in loops
    assert "igni ext install --replace <dir>" in bridge.read_text(encoding="utf-8")


def test_the_example_s_readme_says_how_to_run_it() -> None:
    """The example's README documented only `pytest`, and its extension's
    README no command at all: a reader of the README alone could not start,
    install or use the example."""
    example = REPO / "examples" / "ticket-lookup"
    readme = (example / "README.md").read_text(encoding="utf-8")
    extension = (example / "extension" / "README.md").read_text(encoding="utf-8")

    for command in (
        "igni ext doctor extension",
        "IGNI_DEV_EXTENSIONS=1 igni ext install extension",
        'igni --read-only -m "What is the status of ticket T-1001?"',
    ):
        assert command in readme, command
    for anchor in re.findall(r"YOUR_FIRST_EXTENSION\.md#([\w-]+)", readme):
        headings = TUTORIAL.read_text(encoding="utf-8")
        slugs = {
            re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-")
            for h in re.findall(r"^#+ (.+)$", headings, re.M)
        }
        assert anchor in slugs, f"no heading for #{anchor}"
    assert "igni ext install ." in extension and "../README.md#run-it" in extension


def test_the_bridge_readme_says_how_to_test_a_page_outside_igni_s_app() -> None:
    """Nothing said how to drive a page outside igni's app: an author took the
    hello shape and the window's `caller` envelope from igni-app's source.
    The README now gives the stand-in parent, with the protocol's own types,
    and names the repository's test that does it."""
    readme = (REPO / "packages" / "extension-bridge" / "README.md").read_text(encoding="utf-8")
    section = readme[readme.index("## Testing a page") : readme.index("## The floor")]
    protocol = (REPO / "packages" / "extension-bridge" / "src" / "protocol.ts").read_text()

    for name in ("BRIDGE_VERSION", "isGuestMessage", "HelloMessage", "ResultMessage"):
        assert name in section and re.search(
            rf"export (const|function|interface) {name}\b", protocol
        )
    (example,) = re.findall(r"`(packages/test-utils/[\w.]+)`", section)
    assert (REPO / example).is_file()
    assert "HostHarness" in section


@needs_core
def test_step_7_says_the_first_run_writes_igni_s_project_files() -> None:
    """The first headless run in ~/ticket-lookup wrote igni.md and a .igni/
    tree of 22 files, untrusted folder or not, and nothing in the tutorial said
    igni writes into the project: a reader who commits the directory picks
    them up unknowingly. igni's QUICKSTART says the first run writes them."""
    quickstart = (IGNI_CORE / "QUICKSTART.md").read_text(encoding="utf-8")
    first_run = quickstart[quickstart.index("## First Run") :]
    assert "Writes `igni.md`" in first_run.split("\n## ", 1)[0]

    section = " ".join(_section("## 7. Use it").split())
    assert "it writes `igni.md` and a `.igni/` directory" in section
    assert "QUICKSTART.md#first-run" in section
    assert "`igni-service-bundle` reads only `extension/`" in section


def test_the_example_s_readme_says_the_untrusted_notice_is_not_about_the_extension() -> None:
    """Every run in the example's directory prints the untrusted-folder notice,
    "… hooks … are off", while the extension's PostToolUse hook still runs: a
    reader of 'Run it' took it to mean the audit hook did not."""
    readme = (REPO / "examples" / "ticket-lookup" / "README.md").read_text(encoding="utf-8")
    run_it = " ".join(readme[readme.index("## Run it") :].split("\n## ", 1)[0].split())
    manifest = (REPO / "examples" / "ticket-lookup" / "extension" / "manifest.json").read_text()

    assert "PostToolUse" in manifest
    assert "is not trusted" in run_it
    assert "`PostToolUse` audit hook" in run_it
    assert "tool-audit.log" in run_it


def test_igni_client_s_approval_answers_are_one_list() -> None:
    """A paragraph inserted after the AccessRefused bullet split the Approvals
    answers in two: `decide(...)` rendered as a list of its own."""
    readme = (REPO / "packages" / "igni-client" / "README.md").read_text(encoding="utf-8")
    start = readme.index("- `approve(choice)`")
    block = readme[start : readme.index("\n\n", start)]

    for answer in ("`approve(choice)`", "`reject(remember=False)`", "`AccessRefused`", "`decide("):
        assert answer in block, answer


def test_ui_react_s_quick_start_page_has_the_igni_root_class() -> None:
    """With index.html as the Quick start described it — `<div id="root">` and
    nothing on body — the page rendered unstyled: transparent, Times, an 8px
    body margin. `igni-root` styles it, and connect() does not add it."""
    readme = (REPO / "packages" / "ui-react" / "README.md").read_text(encoding="utf-8")
    quick_start = readme[
        readme.index("## Quick start") : readme.index("\n## ", readme.index("## Quick start") + 1)
    ]
    bridge = (REPO / "packages" / "extension-bridge" / "src").glob("*.ts")
    css = (REPO / "clients" / "ui").rglob("*.css")

    (html,) = quick_start.split("```html\n")[1:2]
    assert '<body class="igni-root">' in html.split("```", 1)[0]
    assert not any("igni-root" in f.read_text(encoding="utf-8") for f in bridge)
    assert any(
        ".igni-root" in f.read_text(encoding="utf-8") for f in css if "node_modules" not in f.parts
    )


def test_the_bridge_readme_says_when_to_post_hello_and_that_there_is_no_real_route() -> None:
    """Following 'Testing a page': connect() only sees a hello posted after the
    page's script runs, and the section did not say to wait for the frame's
    load event, nor that a framed page has no route to the real backend
    outside igni's app."""
    readme = (REPO / "packages" / "extension-bridge" / "README.md").read_text(encoding="utf-8")
    section = readme[readme.index("## Testing a page") : readme.index("## The floor")]

    assert 'frame.addEventListener("load"' in section
    assert "deliberately no way to send a framed page's calls to the real" in section

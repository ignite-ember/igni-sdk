"""What the SDK docs generator does with each input, not only what it wrote last time.

``test_the_sdk_docs_are_generated.py`` compares the checked-in pages with a
fresh run, which stays true however wrong the run is. These tests give the
generator small inputs and say what must come out.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from tools import client_doc_layout, sdk_docs
from tools.client_codegen import README_END, README_START, Placement, push_class
from tools.client_contract import RpcContract
from tools.client_errors_doc import read_errors
from tools.client_example_check import check_example
from tools.client_method_notes import place_text, source_text
from tools.client_names import (
    FOLLOWED,
    MESSAGE_METHODS,
    MESSAGES_NOT_SENT,
    NOT_FOR_CLIENTS,
    OWN_SESSION_ARG,
    REFERENCE_PAGES,
)
from tools.client_signatures import Param
from tools.markdown_pages import ReadmePages
from tools.reference_area import Anchor
from tools.sdk_docs import (
    INDEX,
    OUTPUT,
    PACKAGES,
    ClientReference,
    DocsError,
    Package,
    Page,
    ReadmeSite,
    SdkDocs,
    docs_url,
    url,
)
from tools.site_packages import NpmManifest
from tools.site_page import PackageReport, Section
from tools.wire_prose import ArgumentFreeText, cell, rst

ROOT = Path(__file__).resolve().parent.parent
CANCEL = Placement.of("cancel_scheduled_task", "session.scheduler.cancel")


def _param(name: str, annotation: str = "str") -> Param:
    return Param(name=name, annotation=annotation, default=None, value=name)


def _check(code: str, *names: str) -> None:
    check_example(CANCEL, [_param(name) for name in names], code)


def test_an_example_may_pass_as_many_positionals_as_the_method_has_parameters() -> None:
    _check("await session.scheduler.cancel('t1')\n", "task_id")
    _check("await session.scheduler.cancel('t1', 'x')\n", "task_id", "other")
    _check("await session.scheduler.cancel()\n")


def test_an_example_that_passes_a_positional_to_a_method_without_parameters_fails() -> None:
    with pytest.raises(DocsError, match="too many arguments"):
        _check("await session.scheduler.cancel('t1')\n")


def test_an_example_that_passes_more_positionals_than_parameters_fails() -> None:
    with pytest.raises(DocsError, match="too many arguments"):
        _check("await session.scheduler.cancel('a', 'b', 'c')\n", "task_id", "other")


def test_an_example_that_is_not_python_fails() -> None:
    with pytest.raises(DocsError, match=r"session\.scheduler\.cancel\(\) is not Python"):
        _check("await session.scheduler.cancel(\n")


def test_an_example_that_never_calls_its_method_fails() -> None:
    with pytest.raises(DocsError, match="does not call it"):
        _check("await session.scheduler.list()\n")


def test_an_example_that_passes_a_keyword_the_method_lacks_fails() -> None:
    with pytest.raises(DocsError, match="task="):
        _check("await session.scheduler.cancel(task='t1')\n", "task_id")
    _check("await session.scheduler.cancel(task_id='t1')\n", "task_id")


def test_an_example_may_spread_a_dict_of_keywords() -> None:
    _check("await session.scheduler.cancel(**options)\n", "task_id")


def test_a_parameter_the_page_does_not_show_is_not_one_the_example_may_pass() -> None:
    params = [_param("task_id"), _param("session_id", "")]
    with pytest.raises(DocsError, match="session_id="):
        check_example(CANCEL, params, "await session.scheduler.cancel(session_id='s')\n")


def _npm_source(manifest: dict[str, Any]) -> str:
    return NpmManifest.model_validate({"version": "1", "description": "d", **manifest}).source


def test_an_npm_package_may_name_its_repository_as_a_string_or_not_at_all() -> None:
    assert _npm_source({"repository": "https://github.com/o/r"}) == "https://github.com/o/r"
    assert _npm_source({}) == ""
    assert _npm_source({"repository": {"type": "git"}}) == ""


def test_an_npm_repository_url_loses_its_git_prefix_and_suffix() -> None:
    assert _npm_source({"repository": {"url": "git+https://github.com/o/r.git"}}) == (
        "https://github.com/o/r"
    )
    assert _npm_source({"repository": {"url": "https://github.com/o/r"}}) == (
        "https://github.com/o/r"
    )
    assert _npm_source({"repository": {"url": "git+ssh://x/y.gitx"}}) == "ssh://x/y.gitx"


# ── The small helpers ────────────────────────────────────────────────────


def test_a_page_is_at_the_package_path_and_the_overview_is_the_package_itself() -> None:
    assert url("igni-client") == "/docs/sdk/igni-client"
    assert url("igni-client", "overview") == "/docs/sdk/igni-client"
    assert url("igni-client", "") == "/docs/sdk/igni-client"
    assert url("igni-client", "access") == "/docs/sdk/igni-client/access"
    assert url("igni-client", "access", "raises") == "/docs/sdk/igni-client/access#raises"
    assert url("igni-client", "overview", "top") == "/docs/sdk/igni-client#top"
    assert docs_url("ui-css") == "https://ignite-ember.sh/docs/sdk/ui-css"


def test_the_docstring_roles_become_code_spans() -> None:
    assert rst("See :class:`~igni_client.Session` and :meth:`run` or :exc:`Boom`.") == (
        "See `igni_client.Session` and `run` or `Boom`."
    )
    for role in ("func", "attr", "data", "mod"):
        assert rst(f":{role}:`a.b`") == "`a.b`"
    assert rst("a ``literal`` here") == "a `literal` here"
    assert rst("plain text") == "plain text"


def test_a_table_cell_is_one_line_with_its_pipes_escaped() -> None:
    assert cell("a  b\n  c\t d") == "a b c d"
    assert cell("x | y") == "x \\| y"
    assert cell("") == ""


def test_an_opening_takes_no_arguments_is_taken_out_with_its_note() -> None:
    assert ArgumentFreeText.of("Takes no arguments. Lists them.") == ArgumentFreeText(
        text="Lists them."
    )
    assert ArgumentFreeText.of("Takes no arguments (any are ignored).  Rest.") == (
        ArgumentFreeText(text="Rest.", note="any are ignored")
    )
    assert ArgumentFreeText.of("Lists them. Takes no arguments.") == ArgumentFreeText(
        text="Lists them. Takes no arguments."
    )


def test_a_package_report_says_only_the_counts_that_are_not_zero() -> None:
    assert PackageReport().notes() == []
    report = PackageReport(missing_meanings=["w.p"], undocumented_models=2)
    assert report.notes() == ["missing_meanings: ['w.p']", "undocumented_models: 2"]


def test_a_package_says_how_to_install_it_and_where_it_is_published() -> None:
    py = Package("igni-client", "igni_client", "packages/igni-client")
    assert py.site == "igni-client"
    assert py.install == "pip install igni-client"
    assert py.registry_url == "https://pypi.org/project/igni-client/"
    assert py.registry == "PyPI"
    npm = Package("@scope/pkg", "@scope/pkg", "p", kind="npm", slug="pkg", registry="npm")
    assert npm.site == "pkg"
    assert npm.install == "npm install @scope/pkg"
    assert npm.registry_url == "https://www.npmjs.com/package/@scope/pkg"


def test_the_six_published_packages_are_the_ones_the_registries_hold() -> None:
    assert [(p.name, p.kind, p.site, p.registry) for p in PACKAGES] == [
        ("igni-client", "python", "igni-client", "PyPI"),
        ("igni-extension", "python", "igni-extension", "PyPI"),
        ("igni-service", "python", "igni-service", "PyPI"),
        ("@ignite-ember/extension-bridge", "npm", "extension-bridge", "npm"),
        ("@ignite-ember/ui-react", "npm", "ui-react", "npm"),
        ("@ignite-ember/ui-css", "npm", "ui-css", "npm"),
    ]
    assert [p.path for p in PACKAGES] == [
        "packages/igni-client",
        "packages/igni-extension",
        "packages/igni-service",
        "packages/extension-bridge",
        "packages/ui-react",
        "clients/ui",
    ]
    assert [p.readme_title for p in PACKAGES[3:]] == [
        "`@ignite-ember/extension-bridge`",
        "`@ignite-ember/ui-react`",
        "igni-ui",
    ]
    for package in PACKAGES:
        assert "/" not in package.site


def _page(body: str, **kw: Any) -> Page:
    fields: dict[str, Any] = {
        "package": "pkg",
        "slug": "guide",
        "title": "A guide",
        "description": "d",
        "category": "guide",
        "order": 1,
        "body": body,
        "source": "pkg/README.md",
    }
    return Page(**{**fields, **kw})


def test_a_page_is_written_with_a_banner_a_title_and_one_trailing_newline() -> None:
    page = _page("\n\nBody text.\n\n\n")
    assert page.file == "pkg/guide.md"
    assert page.text() == (
        "<!-- Generated by igni-sdk's tools/sdk_docs.py from pkg/README.md. "
        "Do not edit: run `make sdk-docs` in igni-sdk. -->\n\n# A guide\n\nBody text.\n"
    )


def test_a_pages_sections_are_its_second_and_third_level_headings() -> None:
    page = _page(
        "Intro\n\n# Not a section\n\n## The `call()` API\n\ntext\n\n### Under it\n\n"
        "#### Too deep\n\n## Last one  \n"
    )
    assert page.sections() == [
        Section(level=2, id="the-call-api", title="The call() API"),
        Section(level=3, id="under-it", title="Under it"),
        Section(level=2, id="last-one", title="Last one"),
    ]


def test_a_heading_inside_a_code_fence_is_not_a_section() -> None:
    page = _page(
        "## Real\n\n```sh\n## not a heading\n### nor this\n```\n\n~~~\n## nor in a tilde fence\n~~~\n\n"
        "## After\n"
    )
    assert [s.title for s in page.sections()] == ["Real", "After"]
    assert _page("no headings at all").sections() == []


def test_a_place_in_a_message_and_in_a_call_are_said_in_words() -> None:
    assert place_text("id") == "the message's own id"
    assert place_text("session_id") == "the session the message is for"
    assert place_text("run_id") == "the run the message is of"
    assert place_text("channel") == "the channel the message is on"
    assert place_text("payload.workflow_run_id") == "the message's `workflow_run_id`"
    assert place_text("kind") == "the message's `kind`"
    assert source_text("request.id") == "the id the call was sent as"
    assert source_text("request.session_id") == "the session the call was for"
    assert source_text("args.run_id") == "the `run_id` the call was given"
    assert source_text("result.pid") == "the `pid` the call was answered with"
    assert source_text("other") == "the call's `other`"


# ── The READMEs ──────────────────────────────────────────────────────────

PKG = Package("pkg", "pkg", "packages/pkg")


def _site(text: str, **kw: Any) -> ReadmeSite:
    return ReadmeSite(PKG, text, description="what it is", **kw)


def test_a_readme_with_no_sections_is_its_overview_alone() -> None:
    pages = _site("# pkg\n\nJust an intro.\n").pages()
    assert [(p.slug, p.title, p.order, p.category) for p in pages] == [
        ("overview", "Overview", 0, "guide")
    ]
    assert pages[0].description == "what it is"
    assert pages[0].body.strip() == "Just an intro."
    assert pages[0].source == "packages/pkg/README.md (before its first section)"


def test_a_readme_with_only_contents_is_its_overview_alone() -> None:
    pages = _site("# pkg\n\nIntro.\n\n## Contents\n\n- [x](#x)\n").pages()
    assert [p.slug for p in pages] == ["overview"]


def test_each_section_is_a_page_with_its_order_title_and_first_sentences() -> None:
    pages = _site(
        "# pkg\n\nIntro.\n\n## Contents\n\n- x\n\n## Quick start\n\nRun it. Then stop.\n\n"
        "## The `API`\n\nCall it.\n",
    ).pages()
    assert [(p.slug, p.title, p.order) for p in pages] == [
        ("overview", "Overview", 0),
        ("quick-start", "Quick start", 1),
        ("the-api", "The API", 2),
    ]
    assert pages[1].description.startswith("Run it.")
    assert pages[1].source == "packages/pkg/README.md, “Quick start”"
    assert pages[1].package == "pkg"


def test_the_pages_of_a_later_package_part_start_at_the_given_order() -> None:
    pages = _site("# pkg\n\nIntro.\n\n## One\n\nx\n\n## Two\n\ny\n").pages(start=5)
    assert [p.order for p in pages] == [5, 6, 7]


def test_the_readmes_own_link_to_the_site_is_dropped_from_the_overview() -> None:
    text = (
        "# pkg\n\nSee [the docs](https://ignite-ember.sh/docs/sdk/pkg).\n\nKeep this line.\n\n"
        "## One\n\nx\n"
    )
    body = _site(text).pages()[0].body
    assert "ignite-ember.sh" not in body
    assert "Keep this line." in body


def test_a_link_to_a_heading_on_the_same_page_is_a_bare_anchor() -> None:
    pages = _site("# pkg\n\nIntro.\n\n## One\n\n### Deeper\n\nBack to [deeper](#deeper).\n").pages()
    assert "(#deeper)" in pages[1].body


def test_a_link_to_another_page_is_a_full_site_path() -> None:
    pages = _site(
        "# pkg\n\nSee [one](#one) and [deeper](#deeper).\n\n## One\n\nx\n\n### Deeper\n\ny\n\n"
        "## Two\n\nSee [one](#one) or [deeper](#deeper).\n"
    ).pages()
    assert "(/docs/sdk/pkg/one)" in pages[0].body
    assert "(/docs/sdk/pkg/one#deeper)" in pages[0].body
    assert "(/docs/sdk/pkg/one)" in pages[2].body


def test_a_link_into_the_skipped_contents_section_is_an_error() -> None:
    text = "# pkg\n\nSee [toc](#contents).\n\n## Contents\n\n- x\n\n## One\n\nx\n"
    with pytest.raises(ValueError, match="in a section that is not a page"):
        _site(text).pages()


def test_a_link_to_a_heading_the_readme_lacks_is_an_error_naming_it() -> None:
    with pytest.raises(ValueError, match="#nowhere, which it has no heading for"):
        _site("# pkg\n\n[x](#nowhere)\n\n## One\n\nx\n").pages()


def test_an_extra_anchor_sends_a_link_to_the_page_the_site_moved_it_to() -> None:
    text = "# pkg\n\nSee [moved](#moved).\n\n## One\n\nSee [again](#moved).\n"
    moved = Anchor(slug="reference", anchor="moved-heading")
    pages = _site(text, extra_anchors={"moved": moved}).pages()
    assert "(/docs/sdk/pkg/reference#moved-heading)" in pages[0].body
    assert "(/docs/sdk/pkg/reference#moved-heading)" in pages[1].body
    pages = _site(text, extra_anchors={"moved": Anchor(slug="one", anchor="")}).pages()
    assert "(/docs/sdk/pkg/one)" in pages[0].body
    assert "(#)" in pages[1].body


def test_a_heading_in_a_code_fence_does_not_cut_a_readme() -> None:
    pages = _site("# pkg\n\nx\n\n## One\n\n```md\n## inside\n```\n\n## Two\n\ny\n").pages()
    assert [p.slug for p in pages] == ["overview", "one", "two"]


def test_igni_clients_exceptions_are_read_without_importing_them(tmp_path: Path) -> None:
    source = tmp_path / "errors.py"
    source.write_text(
        '"""Module doc."""\n\n'
        'class Root(Exception):\n    """The root.\n\n    More."""\n\n'
        "class Child(Root, mod.Other):\n    pass\n\n"
        "class Two(Root, ValueError):\n    '''Two\\nlines.'''\n\n"
        "def helper() -> None: ...\n",
        encoding="utf-8",
    )
    errors = read_errors(source)
    assert [(e.name, e.bases) for e in errors] == [
        ("Root", ["Exception"]),
        ("Child", ["Root"]),
        ("Two", ["Root", "ValueError"]),
    ]
    assert errors[0].doc == "The root.\n\nMore."
    assert errors[0].summary == "The root."
    assert errors[1].doc == "" and errors[1].summary == ""
    assert errors[2].summary == "Two lines."


def test_igni_clients_real_exceptions_are_read_with_their_docstrings() -> None:
    errors = {
        e.name: e for e in read_errors(ROOT / "packages/igni-client/src/igni_client/errors.py")
    }
    assert {"InvalidArguments", "AccessRefused", "MethodFailed", "UnknownMethod"} <= set(errors)
    assert all(e.doc for e in errors.values())


# ── igni-client's reference ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def client() -> ClientReference:
    readme = (ROOT / "packages/igni-client/README.md").read_text(encoding="utf-8")
    return ClientReference(
        RpcContract.read(),
        read_errors(ROOT / "packages/igni-client/src/igni_client/errors.py"),
        ReadmePages(readme, "packages/igni-client/README.md"),
    )


def _section(client: ClientReference, path: str) -> str:
    wire = next(w for w, p in client.sources.layout.placements.items() if p.path == path)
    return "\n".join(client.methods.section(wire))


def test_a_page_names_what_igni_client_lacks_when_the_table_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        client_doc_layout, "REFERENCE_PAGES", [("p", "P", ("session.nothing.here",))]
    )
    with pytest.raises(
        DocsError, match=r"names what igni-client lacks: \['session.nothing.here'\]"
    ):
        SdkDocs(ROOT).pages()


def test_a_method_no_page_takes_is_an_error_naming_it(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [p for p in REFERENCE_PAGES if p[0] != "igni"]
    monkeypatch.setattr(client_doc_layout, "REFERENCE_PAGES", pages)
    with pytest.raises(
        DocsError,
        match=r"no page in REFERENCE_PAGES .* takes: igni.check_for_update, igni.group_policy",
    ):
        SdkDocs(ROOT).pages()


def test_a_method_on_two_pages_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # A page naming a method takes it; a second page naming it too is a clash.
    first = ("first", "First", ("igni.processes.tail",))
    second = ("second", "Second", ("igni.processes.tail",))
    monkeypatch.setattr(client_doc_layout, "REFERENCE_PAGES", [*REFERENCE_PAGES, first, second])
    with pytest.raises(DocsError, match="methods on two reference pages"):
        SdkDocs(ROOT).pages()


def test_every_placed_method_is_on_exactly_one_page_and_each_page_lists_it(
    client: ClientReference,
) -> None:
    assert set(client.sources.layout.page_of) == set(client.sources.layout.placements)
    pages = {p.slug: p for p in client.reference_pages(0)}
    assert list(pages) == [slug for slug, _, _ in REFERENCE_PAGES]
    for wire, slug in client.sources.layout.page_of.items():
        assert f"## {client.sources.layout.placements[wire].path}()" in pages[slug].body, wire
        assert all(p.category == "reference" for p in pages.values())


def test_a_method_page_says_what_igni_client_does_for_a_call(client: ClientReference) -> None:
    section = _section(client, "session.scheduler.cancel")
    assert section.startswith("## session.scheduler.cancel()")
    assert "```python\nasync def cancel(" in section
    assert "| Parameter | Type | Default | Meaning |" in section
    assert "**Returns**" in section
    assert "**How long** `io`" in section
    assert "The client waits up to 30 seconds." in section
    assert "**On the wire** RPC method `cancel_scheduled_task`" in section
    assert "**Raises**" in section and "AccessRefused" not in section
    assert "MethodFailed" in section and "UnknownMethod" in section


def test_a_followed_method_returns_a_call_and_can_be_interrupted(client: ClientReference) -> None:
    wire = next(w for w in FOLLOWED if w in client.sources.layout.placements)
    section = "\n".join(client.methods.section(wire))
    name = client.sources.layout.placements[wire].name
    assert f"\ndef {name}(" in section and "-> Call[" in section
    assert "await it for the result" in section and "`async with` it" in section
    assert "RunInterrupted" in section
    assert "**Events**" in section


def test_a_method_that_needs_more_than_client_access_raises_access_refused(
    client: ClientReference,
) -> None:
    wire = next(
        w
        for w, p in client.sources.layout.placements.items()
        if w not in MESSAGE_METHODS and client.sources.contract.methods[w].access == "approver"
    )
    section = "\n".join(client.methods.section(wire))
    assert "when this connection does not stand as `approver`" in section
    assert "**Access** [`approver`](/docs/sdk/igni-client/access)" in section
    plain = _section(client, "session.scheduler.cancel")
    assert (
        "**Access** [`client`](/docs/sdk/igni-client/access) — any connection igni admitted."
        in plain
    )


def test_a_message_method_that_is_only_sent_has_no_answer_to_fail(client: ClientReference) -> None:
    sent_only = [
        w for w in MESSAGE_METHODS if "MethodFailed" not in "\n".join(client.methods.section(w))
    ]
    answered = [w for w in MESSAGE_METHODS if w not in sent_only]
    assert sent_only, "some client message is sent without an answer"
    for wire in sent_only:
        text = "\n".join(client.methods.section(wire))
        assert "InvalidArguments" in text and "Unavailable" in text
        assert "UnknownMethod" not in text and "UnexpectedAnswer" not in text
    for wire in answered:
        text = "\n".join(client.methods.section(wire))
        assert "MethodFailed" in text and "UnknownMethod" in text and "UnexpectedAnswer" in text


def test_a_method_with_no_arguments_says_so_and_its_own_session_is_noted(
    client: ClientReference,
) -> None:
    section = _section(client, "session.status")
    assert "Takes no arguments" in section
    assert "| Parameter |" not in section
    hidden = [
        w
        for w in OWN_SESSION_ARG
        if w in client.sources.layout.placements
        and client.sources.layout.placements[w].owner == "session"
        and not [
            p
            for p in client.sources.api.params(client.sources.layout.placements[w])[0]
            if p.annotation
        ]
    ]
    assert hidden
    text = "\n".join(client.methods.section(hidden[0]))
    assert "Takes no arguments (`session_id` is this session's own)." in text


def test_a_method_with_no_arguments_says_so_once_whoever_wrote_it_first(
    client: ClientReference,
) -> None:
    for path in ("session.workflows.list", "session.plans.latest", "igni.models.list"):
        placements = [p for p in client.sources.layout.placements.values() if p.path == path]
        if not placements:
            continue
        assert _section(client, path).count("Takes no arguments") == 1, path
    workflows = _section(client, "session.workflows.list")
    # The contract's own note in brackets survives, once.
    assert "Takes no arguments (any it is sent are ignored)." in workflows
    assert workflows.count("Takes no arguments") == 1


def test_the_text_igni_core_wrote_for_the_wire_names_the_python_attribute_and_call(
    client: ClientReference,
) -> None:
    listed = _section(client, "session.workflows.list")
    assert "`when_to_use`" in listed and "`whenToUse`" not in listed
    cancelled = _section(client, "session.workflows.cancel")
    assert "(from `session.workflows.run()`)" in cancelled
    assert "`run_workflow`" not in cancelled.split("**On the wire**")[0]
    # What the page says of the wire stays the wire's own.
    assert "**On the wire** RPC method `cancel_workflow`" in cancelled
    # A `Session` is one session: the wire's `session_id` is not a parameter.
    history = _section(client, "session.history.get")
    assert "names the session" not in history and "`session_id`" in history
    truncate = _section(client, "session.history.truncate")
    assert "names the session" not in truncate
    assert "`session_id` is this session's own, so it is not a parameter." in truncate
    # A word that is a field and a method on the wire is left as it is.
    assert client.sources.prose.prose("the `status` field") == "the `status` field"


def test_the_wait_the_docs_state_is_the_wait_the_client_applies(client: ClientReference) -> None:
    """``The client waits up to N seconds`` is what ``igni_client`` does for that method."""
    src = str(ROOT / "packages" / "igni-client" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from igni_client.calls import timeout_of

    for wire in client.sources.layout.placements:
        if wire in MESSAGE_METHODS:
            continue
        text = "\n".join(client.methods.notes.duration(wire))
        real = timeout_of(wire)
        if real is None:
            assert "The client waits as long as it takes." in text, wire
            assert "waits up to" not in text, wire
        else:
            assert f"The client waits up to {real:g} seconds." in text, wire


def test_a_call_is_told_apart_the_way_the_contract_says(client: ClientReference) -> None:
    by_contract = {
        w: m
        for w, m in client.sources.contract.methods.items()
        if w in client.sources.layout.placements
    }
    equals = next(w for w, m in by_contract.items() if m.correlate and m.correlate.equals)
    assert "is `" in client.methods.notes.told_apart(equals)[0]
    assert client.methods.notes.told_apart(equals)[0].startswith(
        "**Told apart by** the message's `cause` is `"
    )
    source = next(
        w
        for w, m in by_contract.items()
        if m.correlate and m.correlate.source and not m.correlate.equals
    )
    assert "igni's contract says so." in client.methods.notes.told_apart(source)[0]
    caused = next(
        w
        for w, m in by_contract.items()
        if m.correlate and not m.correlate.source and not m.correlate.equals
    )
    assert client.methods.notes.told_apart(caused)[0].endswith(", and by what the call causes.")
    plain = next(w for w, m in by_contract.items() if m.correlate is None)
    assert client.methods.notes.told_apart(plain) == []


def test_an_argument_free_read_gets_an_example_of_its_first_fields(client: ClientReference) -> None:
    def example(path: str) -> str | None:
        wire = next(w for w, p in client.sources.layout.placements.items() if p.path == path)
        placement = client.sources.layout.placements[wire]
        return client.methods.examples.generated(
            wire, placement, client.sources.api.params(placement)[0]
        )

    # An array of models: a loop printing the preferred fields first.
    assert example("session.scheduler.list") == (
        "for scheduled_task in await session.scheduler.list():\n"
        "    print(scheduled_task.id, scheduled_task.status)\n"
    )
    # One model: the variable is named for the method, and the preferred fields lead.
    assert example("session.status") == (
        "status = await session.status()\nprint(status.cloud_connected, status.cloud_email)\n"
    )
    # A model or nothing: guarded against None.
    assert example("session.auth.plan") == (
        "plan = await session.auth.plan()\nif plan is not None:\n    print(plan.email, plan.full_name)\n"
    )
    # A scalar: printed as it is.
    assert example("session.get_project_dir") == "print(await session.get_project_dir())\n"
    # Not a read, or followed, or a message: no generated example.
    assert example("session.scheduler.cancel") is None


def test_a_parameter_with_no_meaning_in_the_schema_or_the_doc_is_a_dash_and_recorded() -> None:
    contract = RpcContract.read()
    readme = (ROOT / "packages/igni-client/README.md").read_text(encoding="utf-8")
    ref = ClientReference(contract, [], ReadmePages(readme, "x"))
    assert (
        ref.meanings.meaning("w", "p", {"description": "From the ``schema``."}, "doc")
        == "From the `schema`."
    )
    doc = "Does a thing.\nThe ``flag`` says when. Other text."
    assert ref.meanings.meaning("w", "flag", {}, doc) == "The `flag` says when."
    assert ref.meanings.missing == []
    assert ref.meanings.meaning("w", "other", {}, doc) == "—"
    assert ref.meanings.missing == ["w.other"]


def test_igni_clients_reference_has_no_page_without_its_error_classes() -> None:
    contract = RpcContract.read()
    readme = (ROOT / "packages/igni-client/README.md").read_text(encoding="utf-8")
    ref = ClientReference(contract, [], ReadmePages(readme, "x"))
    wire = next(
        w for w, p in ref.sources.layout.placements.items() if p.path == "session.scheduler.cancel"
    )
    with pytest.raises(DocsError, match="igni-client has no InvalidArguments to document"):
        ref.methods.section(wire)


def test_the_access_page_lists_every_method_that_needs_more_than_a_client(
    client: ClientReference,
) -> None:
    body = client.access_page(0).body
    for wire, placement in client.sources.layout.placements.items():
        access = (
            "client" if wire in MESSAGE_METHODS else client.sources.contract.methods[wire].access
        )
        if access == "client":
            continue
        row = next(line for line in body.split("\n") if line.startswith(f"| `{access}` |"))
        assert f"`{placement.path}()`" in row, wire
    for wire in NOT_FOR_CLIENTS:
        assert f"| `{wire}` |" in body
    for wire in MESSAGES_NOT_SENT:
        assert f"| `{wire}` |" in body
    assert body.count("Every other method needs only `client`.") == 1


def test_the_models_page_names_every_model_and_the_events_page_every_message(
    client: ClientReference,
) -> None:
    models = client.models_page(0).body
    events = client.events_page(0).body
    args = {
        client.sources.contract.ref_name(client.sources.contract.methods[w].args)
        for w in client.sources.plan.placements
    }
    for name in (client.sources.plan.defs_in | client.sources.plan.defs_out) - args:
        cls = client.sources.types.class_name(name)
        page = events if name in client.sources.messages else models
        assert f"## {cls}" in page or f"### {cls}" in page, name
    for channel in client.sources.contract.push_channels:
        assert f"## {push_class(channel)}" in events or f"### {push_class(channel)}" in events


def test_the_errors_page_lists_the_tree_with_each_classs_summary(client: ClientReference) -> None:
    body = client.errors_page(0).body
    for name, error in client.errors.items():
        assert name in body, name
        if error.summary:
            assert error.summary in body or error.summary[:40] in body, name


# ── The whole run, on a copy of the sources ──────────────────────────────

_SKIP = shutil.ignore_patterns(
    "node_modules", "dist", ".venv", "__pycache__", "tests", ".git", "*.pyc", ".mypy_cache"
)


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The sources the generator reads, without the pages it writes."""
    root = tmp_path_factory.mktemp("sdk")
    for name in ("packages", "clients", "contracts"):
        shutil.copytree(ROOT / name, root / name, ignore=_SKIP)
    return root


@pytest.fixture
def tree(sources: Path, tmp_path: Path) -> Path:
    """A fresh copy of the sources for a test that writes."""
    root = tmp_path / "sdk"
    shutil.copytree(sources, root)
    return root


def test_a_run_writes_every_page_and_the_index_and_a_second_run_writes_nothing(
    tree: Path,
) -> None:
    docs = SdkDocs(tree)
    written = docs.write()
    pages = docs.pages()
    assert {p.relative_to(tree / OUTPUT).as_posix() for p in written} == {
        *(page.file for page in pages),
        "index.json",
    }
    assert (tree / OUTPUT / pages[0].file).read_text(encoding="utf-8") == pages[0].text()
    assert docs.stale() == []
    assert SdkDocs(tree).write() == []


def test_a_missing_file_a_differing_file_and_a_stray_file_are_each_stale(tree: Path) -> None:
    docs = SdkDocs(tree)
    docs.write()
    pages = docs.pages()
    missing = tree / OUTPUT / pages[0].file
    differing = tree / OUTPUT / pages[1].file
    stray = tree / OUTPUT / "igni-client" / "left-over.md"
    missing.unlink()
    differing.write_text("edited by hand\n", encoding="utf-8")
    stray.write_text("old page\n", encoding="utf-8")
    assert sorted(docs.stale()) == sorted([missing, differing, stray])


def test_writing_rewrites_what_differs_and_removes_what_is_not_generated(tree: Path) -> None:
    docs = SdkDocs(tree)
    docs.write()
    pages = docs.pages()
    differing = tree / OUTPUT / pages[1].file
    stray = tree / OUTPUT / "igni-client" / "left-over.md"
    nested = tree / OUTPUT / "gone" / "deeper" / "x.json"
    differing.write_text("edited by hand\n", encoding="utf-8")
    stray.write_text("old page\n", encoding="utf-8")
    nested.parent.mkdir(parents=True)
    nested.write_text("{}", encoding="utf-8")
    written = docs.write()
    assert sorted(written) == sorted([differing, stray, nested])
    assert differing.read_text(encoding="utf-8") == pages[1].text()
    assert not stray.exists() and not nested.exists()
    assert docs.stale() == []


def test_the_command_says_what_it_wrote_and_removed_and_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run on this repository's own pages, which it leaves as it found them."""
    page = ROOT / OUTPUT / "igni-client" / "overview.md"
    original = page.read_text(encoding="utf-8")
    stray = ROOT / OUTPUT / "stray.md"
    try:
        page.unlink()
        stray.write_text("x\n", encoding="utf-8")
        assert sdk_docs.main() == 0
        lines = capsys.readouterr().out.splitlines()
        assert "wrote docs/site/igni-client/overview.md" in lines
        assert "removed docs/site/stray.md" in lines
        assert {
            line.split(": ")[0] for line in lines if not line.startswith(("wrote", "removed"))
        } <= {p.name for p in PACKAGES}
        assert page.read_text(encoding="utf-8") == original
        assert not stray.exists()
        assert sdk_docs.main() == 0
        assert not [
            line
            for line in capsys.readouterr().out.splitlines()
            if line.startswith(("wrote", "removed"))
        ]
    finally:
        page.write_text(original, encoding="utf-8")
        stray.unlink(missing_ok=True)


def test_a_readme_without_the_generated_reference_markers_is_refused(sources: Path) -> None:
    text = (sources / "packages/igni-client/README.md").read_text(encoding="utf-8")
    bare = text.replace(README_START, "").replace(README_END, "")
    with pytest.raises(DocsError, match="has no generated API reference"):
        SdkDocs(sources, readmes={"igni-client": bare}).pages()
    reversed_ = text.replace(README_START, "@@S@@").replace(README_END, README_START)
    reversed_ = reversed_.replace("@@S@@", README_END)
    with pytest.raises(DocsError, match="has no generated API reference"):
        SdkDocs(sources, readmes={"igni-client": reversed_}).pages()


def test_two_pages_with_one_package_and_slug_are_refused(
    sources: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = (sources / "packages/igni-service/README.md").read_text(encoding="utf-8")
    twice = text + "\n## Installing\n\nAgain.\n\n## Installing\n\nAnd again.\n"
    with pytest.raises(DocsError, match="two pages are igni-service/installing"):
        SdkDocs(sources, readmes={"igni-service": twice}).pages()


def test_the_index_names_each_package_and_page_and_keeps_unicode_as_written(
    sources: Path,
) -> None:
    text = (sources / "packages/igni-service/README.md").read_text(encoding="utf-8")
    docs = SdkDocs(sources, readmes={"igni-service": text + "\n## Café — naïve\n\nHéllo.\n"})
    raw = docs.index(docs.pages())
    assert raw.endswith("}\n") and not raw.endswith("\n\n")
    assert "Café — naïve" in raw and "\\u00e9" not in raw
    index = json.loads(raw)
    assert index["generated_by"].startswith("igni-sdk tools/sdk_docs.py")
    by_name = {p["name"]: p for p in index["packages"]}
    assert list(by_name) == [p.site for p in PACKAGES]
    client = by_name["igni-client"]
    assert client["install"] == "pip install igni-client"
    assert client["pypi"] == "https://pypi.org/project/igni-client/"
    assert client["importName"] == "igni_client"
    bridge = by_name["extension-bridge"]
    assert bridge["registry"] == "npm" and "pypi" not in bridge
    assert bridge["registryName"] == "@ignite-ember/extension-bridge"
    assert bridge["install"] == "npm install @ignite-ember/extension-bridge"
    page = next(p for p in index["pages"] if p["slug"] == "cafe-naive" or "Café" in p["title"])
    assert page["file"] == f"igni-service/{page['slug']}.md"
    assert page["sections"] == []


def test_a_package_says_its_version_summary_and_source_from_its_manifest(sources: Path) -> None:
    python = next(p for p in PACKAGES if p.name == "igni-service")
    npm = next(p for p in PACKAGES if p.site == "ui-react")
    manifest = sources / python.path / "pyproject.toml"
    text = manifest.read_text(encoding="utf-8")
    assert python.project(sources).source.startswith("https://")
    manifest.write_text(re.sub(r"(?m)^Source = .*\n", "", text), encoding="utf-8")
    assert python.project(sources).source == ""
    package_json = sources / npm.path / "package.json"
    data = json.loads(package_json.read_text(encoding="utf-8"))
    data["repository"] = {"type": "git", "url": "git+https://github.com/o/r.git"}
    package_json.write_text(json.dumps(data), encoding="utf-8")
    assert npm.project(sources).model_dump() == {
        "version": data["version"],
        "description": data["description"],
        "source": "https://github.com/o/r",
    }
    del data["repository"]
    package_json.write_text(json.dumps(data), encoding="utf-8")
    assert npm.project(sources).source == ""


# ── The pages of this repository, by what each kind of package gets ──────


@pytest.fixture(scope="module")
def pages() -> list[Page]:
    return SdkDocs(ROOT).pages()


def _slugs(pages: list[Page], package: str) -> list[str]:
    return [p.slug for p in pages if p.package == package]


def test_igni_client_has_guides_then_a_reference_page_per_area_then_the_four_shared_pages(
    pages: list[Page],
) -> None:
    mine = [p for p in pages if p.package == "igni-client"]
    reference = [p.slug for p in mine if p.category == "reference"]
    assert reference == [
        *(slug for slug, _, _ in REFERENCE_PAGES),
        "access",
        "models-reference",
        "events-reference",
        "errors-reference",
    ]
    assert [p.category for p in mine] == sorted(
        (p.category for p in mine), key=lambda c: c != "guide"
    )
    assert [p.order for p in mine] == list(range(len(mine)))
    assert mine[0].slug == "overview" and "contents" not in [p.slug for p in mine]


def test_igni_clients_readme_reference_is_replaced_by_the_reference_pages(
    pages: list[Page],
) -> None:
    text = (ROOT / "packages/igni-client/README.md").read_text(encoding="utf-8")
    generated = text.split(README_START, 1)[1].split(README_END, 1)[0]
    body = "\n".join(p.body for p in pages if p.package == "igni-client" and p.category == "guide")
    assert README_START not in body and README_END not in body
    assert generated.strip().splitlines()[0] not in body


def test_the_python_packages_have_guides_and_reference_pages_read_from_their_code(
    pages: list[Page],
) -> None:
    for package, module in (("igni-service", "igni_service"), ("igni-extension", "igni_extension")):
        mine = [p for p in pages if p.package == package]
        guide = [p for p in mine if p.category == "guide"]
        reference = [p for p in mine if p.category == "reference"]
        assert guide[0].slug == "overview" and reference, package
        assert [p.order for p in mine] == list(range(len(mine)))
        assert all(p.source for p in mine)
        assert module in "\n".join(p.body for p in reference)


def test_each_npm_package_has_guide_pages_and_reference_pages_after_them(
    pages: list[Page],
) -> None:
    for package in (p for p in PACKAGES if p.kind == "npm"):
        mine = [p for p in pages if p.package == package.site]
        categories = [p.category for p in mine]
        assert "guide" in categories and "reference" in categories, package.name
        assert categories == sorted(categories, key=lambda c: c != "guide"), package.name
        assert [p.order for p in mine] == list(range(len(mine))), package.name
        assert mine[0].slug == "overview"
    assert "reference-the-bridge" in _slugs(pages, "extension-bridge")
    assert _slugs(pages, "ui-css")[-2:] == ["reference-tokens", "reference-classes"]


def test_the_index_of_the_checked_in_pages_gives_each_npm_package_its_registry_fields() -> None:
    index = json.loads((ROOT / INDEX).read_text(encoding="utf-8"))
    by_name = {p["name"]: p for p in index["packages"]}
    assert by_name["ui-react"] == {
        "name": "ui-react",
        "registry": "npm",
        "registryName": "@ignite-ember/ui-react",
        "registryUrl": "https://www.npmjs.com/package/@ignite-ember/ui-react",
        "install": "npm install @ignite-ember/ui-react",
        "importName": "@ignite-ember/ui-react",
        "version": by_name["ui-react"]["version"],
        "description": by_name["ui-react"]["description"],
        "source": by_name["ui-react"]["source"],
    }
    assert by_name["igni-service"]["registry"] == "PyPI"
    assert by_name["igni-service"]["pypi"] == "https://pypi.org/project/igni-service/"
    assert list(by_name["igni-service"]) == [
        "name",
        "registry",
        "registryName",
        "registryUrl",
        "install",
        "importName",
        "version",
        "description",
        "source",
        "pypi",
    ]


def test_the_host_model_page_says_a_field_the_schema_does_not_describe_has_no_description(
    pages: list[Page],
) -> None:
    page = next(
        p
        for p in pages
        if p.package == "extension-bridge" and p.slug == "reference-the-host-object-model"
    )
    assert "`SCHEMA_VERSION` says which version of it" in page.body
    assert "A field the schema does not describe is listed without a description" in page.body
    schema = json.loads((ROOT / "contracts/host-schema.json").read_text(encoding="utf-8"))
    undescribed = {
        f["name"]
        for spec in schema["types"]
        for f in spec.get("fields", [])
        if not (f.get("doc") or "").strip()
    }
    assert undescribed, "the claim has a field to be about"
    rows = [line for line in page.body.split("\n") if line.startswith("| `")]
    blank = [line for line in rows if line.rstrip().endswith("|  |")]
    assert blank, "such a field is listed with an empty description"

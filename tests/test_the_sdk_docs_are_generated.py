"""The SDKs' pages on igni's site are generated from this repository, and current.

``tools/sdk_docs.py`` writes ``docs/site/`` — every package README cut into
pages, igni-client's reference from igni-core's contract, igni-service's
and igni-extension's from their code — and the site copies it
(``scripts/sync-sdk-docs.mjs`` in igni-site). Change a README, a docstring,
the contract or an example and forget ``make sdk-docs``, and this fails.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.client_contract import RpcContract
from tools.client_examples import EXAMPLES
from tools.client_names import METHODS, NOT_FOR_CLIENTS, REFERENCE_PAGES
from tools.markdown_pages import ReadmePages, github_anchor, site_id
from tools.sdk_docs import INDEX, OUTPUT, PACKAGES, DocsError, SdkDocs, docs_url

ROOT = Path(__file__).resolve().parent.parent
DOCS = SdkDocs(ROOT)
PAGES = DOCS.pages()


def test_the_checked_in_pages_are_what_the_sources_generate() -> None:
    stale = DOCS.stale()
    assert not stale, (
        f"stale or left over: {[str(p.relative_to(ROOT)) for p in stale]}. Run `make sdk-docs`."
    )


def test_the_index_lists_every_page_once() -> None:
    index = json.loads((ROOT / INDEX).read_text(encoding="utf-8"))
    files = {p["file"] for p in index["pages"]}
    on_disk = {str(p.relative_to(ROOT / OUTPUT)) for p in (ROOT / OUTPUT).rglob("*.md")}
    assert files == on_disk
    assert len(files) == len(index["pages"])
    assert [p["name"] for p in index["packages"]] == [p.site for p in PACKAGES]
    for page in index["pages"]:
        assert set(page) == {
            "package",
            "slug",
            "title",
            "description",
            "category",
            "order",
            "file",
            "sections",
        }
        assert page["category"] in ("guide", "reference")
        assert page["description"], page["file"]


def test_every_client_method_has_a_section_with_everything_it_should() -> None:
    contract = RpcContract.read()
    client = {p.slug: p.body for p in PAGES if p.package == "igni-client"}
    reference = "\n".join(client[slug] for slug, _, _ in REFERENCE_PAGES)
    for wire, path in METHODS.items():
        assert wire not in NOT_FOR_CLIENTS
        heading = f"## {path}()"
        assert heading in reference, path
        section = reference.split(heading, 1)[1].split("\n## ", 1)[0]
        assert "```python" in section, path
        for label in ("**Returns**", "**Access**", "**Raises**", "**On the wire**", "**Example**"):
            assert label in section, f"{path} has no {label}"
        assert f"`{wire}`" in section, path
        if contract.methods[wire].streams:
            assert "**Events**" in section, path


def test_a_method_with_no_example_fails_the_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(EXAMPLES, "cancel_scheduled_task")
    with pytest.raises(DocsError, match="session.scheduler.cancel"):
        SdkDocs(ROOT).pages()


def test_an_example_that_passes_what_the_method_does_not_take_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        EXAMPLES, "cancel_scheduled_task", "await session.scheduler.cancel(task='t1')\n"
    )
    with pytest.raises(DocsError, match="task="):
        SdkDocs(ROOT).pages()


def test_every_link_between_pages_lands_on_a_page_and_a_heading() -> None:
    by_url: dict[str, set[str]] = {}
    for page in PAGES:
        ids = {site_id(m.group(1)) for m in re.finditer(r"^#{2,6}\s+(.+)$", page.body, re.M)}
        path = f"/docs/sdk/{page.package}" + ("" if page.slug == "overview" else f"/{page.slug}")
        by_url[path] = ids
    broken: list[str] = []
    for page in PAGES:
        here = f"/docs/sdk/{page.package}" + ("" if page.slug == "overview" else f"/{page.slug}")
        for target in re.findall(r"\]\((/docs/sdk/[^)\s]+|#[^)\s]*)\)", page.body):
            path, _, anchor = target.partition("#")
            path = path or here
            if path not in by_url or (anchor and anchor not in by_url[path]):
                broken.append(f"{page.file}: {target}")
    assert not broken, broken[:20]


def test_a_readme_link_to_a_heading_it_lacks_is_an_error() -> None:
    text = "# pkg\n\nSee [nothing](#no-such-heading).\n\n## Installing\n\nIt installs.\n"
    from tools.sdk_docs import Package, ReadmeSite

    site = ReadmeSite(Package("pkg", "pkg", "packages/pkg"), text, description="d")
    with pytest.raises(ValueError, match="no-such-heading"):
        site.pages()


def test_a_readme_is_cut_at_its_top_level_sections_and_its_links_follow() -> None:
    text = (
        "# pkg\n\nIntro, see [the call](#the-call).\n\n## Contents\n\n- x\n\n"
        "## Installing\n\n```sh\n## not a heading\n```\n\n### The call\n\nIt calls.\n\n"
        "## Guides\n\nBack to [installing](#installing).\n"
    )
    from tools.sdk_docs import Package, ReadmeSite

    pages = ReadmeSite(Package("pkg", "pkg", "packages/pkg"), text, description="d").pages()
    assert [p.slug for p in pages] == ["overview", "installing", "guides"]
    assert "(/docs/sdk/pkg/installing#the-call)" in pages[0].body
    assert "## The call" in pages[1].body and "## not a heading" in pages[1].body
    assert "(/docs/sdk/pkg/installing)" in pages[2].body


def test_github_and_the_site_name_headings_as_they_do() -> None:
    assert github_anchor("igni_client.testing") == "igni_clienttesting"
    assert github_anchor("Where the igni is: Fleet or this machine") == (
        "where-the-igni-is-fleet-or-this-machine"
    )
    assert site_id("session.scheduler.list()") == "session-scheduler-list"
    assert site_id("igni.check_for_update()") == "igni-check-for-update"
    assert site_id("`IgniClient`") == "igniclient"


@pytest.mark.parametrize("package", PACKAGES, ids=lambda p: p.name)
def test_each_package_links_its_registry_to_its_pages(package) -> None:  # type: ignore[no-untyped-def]
    readme = (ROOT / package.path / "README.md").read_text()
    head = readme.split("\n## ", 1)[0]
    assert f"]({docs_url(package.site)})" in head
    assert ReadmePages(readme, package.path).title == (package.readme_title or package.name)
    if package.kind == "python":
        import tomllib

        project = tomllib.loads((ROOT / package.path / "pyproject.toml").read_text())["project"]
        assert project["urls"]["Documentation"] == docs_url(package.site)
        assert {"Homepage", "Source", "Issues"} <= set(project["urls"])
    else:
        data = json.loads((ROOT / package.path / "package.json").read_text())
        assert data["documentation"] == docs_url(package.site)
        assert data["homepage"] == docs_url(package.site)


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv to type-check in igni-client")
def test_every_client_example_type_checks(tmp_path: Path) -> None:
    """Each example, as the reader would paste it, passes igni-client's ``mypy --strict``."""
    source = ["from igni_client import IgniClient, Session\n"]
    count = 0
    for page in PAGES:
        if page.package != "igni-client":
            continue
        for match in re.finditer(
            r"^## (\S+)\(\)\n.*?\*\*Example\*\*\n\n```python\n(.*?)\n```", page.body, re.S | re.M
        ):
            count += 1
            body = "\n".join("    " + line for line in match.group(2).split("\n"))
            source.append(
                f"\n\nasync def example_{count}(igni: IgniClient, session: Session) -> None:"
                f"  # {match.group(1)}\n{body}\n"
            )
    assert count >= len(METHODS)
    checked = tmp_path / "examples.py"
    checked.write_text("".join(source), encoding="utf-8")
    done = subprocess.run(  # noqa: S603 — uv, on our own generated file
        [
            "uv",
            "run",
            "--quiet",
            "--directory",
            "packages/igni-client",
            "mypy",
            "--strict",
            str(checked),
        ],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_long_signature_is_one_parameter_a_line_as_black_writes_it() -> None:
    from tools.markdown_pages import signature

    assert signature("def f", "self, a: int") == "def f(self, a: int)"
    long = signature(
        "async def model",
        "self, *, op: Literal['a', 'b'], window: str" + ", x: str = ''" * 8,
        " -> R",
    )
    assert long.split("\n")[:4] == [
        "async def model(",
        "    self,",
        "    *,",
        "    op: Literal['a', 'b'],",
    ]
    assert long.endswith("\n) -> R")
    assert all(len(line) <= 88 for line in long.split("\n"))


def test_the_index_carries_each_package_version_from_its_manifest() -> None:
    index = json.loads((ROOT / INDEX).read_text(encoding="utf-8"))
    for entry, package in zip(index["packages"], PACKAGES, strict=True):
        if package.kind == "python":
            import tomllib

            project = tomllib.loads((ROOT / package.path / "pyproject.toml").read_text())["project"]
            assert entry["version"] == project["version"], package.name
        else:
            data = json.loads((ROOT / package.path / "package.json").read_text())
            assert entry["version"] == data["version"], package.name


def test_the_index_names_each_package_the_way_the_site_routes_it() -> None:
    """A package's name on the registry carries a ``/``; the site routes on a slug."""
    index = json.loads((ROOT / INDEX).read_text(encoding="utf-8"))
    for entry, package in zip(index["packages"], PACKAGES, strict=True):
        assert entry["name"] == package.site, package.name
        assert entry["registryName"] == package.name
        assert entry["registry"] == package.registry
        assert entry["registryUrl"] == package.registry_url
        assert entry["install"] == package.install
        assert entry["importName"] == package.module
        assert "/" not in entry["name"], package.name
        if package.kind == "python":
            assert entry["pypi"] == package.registry_url
        else:
            assert "pypi" not in entry


def test_the_pages_are_the_same_whatever_the_hash_seed_is() -> None:
    """The generator writes the same pages every run.

    Python randomises the hash of a string per process, so a set of
    strings iterates in a different order in each one. A page built
    from such a set would differ between ``make sdk-docs`` and the
    staleness test — both correct, and neither the other.
    """
    outputs = []
    for seed in ("0", "1", "424242"):
        done = subprocess.run(  # noqa: S603 — python, on our own generator
            [sys.executable, "-m", "tools.sdk_docs"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert done.returncode == 0, done.stderr
        outputs.append(
            {
                str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
                for path in sorted((ROOT / OUTPUT).rglob("*.md"))
            }
            | {INDEX: (ROOT / INDEX).read_text(encoding="utf-8")}
        )
    assert outputs[0] == outputs[1] == outputs[2]

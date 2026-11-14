"""The SDKs' documentation for igni's site, generated: ``make sdk-docs``.

PyPI shows one README per package, npm one page per package. The site
(ignite-ember.sh, the ``igni-site`` repository) shows the same documentation
as many pages, under ``/docs/sdk/<package>/<page>``, and copies them from
here (``scripts/sync-sdk-docs.mjs`` there). This writes ``docs/site/``:

* ``<package>/<slug>.md`` — one page each (``tools/site_page.py``):

  - every package README, cut at its top-level sections: an overview (what
    comes before the first ``##``), then ``Installing``, ``Quick start``,
    ``Concepts``, ``Guides`` and the rest, each a page
    (``tools/readme_site.py``, ``tools/markdown_pages.py``);
  - igni-client's methods, a page per area (``REFERENCE_PAGES`` in
    ``tools/client_names.py``), from igni-core's RPC contract: each method's
    signature, parameters, result, events, access, errors, wire name and an
    example (``tools/client_examples.py``); and its models, events and
    errors (``tools/client_site.py``);
  - igni-service's and igni-extension's public names, a page per area, read
    from the code (``tools/py_reference.py``);
  - the npm packages' public names, a page per area, read from their
    TypeScript (``tools/ts_reference.py``) — the bridge's wire and host
    model, the React floor's components — and the stylesheet's tokens and
    classes, read from the CSS itself (``tools/css_reference.py``); which
    page each name is on is ``tools/reference_areas.py``, and
    ``tools/package_reference.py`` writes them;

* ``index.json`` — every page's slug, title, description, category,
  package, order and file, and each package's name, version, summary, and
  where it is published (``tools/site_index.py``).

Nothing here is written by hand except which page a thing is on and the
examples. ``tests/test_the_sdk_docs_are_generated.py`` regenerates it all in
memory and fails when what is checked in differs.
"""

from __future__ import annotations

from pathlib import Path

from tools.client_contract import CONTRACT_FILE, RpcContract
from tools.client_errors_doc import read_errors
from tools.client_site import ClientReference
from tools.markdown_pages import ReadmePages
from tools.package_reference import package_reference
from tools.readme_site import ReadmeSite
from tools.reference_areas import NPM_AREAS, NPM_ENTRIES, PYTHON_AREAS
from tools.site_index import IndexPackage, IndexPage, SiteIndex
from tools.site_packages import PACKAGES, Package
from tools.site_page import DocsError, PackagePages, PackageReport, Page, docs_url, url

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path("docs/site")
INDEX = OUTPUT / "index.json"

#: The package whose reference is generated from igni-core's contract.
CLIENT = "igni-client"


class SdkDocs:
    """The pages and their index, and whether what is checked in is current."""

    def __init__(self, root: Path = ROOT, readmes: dict[str, str] | None = None) -> None:
        self.root = root
        #: README text by package, to generate from other READMEs than the checked-in ones.
        self.readmes = readmes or {}
        #: What each package's pages could not explain, by package name; filled by ``pages``.
        self.report: dict[str, PackageReport] = {}

    def _readme(self, package: Package) -> str:
        if package.name in self.readmes:
            return self.readmes[package.name]
        return (self.root / package.path / "README.md").read_text(encoding="utf-8")

    def _package_pages(self, package: Package, contract: RpcContract) -> PackagePages:
        """One package's pages: its README's guides, then its reference."""
        text = self._readme(package)
        description = package.project(self.root).description
        if package.name == CLIENT:
            readme = ReadmePages(text, f"{package.path}/README.md")
            errors = read_errors(self.root / package.path / "src/igni_client/errors.py")
            return ClientReference(contract, errors, readme).site_pages(package, description)
        guide = ReadmeSite(package, text, description=description).pages()
        reference = package_reference(package, self.root).pages(len(guide))
        return PackagePages(pages=guide + reference.pages, report=reference.report)

    def pages(self) -> list[Page]:
        contract = RpcContract.read(self.root / CONTRACT_FILE.relative_to(ROOT))
        out: list[Page] = []
        for package in PACKAGES:
            written = self._package_pages(package, contract)
            out += written.pages
            self.report[package.name] = written.report
        seen: set[tuple[str, str]] = set()
        for page in out:
            key = (page.package, page.slug)
            if key in seen:
                raise DocsError(f"two pages are {page.package}/{page.slug}")
            seen.add(key)
        return out

    def index(self, pages: list[Page]) -> str:
        return SiteIndex(
            packages=[IndexPackage.of(p, p.project(self.root)) for p in PACKAGES],
            pages=[IndexPage.of(p) for p in pages],
        ).text()

    def outputs(self) -> dict[Path, str]:
        pages = self.pages()
        out = {self.root / OUTPUT / p.file: p.text() for p in pages}
        out[self.root / INDEX] = self.index(pages)
        return out

    def _strays(self, outputs: dict[Path, str]) -> list[Path]:
        """Files under the output directory that the generator does not write."""
        directory = self.root / OUTPUT
        if not directory.exists():
            return []
        return [p for p in sorted(directory.rglob("*")) if p.is_file() and p not in outputs]

    @staticmethod
    def _differs(path: Path, text: str) -> bool:
        return not path.exists() or path.read_text(encoding="utf-8") != text

    def write(self) -> list[Path]:
        outputs = self.outputs()
        written: list[Path] = []
        for path, text in outputs.items():
            if self._differs(path, text):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                written.append(path)
        for path in self._strays(outputs):
            path.unlink()
            written.append(path)
        return written

    def stale(self) -> list[Path]:
        outputs = self.outputs()
        stale = [path for path, text in outputs.items() if self._differs(path, text)]
        return stale + self._strays(outputs)


def main() -> int:
    docs = SdkDocs()
    for path in docs.write():
        print("wrote" if path.exists() else "removed", path.relative_to(ROOT))
    for package, report in docs.report.items():
        for note in report.notes():
            print(f"{package}: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "INDEX",
    "NPM_AREAS",
    "NPM_ENTRIES",
    "OUTPUT",
    "PACKAGES",
    "PYTHON_AREAS",
    "ClientReference",
    "DocsError",
    "Package",
    "Page",
    "ReadmeSite",
    "SdkDocs",
    "docs_url",
    "url",
]

"""igni-client on the site: its README's guide pages, a reference page per area of its
methods, and the access, models, events and errors pages, all from igni-core's
RPC contract and the generator's plan.

Each page is written by its own module: a method's section by
``tools/client_method_doc.py``, the method pages and the access page by
``tools/client_reference_doc.py``, the models page by
``tools/client_models_doc.py``, the events page by
``tools/client_events_doc.py`` and the errors page by
``tools/client_errors_doc.py``. This composes them.
"""

from __future__ import annotations

from tools.client_contract import RpcContract
from tools.client_doc_links import ClientSources
from tools.client_errors_doc import ErrorCatalog, ErrorClass, ErrorsPage
from tools.client_events_doc import EventsPage
from tools.client_example_check import ClientExamples
from tools.client_method_doc import MethodSection, ParameterMeanings
from tools.client_method_notes import MethodNotes
from tools.client_model_fields import ModelFields
from tools.client_models_doc import ModelsPage
from tools.client_readme_site import ClientReadmeSite
from tools.client_reference_doc import AccessPage, MethodPages
from tools.markdown_pages import ReadmePages
from tools.readme_site import ReadmeSite
from tools.site_packages import Package
from tools.site_page import PackagePages, PackageReport, Page


class ClientReference:
    """igni-client's reference pages, from the contract and the generator's plan."""

    def __init__(
        self, contract: RpcContract, errors: list[ErrorClass], readme: ReadmePages
    ) -> None:
        catalog = ErrorCatalog(errors)
        self.sources = ClientSources.build(contract, catalog, readme)
        self.errors = catalog
        self.meanings = ParameterMeanings(self.sources.prose)
        self.methods = MethodSection(
            self.sources,
            MethodNotes(self.sources, catalog),
            self.meanings,
            ClientExamples(self.sources),
        )
        self.readme = ClientReadmeSite(self.sources.layout, readme.text, readme.path)

    def reference_pages(self, start: int) -> list[Page]:
        return MethodPages(self.sources, self.methods).pages(start)

    def access_page(self, order: int) -> Page:
        return AccessPage(self.sources).page(order)

    def _models(self) -> ModelsPage:
        return ModelsPage(self.sources, ModelFields(self.sources))

    def models_page(self, order: int) -> Page:
        return self._models().page(order)

    def events_page(self, order: int) -> Page:
        return EventsPage(self.sources, ModelFields(self.sources)).page(order)

    def errors_page(self, order: int) -> Page:
        return ErrorsPage(self.errors, self.sources.contract).page(order)

    def report(self) -> PackageReport:
        """What the pages written so far could not explain."""
        return PackageReport(
            missing_meanings=sorted(set(self.meanings.missing)),
            undocumented_models=self._models().undocumented(),
        )

    def site_pages(self, package: Package, description: str) -> PackagePages:
        """Every page of igni-client: the README's guides, then the reference."""
        site = ReadmeSite(
            package,
            self.readme.spliced(),
            description=description,
            extra_anchors=self.readme.anchors(),
        )
        pages = site.pages()
        pages += self.reference_pages(len(pages))
        start = len(pages)
        pages += [
            self.access_page(start),
            self.models_page(start + 1),
            self.events_page(start + 2),
            self.errors_page(start + 3),
        ]
        return PackagePages(pages=pages, report=self.report())


__all__ = ["ClientReference"]

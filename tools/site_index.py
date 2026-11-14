"""``docs/site/index.json``: every page's slug, title, description, category, package,
order, file and sections, and each package's name, version, summary, and where it
is published. The site reads it to build its sidebar and search."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from tools.site_packages import Package, ProjectInfo
from tools.site_page import Page, Section

GENERATED_BY = "igni-sdk tools/sdk_docs.py (make sdk-docs); do not edit"


class IndexPackage(BaseModel):
    """One package in the index, under the names the site reads."""

    name: str
    registry: str
    registry_name: str = Field(serialization_alias="registryName")
    registry_url: str = Field(serialization_alias="registryUrl")
    install: str
    import_name: str = Field(serialization_alias="importName")
    version: str
    description: str
    source: str
    #: The PyPI page, for a Python package only.
    pypi: str | None = None

    @classmethod
    def of(cls, package: Package, project: ProjectInfo) -> IndexPackage:
        return cls(
            name=package.site,
            registry=package.registry,
            registry_name=package.name,
            registry_url=package.registry_url,
            install=package.install,
            import_name=package.module,
            version=project.version,
            description=project.description,
            source=project.source,
            pypi=package.registry_url if package.kind == "python" else None,
        )


class IndexPage(BaseModel):
    """One page in the index."""

    package: str
    slug: str
    title: str
    description: str
    category: str
    order: int
    file: str
    sections: list[Section]

    @classmethod
    def of(cls, page: Page) -> IndexPage:
        return cls(
            package=page.package,
            slug=page.slug,
            title=page.title,
            description=page.description,
            category=page.category,
            order=page.order,
            file=page.file,
            sections=page.sections(),
        )


class SiteIndex(BaseModel):
    """The whole index."""

    generated_by: str = GENERATED_BY
    packages: list[IndexPackage]
    pages: list[IndexPage]

    def text(self) -> str:
        """The index as written: two-space indents, Unicode as it is, one trailing newline."""
        data = self.model_dump(by_alias=True, exclude_none=True)
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


__all__ = ["GENERATED_BY", "IndexPackage", "IndexPage", "SiteIndex"]

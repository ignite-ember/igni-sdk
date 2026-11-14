"""The six published packages the site documents, and what each says of itself."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ProjectInfo(BaseModel):
    """What a package's manifest says of it: its version, its summary, its source."""

    version: str
    description: str
    source: str


class NpmRepository(BaseModel):
    """``repository`` in a package.json, in its object form."""

    model_config = ConfigDict(extra="ignore")

    url: str = ""


class NpmManifest(BaseModel):
    """The parts of a package.json the site reads."""

    model_config = ConfigDict(extra="ignore")

    version: str
    description: str
    #: npm takes the repository as a URL or as ``{"type": ..., "url": ...}``.
    repository: str | NpmRepository | None = None

    @property
    def source(self) -> str:
        """The repository the package's source is in, as a URL."""
        repository = self.repository
        found = repository.url if isinstance(repository, NpmRepository) else repository or ""
        return found.removeprefix("git+").removesuffix(".git")

    def info(self) -> ProjectInfo:
        return ProjectInfo(version=self.version, description=self.description, source=self.source)


class PyProject(BaseModel):
    """The ``[project]`` table of a pyproject.toml, as far as the site reads it."""

    model_config = ConfigDict(extra="ignore")

    version: str
    description: str
    urls: dict[str, str] = Field(default_factory=dict)

    def info(self) -> ProjectInfo:
        return ProjectInfo(
            version=self.version,
            description=self.description,
            source=self.urls.get("Source", ""),
        )


@dataclass(frozen=True)
class Package:
    #: The name the registry knows the package by.
    name: str
    #: The name it is imported by: ``igni_client`` for Python, the package's
    #: own name for npm.
    module: str
    #: Where the package lives in this repository.
    path: str
    #: ``python`` or ``npm``.
    kind: str = "python"
    #: The segment the site routes the package's pages on: the name for
    #: Python, a short slug for npm — a package's name carries a ``/``,
    #: which a path cannot.
    slug: str = ""
    #: The registry the package is published on.
    registry: str = "PyPI"
    #: The title its README opens with, when it is not the package's name.
    readme_title: str = ""

    @property
    def site(self) -> str:
        """The name the site routes the package's pages on."""
        return self.slug or self.name

    @property
    def install(self) -> str:
        """The line that installs the package."""
        if self.kind == "python":
            return f"pip install {self.name}"
        return f"npm install {self.name}"

    @property
    def registry_url(self) -> str:
        """The registry's own page for the package."""
        if self.kind == "python":
            return f"https://pypi.org/project/{self.name}/"
        return f"https://www.npmjs.com/package/{self.name}"

    def project(self, root: Path) -> ProjectInfo:
        """What the package's manifest under ``root`` says of it."""
        directory = root / self.path
        if self.kind == "npm":
            text = (directory / "package.json").read_text(encoding="utf-8")
            return NpmManifest.model_validate(json.loads(text)).info()
        data = tomllib.loads((directory / "pyproject.toml").read_text(encoding="utf-8"))
        return PyProject.model_validate(data["project"]).info()


PACKAGES = (
    Package("igni-client", "igni_client", "packages/igni-client"),
    Package("igni-extension", "igni_extension", "packages/igni-extension"),
    Package("igni-service", "igni_service", "packages/igni-service"),
    Package(
        "@ignite-ember/extension-bridge",
        "@ignite-ember/extension-bridge",
        "packages/extension-bridge",
        kind="npm",
        slug="extension-bridge",
        registry="npm",
        readme_title="`@ignite-ember/extension-bridge`",
    ),
    Package(
        "@ignite-ember/ui-react",
        "@ignite-ember/ui-react",
        "packages/ui-react",
        kind="npm",
        slug="ui-react",
        registry="npm",
        readme_title="`@ignite-ember/ui-react`",
    ),
    Package(
        "@ignite-ember/ui-css",
        "@ignite-ember/ui-css",
        "clients/ui",
        kind="npm",
        slug="ui-css",
        registry="npm",
        readme_title="igni-ui",
    ),
)

__all__ = ["PACKAGES", "NpmManifest", "NpmRepository", "Package", "ProjectInfo", "PyProject"]

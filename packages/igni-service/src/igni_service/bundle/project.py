"""The parts of the extension's `pyproject.toml` the bundle builder reads.

`[project]` for the package name and its console scripts, and
`[tool.igni.bundle]` for the dependencies it may build from an sdist:

    [tool.igni.bundle]
    sdist-only = ["wikipedia"]
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from igni_service.bundle.manifest import PythonPackaging
from igni_service.bundle.requirements import Requirement
from igni_service.errors import BundleError


class ProjectTable(BaseModel):
    """`[project]`."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str = ""
    scripts: dict[str, str] = Field(default_factory=dict)


class IgniBundleTable(BaseModel):
    """`[tool.igni.bundle]`."""

    model_config = ConfigDict(populate_by_name=True, use_attribute_docstrings=True)

    sdist_only: list[str] = Field(default_factory=list, alias="sdist-only")
    """Dependencies with no wheel that may be built from their sdist."""


class IgniTable(BaseModel):
    """`[tool.igni]`."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    bundle: IgniBundleTable = Field(default_factory=IgniBundleTable)


class ToolTable(BaseModel):
    """`[tool]`, for igni's own table only."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    igni: IgniTable = Field(default_factory=IgniTable)


class ExtensionProject(BaseModel):
    """An extension's `pyproject.toml`."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    project: ProjectTable = Field(default_factory=ProjectTable)
    tool: ToolTable = Field(default_factory=ToolTable)

    SDIST_ONLY: ClassVar[tuple[str, ...]] = ("tool", "igni", "bundle", "sdist-only")
    """Where `sdist-only` sits, as a validation error locates it."""

    @classmethod
    def read(cls, directory: Path) -> ExtensionProject:
        path = directory / "pyproject.toml"
        try:
            return cls.model_validate(tomllib.loads(path.read_text()))
        except FileNotFoundError:
            raise BundleError(f"{path} does not exist: the extension is a Python package") from None
        except tomllib.TOMLDecodeError as exc:
            raise BundleError(f"{path} is not valid TOML: {exc}") from exc
        except ValidationError as exc:
            if any(error["loc"][:4] == cls.SDIST_ONLY for error in exc.errors()):
                raise BundleError("[tool.igni.bundle] sdist-only must be a list of names") from exc
            raise BundleError(
                f"{path}: [project] needs a name and string [project.scripts], and "
                f"[tool.igni.bundle] sdist-only must be a list of names: {exc}"
            ) from exc

    def sdist_only(self) -> set[str]:
        return {Requirement.normalise(name) for name in self.tool.igni.bundle.sdist_only}

    def check_package(self, python: PythonPackaging) -> None:
        """Raises `BundleError` unless this builds the package the manifest installs and starts."""
        name = self.project.name
        if Requirement.normalise(name) != Requirement.normalise(python.package):
            raise BundleError(
                f"manifest.json installs {python.package!r} but pyproject.toml builds {name!r}"
            )
        if python.entry not in self.project.scripts:
            raise BundleError(
                f"manifest.json starts {python.entry!r}, which pyproject.toml "
                "does not declare under [project.scripts]"
            )

    def module_of(self, entry: str) -> str:
        """The module a console script runs, or `""` when it declares none."""
        return self.project.scripts.get(entry, "").partition(":")[0].strip()

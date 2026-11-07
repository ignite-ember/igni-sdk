"""The extension's `manifest.json`, as the bundle builder reads and writes it."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from igni_service.assets import BundleAsset, BundleAssets
from igni_service.errors import BundleError


class PythonPackaging(BaseModel):
    """The manifest's `python` packaging."""

    model_config = ConfigDict(extra="allow")

    package: str
    entry: str
    wheels: str = "wheels"


class ToolAnnotations(BaseModel):
    """MCP's four hints, every one stated: igni refuses a bundle that leaves one out."""

    model_config = ConfigDict(extra="forbid")

    readOnlyHint: bool  # noqa: N815 — MCP's name for it
    destructiveHint: bool  # noqa: N815
    idempotentHint: bool  # noqa: N815
    openWorldHint: bool  # noqa: N815

    def differences(self, code: ToolAnnotations) -> list[str]:
        """Each hint these state differently from the code's, said both ways."""
        return [
            f"{hint} {getattr(self, hint)} in the manifest, {getattr(code, hint)} in the code"
            for hint in ToolAnnotations.model_fields
            if getattr(self, hint) != getattr(code, hint)
        ]


class AgentTool(BaseModel):
    """A tool in `permissions.tools`: one the agent may call, and what it says it is."""

    model_config = ConfigDict(extra="forbid")

    name: str
    annotations: ToolAnnotations


class BundlePermissions(BaseModel):
    model_config = ConfigDict(extra="allow")

    tools: list[AgentTool] = Field(default_factory=list)
    #: igni's hook events its process answers (`PreToolUse`, `PlanSubmit`, …).
    hooks: list[str] = Field(default_factory=list)


class ManifestEndpoint(BaseModel):
    """An extension igni reaches at a URL instead of starting a process.

    Only its presence matters to the builder; the rest is igni's to read.
    """

    model_config = ConfigDict(extra="allow")


class BundleManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    version: str
    python: PythonPackaging
    #: Read for `tools`, so a bundle igni would refuse is not built.
    permissions: BundlePermissions = Field(default_factory=BundlePermissions)
    endpoint: ManifestEndpoint | None = None
    assets: list[BundleAsset] = Field(default_factory=list)

    @classmethod
    def read(cls, path: Path) -> BundleManifest:
        try:
            return cls.model_validate_json(path.read_text())
        except FileNotFoundError:
            raise BundleError(f"{path} does not exist") from None
        except (ValueError, ValidationError) as exc:
            raise BundleError(
                f"{path} must name an id, a version and the `python` packaging, "
                f"state all four hints of every tool in permissions.tools, and pin "
                f"every asset it declares: {exc}"
            ) from exc

    @field_validator("assets")
    @classmethod
    def _assets_cover_every_platform(cls, assets: list[BundleAsset]) -> list[BundleAsset]:
        return BundleAssets(assets=assets).assets

    @model_validator(mode="after")
    def _hooks_need_a_process(self) -> BundleManifest:
        """Only a process igni starts is asked about a hook event; an `endpoint` never is."""
        if self.permissions.hooks and self.endpoint is not None:
            events = ", ".join(self.permissions.hooks)
            raise ValueError(
                f"permissions.hooks ({events}) needs a process igni starts, and an "
                "`endpoint` never is one: its silence would block every fail-closed event"
            )
        return self

    @property
    def declares_tools(self) -> bool:
        """Whether the file states `permissions.tools` at all, even as an empty list."""
        return (
            "permissions" in self.model_fields_set and "tools" in self.permissions.model_fields_set
        )

    def qualified(self, tool: str) -> str:
        """A tool's name as the code registers it: under the extension's id."""
        return tool if tool.startswith(f"{self.id}.") else f"{self.id}.{tool}"

    def with_tools(self, tools: list[AgentTool]) -> BundleManifest:
        permissions = self.permissions.model_copy(update={"tools": tools})
        return self.model_copy(update={"permissions": permissions})

    def to_json(self) -> str:
        """The manifest as written into a bundle: what the file said, nothing defaulted."""
        dumped = self.model_dump(mode="json", exclude_unset=True)
        return json.dumps(dumped, indent=2) + "\n"

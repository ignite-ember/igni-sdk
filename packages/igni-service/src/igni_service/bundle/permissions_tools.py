"""`permissions.tools`, written from the code or held to it.

When the extension is built with `igni-extension` and its manifest
leaves `permissions.tools` out, the bundle's manifest gets every tool
the code registers, with the hints `ext.tool(hints=...)` states. A
manifest that does declare them is checked against the code instead,
and a difference stops the build.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from igni_service.bundle.code_tools import CodeToolsRead
from igni_service.bundle.manifest import AgentTool, BundleManifest
from igni_service.errors import BundleError


class ToolsOutcome(BaseModel):
    """What the bundle's manifest should say about its tools, and what was said about it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    written: list[AgentTool] | None = None
    """The tools to write into the bundle's manifest; `None` leaves it as written."""
    notes: list[str] = Field(default_factory=list)


class PermissionsTools:
    """One manifest's `permissions.tools`, against what the code registers."""

    def __init__(self, manifest: BundleManifest) -> None:
        self._manifest = manifest

    def against(self, read: CodeToolsRead) -> ToolsOutcome:
        if read.tools is None:
            return ToolsOutcome(notes=self._unread(read.problem))
        if not self._manifest.declares_tools:
            return self._written(read.tools)
        return ToolsOutcome(notes=self._checked(read.tools))

    def _unread(self, problem: str) -> list[str]:
        if not problem:
            return []
        if self._manifest.permissions.tools:
            return [
                f"could not read the tools from the code ({problem}); "
                "permissions.tools is the manifest's, unchecked"
            ]
        return [
            f"could not read the tools from the code ({problem}), and the manifest "
            "declares no permissions.tools: the agent is offered none of its tools. "
            "Build on a platform the bundle includes, or declare them."
        ]

    @staticmethod
    def _written(code: list[AgentTool]) -> ToolsOutcome:
        if not code:
            return ToolsOutcome()
        return ToolsOutcome(
            written=code,
            notes=[
                "permissions.tools written from the code: " + ", ".join(tool.name for tool in code)
            ],
        )

    def _checked(self, code: list[AgentTool]) -> list[str]:
        """Raises `BundleError` when the declaration and the code disagree."""
        by_name = {tool.name: tool for tool in code}
        problems: list[str] = []
        for declared in self._manifest.permissions.tools:
            found = by_name.pop(self._manifest.qualified(declared.name), None)
            if found is None:
                problems.append(f"{declared.name}: declared, and the code does not register it")
                continue
            differ = declared.annotations.differences(found.annotations)
            if differ:
                problems.append(f"{declared.name}: " + "; ".join(differ))
        if problems:
            raise BundleError(
                "permissions.tools does not say what the code does:\n  "
                + "\n  ".join(problems)
                + "\nFix the manifest, or leave permissions.tools out and the builder "
                "writes it from the code."
            )
        if by_name:
            return [
                "not offered to the agent (registered, not in permissions.tools): "
                + ", ".join(sorted(by_name))
            ]
        return []

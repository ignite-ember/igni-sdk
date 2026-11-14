"""A package's optional peers are only ever imported on demand.

`@ignite-ember/ui-react` listed `react-markdown` and `remark-gfm` as
optional peers while `Markdown.tsx` imported them statically and the
entry re-exported it. A Vite build without them succeeded and the page
threw `Could not resolve "react-markdown"` the moment it loaded. A module
imported statically by the published source is needed by every consumer:
it is a dependency or a required peer. Only a dynamic `import()` (as
`mermaid` is loaded) may name an optional one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = sorted(p.parent for p in (ROOT / "packages").glob("*/package.json"))

#: `import x from "pkg"`, `import { a } from "pkg/sub"`, `import "pkg"`;
#: not `import type`, which the build erases.
_STATIC = re.compile(r'^import\s+(?!type\s)(?:[^;]*?\sfrom\s+)?"([^".][^"]*)"', re.M)


def _package_name(specifier: str) -> str:
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]


def _published_sources(package: Path) -> list[Path]:
    return [
        path
        for path in (package / "src").rglob("*.ts*")
        if ".test." not in path.name and "__tests__" not in path.parts
    ]


@pytest.mark.parametrize("package", PACKAGES, ids=lambda p: p.name)
def test_a_statically_imported_module_is_a_dependency_or_a_required_peer(package: Path) -> None:
    manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
    optional = {
        name
        for name, meta in manifest.get("peerDependenciesMeta", {}).items()
        if meta.get("optional")
    }
    required = (
        set(manifest.get("dependencies", {})) | set(manifest.get("peerDependencies", {})) - optional
    )
    imported: dict[str, str] = {}
    for source in _published_sources(package):
        for specifier in _STATIC.findall(source.read_text(encoding="utf-8")):
            name = _package_name(specifier)
            if name.startswith("node:") or name == manifest["name"]:
                continue
            imported.setdefault(name, source.name)

    wrong = sorted(
        f"{name} (imported by {where})" for name, where in imported.items() if name not in required
    )
    assert not wrong, f"{manifest['name']} imports {wrong} statically, but needs none of them"

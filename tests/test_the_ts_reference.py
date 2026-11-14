"""``TsReference`` reads an npm package's TypeScript into pages: pinned on small packages written here.

The checked-in pages only show that the three real packages come out as they
did last time. Each rule of the reader is pinned here on a source built to hold
exactly the case: how a file's declarations and exports are found, how a name is
traced through re-exports, how a signature and its parameters are read, and the
errors a package that does not fit its areas raises.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from tools.reference_area import Area
from tools.ts_reference import Module, TsReference


def package(root: Path, files: dict[str, str]) -> Path:
    """A ``src`` directory holding ``files``, each dedented."""
    src = root / "src"
    for name, text in files.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return src


def module(root: Path, text: str, name: str = "m.ts") -> Module:
    src = package(root, {name: text})
    return Module(src / name, name)


# ── Exports are followed through every form, and a cycle ends ──


def test_two_modules_exporting_each_other_whole_end_and_list_each_name_once(
    tmp_path: Path,
) -> None:
    src = package(
        tmp_path,
        {
            "a.ts": 'export * from "./b.js";\nexport const A = 1;\n',
            "b.ts": 'export * from "./a.js";\nexport const B = 1;\n',
        },
    )
    reference = TsReference("p", src, [Area("all", "All", ("a.ts",))], entries=("a.ts",))
    assert reference.entry_names("a.ts") == ["A", "B"]
    assert reference.public == {"A", "B"}

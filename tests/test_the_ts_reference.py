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


def test_an_enum_lists_every_member_with_its_value_whatever_follows_it(tmp_path: Path) -> None:
    parsed = module(
        tmp_path,
        """
        export enum Color {
          Red = 1,
          Green,
          // a note between members
          Blue = "b", // and one after
          /* block */
          Last = 4
        }
        """,
    )
    members = parsed.declarations["Color"].members
    assert [(m.name, m.kind, m.type) for m in members] == [
        ("Red", "member", "1"),
        ("Green", "member", ""),
        ("Blue", "member", '"b"'),
        ("Last", "member", "4"),
    ]


def test_a_rest_parameter_is_optional_in_the_table_and_loses_its_dots(tmp_path: Path) -> None:
    src = package(
        tmp_path,
        {
            "index.ts": """
            /** Joins. */
            export function join(sep: string, ...parts: string[]): string {
              return parts.join(sep);
            }
            """
        },
    )
    reference = TsReference("p", src, [Area("all", "All", ("index.ts",))])
    page, _ = reference.page(reference.areas[0])
    assert "| `sep` | `string` | required | Not documented yet. |" in page
    assert "| `parts` | `string[]` | optional | Not documented yet. |" in page


def test_a_parameter_with_a_default_and_no_type_is_its_name_and_its_default(
    tmp_path: Path,
) -> None:
    src = package(
        tmp_path,
        {
            "index.ts": """
            /** Greets. */
            export function greet(name = "a, b", count = 2, fn = (x: number) => x) {}
            """
        },
    )
    reference = TsReference("p", src, [Area("all", "All", ("index.ts",))])
    page, _ = reference.page(reference.areas[0])
    assert '| `name` | — | `"a, b"` | Not documented yet. |' in page
    assert "| `count` | — | `2` | Not documented yet. |" in page
    assert "| `fn` | — | `(x: number) => x` | Not documented yet. |" in page


def test_a_regex_after_return_hides_its_brackets_but_a_division_does_not(
    tmp_path: Path,
) -> None:
    parsed = module(
        tmp_path,
        """
        export function f(a = (x: string) => { return /[)]/.test(x) }, b: number): void {}
        export function g(a = (n: number) => { return (n) / 2 }, b = 1): void {}
        """,
    )
    assert parsed.declarations["f"].signature == (
        "function f(a = (x: string) => { return /[)]/.test(x) }, b: number): void"
    )
    assert parsed.declarations["g"].signature == (
        "function g(a = (n: number) => { return (n) / 2 }, b = 1): void"
    )


def test_a_signature_written_with_a_trailing_comma_is_shown_without_it(tmp_path: Path) -> None:
    parsed = module(
        tmp_path,
        """
        export function run(
          a: number, // first
          b = 2,
        ): void {}
        """,
    )
    assert parsed.declarations["run"].signature == "function run(a: number, b = 2): void"


def test_a_union_type_in_a_member_table_cannot_end_its_cell(tmp_path: Path) -> None:
    src = package(
        tmp_path,
        {
            "index.ts": """
            export interface Opts {
              /** One of a | b. */
              mode: "a" | "b";
            }
            """
        },
    )
    reference = TsReference("p", src, [Area("all", "All", ("index.ts",))])
    page, _ = reference.page(reference.areas[0])
    assert '| `mode` | field | `"a" \\| "b"` | One of a \\| b. |' in page

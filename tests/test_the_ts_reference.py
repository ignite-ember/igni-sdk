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
from tools.ts_reference import Module, TsReference, object_pattern_properties


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


def test_a_method_written_with_a_trailing_comma_is_shown_without_it(tmp_path: Path) -> None:
    parsed = module(
        tmp_path,
        """
        export class Link {
          constructor(
            readonly url: string,
            private readonly env: { now?: () => number } = {},
          ) {}
          open(a: number, b: string,): void {}
        }
        """,
    )
    types = {m.name: m.type for m in parsed.declarations["Link"].members}
    assert types == {
        "constructor": "(readonly url: string, private readonly env: { now?: () => number } = {})",
        "open": "(a: number, b: string) => void",
    }


# ── Parameters: modifiers, patterns, the table ──


def page_of(root: Path, files: dict[str, str], link: object = None) -> str:
    src = package(root, files)
    reference = TsReference(
        "p",
        src,
        [Area("all", "All", ("index.ts",))],
        link=link,  # type: ignore[arg-type]
    )
    page, _ = reference.page(reference.areas[0])
    return page


def test_every_leading_modifier_of_a_constructor_parameter_is_dropped_from_its_name(
    tmp_path: Path,
) -> None:
    page = page_of(
        tmp_path,
        {
            "index.ts": """
            export class Client {
              /**
               * Connects.
               * @param link The link.
               * @param base Where.
               * @param name What.
               */
              constructor(protected readonly link: Link, private override base?: string, public name = "x") {}
            }
            """
        },
    )
    section = page.split("### Client.constructor()")[1]
    assert "| `link` | `Link` | required | The link. |" in section
    assert "| `base` | `string` | optional | Where. |" in section
    assert '| `name` | — | `"x"` | What. |' in section
    assert "readonly" not in section
    assert "Not documented yet." not in section


def test_a_props_pattern_lists_each_prop_by_the_name_a_caller_writes(tmp_path: Path) -> None:
    page = page_of(
        tmp_path,
        {
            "index.ts": """
            export interface ButtonProps {
              variant: "a" | "b";
              size?: string;
              label?: string;
            }

            /**
             * A button.
             * @param variant Which look.
             * @param size How big.
             */
            export function Button({ variant, size = "m", label: shown, ...rest }: ButtonProps) {}
            """
        },
    )
    assert '| `variant` | `"a" \\| "b"` | required | Which look. |' in page
    assert '| `size` | `string` | `"m"` | How big. |' in page
    assert "| `label` | `string` | optional | Not documented yet. |" in page
    assert "| `rest` | — | optional | Not documented yet. |" in page
    table = page.split("## Button\n")[1].split("A button.")[0].split("```\n")[1]
    assert "shown" not in table


def test_a_props_pattern_with_no_interface_has_no_types_and_only_a_default_makes_it_optional(
    tmp_path: Path,
) -> None:
    page = page_of(
        tmp_path,
        {"index.ts": 'export function Tag({ text, tone = "plain" }: TagProps) {}\n'},
    )
    assert "| `text` | — | optional | Not documented yet. |" in page
    assert '| `tone` | — | `"plain"` | Not documented yet. |' in page


def test_the_parameter_table_says_type_default_required_optional_or_undocumented(
    tmp_path: Path,
) -> None:
    page = page_of(
        tmp_path,
        {
            "index.ts": """
            /**
             * Does it.
             * @param a The first one,
             *   over two lines.
             * @param c With a default.
             */
            export function run(
              a: Record<string, number>,
              b?: (x: number, y: string) => void, // a comment, with a comma
              c: number = 3,
              d,
            ): void {}
            """
        },
    )
    assert (
        "```typescript\nfunction run(a: Record<string, number>, b?: (x: number, y: string) => void, c: number = 3, d): void\n```"
        in page
    )
    assert "| `a` | `Record<string, number>` | required | The first one, over two lines. |" in page
    assert "| `b` | `(x: number, y: string) => void` | optional | Not documented yet. |" in page
    assert "| `c` | `number` | `3` | With a default. |" in page
    assert "| `d` | — | required | Not documented yet. |" in page
    assert "@param" not in page


def test_a_function_with_no_parameters_has_no_table(tmp_path: Path) -> None:
    page = page_of(tmp_path, {"index.ts": "/** Go. */\nexport function go(): void {}\n"})
    assert "| Parameter" not in page


def test_a_class_page_has_a_table_of_parameters_for_each_method_that_takes_some(
    tmp_path: Path,
) -> None:
    page = page_of(
        tmp_path,
        {
            "index.ts": """
            export class Box {
              /**
               * Puts it in.
               * @param value What goes in.
               */
              put(value: string, at?: number): void {}
              /** Takes it out. */
              take(): string { return ""; }
            }
            """
        },
    )
    assert "### Box.put()" in page
    assert "| `value` | `string` | required | What goes in. |" in page
    assert "| `at` | `number` | optional | Not documented yet. |" in page
    assert "### Box.take()" not in page


def test_an_object_pattern_names_the_property_not_its_local_rename() -> None:
    assert object_pattern_properties("{ base: givenBase, n = 2, label: l = 'x', ...others }") == [
        ("base", "", False),
        ("n", "2", False),
        ("label", "'x'", False),
        ("others", "", True),
    ]
    assert object_pattern_properties("{}") == []


def test_a_type_parameter_defaulting_to_an_object_type_does_not_hide_the_extends_clause(
    tmp_path: Path,
) -> None:
    parsed = module(
        tmp_path,
        """
        export interface Opts<T extends object = {}> extends Base<T> {
          value: T;
        }
        export class Box<T = {}> implements Holder {
          item: T;
        }
        """,
    )
    opts = parsed.declarations["Opts"]
    assert opts.signature == "interface Opts<T extends object = {}> extends Base<T>"
    assert [m.name for m in opts.members] == ["value"]
    box = parsed.declarations["Box"]
    assert box.signature == "class Box<T = {}> implements Holder"
    assert [m.name for m in box.members] == ["item"]


def test_a_field_type_written_over_several_lines_as_a_union_is_one_type(tmp_path: Path) -> None:
    parsed = module(
        tmp_path,
        """
        export interface Job {
          state:
            | "queued"
            | "running";
          kind: "a" |
            "b";
          plain: string
          next: number;
        }
        """,
    )
    types = {m.name: m.type for m in parsed.declarations["Job"].members}
    assert types == {
        "state": '"queued" | "running"',
        "kind": '"a" | "b"',
        "plain": "string",
        "next": "number",
    }

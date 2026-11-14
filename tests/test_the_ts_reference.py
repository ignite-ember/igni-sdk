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

import pytest

from tools.reference_area import Area
from tools.ts_reference import (
    Module,
    ReferenceError_,
    TsReference,
    _prev_significant_index,
    member_parameters_text,
    object_pattern_properties,
    signature_parameters,
)


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


def test_a_docstring_line_that_starts_with_markdown_keeps_its_asterisks(tmp_path: Path) -> None:
    page = page_of(
        tmp_path,
        {
            "index.ts": """
            /**
             * Says where.
             *
             * **Not a navigation.** It stays here.
             *
             * *Soft* words.
             */
            export interface Where {
              /** Where. */
              at: string;
            }
            """
        },
    )

    assert "\n**Not a navigation.** It stays here.\n" in page
    assert "\n*Soft* words.\n" in page


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


# ── What each name says it is: member kinds and the member table ──


def test_each_member_says_whether_it_is_a_field_a_method_or_an_accessor(tmp_path: Path) -> None:
    parsed = module(
        tmp_path,
        """
        export class Thing {
          /** Name. */
          readonly name: string;
          count?: number = 0;
          static create<T>(x: T): Thing { return new Thing(); }
          get size(): number { return 1; }
          set size(value: number) {}
          private async run(a: string): Promise<void> {}
          inner: { a: number; b: string };
          /** @internal */
          secret: string;
        }
        """,
    )
    rows = [(m.name, m.kind, m.type, m.optional) for m in parsed.declarations["Thing"].members]
    assert rows == [
        ("name", "field", "string", False),
        ("count", "field", "number", True),
        ("create", "method", "(x: T) => Thing", False),
        ("size", "accessor", "number", False),
        ("size", "accessor", "value: number", False),
        ("run", "method", "(a: string) => Promise<void>", False),
        ("inner", "field", "{ a: number; b: string }", False),
    ]


def test_the_member_table_drops_its_description_column_when_no_member_says_what_it_is(
    tmp_path: Path,
) -> None:
    undocumented = page_of(
        tmp_path / "a",
        {"index.ts": "export interface Opts {\n  a: string;\n  b?: number;\n}\n"},
    )
    assert "| Member | Kind | Type |\n|---|---|---|\n| `a` | field | `string` |\n" in undocumented
    assert "What it is |\n|---|---|---|---|\n| `a`" not in undocumented
    documented = page_of(
        tmp_path / "b",
        {"index.ts": "export interface Opts {\n  /** The a. */\n  a: string;\n  b: number;\n}\n"},
    )
    assert (
        "| Member | Kind | Type | What it is |\n|---|---|---|---|\n"
        "| `a` | field | `string` | The a. |\n| `b` | field | `number` |  |\n"
    ) in documented


def test_a_name_exported_under_another_is_documented_as_the_package_names_it(
    tmp_path: Path,
) -> None:
    src = package(
        tmp_path,
        {
            "index.ts": (
                'export { Timeout as Wait } from "./time.js";\n'
                "/** Close by. */\nfunction Local(): void {}\n"
                "export { Local as Near };\n"
            ),
            "time.ts": "/** How long to wait. */\nexport const Timeout = 30;\n",
        },
    )
    reference = TsReference("p", src, [Area("all", "All", ("index.ts",))])
    index = reference.modules["index.ts"]
    wait = reference.resolve(index, "Wait")
    near = reference.resolve(index, "Near")
    assert wait is not None and near is not None
    assert (wait.name, wait.signature) == ("Wait", "const Wait = 30")
    assert (near.name, near.signature) == ("Near", "function Near(): void")
    page, _ = reference.page(reference.areas[0])
    assert "| [`Wait`](#wait) | const | `time.ts` | How long to wait. |" in page
    assert "| [`Near`](#near) | function | `index.ts` | Close by. |" in page
    assert "Timeout" not in page and "Local" not in page


def test_a_name_whose_reexport_leaves_the_package_or_is_never_declared_resolves_to_nothing(
    tmp_path: Path,
) -> None:
    src = package(
        tmp_path,
        {
            "index.ts": (
                'export { Outside as Far } from "zod";\n'
                'export { Absent as Gone } from "./time.js";\n'
                "export { Nowhere as Near };\n"
            ),
            "time.ts": "export const Timeout = 30;\n",
        },
    )
    reference = TsReference("p", src, [Area("all", "All", ("index.ts",))])
    index = reference.modules["index.ts"]
    assert reference.resolve(index, "Far") is None
    assert reference.resolve(index, "Gone") is None
    assert reference.resolve(index, "Near") is None


def test_the_character_before_an_index_skips_spaces_and_comments() -> None:
    assert _prev_significant_index("a /* c */ b", 10) == 0
    assert _prev_significant_index("  \n ", 4) == -1
    assert _prev_significant_index("/* c */ b", 8) == -1
    # A comment end with no start: the `/` itself is the last significant character.
    assert _prev_significant_index("*/ b", 3) == 1


# ── A package read into pages ──

SMALL = {
    "index.ts": """
    export { greet, type Options } from "./greet.js";
    export * from "./shapes.js";
    export { Timeout } from "./time.js";
    """,
    "greet.ts": """
    /** Options of {@link greet}. */
    export interface Options {
      /** Who to greet. */
      name: string;
    }

    /**
     * Says hello.
     *
     * More words that the table cell leaves out.
     * @param options Who and how.
     */
    export function greet(options: Options): string {
      return options.name;
    }

    /** Not public: index.ts does not export it. */
    export function helper(): void {}
    """,
    "shapes.ts": """
    /** @internal */
    export const HIDDEN = 1;
    /** A colour. */
    export type Colour =
      | "red"
      | "blue";
    export const SIZE = 3;
    """,
    "time.ts": """
    /** How long to wait. */
    export const Timeout = 30;
    """,
}


def small(root: Path, link: object = None) -> TsReference:
    return TsReference(
        "small",
        package(root, SMALL),
        [
            Area("hello", "Hello", ("greet.ts",), "About greeting."),
            Area("rest", "Rest", ("shapes.ts", "time.ts")),
        ],
        link=link,  # type: ignore[arg-type]
    )


def test_a_page_is_its_note_a_table_of_names_and_a_section_for_each(tmp_path: Path) -> None:
    reference = small(tmp_path)
    page, missing = reference.page(reference.areas[0])
    assert missing == 0
    assert page == textwrap.dedent(
        """\
        About greeting.

        Read from the source: every name below, its signature, its JSDoc, and — for a type or a class — its own members.

        | Name | Kind | Defined in | What it is |
        |---|---|---|---|
        | [`Options`](#options) | interface | `greet.ts` | Options of `greet`. |
        | [`greet`](#greet) | function | `greet.ts` | Says hello. |

        ## Options

        ```typescript
        interface Options
        ```

        Options of `greet`.

        | Member | Kind | Type | What it is |
        |---|---|---|---|
        | `name` | field | `string` | Who to greet. |

        ## greet

        ```typescript
        function greet(options: Options): string
        ```

        | Parameter | Type | Default | Meaning |
        |---|---|---|---|
        | `options` | `Options` | required | Who and how. |

        Says hello.

        More words that the table cell leaves out.
        """
    )


def test_a_name_is_documented_where_it_is_declared_through_every_way_it_is_exported(
    tmp_path: Path,
) -> None:
    reference = small(tmp_path)
    assert reference.entry_names() == ["greet", "Options", "Timeout", "HIDDEN", "Colour", "SIZE"]
    assert reference.public == {"greet", "Options", "Timeout", "HIDDEN", "Colour", "SIZE"}
    assert reference.entry_names("nowhere.ts") == []
    placed = reference.place()
    # Each name is on exactly one page, in the order its module exports it; the
    # private helper and the @internal name are on none.
    assert {slug: [d.name for d in found] for slug, found in placed.items()} == {
        "hello": ["Options", "greet"],
        "rest": ["Colour", "SIZE", "Timeout"],
    }
    assert reference.anchors() == {
        "Options": ("hello", "options"),
        "greet": ("hello", "greet"),
        "Colour": ("rest", "colour"),
        "SIZE": ("rest", "size"),
        "Timeout": ("rest", "timeout"),
    }


# ── The refusals ──


def test_a_missing_source_is_refused_naming_the_package_and_the_file(tmp_path: Path) -> None:
    src = package(tmp_path, {"index.ts": "export const A = 1;\n"})
    with pytest.raises(ReferenceError_, match="p: no source file gone.ts"):
        TsReference("p", src, [Area("a", "A", ("gone.ts",))])
    with pytest.raises(ReferenceError_, match="p: no source file other.ts"):
        TsReference("p", src, [Area("a", "A", ("index.ts",))], entries=("other.ts",))


def test_a_public_name_no_area_takes_is_refused_and_so_is_an_area_with_none(
    tmp_path: Path,
) -> None:
    src = package(
        tmp_path,
        {
            "index.ts": "export const A = 1;\nexport const B = 2;\n",
            "empty.ts": "const hidden = 1;\n",
        },
    )
    with pytest.raises(ReferenceError_, match=r"no reference page takes: \['A', 'B'\]"):
        TsReference("p", src, [Area("x", "X", ("empty.ts",))]).place()
    with pytest.raises(ReferenceError_, match=r"no public name: \['x'\]"):
        TsReference(
            "p", src, [Area("a", "A", ("index.ts",)), Area("x", "X", ("empty.ts",))]
        ).place()


def test_an_internal_name_needs_no_page_and_a_package_of_only_those_has_none(
    tmp_path: Path,
) -> None:
    src = package(tmp_path, {"index.ts": "/** @internal */\nexport const A = 1;\n"})
    reference = TsReference("p", src, [])
    assert reference.public == {"A"}
    assert reference.place() == {}


def test_an_unclosed_bracket_is_refused_when_a_declaration_is_read(tmp_path: Path) -> None:
    with pytest.raises(ReferenceError_, match="an unclosed bracket"):
        module(tmp_path, "export function f(a: number {\n")
    with pytest.raises(ReferenceError_, match="an unclosed bracket"):
        module(tmp_path, "export interface I {\n  a: number;\n")


def test_an_unclosed_bracket_in_a_member_leaves_its_type_empty_and_hides_what_follows(
    tmp_path: Path,
) -> None:
    parsed = module(tmp_path, "export class C {\n  go(a: number\n  other: string;\n}\n")
    members = parsed.declarations["C"].members
    # The line after the open bracket is inside it, so it is no member.
    assert [(m.name, m.type) for m in members] == [("go", "")]
    assert member_parameters_text(members[0]) == ""


# ── Exports: lists, stars, specifiers, cycles ──


def test_an_export_list_reads_type_prefixes_renames_trailing_commas_and_empty_items(
    tmp_path: Path,
) -> None:
    parsed = module(
        tmp_path,
        """
        export { type A, B as C, , D, } from "./x.js";
        export type { E } from "./y.js";
        export { F };
        export {};
        """,
    )
    assert parsed.reexports == {"A": "./x.js", "C": "./x.js", "D": "./x.js", "E": "./y.js", "F": ""}
    assert list(parsed.exported) == ["F"]
    assert parsed.aliases == {"C": "B"}


def test_a_module_exports_its_own_names_in_the_order_it_declares_them(tmp_path: Path) -> None:
    parsed = module(
        tmp_path,
        """
        export const zeta = 1;
        const private_ = 2;
        export function alpha(): void {}
        export type Mid = string;
        """,
    )
    assert list(parsed.exported) == ["zeta", "alpha", "Mid"]
    assert list(parsed.declarations) == ["zeta", "private_", "alpha", "Mid"]


def test_a_specifier_names_a_ts_tsx_or_index_file_and_a_package_specifier_is_ignored(
    tmp_path: Path,
) -> None:
    src = package(
        tmp_path,
        {
            "index.ts": (
                'export * from "./a.js";\nexport * from "./b.jsx";\n'
                'export * from "./dir/index.js";\nexport * from "./tsxdir";\n'
                'export * from "zod";\nexport * from "./nowhere.js";\n'
            ),
            "a.ts": "export const A = 1;\n",
            "b.tsx": "export const B = 1;\n",
            "dir/index.ts": "export const D = 1;\n",
            "tsxdir/index.tsx": "export const T = 1;\n",
            "dir/deep.ts": 'export * from "../a.js";\nexport const Deep = 1;\n',
        },
    )
    reference = TsReference("p", src, [Area("a", "A", ("index.ts",))])
    assert reference.target("index.ts", "./a.js") == "a.ts"
    assert reference.target("index.ts", "./b.jsx") == "b.tsx"
    assert reference.target("index.ts", "./dir/index.js") == "dir/index.ts"
    assert reference.target("index.ts", "./tsxdir") == "tsxdir/index.tsx"
    assert reference.target("dir/deep.ts", "../a.js") == ""  # only ./ specifiers are followed
    assert reference.target("index.ts", "zod") == ""
    assert reference.target("index.ts", "./nowhere.js") == ""
    assert reference.entry_names() == ["A", "B", "D", "T"]


def test_a_name_is_found_through_a_chain_of_re_exports_and_stars(tmp_path: Path) -> None:
    src = package(
        tmp_path,
        {
            "index.ts": 'export * from "./mid.js";\n',
            "mid.ts": 'export { Deep } from "./deep.js";\nexport * from "./other.js";\n',
            "deep.ts": "/** Deep. */\nexport function Deep(): void {}\n",
            "other.ts": "export const Other = 1;\n",
        },
    )
    reference = TsReference("p", src, [Area("a", "A", ("index.ts",))])
    index = reference.modules["index.ts"]
    deep = reference.resolve(index, "Deep")
    assert deep is not None and deep.exported_from == "deep.ts"
    other = reference.resolve(index, "Other")
    assert other is not None and other.exported_from == "other.ts"
    assert reference.resolve(index, "Missing") is None
    assert reference.entry_names() == ["Deep", "Other"]


def test_a_cycle_of_re_exports_resolves_to_nothing_instead_of_looping(tmp_path: Path) -> None:
    src = package(
        tmp_path,
        {
            "a.ts": 'export { X } from "./b.js";\nexport * from "./b.js";\n',
            "b.ts": 'export { X } from "./a.js";\nexport * from "./a.js";\n',
        },
    )
    reference = TsReference("p", src, [Area("a", "A", ("a.ts",))], entries=("a.ts",))
    assert reference.resolve(reference.modules["a.ts"], "X") is None
    assert reference.resolve(reference.modules["b.ts"], "Y") is None
    assert reference.entry_names("a.ts") == ["X"]
    # The name is public but has no declaration anywhere, so no page can hold it.
    with pytest.raises(ReferenceError_, match="no public name"):
        reference.place()


# ── Reading the text: brackets, strings, comments, regexes ──


def test_brackets_inside_strings_comments_and_regexes_do_not_end_a_parameter_list(
    tmp_path: Path,
) -> None:
    parsed = module(
        tmp_path,
        """
        export function f(a = ")", b = `)`, c = /[)]/, d = 1 / 2, /* ) */ e = '\\'' ): void {}
        export function g(
          // it's a comment with ) and a quote
          x: number,
        ): string {}
        """,
    )
    assert parsed.declarations["f"].signature == (
        "function f(a = \")\", b = `)`, c = /[)]/, d = 1 / 2, e = '\\''): void"
    )
    assert parsed.declarations["g"].signature == "function g(x: number): string"


# ── The words: JSDoc, summaries, the Also line ──


def summary_of(root: Path, doc: str) -> str:
    """The cell a table shows for a declaration documented by ``doc``."""
    src = package(root, {"index.ts": f"{doc}\nexport const A = 1;\n"})
    reference = TsReference("p", src, [Area("a", "A", ("index.ts",))])
    page, _ = reference.page(reference.areas[0])
    return page.split("| [`A`](#a) | const | `index.ts` | ")[1].split(" |\n")[0]


def test_a_summary_is_the_first_paragraph_on_one_line_and_stops_at_a_tag_fence_or_table(
    tmp_path: Path,
) -> None:
    def summary(name: str, doc: str) -> str:
        return summary_of(tmp_path / name, doc)

    assert summary("a", "/** One line. */") == "One line."
    assert summary("b", "/**\n * First line\n * goes on.\n *\n * Second paragraph.\n */") == (
        "First line goes on."
    )
    assert summary("c", "/**\n * Before the tag.\n * @param x ignored\n */") == "Before the tag."
    assert summary("d", "/**\n * Text.\n * ```ts\n * code\n * ```\n */") == "Text."
    assert summary("e", "/**\n * Text.\n * | a | b |\n */") == "Text."
    assert summary("f", "/**\n *\n * After a blank line.\n */") == "After a blank line."
    assert summary("g", "/** See {@link Foo} and {@link Bar baz}. */") == "See `Foo` and `Bar baz`."


def test_a_name_with_no_summary_is_a_dash_and_is_counted(tmp_path: Path) -> None:
    src = package(
        tmp_path,
        {"index.ts": "/** Has one. */\nexport const A = 1;\nexport const B = 2;\n"},
    )
    reference = TsReference("p", src, [Area("a", "A", ("index.ts",))])
    page, missing = reference.page(reference.areas[0])
    assert missing == 1
    assert "| [`A`](#a) | const | `index.ts` | Has one. |" in page
    assert "| [`B`](#b) | const | `index.ts` | — |" in page


def test_a_long_summary_is_cut_at_a_sentence_after_sixty_characters_else_at_a_word(
    tmp_path: Path,
) -> None:
    sentence = "This first sentence is comfortably longer than sixty characters in all."
    long_rest = " ".join(["more"] * 60)
    cut_at_sentence = summary_of(tmp_path / "a", f"/** {sentence} {long_rest} */")
    assert cut_at_sentence == sentence
    short = "Short one."
    cut_at_word = summary_of(tmp_path / "b", f"/** {short} {long_rest} */")
    assert cut_at_word.endswith("…") and len(cut_at_word) <= 201
    assert cut_at_word.startswith("Short one. more more")
    assert not cut_at_word[:-1].endswith(" ")
    exactly = "x" * 200
    assert summary_of(tmp_path / "c", f"/** {exactly} */") == exactly


def test_a_jsdoc_loses_its_marks_keeps_its_paragraphs_and_rewrites_links(tmp_path: Path) -> None:
    src = package(
        tmp_path,
        {
            "index.ts": (
                "/**\n * Title line.\n *\n * Body with {@link Other} in it.\n"
                " *   indented line\n * @param x The x.\n * @returns Ignored here.\n */\n"
                "export function f(x: number): void {}\n"
            )
        },
    )
    reference = TsReference("p", src, [Area("a", "A", ("index.ts",))])
    page, _ = reference.page(reference.areas[0])
    body = page.split("| `x` | `number` | required | The x. |\n\n")[1]
    assert body == (
        "Title line.\n\nBody with `Other` in it.\n  indented line\n@returns Ignored here.\n"
    )


def test_a_doc_separated_from_its_declaration_by_code_is_not_its_doc(tmp_path: Path) -> None:
    parsed = module(
        tmp_path,
        """
        /** Belongs to A. */
        export const A = 1;
        export const B = 2;
        /** Right above C. */

        export const C = 3;
        """,
    )
    docs = {name: d.doc for name, d in parsed.declarations.items()}
    assert docs == {"A": "/** Belongs to A. */", "B": "", "C": "/** Right above C. */"}


def test_windows_line_endings_read_like_unix_ones(tmp_path: Path) -> None:
    unix = (
        "/**\n * Does it.\n * @param a The a.\n */\nexport class K {\n  /** Field. */\n"
        "  a: string;\n  go(x: number): void {}\n}\n"
    )
    pages = []
    for name, text in (("u", unix), ("w", unix.replace("\n", "\r\n"))):
        src = tmp_path / name / "src"
        src.mkdir(parents=True)
        (src / "index.ts").write_bytes(text.encode())
        reference = TsReference("p", src, [Area("a", "A", ("index.ts",))])
        pages.append(reference.page(reference.areas[0])[0])
    assert pages[0] == pages[1].replace("\r", "")
    assert "\r" not in pages[1]


def test_the_also_line_links_the_other_public_names_a_signature_names(tmp_path: Path) -> None:
    files = {
        "index.ts": (
            "export interface Opts {}\nexport type Id = string;\n"
            "export function make(opts: Opts, id: Id, more: Opts, other: Unknown): make2 {}\n"
        )
    }
    asked: list[str] = []

    def link(name: str) -> str | None:
        asked.append(name)
        return {"Opts": "#opts", "Id": "other.md#id"}.get(name)

    page = page_of(tmp_path / "a", files, link)
    assert "**Also** [`Opts`](#opts), [`Id`](other.md#id).\n" in page
    assert "make" not in asked  # its own name is never asked about
    assert asked.count("Opts") >= 1
    assert "**Also**" not in page_of(tmp_path / "b", files)
    assert "**Also**" not in page_of(tmp_path / "c", files, lambda name: None)


def test_an_anchor_is_the_name_lower_cased_with_hyphens(tmp_path: Path) -> None:
    reference = small(tmp_path)
    assert reference.anchor("HostErrorCode") == "hosterrorcode"
    assert reference.anchor("a_b$C") == "a-b-c"
    assert reference.anchor("__x__") == "x"


# ── Declarations: what each form's signature is ──


def test_each_declaration_form_has_the_signature_a_reader_expects(tmp_path: Path) -> None:
    parsed = module(
        tmp_path,
        """
        export class Thing extends Base implements A, B {}
        export abstract class Abs {}
        export interface Opts<T extends object> extends Base<T> {}
        export async function af<T>(a: T): Promise<T> { return a; }
        export declare function d(a: number): void;
        export type Kind =
          | "a"
          | "b";
        export type Pair<A, B> = [A, B];
        export const MAX = 5;
        export const NAME: string = "x";
        export const LONG: string = "0123456789012345678901234567890123456789012345678901234567890";
        export const BIG = "01234567890123456789012345678901234567890123456789012345678901234567890123456789ab";
        export const table = {
          one: 1,
          two(a: number): number { return a; },
        };
        const hidden = 1;
        """,
    )
    signatures = {name: d.signature for name, d in parsed.declarations.items()}
    assert signatures == {
        "Thing": "class Thing extends Base implements A, B",
        "Abs": "class Abs",
        "Opts": "interface Opts<T extends object> extends Base<T>",
        "af": "async function af<T>(a: T): Promise<T>",
        "d": "function d(a: number): void",
        "Kind": 'type Kind = "a" | "b"',
        "Pair": "type Pair<A, B> = [A, B]",
        "MAX": "const MAX = 5",
        "NAME": 'const NAME: string = "x"',
        "LONG": "const LONG: string",
        "BIG": "const BIG",
        "table": "const table",
        "hidden": "const hidden = 1",
    }
    assert [(m.name, m.kind) for m in parsed.declarations["table"].members] == [
        ("one", "field"),
        ("two", "method"),
    ]
    assert list(parsed.exported) == [n for n in signatures if n != "hidden"]


def test_a_function_with_no_parens_and_a_class_with_no_body_are_not_declarations(
    tmp_path: Path,
) -> None:
    parsed = module(
        tmp_path,
        "export function nothing\nexport class Bare\nexport interface Open\nexport const ok = 1;\n",
    )
    assert list(parsed.declarations) == ["ok"]


def test_a_declaration_inside_a_body_is_not_a_declaration_and_the_last_of_a_name_wins(
    tmp_path: Path,
) -> None:
    parsed = module(
        tmp_path,
        """
        export function outer(): void {
          const inner = 1;
          function nested(): void {}
        }
        export function over(a: string): void;
        export function over(a: number): void {}
        """,
    )
    assert list(parsed.declarations) == ["outer", "over"]
    assert parsed.declarations["over"].signature == "function over(a: number): void"


def test_an_empty_file_and_a_file_with_only_comments_declare_and_export_nothing(
    tmp_path: Path,
) -> None:
    for name, text in (("a.ts", ""), ("b.ts", "// only a comment\n/* and another */\n")):
        parsed = module(tmp_path, text, name)
        assert (parsed.declarations, parsed.exported, parsed.reexports, parsed.stars) == (
            {},
            {},
            {},
            [],
        )


def test_the_module_exports_what_the_pages_use() -> None:
    import tools.ts_reference as ts_reference

    assert sorted(ts_reference.__all__) == [
        "Area",
        "Declaration",
        "Member",
        "Module",
        "ReferenceError_",
        "TsReference",
    ]
    assert issubclass(ReferenceError_, ValueError)


def test_a_pattern_annotated_with_an_inline_type_takes_its_types_and_requiredness() -> None:
    """``({ name, size = 18 }: { name: string; size?: number })`` is not all optional."""
    params = signature_parameters(
        "{ name, size = 18 }: { name: string; size?: number }"
    )
    assert [(p.name, p.type, p.default, p.optional) for p in params] == [
        ("name", "string", "", False),
        ("size", "number", "18", True),
    ]

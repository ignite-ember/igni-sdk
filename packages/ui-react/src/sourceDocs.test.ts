/**
 * What the pages generated from these five files' doc comments say
 * about them, and how they are imported.
 *
 * The reference pages on the site are written from each component's
 * `@param` lines, so a line naming a prop the component does not take,
 * or a prop with no line, is a page that lies. And the published build
 * is compiled for NodeNext, where a relative import without `.js` does
 * not resolve: it works in this repository and breaks for the consumer.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const FILES = [
  "OverflowMenu.tsx",
  "Shell.tsx",
  "Skeleton.tsx",
  "Split.tsx",
  "Toast.tsx",
];

function parse(file: string): ts.SourceFile {
  return ts.createSourceFile(
    file,
    readFileSync(join(here, file), "utf8"),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
}

/** A function whose first parameter is destructured, with what each side says. */
interface Documented {
  name: string;
  exported: boolean;
  props: string[];
  documented: string[];
}

function collect(source: ts.SourceFile): Documented[] {
  const found: Documented[] = [];
  const visit = (node: ts.Node) => {
    const isFunction =
      ts.isFunctionDeclaration(node) ||
      (ts.isMethodDeclaration(node) && ts.isObjectLiteralExpression(node.parent));
    if (isFunction) {
      const first = node.parameters[0];
      if (first !== undefined && ts.isObjectBindingPattern(first.name)) {
        const exported =
          (ts.isFunctionDeclaration(node) &&
            node.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword)) ||
          // A method on the exported `Skeleton` object.
          ts.isMethodDeclaration(node);
        found.push({
          name: node.name?.getText() ?? "",
          exported: Boolean(exported),
          props: first.name.elements.map((e) => e.name.getText()),
          documented: ts
            .getJSDocTags(node)
            .filter(ts.isJSDocParameterTag)
            .map((t) => t.name.getText()),
        });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

describe("the @param lines of the components", () => {
  for (const file of FILES) {
    it(`${file} documents exactly the props each exported component takes`, () => {
      const components = collect(parse(file)).filter((c) => c.exported);
      expect(components.length).toBeGreaterThan(0);
      for (const c of components) {
        expect(
          [...c.documented].sort(),
          `${file}: ${c.name}`,
        ).toEqual([...c.props].sort());
      }
    });
  }

  it("covers every component the five files export", () => {
    const names = FILES.flatMap((f) =>
      collect(parse(f))
        .filter((c) => c.exported)
        .map((c) => c.name),
    );
    expect(names.sort()).toEqual(
      [
        "AppShell",
        "Banner",
        "Block",
        "Circle",
        "Line",
        "OverflowMenu",
        "Rows",
        "Scroll",
        "Split",
        "ToastHost",
      ].sort(),
    );
  });
});

describe("the imports of the components", () => {
  for (const file of FILES) {
    it(`${file} imports its neighbours with a .js specifier`, () => {
      const specifiers: string[] = [];
      for (const stmt of parse(file).statements) {
        if (
          (ts.isImportDeclaration(stmt) || ts.isExportDeclaration(stmt)) &&
          stmt.moduleSpecifier !== undefined &&
          ts.isStringLiteral(stmt.moduleSpecifier)
        ) {
          specifiers.push(stmt.moduleSpecifier.text);
        }
      }
      const relative = specifiers.filter((s) => s.startsWith("."));
      for (const s of relative) expect(s, file).toMatch(/\.js$/);
    });
  }

  it("has relative imports to check in the files that are known to have them", () => {
    // Guards the loop above from passing on a parse that found nothing.
    const count = (file: string) =>
      parse(file).statements.filter(
        (s) =>
          ts.isImportDeclaration(s) &&
          ts.isStringLiteral(s.moduleSpecifier) &&
          s.moduleSpecifier.text.startsWith("."),
      ).length;
    expect(count("OverflowMenu.tsx")).toBe(1);
    expect(count("Split.tsx")).toBe(1);
    expect(count("Toast.tsx")).toBe(1);
  });
});

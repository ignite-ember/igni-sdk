/**
 * Every name an npm package exports is on its reference page.
 *
 * The reference pages on igni's site are written by the Python
 * generator (`tools/sdk_docs.py`), which reads the TypeScript source
 * as text. Text is the wrong instrument for a question like "what does
 * this package publish?", and it was the right one for none of them:
 * a name can be exported through a form the reader of the text misses,
 * and the page then omits it silently — the reader looks for it in the
 * reference and it is not there.
 *
 * This asks the compiler instead. `ts.createProgram` reads the
 * package the way Node will, and `checker.getExportsOfModule` answers
 * the question exactly: these are the names. Every one of them has to
 * be on a page, or the package publishes something it does not
 * document.
 *
 * The two sides are independent on purpose. The generator's answer
 * comes from a regex over the source; this one comes from the
 * compiler's symbol table. If they ever disagree, one of them is
 * wrong, and the reference is the place it shows.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "..", "..");
const SITE = join(ROOT, "docs", "site");

/**
 * The npm packages, and the entry points that make up their public
 * surface — the main one, and any subpath they publish.
 */
const PACKAGES = [
  {
    slug: "extension-bridge",
    directory: join("packages", "extension-bridge"),
    entries: ["src/index.ts", "src/protocol.ts", "src/tokens.ts"],
  },
  {
    slug: "ui-react",
    directory: join("packages", "ui-react"),
    entries: ["src/index.ts"],
  },
];

interface Index {
  packages: { name: string; version: string; registryName: string }[];
  pages: { package: string; slug: string; file: string; category: string }[];
}

function readIndex(): Index {
  return JSON.parse(readFileSync(join(SITE, "index.json"), "utf8")) as Index;
}

/**
 * The names a package's reference pages document.
 *
 * Only the reference pages count: a guide page may have a heading that
 * happens to share a name with an export, and that would satisfy this
 * test without documenting anything.
 */
function documentedNames(index: Index, slug: string): Set<string> {
  const out = new Set<string>();
  for (const page of index.pages) {
    if (page.package !== slug || !page.slug.startsWith("reference-")) continue;
    const file = join(SITE, page.file);
    if (!existsSync(file)) continue;
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(/^## (.+)$/gm)) {
      out.add(match[1].trim());
    }
  }
  return out;
}

/**
 * The names an entry point exports, as the compiler sees them, and
 * whether each is marked `@internal` — a name the package declares
 * for its own use and does not publish.
 *
 * One program reads every entry point of a package: the standard
 * library's type definitions are the expensive part, and loading them
 * once for the package is seconds the test does not wait twice.
 */
function exportedNames(directory: string, entries: string[]): Map<string, Map<string, boolean>> {
  const files = entries.map((entry) => join(ROOT, directory, entry));
  const program = ts.createProgram(files, {
    target: ts.ScriptTarget.ES2022,
    lib: ["lib.es2022.d.ts", "lib.dom.d.ts", "lib.dom.iterable.d.ts"],
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    jsx: ts.JsxEmit.ReactJSX,
    strict: true,
    skipLibCheck: true,
    noEmit: true,
  });
  const checker = program.getTypeChecker();
  const out = new Map<string, Map<string, boolean>>();
  for (const [index, file] of files.entries()) {
    const entry = entries[index];
    const source = program.getSourceFile(file);
    if (!source) throw new Error(`no source file for ${entry}`);
    const moduleSymbol = checker.getSymbolAtLocation(source);
    if (!moduleSymbol) throw new Error(`${entry} is not a module`);
    const names = new Map<string, boolean>();
    for (const symbol of checker.getExportsOfModule(moduleSymbol)) {
      const name = symbol.getName();
      if (name === "default") continue;
      const target =
        symbol.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
      const internal = target.getJsDocTags().some((tag) => tag.name === "internal");
      names.set(name, internal);
    }
    out.set(entry, names);
  }
  return out;
}

describe("the npm packages' reference pages", () => {
  const index = readIndex();

  it("the index knows each package by the name the site routes it on", () => {
    for (const pkg of PACKAGES) {
      expect(index.packages.map((entry) => entry.name)).toContain(pkg.slug);
    }
  });

  for (const pkg of PACKAGES) {
    it(
      `${pkg.slug}: every name it exports is documented`,
      () => {
        const documented = documentedNames(index, pkg.slug);
        expect(documented.size).toBeGreaterThan(0);
        const missing: string[] = [];
        const exported = exportedNames(pkg.directory, pkg.entries);
        for (const entry of pkg.entries) {
          const names = exported.get(entry);
          if (!names) throw new Error(`no exports read for ${entry}`);
          for (const [name, internal] of names) {
            if (internal) continue;
            if (!documented.has(name)) missing.push(`${entry}: ${name}`);
          }
        }
        expect(missing).toEqual([]);
      },
      // Reading the standard library's types is slow on a cold
      // machine: ten seconds on CI, under two here. The test is not
      // slow because it is wrong, so it is given the time it needs.
      120_000,
    );
  }
});

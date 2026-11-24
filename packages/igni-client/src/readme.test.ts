// Every TypeScript block in this package's README compiles against the client,
// and runs as it is pasted.
//
// The README pairs each ```python block with a ```typescript twin right after
// it (the site shows the pair as one Python | TypeScript toggle). A twin takes
// its Python block's marker, the comment on the line before the python fence:
//
// * none — the twin runs on its own, as a module, top-level `await` and all;
// * `<!-- continues -->` — it runs in one module with the twin before it;
// * `<!-- illustrative -->` — it needs a live igni, so it is only type-checked;
// * `<!-- illustrative-ts -->` — the Python block runs, but the TypeScript
//   FakeIgni cannot play what it shows, so the twin is only type-checked.
//
// Everything below "## API reference" is the generated reference, not examples.

import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

const PACKAGE = join(dirname(fileURLToPath(import.meta.url)), "..");
const README = join(PACKAGE, "README.md");
const REPO = join(PACKAGE, "..", "..");
const END = "## API reference";
/** How long one twin may take before it counts as hung. */
const RUN_TIMEOUT_MS = 15_000;

type Marker = "" | "continues" | "illustrative" | "illustrative-ts";

interface Block {
  lang: string;
  /** The README line of the opening fence. */
  line: number;
  /** The README line after the closing fence. */
  after: number;
  code: string;
  marker: Marker;
}

/** A run of twins that execute as one module: a block and the ones that continue it. */
interface Chain {
  line: number;
  code: string;
  runs: boolean;
}

const FENCE = /^```([\w-]*)\s*$/;
const MARKER = /^<!--\s*(continues|illustrative|illustrative-ts)\s*-->$/;

/** The fenced blocks above the API reference, with the marker on the line before each. */
function readmeBlocks(text: string): Block[] {
  const lines = text.split("\n");
  const end = lines.findIndex((line) => line.trim() === END);
  const blocks: Block[] = [];
  for (let i = 0; i < (end < 0 ? lines.length : end); i++) {
    const opened = FENCE.exec(lines[i]);
    if (!opened || !opened[1]) {
      continue;
    }
    let j = i + 1;
    while (j < lines.length && !/^```\s*$/.test(lines[j])) {
      j++;
    }
    const marked = MARKER.exec((lines[i - 1] ?? "").trim());
    blocks.push({
      lang: opened[1],
      line: i + 1,
      after: j + 1,
      code: lines.slice(i + 1, j).join("\n"),
      marker: (marked?.[1] ?? "") as Marker,
    });
    i = j;
  }
  return blocks;
}

/** Each python block's twin, or the python blocks that have none. */
function twins(text: string): { pairs: Array<[Block, Block]>; missing: Block[] } {
  const lines = text.split("\n");
  const blocks = readmeBlocks(text);
  const pairs: Array<[Block, Block]> = [];
  const missing: Block[] = [];
  blocks.forEach((block, index) => {
    if (block.lang !== "python") {
      return;
    }
    const next = blocks[index + 1];
    const between = next ? lines.slice(block.after, next.line - 1) : [];
    if (next && next.lang === "typescript" && between.length === 1 && between[0].trim() === "") {
      pairs.push([block, next]);
    } else {
      missing.push(block);
    }
  });
  return { pairs, missing };
}

/** The twins as modules: continuing ones joined, each knowing whether it runs. */
function chains(text: string): Chain[] {
  const found: Chain[] = [];
  for (const [python, ts] of twins(text).pairs) {
    if (python.marker === "continues" && found.length) {
      found[found.length - 1].code += `\n${ts.code}`;
      continue;
    }
    const runs = python.marker !== "illustrative" && python.marker !== "illustrative-ts";
    found.push({ line: ts.line, code: ts.code, runs });
  }
  return found;
}

/** A twin as a module beside the package: the package names point at its source. */
function asModule(code: string): string {
  const rewritten = code
    .replaceAll('"@ignite-ember/igni-client/testing"', '"../src/testing/index.js"')
    .replaceAll('"@ignite-ember/igni-client"', '"../src/index.js"');
  return `${rewritten}\n\nexport {};\n`;
}

function failAfter(ms: number, line: number): { promise: Promise<never>; cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const promise = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`README.md:${line} did not finish in ${ms} ms`)), ms);
  });
  return { promise, cancel: () => clearTimeout(timer) };
}

const text = readFileSync(README, "utf-8");
const modules = chains(text);
let work = "";
let scratch = "";

describe("the README's TypeScript twins", () => {
  beforeAll(() => {
    // Inside the package, so its modules resolve the client's source and ws.
    work = mkdtempSync(join(PACKAGE, ".readme-twins-"));
    scratch = join(work, "cwd");
    mkdirSync(scratch);
    for (const chain of modules) {
      writeFileSync(join(work, `readme_${chain.line}.ts`), asModule(chain.code));
    }
  });

  afterAll(() => {
    if (work) {
      rmSync(work, { recursive: true, force: true });
    }
  });

  it("finds the twins", () => {
    expect(modules.length).toBeGreaterThanOrEqual(20);
  });

  it("gives every python example a typescript twin right after it", () => {
    const { missing } = twins(text);
    expect(missing.map((block) => `README.md:${block.line}`)).toEqual([]);
  });

  it(
    "type-checks every twin against the client's source",
    () => {
      const config = {
        extends: "../../../tsconfig.json",
        compilerOptions: { noEmit: true, skipLibCheck: true },
        include: ["readme_*.ts"],
      };
      writeFileSync(join(work, "tsconfig.json"), JSON.stringify(config));
      const done = spawnSync("npx", ["tsc", "--noEmit", "-p", join(work, "tsconfig.json")], {
        cwd: REPO,
        encoding: "utf-8",
      });
      // tsc names a twin by its module, readme_<line>.ts: the README line of its fence.
      expect(done.stdout + done.stderr).toBe("");
      expect(done.status).toBe(0);
    },
    180_000,
  );

  for (const chain of modules.filter((each) => each.runs)) {
    it(
      `runs the twin at README.md:${chain.line}`,
      async () => {
        const here = process.cwd();
        const log = vi.spyOn(console, "log").mockImplementation(() => {});
        const write = vi.spyOn(process.stdout, "write").mockImplementation(() => true);
        process.chdir(scratch); // a twin may write files (App.generateKey)
        const deadline = failAfter(RUN_TIMEOUT_MS, chain.line);
        try {
          const module = pathToFileURL(join(work, `readme_${chain.line}.ts`)).href;
          await Promise.race([import(/* @vite-ignore */ module), deadline.promise]).catch((error: unknown) => {
            throw new Error(`README.md:${chain.line}: ${String(error instanceof Error ? error.stack : error)}`);
          });
        } finally {
          deadline.cancel();
          process.chdir(here);
          log.mockRestore();
          write.mockRestore();
        }
      },
      RUN_TIMEOUT_MS + 5_000,
    );
  }
});

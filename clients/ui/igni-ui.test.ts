/**
 * The stylesheet an extension bundles, read as CSS rather than as text.
 *
 * `ui-react/styled.test.ts` pins that every class a component renders
 * is defined here, and `extension-bridge/tokens.test.ts` that the token
 * lists agree. Neither looks at a declaration: a colour, a `min-height`
 * or a media query could change and both would pass. This reads the file
 * into rules and asserts what the rules say.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(here, "igni-ui.css"), "utf8");

interface Rule {
  /** The enclosing at-rule's prelude, or "" at top level. */
  media: string;
  selector: string;
  decls: Record<string, string>;
}

/** Strip comments, then walk braces. Throws on an unbalanced file. */
function parse(css: string): Rule[] {
  const text = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const rules: Rule[] = [];
  const stack: string[] = [];
  let buf = "";
  let current: Rule | null = null;
  for (const ch of text) {
    if (ch === "{") {
      const prelude = buf.trim().replace(/\s+/g, " ");
      buf = "";
      if (prelude.startsWith("@media") || prelude.startsWith("@supports")) {
        stack.push(prelude);
      } else if (prelude.startsWith("@keyframes")) {
        stack.push(prelude);
      } else {
        current = { media: stack.join(" "), selector: prelude, decls: {} };
        stack.push("");
      }
    } else if (ch === "}") {
      if (stack.length === 0) throw new Error("unbalanced closing brace");
      stack.pop();
      if (current) {
        for (const d of buf.split(";")) {
          const i = d.indexOf(":");
          if (i > 0) current.decls[d.slice(0, i).trim()] = d.slice(i + 1).trim().replace(/\s+/g, " ");
        }
        rules.push(current);
        current = null;
      }
      buf = "";
    } else {
      buf += ch;
    }
  }
  if (stack.length !== 0) throw new Error("unclosed brace");
  return rules;
}

const RULES = parse(SOURCE);

/** The declarations of every top-level rule whose selector list contains `selector`. */
function declsOf(selector: string, media = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of RULES) {
    if (r.media !== media) continue;
    if (r.selector.split(",").map((s) => s.trim()).includes(selector)) Object.assign(out, r.decls);
  }
  return out;
}

describe("the file is CSS", () => {
  it("has balanced braces and no rule without a selector", () => {
    expect(RULES.length).toBeGreaterThan(200);
    expect(RULES.every((r) => r.selector.length > 0)).toBe(true);
  });

  it("imports nothing, so an extension can bundle it as is", () => {
    expect(SOURCE).not.toMatch(/@import/);
  });
});

describe("the tokens", () => {
  const root = RULES.filter((r) => r.selector === ":root" && r.media === "").flatMap((r) =>
    Object.entries(r.decls),
  );

  it("are named igni's, with none left from the old product name", () => {
    const names = root.map(([k]) => k);
    expect(names).toContain("--igni-orange");
    expect(names).toContain("--igni-red");
    expect(SOURCE.toLowerCase()).not.toContain("ember-orange");
    expect(names.filter((n) => /ember/i.test(n))).toEqual([]);
  });

  it("each say in a comment what they are for", () => {
    const block = SOURCE.slice(SOURCE.indexOf(":root {"), SOURCE.indexOf("\n}\n", SOURCE.indexOf(":root {")));
    const lines = block.split("\n").map((l) => l.trim());
    const bare: string[] = [];
    let described = false;
    for (const line of lines) {
      if (line.startsWith("/*")) described = true;
      else if (line.startsWith("--")) {
        if (!described) bare.push(line.split(":")[0]);
        // A comment covers the declarations up to the next blank line.
      } else if (line === "") described = false;
    }
    expect(bare).toEqual([]);
  });

  it("have a standalone fallback for every var() the file uses without one", () => {
    const defined = new Set(root.map(([k]) => k));
    const local = new Set(["--ui-split-w"]);
    const used = new Set([...SOURCE.matchAll(/var\((--[a-z0-9-]+)\s*[,)]/g)].map((m) => m[1]));
    const missing = [...used].filter((u) => !defined.has(u) && !local.has(u));
    expect(missing).toEqual([]);
  });
});

describe("the header comment", () => {
  const header = SOURCE.slice(0, SOURCE.indexOf("*/"));

  it("does not deny the layout the file defines", () => {
    expect(header).not.toMatch(/no page shell/i);
    expect(header).not.toMatch(/no\s+split pane/i);
    expect(header).not.toMatch(/no scroll container/i);
  });

  it("names the three shapes it does define, and they exist", () => {
    for (const cls of [".ui-shell", ".ui-scroll", ".ui-split"]) {
      expect(header).toContain(cls);
      expect(Object.keys(declsOf(cls)).length).toBeGreaterThan(0);
    }
  });
});

describe("a failed copy", () => {
  it("shows in the danger colour rather than looking like it worked", () => {
    const failed = declsOf('.diagram-copy[data-state="failed"]');
    expect(failed.color).toMatch(/^var\(--danger,/);
    expect(failed["border-color"]).toMatch(/^var\(--danger,/);
    expect(failed.color).not.toBe(declsOf(".diagram-copy").color);
  });
});

describe("layout", () => {
  it("lets the shell's body and a scroll pane shrink so panes scroll rather than grow", () => {
    expect(declsOf(".ui-shell").display).toBe("flex");
    expect(declsOf(".ui-shell")["flex-direction"]).toBe("column");
    expect(declsOf(".ui-shell-body")["min-height"]).toBe("0");
    expect(declsOf(".ui-scroll")["min-height"]).toBe("0");
    expect(declsOf(".ui-scroll").overflow).toBe("auto");
    expect(declsOf(".ui-split")["min-height"]).toBe("0");
  });

  it("gives the element a page mounts its shell into the body's height", () => {
    // `<body><div id="root"><div class="ui-shell">`: without it the shell's
    // `height: 100%` resolved against an auto-height #root, and collapsed.
    expect(declsOf("html")["height"]).toBe("100%");
    expect(declsOf("body")["height"]).toBe("100%");
    expect(declsOf("body > :has(> .ui-shell)")["height"]).toBe("100%");
    expect(declsOf(".ui-shell")["height"]).toBe("100%");
  });

  it("sizes a split from its own --ui-split-w, 280px by default, on either side", () => {
    expect(declsOf(".ui-split")["grid-template-columns"]).toBe("var(--ui-split-w, 280px) 5px 1fr");
    expect(declsOf(".ui-split-end")["grid-template-columns"]).toBe("1fr 5px var(--ui-split-w, 280px)");
    // No literal width anywhere else: two splits would share it.
    expect(SOURCE).not.toMatch(/--ui-split-w:\s*\d/);
  });
});

describe("forms", () => {
  it("dims a disabled check once, on the wrapper only", () => {
    expect(declsOf(".ui-check:has(input:disabled)").opacity).toBe("0.5");
    expect(declsOf(".ui-check input:disabled").opacity).toBeUndefined();
    expect(declsOf(".ui-check input").opacity).toBeUndefined();
  });
});

describe("motion", () => {
  it("slows the spinner under prefers-reduced-motion", () => {
    const reduced = declsOf(".ui-spinner", "@media (prefers-reduced-motion: reduce)");
    expect(reduced["animation-duration"]).toBe("2.4s");
    expect(declsOf(".ui-spinner").animation).toContain("ui-spin");
  });

  it("has a reduced-motion rule for each of the file's blocks", () => {
    expect(SOURCE.match(/@media \(prefers-reduced-motion: reduce\)/g)?.length).toBe(4);
  });
});

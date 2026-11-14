// @vitest-environment jsdom
/**
 * Markdown as prose: what the wrapper is, which GitHub extensions
 * render, how links are opened, and what an unsafe source cannot do.
 *
 * Block structure, a table, one link and a raw img are in
 * tier1.test.tsx.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Markdown } from "./Markdown.js";

afterEach(cleanup);

function draw(source: string, className?: string) {
  return render(<Markdown className={className}>{source}</Markdown>).container;
}

describe("the wrapper", () => {
  it("is a div of ui-prose, and adds a caller's class after it", () => {
    expect(draw("x").firstElementChild?.className).toBe("ui-prose");
    cleanup();
    expect(draw("x", "wide").firstElementChild?.className).toBe("ui-prose wide");
  });

  it("is there, and empty, for an empty source", () => {
    const root = draw("").firstElementChild;
    expect(root?.className).toBe("ui-prose");
    expect(root?.childElementCount).toBe(0);
  });
});

describe("GitHub-flavoured markdown", () => {
  it("renders strikethrough", () => {
    expect(draw("~~gone~~").querySelector("del")?.textContent).toBe("gone");
  });

  it("renders task lists as checkboxes, checked or not", () => {
    const boxes = draw("- [x] done\n- [ ] todo").querySelectorAll(
      'input[type="checkbox"]',
    );
    expect(boxes).toHaveLength(2);
    expect((boxes[0] as HTMLInputElement).checked).toBe(true);
    expect((boxes[1] as HTMLInputElement).checked).toBe(false);
  });

  it("turns a bare address into a link", () => {
    const a = draw("see https://example.test/docs now").querySelector("a");
    expect(a?.getAttribute("href")).toBe("https://example.test/docs");
    expect(a?.textContent).toBe("https://example.test/docs");
  });
});

describe("links", () => {
  it("open in a new tab without a handle on this frame, autolinks too", () => {
    const links = draw(
      "[one](https://a.test) and https://b.test and [two](https://c.test \"Title\")",
    ).querySelectorAll("a");
    expect(links).toHaveLength(3);
    for (const a of links) {
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toBe("noopener noreferrer");
    }
    expect(links[2].getAttribute("title")).toBe("Title");
  });

  it.each([
    ["javascript:alert(1)"],
    ["JaVaScRiPt:alert(1)"],
    ["data:text/html,<script>alert(1)</script>"],
  ])("does not leave %s as an address to follow", (href) => {
    const a = draw(`[click](${href})`).querySelector("a");
    const kept = a?.getAttribute("href") ?? "";
    expect(kept).not.toMatch(/^\s*(javascript|data):/i);
  });
});

describe("raw HTML", () => {
  it("is shown as text, never made into elements", () => {
    const c = draw(
      '<script>alert(1)</script>\n\n<b onclick="x()">bold</b>\n\n<iframe src="https://evil.test"></iframe>',
    );
    expect(c.querySelector("script, iframe, b, [onclick]")).toBeNull();
  });
});

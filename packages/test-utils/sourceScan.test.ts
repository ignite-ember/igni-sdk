/**
 * `withoutComments` is the scanner the floor's guards read source
 * through. Its promise is that comments vanish and nothing else moves:
 * the same length, the same lines, strings untouched.
 */
import { describe, expect, it } from "vitest";

import { withoutComments } from "./sourceScan";

describe("withoutComments: offsets and lines", () => {
  it("keeps the length when a block comment holds an astral character", () => {
    const src = "a /* 😀 */ b";
    const out = withoutComments(src);
    expect(out.length).toBe(src.length);
    expect(out).toBe("a " + " ".repeat(src.length - 4) + " b");
    expect(out.indexOf("b")).toBe(src.indexOf("b"));
  });
});

/**
 * Joining class names: the ones that are set, one space apart, in the
 * order given.
 */
import { describe, expect, it } from "vitest";

import { cx } from "./cx.js";

describe("cx", () => {
  it("is an empty string for no parts", () => {
    expect(cx()).toBe("");
  });

  it("is an empty string when every part is unset", () => {
    expect(cx(false, null, undefined, "")).toBe("");
  });

  it("drops false, null, undefined and the empty string", () => {
    expect(cx("a", false, "b", null, "c", undefined, "", "d")).toBe("a b c d");
  });

  it("joins with one space and no space at either end", () => {
    expect(cx("a", "b")).toBe("a b");
    expect(cx("a")).toBe("a");
    expect(cx("", "a", "")).toBe("a");
  });

  it("keeps the order it was given", () => {
    expect(cx("z", "a", "m")).toBe("z a m");
  });

  it("keeps a part that already holds several classes, and repeats", () => {
    expect(cx("a b", "a")).toBe("a b a");
  });
});

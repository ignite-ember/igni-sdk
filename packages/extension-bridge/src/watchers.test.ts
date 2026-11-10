/**
 * `Watchers`: the functions following the theme or the params.
 */
import { describe, expect, it } from "vitest";

import { Watchers } from "./watchers";

describe("Watchers", () => {
  it("tells every watcher, in the order they started watching", () => {
    const watchers = new Watchers<string>();
    const seen: string[] = [];
    watchers.add((value) => seen.push(`a:${value}`));
    watchers.add((value) => seen.push(`b:${value}`));

    watchers.emit("light");

    expect(seen).toEqual(["a:light", "b:light"]);
  });

  it("stops telling a watcher that unsubscribed, and says whether it stopped anything", () => {
    const watchers = new Watchers<string>();
    const seen: string[] = [];
    const stop = watchers.add((value) => seen.push(value));

    expect(stop() as unknown).toBe(true);
    expect(stop() as unknown).toBe(false);
    watchers.emit("dark");

    expect(seen).toEqual([]);
  });

  it("tells nobody when nobody watches", () => {
    expect(() => new Watchers<number>().emit(1)).not.toThrow();
  });

  it("lets a watcher that throws stop the ones after it, as it always has", () => {
    const watchers = new Watchers<string>();
    const seen: string[] = [];
    watchers.add(() => {
      throw new Error("broken watcher");
    });
    watchers.add((value) => seen.push(value));

    expect(() => watchers.emit("light")).toThrow("broken watcher");
    expect(seen).toEqual([]);
  });
});

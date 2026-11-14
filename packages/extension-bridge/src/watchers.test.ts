/**
 * `Watchers`: the functions following the theme or the params.
 */
import { describe, expect, it } from "vitest";

import { Watchers } from "./watchers.js";

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

describe("Watchers held once and changed while they are told", () => {
  it("holds the same function once, and one unsubscribe removes it", () => {
    const watchers = new Watchers<string>();
    const seen: string[] = [];
    const fn = (value: string) => seen.push(value);
    const stopFirst = watchers.add(fn);
    const stopSecond = watchers.add(fn);

    watchers.emit("a");
    expect(seen).toEqual(["a"]);

    expect(stopFirst() as unknown).toBe(true);
    expect(stopSecond() as unknown).toBe(false);
    watchers.emit("b");
    expect(seen).toEqual(["a"]);
  });

  it("lets a watcher unsubscribe itself while it is being told, without skipping the next", () => {
    const watchers = new Watchers<string>();
    const seen: string[] = [];
    const stop = watchers.add((value) => {
      seen.push(`once:${value}`);
      stop();
    });
    watchers.add((value) => seen.push(`other:${value}`));

    watchers.emit("1");
    watchers.emit("2");

    expect(seen).toEqual(["once:1", "other:1", "other:2"]);
  });

  it("tells a watcher added during the emit in that same emit", () => {
    const watchers = new Watchers<string>();
    const seen: string[] = [];
    watchers.add(() => {
      watchers.add((value) => seen.push(`late:${value}`));
    });

    watchers.emit("1");

    expect(seen).toEqual(["late:1"]);
  });
});

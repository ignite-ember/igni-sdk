// @vitest-environment jsdom
/**
 * `Split`'s pointer drag and its limits, which tier1.test.tsx leaves
 * open because jsdom has no layout.
 *
 * Layout is stood in for by hand: the aside reports the width a browser
 * would have measured, and the window is as wide as the test says. What
 * is asserted is what the component does with those numbers: the width it
 * writes to its variable, what it announces, and what it tells `onResize`.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Split } from "./Split.js";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const originalWidth = window.innerWidth;
const windowWidth = (px: number) =>
  Object.defineProperty(window, "innerWidth", { value: px, configurable: true });
beforeEach(() => windowWidth(1_000));
afterEach(() => windowWidth(originalWidth));

function setup(
  props: Partial<Parameters<typeof Split>[0]> = {},
  measured = 300,
) {
  const result = render(
    <Split aside={<p>list</p>} label="Resize the list" {...props}>
      <p>document</p>
    </Split>,
  );
  const root = result.container.firstElementChild as HTMLElement;
  const handle = screen.getByRole("separator");
  const aside = root.querySelector(".ui-split-aside") as HTMLElement;
  vi.spyOn(aside, "getBoundingClientRect").mockReturnValue({
    width: measured,
  } as DOMRect);
  // jsdom does not implement pointer capture.
  const setPointerCapture = vi.fn();
  const releasePointerCapture = vi.fn();
  Object.assign(handle, { setPointerCapture, releasePointerCapture });
  const variable = root.getAttribute("data-split-var")!;
  return {
    ...result,
    root,
    handle,
    aside,
    setPointerCapture,
    releasePointerCapture,
    width: () => root.style.getPropertyValue(variable),
    announced: () => handle.getAttribute("aria-valuenow"),
    setMeasured: (px: number) =>
      vi.spyOn(aside, "getBoundingClientRect").mockReturnValue({
        width: px,
      } as DOMRect),
  };
}

const down = (el: Element, x: number) =>
  fireEvent.pointerDown(el, { clientX: x, pointerId: 7 });
const move = (el: Element, x: number) =>
  fireEvent.pointerMove(el, { clientX: x, pointerId: 7 });
const up = (el: Element) => fireEvent.pointerUp(el, { pointerId: 7 });

describe("Split without an onResize", () => {
  it("still moves with the keys", () => {
    const s = setup();
    fireEvent.keyDown(s.handle, { key: "Home" });
    expect(s.width()).toBe("160px");
    expect(s.announced()).toBe("160");
    // The aside is measured at 300px, as in a browser that has not
    // yet laid out the new width.
    fireEvent.keyDown(s.handle, { key: "ArrowRight" });
    expect(s.width()).toBe("312px");
    expect(s.announced()).toBe("312");
  });

  it("still goes back to defaultWidth on a double click", () => {
    const s = setup({ defaultWidth: 250 });
    fireEvent.keyDown(s.handle, { key: "End" });
    expect(s.width()).toBe("600px");
    fireEvent.doubleClick(s.handle);
    expect(s.width()).toBe("250px");
    expect(s.announced()).toBe("250");
  });
});

describe("Split drag", () => {
  it("captures the pointer and marks the root as resizing while it is down", () => {
    const s = setup();
    down(s.handle, 100);
    expect(s.setPointerCapture).toHaveBeenCalledWith(7);
    expect(s.root.classList.contains("ui-split-resizing")).toBe(true);
    up(s.handle);
    expect(s.root.classList.contains("ui-split-resizing")).toBe(false);
    expect(s.releasePointerCapture).toHaveBeenCalledWith(7);
  });

  it("widens by the distance travelled and announces it", () => {
    const s = setup();
    down(s.handle, 100);
    move(s.handle, 150);
    expect(s.width()).toBe("350px");
    expect(s.announced()).toBe("350");
  });

  it("goes the other way for an aside at the end", () => {
    const s = setup({ side: "end" });
    down(s.handle, 100);
    move(s.handle, 150);
    expect(s.width()).toBe("250px");
    move(s.handle, 40);
    expect(s.width()).toBe("360px");
  });

  it("tells onResize once, on release, and not on every move", () => {
    const onResize = vi.fn();
    const s = setup({ onResize });
    down(s.handle, 100);
    move(s.handle, 120);
    move(s.handle, 140);
    expect(onResize).not.toHaveBeenCalled();
    s.setMeasured(340);
    up(s.handle);
    expect(onResize).toHaveBeenCalledTimes(1);
    expect(onResize).toHaveBeenCalledWith(340);
  });

  it("finishes on a cancelled pointer the same way", () => {
    const onResize = vi.fn();
    const s = setup({ onResize });
    down(s.handle, 100);
    fireEvent.pointerCancel(s.handle, { pointerId: 7 });
    expect(onResize).toHaveBeenCalledTimes(1);
    expect(s.root.classList.contains("ui-split-resizing")).toBe(false);
  });

  it("ignores moves, releases and cancels when no drag is under way", () => {
    const onResize = vi.fn();
    const s = setup({ onResize });
    move(s.handle, 500);
    up(s.handle);
    fireEvent.pointerCancel(s.handle);
    expect(onResize).not.toHaveBeenCalled();
    expect(s.width()).toBe("280px");
    expect(s.announced()).toBe("280");
    expect(s.releasePointerCapture).not.toHaveBeenCalled();
  });

  it("stops following the pointer once released", () => {
    const s = setup();
    down(s.handle, 100);
    up(s.handle);
    move(s.handle, 400);
    expect(s.width()).toBe("280px");
  });

  it("releases without complaint where the browser has no releasePointerCapture", () => {
    const s = setup();
    Object.assign(s.handle, { releasePointerCapture: undefined });
    down(s.handle, 0);
    expect(() => up(s.handle)).not.toThrow();
  });

  it("does not need an onResize", () => {
    const s = setup();
    down(s.handle, 0);
    expect(() => up(s.handle)).not.toThrow();
    expect(() =>
      fireEvent.keyDown(s.handle, { key: "ArrowRight" }),
    ).not.toThrow();
    expect(() => fireEvent.doubleClick(s.handle)).not.toThrow();
  });
});

describe("Split limits", () => {
  it("never goes under min", () => {
    const s = setup({ min: 200 });
    down(s.handle, 500);
    move(s.handle, 0);
    expect(s.width()).toBe("200px");
  });

  it("never goes over max", () => {
    const s = setup({ max: 400 });
    down(s.handle, 0);
    move(s.handle, 900);
    expect(s.width()).toBe("400px");
  });

  it("never takes more than 60% of the window, whatever max says", () => {
    windowWidth(800);
    const s = setup({ max: 640 });
    down(s.handle, 0);
    move(s.handle, 900);
    expect(s.width()).toBe("480px");
  });

  it("lets min win on a window too narrow for it", () => {
    windowWidth(200);
    const s = setup({ min: 160 });
    down(s.handle, 0);
    move(s.handle, 900);
    expect(s.width()).toBe("160px");
  });

  it("clamps what it tells onResize on release", () => {
    windowWidth(800);
    const onResize = vi.fn();
    const s = setup({ onResize });
    down(s.handle, 0);
    s.setMeasured(700);
    up(s.handle);
    expect(onResize).toHaveBeenCalledWith(480);
  });

  it("rounds a fractional width", () => {
    const s = setup();
    down(s.handle, 0);
    move(s.handle, 10.6);
    expect(s.width()).toBe("311px");
  });

  it("keeps the 60% ceiling for the arrow keys, but not for End", () => {
    // End asks for max itself, which the ceiling then caps; the
    // announced width is what was applied.
    windowWidth(800);
    const onResize = vi.fn();
    const s = setup({ onResize, max: 640 });
    fireEvent.keyDown(s.handle, { key: "End" });
    expect(onResize).toHaveBeenLastCalledWith(480);
    expect(s.handle.getAttribute("aria-valuemax")).toBe("640");
  });

  it("steps 48px with Shift held, and 12px without", () => {
    const onResize = vi.fn();
    const s = setup({ onResize });
    fireEvent.keyDown(s.handle, { key: "ArrowRight", shiftKey: true });
    expect(onResize).toHaveBeenLastCalledWith(348);
    fireEvent.keyDown(s.handle, { key: "ArrowLeft" });
    expect(onResize).toHaveBeenLastCalledWith(288);
  });

  it("reports min and max as the range a screen reader hears", () => {
    const s = setup({ min: 120, max: 500 });
    expect(s.handle.getAttribute("aria-valuemin")).toBe("120");
    expect(s.handle.getAttribute("aria-valuemax")).toBe("500");
  });

  it("keeps the arrow keys' preventDefault to the keys it handles", () => {
    const s = setup();
    expect(fireEvent.keyDown(s.handle, { key: "ArrowRight" })).toBe(false);
    expect(fireEvent.keyDown(s.handle, { key: "a" })).toBe(true);
  });
});

describe("Split element", () => {
  it("writes the width into the root's variable, starting at defaultWidth", () => {
    const s = setup({ defaultWidth: 333 });
    expect(s.width()).toBe("333px");
    expect(s.announced()).toBe("333");
    fireEvent.keyDown(s.handle, { key: "Home" });
    expect(s.width()).toBe("160px");
  });

  it("goes back to defaultWidth and says so on a double click", () => {
    const onResize = vi.fn();
    const s = setup({ onResize, defaultWidth: 250 });
    fireEvent.keyDown(s.handle, { key: "End" });
    fireEvent.doubleClick(s.handle);
    expect(s.width()).toBe("250px");
    expect(onResize).toHaveBeenLastCalledWith(250);
  });

  it("adds the caller's class beside its own, and ui-split-end for the end", () => {
    const s = setup({ className: "mine", side: "end" });
    expect(s.root.className).toBe("ui-split ui-split-end mine");
  });

  it("is only ui-split for the start", () => {
    expect(setup().root.className).toBe("ui-split");
  });

  it("spreads the remaining props, and lets a caller's style join the variable", () => {
    const s = setup({
      id: "panes",
      "data-x": "1",
      style: { color: "red" },
    } as never);
    expect(s.root.id).toBe("panes");
    expect(s.root.getAttribute("data-x")).toBe("1");
    expect(s.root.style.color).toBe("red");
    expect(s.width()).toBe("280px");
  });

  it("labels the handle and titles it with the same words", () => {
    const s = setup({ label: "Resize the sidebar" });
    expect(s.handle.getAttribute("aria-label")).toBe("Resize the sidebar");
    expect(s.handle.getAttribute("title")).toBe("Resize the sidebar");
    expect(s.handle.getAttribute("aria-orientation")).toBe("vertical");
  });
});

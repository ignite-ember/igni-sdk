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

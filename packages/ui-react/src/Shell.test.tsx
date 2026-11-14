// @vitest-environment jsdom
/**
 * `AppShell` and `Scroll`: what a caller can add to them.
 *
 * tier0.test.tsx pins the rows and the scroll axes. This file pins the
 * rest of the contract: the caller's classes sit beside the theme's, the
 * remaining props reach the element, and only `undefined` omits a row.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AppShell, Scroll } from "./Shell.js";

afterEach(cleanup);

describe("AppShell props", () => {
  it("keeps its own class and adds the caller's after it", () => {
    const { container } = render(<AppShell className="mine other">x</AppShell>);
    expect(container.firstElementChild?.className).toBe("ui-shell mine other");
  });

  it("is only ui-shell when no class is given", () => {
    const { container } = render(<AppShell>x</AppShell>);
    expect(container.firstElementChild?.className).toBe("ui-shell");
  });

  it("spreads the remaining props onto the shell", () => {
    const { container } = render(
      <AppShell id="frame" role="main" data-x="1" aria-label="Panel">
        x
      </AppShell>,
    );
    const el = container.firstElementChild!;
    expect(el.id).toBe("frame");
    expect(el.getAttribute("role")).toBe("main");
    expect(el.getAttribute("data-x")).toBe("1");
    expect(el.getAttribute("aria-label")).toBe("Panel");
  });

  it("renders an empty row for null, and for 0, and omits only undefined", () => {
    // `undefined` means "none"; anything the caller passed, even
    // nothing-shaped, is a row they asked for.
    const { container, rerender } = render(
      <AppShell header={null} footer={null}>
        B
      </AppShell>,
    );
    expect(container.querySelector(".ui-shell-header")?.textContent).toBe("");
    expect(container.querySelector(".ui-shell-footer")?.textContent).toBe("");
    rerender(
      <AppShell header={0} footer="">
        B
      </AppShell>,
    );
    expect(container.querySelector(".ui-shell-header")?.textContent).toBe("0");
    expect(container.querySelector(".ui-shell-footer")).not.toBeNull();
  });

  it("keeps the body when there are no children", () => {
    const { container } = render(<AppShell />);
    expect(container.querySelector(".ui-shell-body")?.textContent).toBe("");
  });
});

describe("Scroll props", () => {
  it("adds the caller's class after the axis class", () => {
    const { container, rerender } = render(<Scroll className="list">x</Scroll>);
    expect(container.firstElementChild?.className).toBe("ui-scroll list");
    rerender(
      <Scroll axis="x" className="wide">
        x
      </Scroll>,
    );
    expect(container.firstElementChild?.className).toBe("ui-scroll-x wide");
  });

  it("spreads the remaining props, and a tabIndex makes it focusable", () => {
    const { container } = render(
      <Scroll tabIndex={0} aria-label="Results" data-x="1">
        x
      </Scroll>,
    );
    const el = container.firstElementChild as HTMLElement;
    expect(el.getAttribute("tabindex")).toBe("0");
    expect(el.getAttribute("aria-label")).toBe("Results");
    expect(el.getAttribute("data-x")).toBe("1");
    expect(el.textContent).toBe("x");
  });
});

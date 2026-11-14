// @vitest-environment jsdom
/**
 * The sortable heading and the status word, in the cases tier0.test.tsx
 * does not reach: every direction's arrow and next step, the classes
 * and props that pass through, and every state.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SortableTh, Status } from "./DataTable.js";

afterEach(cleanup);

function heading(props: Partial<ComponentProps<typeof SortableTh>> = {}) {
  const onSort = vi.fn();
  render(
    <table>
      <thead>
        <tr>
          <SortableTh onSort={onSort} {...props}>
            Rule
          </SortableTh>
        </tr>
      </thead>
    </table>,
  );
  return { th: screen.getByRole("columnheader"), onSort };
}

describe("SortableTh", () => {
  it.each([
    ["ascending" as const, "▴", "descending"],
    ["descending" as const, "▾", "ascending"],
    [undefined, "▴", "ascending"],
  ])("with direction %s shows %s and asks for %s", (direction, arrow, next) => {
    const { th, onSort } = heading({ direction });
    expect(th.querySelector(".ui-th-arrow")?.textContent).toBe(arrow);
    fireEvent.click(screen.getByRole("button"));
    expect(onSort).toHaveBeenCalledOnce();
    expect(onSort).toHaveBeenCalledWith(next);
  });

  it("says each direction in aria-sort, and none for no direction", () => {
    expect(heading({ direction: "descending" }).th.getAttribute("aria-sort")).toBe(
      "descending",
    );
    cleanup();
    expect(heading({ direction: "ascending" }).th.getAttribute("aria-sort")).toBe(
      "ascending",
    );
    cleanup();
    expect(heading().th.getAttribute("aria-sort")).toBe("none");
  });

  it("is a column heading, whatever scope it was handed", () => {
    const { th } = heading({ scope: "row" } as never);
    expect(th.getAttribute("scope")).toBe("col");
  });

  it("puts the heading in the button, beside the arrow", () => {
    const { th } = heading();
    const button = th.querySelector("button.ui-th-sort");
    expect(button?.getAttribute("type")).toBe("button");
    expect(button?.textContent).toBe("Rule▴");
  });

  it("marks a numeric column, and adds a caller's class to it", () => {
    expect(heading({ numeric: true }).th.className).toBe("ui-num");
    cleanup();
    expect(heading({ numeric: true, className: "wide" }).th.className).toBe(
      "ui-num wide",
    );
  });

  it("is plain unless numeric, and keeps only a caller's class otherwise", () => {
    expect(heading().th.className).toBe("");
    cleanup();
    expect(heading({ className: "wide" }).th.className).toBe("wide");
  });

  it("passes other props on to the th", () => {
    const { th } = heading({ id: "col-rule", title: "Sort by rule" });
    expect(th.id).toBe("col-rule");
    expect(th.title).toBe("Sort by rule");
  });
});

describe("Status", () => {
  it.each(["READY", "PREPARING", "DISABLED", "FAILED"] as const)(
    "puts %s in data-state and says the word",
    (state) => {
      const { container } = render(<Status state={state} />);
      const el = container.firstElementChild as HTMLElement;
      expect(el.tagName).toBe("SPAN");
      expect(el.className).toBe("ui-status");
      expect(el.dataset.state).toBe(state);
      expect(el.textContent).toBe(state);
    },
  );

  it("shows what it was given beside the state, even a number zero", () => {
    const { container, rerender } = render(<Status state="READY">Up 3 days</Status>);
    expect(container.textContent).toBe("Up 3 days");
    rerender(<Status state="READY">{0}</Status>);
    expect(container.textContent).toBe("0");
  });
});

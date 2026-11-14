// @vitest-environment jsdom
/**
 * `Skeleton`: placeholders that hold a layout open while data loads.
 *
 * What a reader sees is the size and the class the stylesheet shimmers,
 * so that is what is asserted: the defaults each part ships with, that a
 * caller's `style` wins over them, and how many rows `Rows` draws.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Skeleton } from "./Skeleton.js";

afterEach(cleanup);

const only = (container: HTMLElement) =>
  container.firstElementChild as HTMLElement;

describe("Skeleton.Line", () => {
  it("is a full-width block 12px tall, shimmered as text", () => {
    const el = only(render(<Skeleton.Line />).container);
    expect(el.tagName).toBe("SPAN");
    expect(el.className).toBe("skeleton skeleton-text");
    expect(el.style.display).toBe("block");
    expect(el.style.width).toBe("100%");
    expect(el.style.height).toBe("12px");
  });

  it("takes its size as pixels or as a CSS length", () => {
    const el = only(render(<Skeleton.Line width={90} height="2rem" />).container);
    expect(el.style.width).toBe("90px");
    expect(el.style.height).toBe("2rem");
  });

  it("lets the caller's style win over the defaults", () => {
    const el = only(
      render(<Skeleton.Line width={90} style={{ display: "inline-block", width: 10 }} />)
        .container,
    );
    expect(el.style.display).toBe("inline-block");
    expect(el.style.width).toBe("10px");
  });
});

describe("Skeleton.Block", () => {
  it("is a full-width block 64px tall, shimmered as a block", () => {
    const el = only(render(<Skeleton.Block />).container);
    expect(el.className).toBe("skeleton skeleton-block");
    expect(el.style.display).toBe("block");
    expect(el.style.height).toBe("64px");
    expect(el.style.width).toBe("100%");
  });

  it("takes its size and merges the caller's style over the defaults", () => {
    const el = only(
      render(<Skeleton.Block height="10vh" width={200} style={{ height: 5 }} />)
        .container,
    );
    expect(el.style.width).toBe("200px");
    expect(el.style.height).toBe("5px");
  });
});

describe("Skeleton.Circle", () => {
  it("is an inline 24px square shimmered as a circle", () => {
    const el = only(render(<Skeleton.Circle />).container);
    expect(el.className).toBe("skeleton skeleton-circle");
    expect(el.style.display).toBe("inline-block");
    expect(el.style.width).toBe("24px");
    expect(el.style.height).toBe("24px");
  });

  it("is as wide and tall as its size, and the caller's style wins", () => {
    const el = only(
      render(<Skeleton.Circle size={48} style={{ width: 7 }} />).container,
    );
    expect(el.style.height).toBe("48px");
    expect(el.style.width).toBe("7px");
  });
});

describe("Skeleton.Rows", () => {
  const rows = (container: HTMLElement) => [...only(container).children];

  it("draws four rows by default, each a short line over a full one", () => {
    const { container } = render(<Skeleton.Rows />);
    expect(rows(container)).toHaveLength(4);
    for (const row of rows(container)) {
      const [head, body] = [...row.children] as HTMLElement[];
      expect(head.style.width).toBe("40%");
      expect(head.style.height).toBe("11px");
      expect(body.style.width).toBe("100%");
      expect(body.style.height).toBe("12px");
    }
  });

  it("is a column of 12px gaps whose style the caller can override", () => {
    const { container, rerender } = render(<Skeleton.Rows />);
    const stack = only(container);
    expect(stack.style.display).toBe("flex");
    expect(stack.style.flexDirection).toBe("column");
    expect(stack.style.gap).toBe("12px");
    rerender(<Skeleton.Rows style={{ gap: 2 }} />);
    expect(only(container).style.gap).toBe("2px");
  });

  it("draws as many rows as asked for, and none for zero", () => {
    const { container, rerender } = render(<Skeleton.Rows count={7} />);
    expect(rows(container)).toHaveLength(7);
    rerender(<Skeleton.Rows count={0} />);
    expect(rows(container)).toHaveLength(0);
  });
});

// @vitest-environment jsdom
/**
 * Mermaid diagrams: the theme they are drawn in, the ids they are
 * drawn under, and what a diagram that does not parse shows instead.
 *
 * `mermaid` itself is replaced: it needs a real layout engine, and
 * what is under test is what this module asks of it and does with
 * the answer, not mermaid's drawing.
 */
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mermaid = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(),
}));

vi.mock("mermaid", () => ({ default: mermaid }));

import { loadMermaid, MermaidBlock } from "./Mermaid";

beforeEach(() => {
  mermaid.initialize.mockReset();
  mermaid.render.mockReset();
  mermaid.render.mockImplementation((id: string) =>
    Promise.resolve({ svg: `<svg id="${id}"></svg>` }),
  );
});

afterEach(() => {
  cleanup();
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

function themeAt(call: number): unknown {
  const [config] = mermaid.initialize.mock.calls[call] as [{ theme: string }];
  return config.theme;
}

/** The drawing, not the copy button's icon. */
function drawn(container: HTMLElement): Element | null {
  return container.querySelector(".mermaid-diagram > div svg");
}

function renderIds(): string[] {
  return mermaid.render.mock.calls.map(([id]) => id as string);
}

describe("loadMermaid", () => {
  it("configures mermaid strictly, without drawing on load", async () => {
    await loadMermaid();
    expect(mermaid.initialize).toHaveBeenCalledWith({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "default",
      themeVariables: {
        fontFamily: "var(--font-ui)",
        background: "transparent",
      },
    });
  });

  it("draws in the theme in force when asked, not the first one", async () => {
    // A diagram drawn after a switch to dark is drawn in dark.
    document.documentElement.dataset.theme = "dark";
    await loadMermaid();
    document.documentElement.dataset.theme = "light";
    await loadMermaid();
    expect(themeAt(0)).toBe("dark");
    expect(themeAt(1)).toBe("default");
  });

  it("follows the system's dark mode when the page names no theme", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(prefers-color-scheme: dark)",
    }));
    await loadMermaid();
    expect(themeAt(0)).toBe("dark");
  });

  it("an explicit light theme wins over a dark system", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    document.documentElement.dataset.theme = "light";
    await loadMermaid();
    expect(themeAt(0)).toBe("default");
  });

  it("tries again after a load that failed", async () => {
    mermaid.initialize.mockImplementationOnce(() => {
      throw new Error("not today");
    });
    await expect(loadMermaid()).rejects.toThrow("not today");
    await expect(loadMermaid()).resolves.toBe(mermaid);
  });
});

describe("MermaidBlock", () => {
  it("draws the svg mermaid renders beside a copy button", async () => {
    const { container } = render(<MermaidBlock source="graph TD; A-->B" />);
    await waitFor(() => expect(drawn(container)).not.toBeNull());
    expect(mermaid.render).toHaveBeenCalledWith(
      expect.any(String),
      "graph TD; A-->B",
    );
    const diagram = container.querySelector(".mermaid-diagram");
    expect(diagram?.querySelector("button.diagram-copy")).not.toBeNull();
    expect(drawn(container)?.id).toBe(renderIds()[0]);
  });

  it("renders every diagram under an id of its own, page-wide", async () => {
    // The id is the SVG's and scopes the styles mermaid injects; two
    // diagrams sharing one restyle each other.
    const first = render(<MermaidBlock source="graph TD; A-->B" />);
    const second = render(<MermaidBlock source="graph TD; C-->D" />);
    await waitFor(() => expect(mermaid.render).toHaveBeenCalledTimes(2));
    first.rerender(<MermaidBlock source="graph TD; A-->C" />);
    await waitFor(() => expect(mermaid.render).toHaveBeenCalledTimes(3));
    second.unmount();
    const ids = renderIds();
    for (const id of ids) expect(id).toMatch(/^mermaid-\d+$/);
    expect(new Set(ids).size).toBe(3);
  });

  it("keeps ids apart across two server-rendered roots", async () => {
    // Two hydrated roots share React's tree-position ids; a page-wide
    // counter does not.
    const html = renderToString(<MermaidBlock source="graph TD; A-->B" />);
    for (const _ of [1, 2]) {
      const container = document.createElement("div");
      container.innerHTML = html;
      document.body.appendChild(container);
      await act(async () => {
        render(<MermaidBlock source="graph TD; A-->B" />, {
          container,
          hydrate: true,
        });
      });
    }
    await waitFor(() => expect(mermaid.render).toHaveBeenCalledTimes(2));
    const [a, b] = renderIds();
    expect(a).not.toBe(b);
  });

  it("shows the source, and why, when it does not parse", async () => {
    mermaid.render.mockRejectedValue(new Error("Parse error on line 1"));
    const { container } = render(<MermaidBlock source="graph TD; A--" />);
    await waitFor(() =>
      expect(container.querySelector("pre.mermaid-error")).not.toBeNull(),
    );
    const pre = container.querySelector("pre.mermaid-error");
    expect(pre?.textContent).toBe("graph TD; A--");
    expect(pre?.getAttribute("title")).toBe(
      "Mermaid render failed: Parse error on line 1",
    );
    expect(container.querySelector(".mermaid-diagram")).toBeNull();
  });

  it("says a failure that is not an Error in its own words", async () => {
    mermaid.render.mockRejectedValue("no diagram type");
    const { container } = render(<MermaidBlock source="nonsense" />);
    await waitFor(() =>
      expect(
        container.querySelector("pre.mermaid-error")?.getAttribute("title"),
      ).toBe("Mermaid render failed: no diagram type"),
    );
  });

  it("drops a render the source has moved past", async () => {
    // An edit in flight: the older drawing finishing last must not
    // replace the newer one.
    let finishOld: (r: { svg: string }) => void = () => {};
    mermaid.render.mockImplementationOnce(
      () => new Promise((resolve) => (finishOld = resolve)),
    );
    const { container, rerender } = render(<MermaidBlock source="old" />);
    await waitFor(() => expect(mermaid.render).toHaveBeenCalledTimes(1));
    rerender(<MermaidBlock source="new" />);
    await waitFor(() => expect(drawn(container)).not.toBeNull());
    await act(async () => finishOld({ svg: '<svg id="stale"></svg>' }));
    expect(container.querySelector("#stale")).toBeNull();
    expect(drawn(container)?.id).toBe(renderIds()[1]);
  });
});

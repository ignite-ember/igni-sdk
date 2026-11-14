// @vitest-environment jsdom
/**
 * The error boundary's edges: what it does with a thrown value that
 * is not an Error, when its keys count as changed, and what the
 * default page offers.
 *
 * The everyday cases (message shown, onError, fallback, a changed
 * key) are in tier0.test.tsx.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary.js";

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function Throws({ value }: { value: unknown }): React.ReactElement {
  throw value;
}

function Fine(): React.ReactElement {
  return <p>fine</p>;
}

describe("the default page", () => {
  it("says the view stopped, shows the message and offers Try again", () => {
    render(
      <ErrorBoundary>
        <Throws value={new Error("the panel exploded")} />
      </ErrorBoundary>,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Something in this view stopped working.");
    expect(alert.querySelector("pre")?.textContent).toBe("the panel exploded");
    expect(screen.getByRole("button", { name: "Try again" })).not.toBeNull();
  });

  it("tries the children again when asked, and stays caught if they still throw", () => {
    let healed = false;
    function Flaky(): React.ReactElement {
      if (!healed) throw new Error("still broken");
      return <p>fine</p>;
    }
    render(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.queryByRole("alert")?.textContent).toContain("still broken");
    healed = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.queryByText("fine")).not.toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("what was thrown", () => {
  it.each([
    ["a string", "just words", "just words"],
    ["undefined", undefined, "undefined"],
    ["null", null, "null"],
    ["a number", 404, "404"],
  ])("gives the fallback an Error when %s was thrown", (_label, thrown, message) => {
    const fallback = vi.fn(() => <p>fell back</p>);
    const onError = vi.fn();
    render(
      <ErrorBoundary fallback={fallback} onError={onError}>
        <Throws value={thrown} />
      </ErrorBoundary>,
    );
    expect(screen.queryByText("fell back")).not.toBeNull();
    const [seen] = fallback.mock.calls[0] as unknown as [Error];
    expect(seen).toBeInstanceOf(Error);
    expect(seen.message).toBe(message);
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);
    expect((onError.mock.calls[0][0] as Error).message).toBe(message);
  });

  it("shows what a thrown string said on the default page", () => {
    render(
      <ErrorBoundary>
        <Throws value="just words" />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert").querySelector("pre")?.textContent).toBe(
      "just words",
    );
  });

  it("hands the very Error that was thrown through, not a copy", () => {
    const thrown = new TypeError("mine");
    const onError = vi.fn();
    render(
      <ErrorBoundary onError={onError}>
        <Throws value={thrown} />
      </ErrorBoundary>,
    );
    expect(onError.mock.calls[0][0]).toBe(thrown);
  });

  it("needs no onError", () => {
    render(
      <ErrorBoundary>
        <Throws value={new Error("quiet")} />
      </ErrorBoundary>,
    );
    expect(screen.queryByRole("alert")).not.toBeNull();
  });
});

describe("resetKeys", () => {
  function caught(keys: readonly unknown[] | undefined) {
    return render(
      <ErrorBoundary resetKeys={keys}>
        <Throws value={new Error("x")} />
      </ErrorBoundary>,
    );
  }
  function again(
    view: ReturnType<typeof render>,
    keys: readonly unknown[] | undefined,
  ) {
    view.rerender(
      <ErrorBoundary resetKeys={keys}>
        <Fine />
      </ErrorBoundary>,
    );
  }

  it("clears when keys appear where there were none", () => {
    const view = caught(undefined);
    again(view, ["a"]);
    expect(screen.queryByText("fine")).not.toBeNull();
  });

  it("clears when keys go away", () => {
    const view = caught(["a"]);
    again(view, undefined);
    expect(screen.queryByText("fine")).not.toBeNull();
  });

  it("clears when only the number of keys changes", () => {
    const view = caught(["a"]);
    again(view, ["a", "b"]);
    expect(screen.queryByText("fine")).not.toBeNull();
  });

  it("clears when the same keys come in a different order", () => {
    const view = caught(["a", "b"]);
    again(view, ["b", "a"]);
    expect(screen.queryByText("fine")).not.toBeNull();
  });

  it("stays caught when no keys were given either time", () => {
    const view = caught(undefined);
    again(view, undefined);
    expect(screen.queryByRole("alert")).not.toBeNull();
  });

  it("stays caught when an empty list is followed by none", () => {
    const view = caught([]);
    again(view, undefined);
    expect(screen.queryByRole("alert")).not.toBeNull();
  });

  it("compares by identity: an equal but new object is a change", () => {
    const view = caught([{ id: 1 }]);
    again(view, [{ id: 1 }]);
    expect(screen.queryByText("fine")).not.toBeNull();
  });

  it("reads NaN as unchanged, as a hook dependency does", () => {
    const view = caught([Number.NaN]);
    again(view, [Number.NaN]);
    expect(screen.queryByRole("alert")).not.toBeNull();
  });

  it("does nothing when keys change while nothing is caught", () => {
    function Counter() {
      const [n, setN] = useState(0);
      return (
        <ErrorBoundary resetKeys={[n]}>
          <button type="button" onClick={() => setN(n + 1)}>
            n={n}
          </button>
        </ErrorBoundary>
      );
    }
    render(<Counter />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText("n=1")).not.toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

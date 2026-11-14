// @vitest-environment jsdom
/**
 * `ToastHost` and `Banner`, the parts tier0.test.tsx leaves open:
 * the durations a caller can choose, dismissing through the API, timers
 * that must not outlive the host, and what a banner passes through.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Banner, ToastHost, useToast, type ToastApi } from "./Toast.js";

afterEach(cleanup);

let api: ToastApi;
function Grab() {
  api = useToast();
  return null;
}
const host = () =>
  render(
    <ToastHost>
      <Grab />
    </ToastHost>,
  );
const toasts = (container: HTMLElement) =>
  [...container.querySelectorAll(".ui-toast")] as HTMLElement[];
const show = (...args: Parameters<ToastApi["show"]>) => {
  let id = "";
  act(() => {
    id = api.show(...args);
  });
  return id;
};
const wait = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

describe("ToastHost durations", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("goes after exactly five seconds by default", () => {
    const { container } = host();
    show("Saved");
    wait(4_999);
    expect(toasts(container)).toHaveLength(1);
    wait(1);
    expect(toasts(container)).toHaveLength(0);
  });

  it("goes after the milliseconds it was given", () => {
    const { container } = host();
    show("Quick", { duration: 1_000 });
    wait(999);
    expect(toasts(container)).toHaveLength(1);
    wait(1);
    expect(toasts(container)).toHaveLength(0);
  });

  it("stays when duration is null, with or without an action", () => {
    const { container } = host();
    show("Sticky", { duration: null });
    show("Sticky too", { duration: null, action: <button>Undo</button> });
    wait(60_000);
    expect(toasts(container)).toHaveLength(2);
  });

  it("goes on an explicit duration even when it has an action", () => {
    const { container } = host();
    show("Undoable", { duration: 2_000, action: <button>Undo</button> });
    wait(1_999);
    expect(toasts(container)).toHaveLength(1);
    wait(1);
    expect(toasts(container)).toHaveLength(0);
  });

  it("shows the action beside the message", () => {
    const { container } = host();
    show("Deleted", { action: <button>Undo</button> });
    expect(toasts(container)[0]?.textContent).toContain("Undo");
    expect(screen.getByRole("button", { name: "Undo" })).toBeTruthy();
  });
});

describe("ToastHost api", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("returns toast-N ids that never repeat", () => {
    host();
    const a = show("a");
    const b = show("b");
    expect(a).toMatch(/^toast-\d+$/);
    expect(b).toMatch(/^toast-\d+$/);
    expect(Number(b.slice(6))).toBe(Number(a.slice(6)) + 1);
  });

  it("dismisses one toast by id and leaves the rest", () => {
    const { container } = host();
    const a = show("first", { duration: null });
    show("second", { duration: null });
    act(() => api.dismiss(a));
    expect(toasts(container).map((t) => t.textContent)).toEqual([
      expect.stringContaining("second"),
    ]);
  });

  it("cancels a dismissed toast's timer", () => {
    host();
    const id = show("a");
    expect(vi.getTimerCount()).toBe(1);
    act(() => api.dismiss(id));
    expect(vi.getTimerCount()).toBe(0);
  });

  it("takes an unknown id, and an empty stack, without complaint", () => {
    const { container } = host();
    act(() => api.dismiss("toast-none"));
    act(() => api.clear());
    expect(toasts(container)).toHaveLength(0);
  });

  it("clears every toast and every timer", () => {
    const { container } = host();
    show("a");
    show("b", { duration: 100 });
    show("c", { duration: null });
    act(() => api.clear());
    expect(toasts(container)).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("dismisses on the button inside the toast", () => {
    const { container } = host();
    show("a", { duration: null });
    show("b", { duration: null });
    fireEvent.click(
      screen.getAllByRole("button", { name: "Dismiss notification" })[0]!,
    );
    expect(toasts(container)).toHaveLength(1);
    expect(toasts(container)[0]?.textContent).toContain("b");
  });

  it("is neutral unless given a tone, and says the tone it was given", () => {
    const { container } = host();
    show("plain", { duration: null });
    show("bad", { tone: "danger", duration: null });
    expect(toasts(container).map((t) => t.dataset.tone)).toEqual([
      "neutral",
      "danger",
    ]);
  });

  it("drops the oldest past four, and the dropped one's timer is harmless", () => {
    const { container } = host();
    const first = show("one");
    for (const m of ["two", "three", "four", "five"]) show(m);
    expect(toasts(container)).toHaveLength(4);
    expect(container.textContent).not.toContain("one×");
    expect(first).toMatch(/^toast-/);
    expect(() => wait(5_000)).not.toThrow();
    expect(toasts(container)).toHaveLength(0);
  });

  it("leaves no timer running once the host unmounts", () => {
    const { unmount } = host();
    show("a");
    show("b", { duration: 10_000 });
    expect(vi.getTimerCount()).toBe(2);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps one api for the life of the host", () => {
    host();
    const before = api;
    show("a");
    expect(api).toBe(before);
  });
});

describe("Banner props", () => {
  it("is neutral unless given a tone", () => {
    const { container, rerender } = render(<Banner>x</Banner>);
    expect(container.firstElementChild?.getAttribute("data-tone")).toBe("neutral");
    rerender(<Banner tone="warning">x</Banner>);
    expect(container.firstElementChild?.getAttribute("data-tone")).toBe("warning");
  });

  it("adds the caller's class after its own and spreads the rest", () => {
    const { container } = render(
      <Banner className="mine" id="b" data-x="1">
        Offline
      </Banner>,
    );
    const el = container.firstElementChild!;
    expect(el.className).toBe("ui-banner mine");
    expect(el.id).toBe("b");
    expect(el.getAttribute("data-x")).toBe("1");
    expect(el.querySelector(".ui-banner-body")?.textContent).toBe("Offline");
  });

  it("calls onDismiss once when its button is clicked", () => {
    const onDismiss = vi.fn();
    render(<Banner onDismiss={onDismiss}>x</Banner>);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss message" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});

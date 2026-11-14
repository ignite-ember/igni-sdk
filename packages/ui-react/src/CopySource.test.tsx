// @vitest-environment jsdom
/**
 * The diagram's copy button: it copies the source, and says so when
 * the clipboard refuses.
 */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CopySource } from "./CopySource.js";
import { MenuIcon } from "./MenuIcon.js";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function stubClipboard(writeText: (text: string) => Promise<void>) {
  vi.stubGlobal("navigator", { clipboard: { writeText } });
}

/** The path a MenuIcon draws for `name`, to tell copy from check. */
function iconPath(name: "copy" | "check"): string | null {
  const { container, unmount } = render(<MenuIcon name={name} />);
  const d = container.querySelector("path")?.getAttribute("d") ?? null;
  unmount();
  return d;
}

function shownPath(): string | null {
  return (
    screen.getByRole("button").querySelector("path")?.getAttribute("d") ?? null
  );
}

function expectIdle() {
  const button = screen.getByRole("button");
  expect(button.dataset.state).toBe("idle");
  expect(button.getAttribute("aria-label")).toBe("Copy source");
  expect(button.getAttribute("title")).toBe("Copy source");
  expect(shownPath()).toBe(iconPath("copy"));
}

async function click() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button"));
  });
}

describe("CopySource", () => {
  it("copies the source and says it did", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    stubClipboard(writeText);
    render(<CopySource source="graph TD; A-->B" />);
    await click();
    expect(writeText).toHaveBeenCalledWith("graph TD; A-->B");
    expect(screen.getByRole("button").getAttribute("aria-label")).toBe(
      "Copied",
    );
  });

  it("says so when the clipboard is blocked", async () => {
    stubClipboard(() => Promise.reject(new Error("denied")));
    render(<CopySource source="graph TD; A-->B" />);
    await click();
    const button = screen.getByRole("button");
    expect(button.dataset.state).toBe("failed");
    expect(button.getAttribute("aria-label")).toMatch(/failed/i);
  });

  it("draws an icon, not a text glyph", () => {
    render(<CopySource source="x" />);
    expect(screen.getByRole("button").querySelector("svg")).not.toBeNull();
    expect(screen.getByRole("button").textContent).toBe("");
  });

  it("waits as a copy button", () => {
    render(<CopySource source="x" />);
    expectIdle();
  });

  it("ticks when it copied, then goes back to waiting", async () => {
    vi.useFakeTimers();
    stubClipboard(() => Promise.resolve());
    render(<CopySource source="x" />);
    await click();
    const button = screen.getByRole("button");
    expect(button.dataset.state).toBe("copied");
    expect(button.getAttribute("title")).toBe("Copied");
    expect(shownPath()).toBe(iconPath("check"));
    act(() => vi.advanceTimersByTime(1299));
    expect(button.dataset.state).toBe("copied");
    act(() => vi.advanceTimersByTime(1));
    expectIdle();
  });

  it("says the clipboard is blocked, in words, then goes back to waiting", async () => {
    vi.useFakeTimers();
    stubClipboard(() => Promise.reject(new Error("denied")));
    render(<CopySource source="x" />);
    await click();
    const button = screen.getByRole("button");
    const said = "Copy failed — the clipboard is blocked";
    expect(button.getAttribute("aria-label")).toBe(said);
    expect(button.getAttribute("title")).toBe(said);
    expect(shownPath()).toBe(iconPath("copy"));
    act(() => vi.advanceTimersByTime(1299));
    expect(button.dataset.state).toBe("failed");
    act(() => vi.advanceTimersByTime(1));
    expectIdle();
  });

  it("counts a page with no clipboard at all as blocked", async () => {
    vi.stubGlobal("navigator", {});
    render(<CopySource source="x" />);
    await click();
    expect(screen.getByRole("button").dataset.state).toBe("failed");
  });

  it("copies the source as it is, empty or not", async () => {
    // Not the drawing, and not a trimmed or escaped copy: what
    // somebody pastes is what was in the fence.
    const writeText = vi.fn(() => Promise.resolve());
    stubClipboard(writeText);
    const { rerender } = render(<CopySource source="" />);
    await click();
    rerender(<CopySource source={"  ä → 😀\n\tA-->B  "} />);
    await click();
    expect(writeText.mock.calls).toEqual([[""], ["  ä → 😀\n\tA-->B  "]]);
  });

  it("gives a second click its own full feedback time", async () => {
    // The first click's timer must not reset the button while the
    // second click's answer is still being shown.
    vi.useFakeTimers();
    stubClipboard(() => Promise.resolve());
    render(<CopySource source="x" />);
    await click();
    act(() => vi.advanceTimersByTime(1000));
    await click();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole("button").dataset.state).toBe("copied");
    act(() => vi.advanceTimersByTime(300));
    expectIdle();
  });

  it("leaves no timer behind when it is removed while showing feedback", async () => {
    vi.useFakeTimers();
    stubClipboard(() => Promise.resolve());
    const { unmount } = render(<CopySource source="x" />);
    await click();
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("starts no timer when it was removed before the clipboard answered", async () => {
    vi.useFakeTimers();
    let answer: () => void = () => {};
    stubClipboard(() => new Promise<void>((resolve) => (answer = resolve)));
    const { unmount } = render(<CopySource source="x" />);
    await click();
    unmount();
    await act(async () => answer());
    expect(vi.getTimerCount()).toBe(0);
  });
});

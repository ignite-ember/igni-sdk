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

import { CopySource } from "./CopySource";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubClipboard(writeText: (text: string) => Promise<void>) {
  vi.stubGlobal("navigator", { clipboard: { writeText } });
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
});

// @vitest-environment jsdom
/**
 * The live regions' roles and attributes, repeats of any length,
 * and what changing or clearing the text does.
 *
 * The first announcement, the repeat and the separate urgencies are
 * in tier0.test.tsx.
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { LiveRegion, useAnnounce, type Announcer } from "./LiveRegion.js";

afterEach(cleanup);

const ZWSP = "​";

function mountAnnouncer() {
  const handle: { current: Announcer | null } = { current: null };
  const seen: Announcer["announce"][] = [];
  function Probe() {
    const announcer = useAnnounce();
    handle.current = announcer;
    seen.push(announcer.announce);
    return announcer.region;
  }
  const view = render(<Probe />);
  const say = (message: string, urgency?: "polite" | "assertive") =>
    act(() => handle.current?.announce(message, urgency));
  return { say, seen, view };
}

const polite = () => screen.getByRole("status");
const assertive = () => screen.getByRole("alert");

describe("useAnnounce's regions", () => {
  it("renders a polite status and an assertive alert, both atomic and empty", () => {
    mountAnnouncer();
    expect(polite().getAttribute("aria-live")).toBe("polite");
    expect(polite().getAttribute("aria-atomic")).toBe("true");
    expect(polite().textContent).toBe("");
    expect(assertive().getAttribute("aria-live")).toBe("assertive");
    expect(assertive().getAttribute("aria-atomic")).toBe("true");
    expect(assertive().textContent).toBe("");
    expect(polite().className).toBe("ui-visually-hidden");
    expect(assertive().className).toBe("ui-visually-hidden");
  });

  it("renders them empty on the server too", () => {
    function Probe() {
      return useAnnounce().region;
    }
    const html = renderToString(<Probe />);
    expect(html).toContain('role="status"');
    expect(html).toContain('role="alert"');
    expect(html).not.toMatch(/>[^<]+</);
  });

  it("writes to the polite region unless told otherwise, and only there", () => {
    const { say } = mountAnnouncer();
    say("saved");
    expect(polite().textContent).toBe("saved");
    expect(assertive().textContent).toBe("");
    say("stop", "assertive");
    expect(assertive().textContent).toBe("stop");
    expect(polite().textContent).toBe("saved");
  });

  it("keeps the same announce function across renders", () => {
    const { say, seen, view } = mountAnnouncer();
    say("one");
    say("two");
    view.rerender(<></>);
    expect(new Set(seen).size).toBe(1);
  });
});

describe("repeats", () => {
  it("makes every repeat differ from the one before it", () => {
    // Each announcement must differ from what is showing, however many
    // times the same thing is said.
    const { say } = mountAnnouncer();
    const shown: string[] = [];
    for (let i = 0; i < 5; i++) {
      say("40 results");
      shown.push(polite().textContent ?? "");
    }
    expect(shown[0]).toBe("40 results");
    for (let i = 1; i < shown.length; i++) {
      expect(shown[i]).not.toBe(shown[i - 1]);
      expect(shown[i].replace(new RegExp(ZWSP, "g"), "")).toBe("40 results");
    }
  });

  it("announces A, B, A as they are, with no space added", () => {
    const { say } = mountAnnouncer();
    for (const m of ["A", "B", "A"]) {
      say(m);
      expect(polite().textContent).toBe(m);
    }
  });

  it("tracks each urgency by itself", () => {
    const { say } = mountAnnouncer();
    say("same");
    say("same", "assertive");
    expect(polite().textContent).toBe("same");
    expect(assertive().textContent).toBe("same");
  });

  it("makes an empty message said twice a change too", () => {
    const { say } = mountAnnouncer();
    say("");
    const first = polite().textContent;
    say("");
    expect(polite().textContent).not.toBe(first);
  });
});

describe("LiveRegion", () => {
  it("is polite by default, with status and aria-live to match", async () => {
    render(<LiveRegion>3 results</LiveRegion>);
    await waitFor(() => expect(polite().textContent).toBe("3 results"));
    expect(polite().getAttribute("aria-live")).toBe("polite");
    expect(polite().className).toBe("ui-visually-hidden");
  });

  it("is an alert, assertively, on request", async () => {
    render(<LiveRegion urgency="assertive">Disk full</LiveRegion>);
    await waitFor(() => expect(assertive().textContent).toBe("Disk full"));
    expect(assertive().getAttribute("aria-live")).toBe("assertive");
    expect(assertive().getAttribute("aria-atomic")).toBe("true");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("renders empty on the server, before anything can be announced", () => {
    const html = renderToString(<LiveRegion>3 results</LiveRegion>);
    expect(html).toContain('role="status"');
    expect(html).not.toContain("3 results");
  });

  it("announces a changed text, and says nothing when cleared or absent", async () => {
    const { rerender } = render(<LiveRegion>1 result</LiveRegion>);
    await waitFor(() => expect(polite().textContent).toBe("1 result"));
    rerender(<LiveRegion>2 results</LiveRegion>);
    await waitFor(() => expect(polite().textContent).toBe("2 results"));
    rerender(<LiveRegion>{""}</LiveRegion>);
    await waitFor(() => expect(polite().textContent).toBe(""));
    rerender(<LiveRegion>3 results</LiveRegion>);
    await waitFor(() => expect(polite().textContent).toBe("3 results"));
    rerender(<LiveRegion />);
    await waitFor(() => expect(polite().textContent).toBe(""));
  });
});

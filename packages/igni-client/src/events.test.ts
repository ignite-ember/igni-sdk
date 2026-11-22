import { describe, expect, it } from "vitest";

import { isKnownEvent, isTypedPush, parseEvent } from "./events.js";

describe("parseEvent", () => {
  it("fills in the envelope with defaults, keeping everything else", () => {
    const ev = parseEvent({ type: "content_delta", text: "hi", extra: 1 });
    expect(ev.type).toBe("content_delta");
    expect(ev.id).toBe("");
    expect(ev.session_id).toBe("");
    expect(ev.event_seq).toBe(0);
    expect(ev.text).toBe("hi");
    expect(ev.extra).toBe(1);
  });

  it("keeps the envelope values it is given", () => {
    const ev = parseEvent({ type: "x", id: "r1", session_id: "s1", event_seq: 7 });
    expect(ev).toMatchObject({ id: "r1", session_id: "s1", event_seq: 7 });
  });

  it("coerces a missing type to the empty string", () => {
    expect(parseEvent({} as { type: string }).type).toBe("");
  });
});

describe("the known-type guards", () => {
  it("knows which wire types and channels this client understands", () => {
    expect(isKnownEvent("welcome")).toBe(true);
    expect(isKnownEvent("content_delta")).toBe(true);
    expect(isKnownEvent("something_a_newer_igni_sends")).toBe(false);
    expect(isTypedPush("workflow_event")).toBe(true);
    expect(isTypedPush("a_new_channel")).toBe(false);
    expect(isTypedPush(undefined)).toBe(false);
  });
});

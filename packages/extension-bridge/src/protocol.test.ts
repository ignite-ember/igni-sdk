/**
 * What the guest accepts from the host, as `isHostMessage` reads it.
 *
 * A frame that fails is dropped without a word, so a guard that is too
 * strict looks like a host that never answers, and one too loose hands
 * the bridge a shape it cannot read.
 */
import { describe, expect, it } from "vitest";

import {
  BRIDGE_VERSION,
  isGuestMessage,
  isHostMessage,
  methodAllowed,
} from "./protocol.js";

function hello(over: Record<string, unknown> = {}) {
  return {
    igni: BRIDGE_VERSION,
    kind: "hello",
    nonce: "n",
    extensionId: "acme.scanner",
    params: {},
    settings: {},
    serviceUrl: null,
    theme: "dark",
    tokens: {},
    ...over,
  };
}

describe("a hello", () => {
  it("is accepted whole, and from a host that predates settings and serviceUrl", () => {
    expect(isHostMessage(hello())).toBe(true);
    expect(isHostMessage(hello({ serviceUrl: "https://notes.example" }))).toBe(
      true,
    );
    const { settings: _s, serviceUrl: _u, ...older } = hello();
    expect(isHostMessage(older)).toBe(true);
  });

  it.each([
    ["settings that are null", { settings: null }],
    ["settings that are not an object", { settings: "eu" }],
    ["a serviceUrl that is not a string", { serviceUrl: 8080 }],
    ["no tokens", { tokens: undefined }],
    ["params that are null", { params: null }],
    ["no nonce", { nonce: undefined }],
  ])("is refused with %s", (_label, over) => {
    expect(isHostMessage(hello(over))).toBe(false);
  });

  it("is refused from another version of the bridge", () => {
    expect(isHostMessage(hello({ igni: BRIDGE_VERSION + 1 }))).toBe(false);
  });
});

describe("after the hello", () => {
  it("refuses params that are a list", () => {
    expect(
      isHostMessage({ igni: BRIDGE_VERSION, kind: "params", params: [] }),
    ).toBe(false);
    expect(
      isHostMessage({ igni: BRIDGE_VERSION, kind: "params", params: {} }),
    ).toBe(true);
  });

  it("refuses a signal with no name", () => {
    expect(
      isHostMessage({ igni: BRIDGE_VERSION, kind: "signal", signal: "" }),
    ).toBe(false);
  });

  it("refuses a token reply whose token is not a string", () => {
    expect(
      isHostMessage({
        igni: BRIDGE_VERSION,
        kind: "service-token-reply",
        id: "s1",
        ok: true,
        token: 7,
      }),
    ).toBe(false);
  });

  it.each([
    ["a result with no id", { kind: "result", ok: true }],
    ["a result whose ok is not a boolean", { kind: "result", id: "1", ok: "yes" }],
    ["a host reply with no id", { kind: "host-reply", ok: true }],
    ["a host reply whose ok is not a boolean", { kind: "host-reply", id: "h1", ok: 1 }],
    ["a theme with no tokens", { kind: "theme", theme: "dark" }],
  ])("refuses %s", (_label, body) => {
    expect(isHostMessage({ igni: BRIDGE_VERSION, ...body })).toBe(false);
  });

  it("accepts a refusal that gives no reason", () => {
    expect(
      isHostMessage({ igni: BRIDGE_VERSION, kind: "result", id: "1", ok: false }),
    ).toBe(true);
    expect(
      isHostMessage({ igni: BRIDGE_VERSION, kind: "host-reply", id: "h1", ok: false }),
    ).toBe(true);
  });

  it("refuses a kind it does not know", () => {
    expect(isHostMessage({ igni: BRIDGE_VERSION, kind: "reload" })).toBe(false);
  });
});

describe("what the host accepts from a guest", () => {
  const sent = (body: Record<string, unknown>) => ({
    igni: BRIDGE_VERSION,
    nonce: "n",
    ...body,
  });

  it.each([
    ["a call", { kind: "call", id: "1", method: "acme_status", args: {} }],
    ["a navigate", { kind: "navigate", to: "/sessions" }],
    ["a location of strings", { kind: "location", state: { tab: "browse" } }],
    ["a close", { kind: "close" }],
    ["a token request", { kind: "service-token", id: "s3" }],
    ["a bare host request", { kind: "host", id: "h2", op: "get", path: "chat.processing" }],
    [
      "a host request with every option",
      {
        kind: "host",
        id: "h2",
        op: "subscribe",
        path: "",
        window: null,
        session: "s-1",
        params: { limit: 5 },
        signals: ["chat.run_completed"],
      },
    ],
  ])("accepts %s", (_label, body) => {
    expect(isGuestMessage(sent(body))).toBe(true);
  });

  it.each([
    ["no nonce", { kind: "close", nonce: undefined }],
    ["an empty nonce", { kind: "close", nonce: "" }],
    ["another version", { kind: "close", igni: BRIDGE_VERSION + 1 }],
    ["a call with no id", { kind: "call", id: "", method: "m", args: {} }],
    ["a call with no method", { kind: "call", id: "1", method: "", args: {} }],
    ["a call whose args are a list", { kind: "call", id: "1", method: "m", args: [] }],
    ["a call whose args are null", { kind: "call", id: "1", method: "m", args: null }],
    ["a navigate to nowhere", { kind: "navigate", to: "" }],
    ["a location with a number in it", { kind: "location", state: { doc: 7 } }],
    ["a location that is a list", { kind: "location", state: ["browse"] }],
    ["a token request with no id", { kind: "service-token", id: "" }],
    ["a host request with an op it does not know", { kind: "host", id: "h1", op: "delete", path: "x" }],
    ["a host request with no path", { kind: "host", id: "h1", op: "get" }],
    ["a host request whose window is a number", { kind: "host", id: "h1", op: "get", path: "x", window: 1 }],
    ["a host request whose session is a number", { kind: "host", id: "h1", op: "get", path: "x", session: 1 }],
    ["a host request whose params are a list", { kind: "host", id: "h1", op: "get", path: "x", params: [] }],
    ["a host request with a signal that is not a string", { kind: "host", id: "h1", op: "subscribe", path: "", signals: [1] }],
    ["a kind it does not know", { kind: "reload" }],
  ])("refuses %s", (_label, body) => {
    expect(isGuestMessage(sent(body))).toBe(false);
  });

  it("refuses what is not an object at all", () => {
    expect(isGuestMessage(null)).toBe(false);
    expect(isGuestMessage("close")).toBe(false);
  });
});

describe("a method an extension may call", () => {
  it("is named exactly, or by a prefix that ends in a star", () => {
    expect(methodAllowed("acme_status", ["acme_status"])).toBe(true);
    expect(methodAllowed("acme_status", ["acme_*"])).toBe(true);
    expect(methodAllowed("acme_status", ["*"])).toBe(true);
    expect(methodAllowed("acme_statuses", ["acme_status"])).toBe(false);
    expect(methodAllowed("run_shell", ["acme_*"])).toBe(false);
    expect(methodAllowed("acme_status", [])).toBe(false);
  });

  it("reads a star anywhere but the end as itself", () => {
    expect(methodAllowed("acme_status", ["*_status"])).toBe(false);
    expect(methodAllowed("*_status", ["*_status"])).toBe(true);
  });
});

describe("a hello that lacks one thing it needs", () => {
  it.each([
    ["an extensionId", { extensionId: undefined }],
    ["an extensionId that is a number", { extensionId: 7 }],
    ["a nonce that is a number", { nonce: 7 }],
    ["a theme", { theme: undefined }],
    ["a theme that is a number", { theme: 1 }],
    ["tokens that are null", { tokens: null }],
    ["tokens that are a string", { tokens: "dark" }],
    ["params that are missing", { params: undefined }],
    ["params that are a string", { params: "x" }],
  ])("is refused with %s", (_label, over) => {
    expect(isHostMessage(hello(over))).toBe(false);
  });

  it("is accepted with settings that are absent, and refused when they are null", () => {
    expect(isHostMessage(hello({ settings: undefined }))).toBe(true);
    expect(isHostMessage(hello({ settings: null }))).toBe(false);
  });
});

describe("what the guest accepts after the hello, whole", () => {
  it.each([
    ["a theme", { kind: "theme", theme: "light", tokens: { "--bg": "#fff" } }],
    ["params", { kind: "params", params: { doc: "d1" } }],
    ["a result", { kind: "result", id: "1", ok: true, value: 3 }],
    ["a host reply", { kind: "host-reply", id: "h1", ok: true, value: [] }],
    ["a token reply", { kind: "service-token-reply", id: "s1", ok: true, token: "t", expiresIn: 600 }],
    ["a refused token reply", { kind: "service-token-reply", id: "s1", ok: false, error: "no" }],
    ["a signal", { kind: "signal", signal: "chat.run_completed", value: { run: "r" } }],
  ])("accepts %s", (_label, body) => {
    expect(isHostMessage({ igni: BRIDGE_VERSION, ...body })).toBe(true);
  });

  it.each([
    ["a theme whose name is not a string", { kind: "theme", theme: 1, tokens: {} }],
    ["a theme whose tokens are null", { kind: "theme", theme: "dark", tokens: null }],
    ["a result whose id is a number", { kind: "result", id: 1, ok: true }],
    ["a host reply whose id is a number", { kind: "host-reply", id: 1, ok: true }],
    ["a token reply with no id", { kind: "service-token-reply", ok: true }],
    ["a token reply whose ok is not a boolean", { kind: "service-token-reply", id: "s", ok: "yes" }],
    ["a token reply whose expiresIn is a string", { kind: "service-token-reply", id: "s", ok: true, token: "t", expiresIn: "600" }],
    ["a signal whose name is a number", { kind: "signal", signal: 4 }],
    ["a message with no kind", {}],
  ])("refuses %s", (_label, body) => {
    expect(isHostMessage({ igni: BRIDGE_VERSION, ...body })).toBe(false);
  });

  it("refuses what is not an object at all, and a message of another version", () => {
    for (const data of [null, undefined, "hello", 7, true]) {
      expect(isHostMessage(data)).toBe(false);
    }
    expect(
      isHostMessage({ igni: BRIDGE_VERSION + 1, kind: "signal", signal: "s" }),
    ).toBe(false);
    expect(isHostMessage({ kind: "signal", signal: "s" })).toBe(false);
  });
});

describe("every op a guest may ask the host for", () => {
  it.each(["get", "set", "call", "subscribe", "unsubscribe"])("accepts %s", (op) => {
    expect(
      isGuestMessage({
        igni: BRIDGE_VERSION,
        nonce: "n",
        kind: "host",
        id: "h1",
        op,
        path: "chat.processing",
        value: { any: "thing" },
      }),
    ).toBe(true);
  });
});

describe("a permission list that grants little", () => {
  it("allows nothing when it is empty, whatever the method", () => {
    expect(methodAllowed("", [])).toBe(false);
    expect(methodAllowed("*", [])).toBe(false);
  });

  it("allows every method, the empty one too, for a bare star", () => {
    expect(methodAllowed("", ["*"])).toBe(true);
    expect(methodAllowed("anything_at_all", ["*"])).toBe(true);
  });

  it("allows the empty method only by the empty name, not by a named pattern", () => {
    expect(methodAllowed("", ["acme_*"])).toBe(false);
    expect(methodAllowed("", [""])).toBe(true);
    expect(methodAllowed("acme_status", [""])).toBe(false);
  });

  it("is granted by any one of several patterns", () => {
    expect(methodAllowed("b_run", ["a_*", "b_*"])).toBe(true);
  });
});

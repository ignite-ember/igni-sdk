/**
 * What the guest accepts from the host, as `isHostMessage` reads it.
 *
 * A frame that fails is dropped without a word, so a guard that is too
 * strict looks like a host that never answers, and one too loose hands
 * the bridge a shape it cannot read.
 */
import { describe, expect, it } from "vitest";

import { BRIDGE_VERSION, isHostMessage } from "./protocol";

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

  it("refuses a kind it does not know", () => {
    expect(isHostMessage({ igni: BRIDGE_VERSION, kind: "reload" })).toBe(false);
  });
});

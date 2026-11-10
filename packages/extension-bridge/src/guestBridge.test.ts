// @vitest-environment jsdom
/**
 * `GuestBridge` on its own: made from a hello, handed host messages one
 * at a time through `receive`, posting through a real `HostChannel` to a
 * stub window. bridge.test.ts drives the same object through `connect`.
 */
import { describe, expect, it } from "vitest";

import { HostChannel } from "./channel.js";
import { GuestBridge } from "./guestBridge.js";
import {
  BRIDGE_VERSION,
  type HelloMessage,
  type HostMessage,
} from "./protocol.js";

function made(over: Partial<HelloMessage> = {}) {
  const posted: { kind: string; id?: string }[] = [];
  const host = {
    postMessage: (message: { kind: string; id?: string }) =>
      posted.push(message),
  } as unknown as Window;
  const hello: HelloMessage = {
    igni: BRIDGE_VERSION,
    kind: "hello",
    nonce: "n",
    extensionId: "acme.scanner",
    params: { tab: "browse" },
    settings: { region: "eu" },
    serviceUrl: "https://notes.example",
    theme: "dark",
    tokens: { "--bg": "#262624" },
    ...over,
  };
  const bridge = new GuestBridge(new HostChannel(host, "n"), hello);
  const receive = (body: Record<string, unknown>) =>
    bridge.receive({ igni: BRIDGE_VERSION, ...body } as HostMessage);
  /** The id of the last thing posted of `kind`. */
  const lastId = (kind: string) =>
    [...posted].reverse().find((m) => m.kind === kind)?.id;
  return { bridge, posted, receive, lastId };
}

describe("GuestBridge", () => {
  it("holds what the hello said, and paints its tokens as it is made", () => {
    document.documentElement.style.removeProperty("--bg");
    const { bridge } = made();

    expect(bridge.extensionId).toBe("acme.scanner");
    expect(bridge.params).toEqual({ tab: "browse" });
    expect(bridge.settings).toEqual({ region: "eu" });
    expect(bridge.service.url).toBe("https://notes.example");
    expect(bridge.theme).toBe("dark");
    expect(bridge.tokens).toEqual({ "--bg": "#262624" });
    expect(document.documentElement.style.getPropertyValue("--bg")).toBe(
      "#262624",
    );
  });

  it("makes do with a hello from a host that predates settings and serviceUrl", () => {
    const { bridge } = made({ settings: undefined, serviceUrl: undefined });

    expect(bridge.settings).toEqual({});
    expect(bridge.service.url).toBeNull();
  });

  it("takes a new theme and new params, and tells whoever follows them", () => {
    const { bridge, receive } = made();
    const seen: unknown[] = [];
    bridge.onTheme((theme) => seen.push(theme));
    bridge.onParams((params) => seen.push(params));

    receive({ kind: "theme", theme: "light", tokens: { "--bg": "#fff" } });
    receive({ kind: "params", params: { tab: "edit" } });

    expect(bridge.theme).toBe("light");
    expect(bridge.tokens).toEqual({ "--bg": "#fff" });
    expect(bridge.params).toEqual({ tab: "edit" });
    expect(seen).toEqual(["light", { tab: "edit" }]);
  });

  it("changes nothing on a second hello", () => {
    const { bridge, receive } = made();

    receive({
      kind: "hello",
      nonce: "other",
      extensionId: "acme.other",
      params: {},
      theme: "light",
      tokens: {},
    });

    expect(bridge.theme).toBe("dark");
    expect(bridge.params).toEqual({ tab: "browse" });
  });

  it("settles each kind of request with its own kind of reply", async () => {
    const { bridge, receive, lastId } = made();

    const call = bridge.rpc("acme_status");
    receive({ kind: "result", id: lastId("call"), ok: true, value: 7 });
    await expect(call).resolves.toBe(7);

    const read = bridge.host.chat.processing.get();
    receive({ kind: "host-reply", id: lastId("host"), ok: true, result: true });
    await expect(read).resolves.toBe(true);

    const token = bridge.service.token();
    receive({
      kind: "service-token-reply",
      id: lastId("service-token"),
      ok: true,
      token: "t1",
      expiresIn: 600,
    });
    await expect(token).resolves.toBe("t1");
  });

  it("hands a signal to the page's handler of it", () => {
    const { bridge, receive } = made();
    const seen: unknown[] = [];
    bridge.on(bridge.host.chat.run_completed, (value) => seen.push(value));

    receive({ kind: "signal", signal: "chat.run_completed", value: { run: "r1" } });

    expect(seen).toEqual([{ run: "r1" }]);
  });
});

// @vitest-environment jsdom
/**
 * The guest half, driven the way a real extension page would drive it.
 *
 * The host here is a stub window: `connect` waits for a `hello` from
 * `window.parent`, so the test replaces that with something it can
 * post from and read what was posted to.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { connect } from "./bridge.js";
import { HostError } from "./hostModel.js";
import { BRIDGE_VERSION } from "./protocol.js";
import { ServiceError } from "./service.js";

/** Stands in for the host app's window. */
function fakeHost() {
  const posted: unknown[] = [];
  const targets: unknown[] = [];
  const host = {
    postMessage: (message: unknown, target: unknown) => {
      posted.push(message);
      targets.push(target);
    },
  } as unknown as Window;
  Object.defineProperty(window, "parent", { value: host, configurable: true });
  return {
    posted,
    /** The target origin of each post, in order. */
    targets,
    /** The ids of everything the guest asked, in order. */
    ids() {
      return posted
        .map((m) => (m as { id?: string }).id)
        .filter((id) => id !== undefined);
    },
    /** Deliver a message to the guest as the host would. */
    send(body: Record<string, unknown>, source: unknown = host) {
      const event = new MessageEvent("message", {
        data: { igni: BRIDGE_VERSION, ...body },
      });
      Object.defineProperty(event, "source", { value: source });
      window.dispatchEvent(event);
    },
    /** The last `call` the guest sent. */
    lastCall() {
      return [...posted]
        .reverse()
        .find((m) => (m as { kind: string }).kind === "call") as {
        id: string;
        method: string;
        args: Record<string, unknown>;
        nonce: string;
      };
    },
  };
}

const NONCE = "test-nonce";

function hello(over: Record<string, unknown> = {}) {
  return {
    kind: "hello",
    nonce: NONCE,
    extensionId: "acme.scanner",
    params: {},
    settings: {},
    serviceUrl: null,
    theme: "dark",
    tokens: { "--bg": "#262624", "--fg": "#f0efea" },
    ...over,
  };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(window, "parent", {
    value: window,
    configurable: true,
  });
});

describe("connecting", () => {
  it("waits for the host to say hello, then reports what it was told", async () => {
    const host = fakeHost();
    const pending = connect();
    host.send(hello({ params: { tab: "browse" }, theme: "light" }));

    const bridge = await pending;

    expect(bridge.extensionId).toBe("acme.scanner");
    expect(bridge.params).toEqual({ tab: "browse" });
    expect(bridge.theme).toBe("light");
  });

  it("connects to a host that predates settings and serviceUrl", async () => {
    const host = fakeHost();
    const pending = connect();
    const { settings: _settings, serviceUrl: _serviceUrl, ...older } = hello();
    host.send(older);

    const bridge = await pending;

    expect(bridge.settings).toEqual({});
    expect(bridge.service.url).toBeNull();
  });

  it("ignores a hello from a window that is not the host", async () => {
    const host = fakeHost();
    const pending = connect({ timeoutMs: 50 });
    host.send(hello(), { not: "the host" });

    await expect(pending).rejects.toThrow(/no hello/);
  });

  it("refuses when the page is not framed at all", async () => {
    Object.defineProperty(window, "parent", {
      value: window,
      configurable: true,
    });
    await expect(connect()).rejects.toThrow(/not framed/);
  });

  it("gives up with a sentence rather than hanging", async () => {
    fakeHost();
    await expect(connect({ timeoutMs: 30 })).rejects.toThrow(
      /no hello from the host/,
    );
  });

  it("says in its refusals what went wrong and how long it waited", async () => {
    fakeHost();
    await expect(connect({ timeoutMs: 30 })).rejects.toThrow(
      new Error("igni bridge: no hello from the host within 30ms"),
    );
    Object.defineProperty(window, "parent", {
      value: window,
      configurable: true,
    });
    await expect(connect()).rejects.toThrow(
      new Error(
        "igni bridge: this page is not framed by a host, so there is nothing to connect to",
      ),
    );
  });

  it("waits thirty seconds for the hello unless told otherwise", async () => {
    const host = fakeHost();
    const pending = connect();

    vi.advanceTimersByTime(29_900);
    host.send(hello());
    await expect(pending).resolves.toMatchObject({ extensionId: "acme.scanner" });

    fakeHost();
    const late = connect().catch((error: unknown) => error);
    vi.advanceTimersByTime(30_000);
    expect(await late).toEqual(
      new Error("igni bridge: no hello from the host within 30000ms"),
    );
  });

  it("hears the host from the moment it says hello, before connect resolves", async () => {
    const host = fakeHost();
    const pending = connect();
    // Both arrive in one task, before the page has the bridge in hand.
    host.send(hello({ theme: "dark" }));
    host.send({ kind: "theme", theme: "light", tokens: {} });

    expect((await pending).theme).toBe("light");
  });

  it("stops listening for a hello once it has given up", async () => {
    const host = fakeHost();
    await expect(connect({ timeoutMs: 30 })).rejects.toThrow(/no hello/);
    document.documentElement.style.removeProperty("--bg");

    host.send(hello({ tokens: { "--bg": "#010203" } }));

    expect(document.documentElement.style.getPropertyValue("--bg")).toBe("");
  });

  it("keeps waiting past a hello it cannot read", async () => {
    const host = fakeHost();
    const pending = connect();
    host.send(hello({ extensionId: 7 }));
    host.send(hello({ extensionId: "acme.second" }));

    await expect(pending).resolves.toMatchObject({ extensionId: "acme.second" });
  });
});

describe("calling", () => {
  async function connected() {
    const host = fakeHost();
    const pending = connect();
    host.send(hello());
    return { host, bridge: await pending };
  }

  it("carries the nonce the host issued", async () => {
    const { host, bridge } = await connected();
    void bridge.rpc("acme_status");

    expect(host.lastCall().nonce).toBe(NONCE);
    expect(host.lastCall().method).toBe("acme_status");
    expect(host.lastCall().args).toEqual({});
  });

  it("resolves with the host's value", async () => {
    const { host, bridge } = await connected();
    const call = bridge.rpc<{ indexed: number }>("acme_status");
    const { id } = host.lastCall();

    host.send({ kind: "result", id, ok: true, value: { indexed: 42 } });

    await expect(call).resolves.toEqual({ indexed: 42 });
  });

  it("rejects with the host's refusal, as a sentence", async () => {
    const { host, bridge } = await connected();
    const call = bridge.rpc("run_shell");
    const { id } = host.lastCall();

    host.send({
      kind: "result",
      id,
      ok: false,
      error: "not permitted to call 'run_shell'",
    });

    await expect(call).rejects.toThrow(/not permitted/);
  });

  it("keeps two calls apart", async () => {
    const { host, bridge } = await connected();
    const first = bridge.rpc("acme_status");
    const firstId = host.lastCall().id;
    const second = bridge.rpc("acme_head");
    const secondId = host.lastCall().id;

    expect(firstId).not.toBe(secondId);
    host.send({ kind: "result", id: secondId, ok: true, value: "second" });
    host.send({ kind: "result", id: firstId, ok: true, value: "first" });

    await expect(first).resolves.toBe("first");
    await expect(second).resolves.toBe("second");
  });

  it("gives up on a call the host never answers", async () => {
    const { bridge } = await connected();
    const call = bridge.rpc("acme_status", {}, 40);
    await expect(call).rejects.toThrow(/timed out after 40ms/);
  });

  it("gives up at once on a call an untyped caller gave a null timeout, as it always has", async () => {
    const { bridge } = await connected();
    const call = bridge.rpc("acme_status", {}, null as unknown as number);
    const outcome = call.catch((error: unknown) => error);

    await vi.advanceTimersByTimeAsync(1);
    expect(await outcome).toEqual(
      new Error("igni bridge: acme_status timed out after nullms"),
    );
  });

  it("waits thirty seconds for a call whose timeout is left undefined", async () => {
    const { host, bridge } = await connected();
    let outcome: unknown = "waiting";
    void bridge.rpc("acme_status", undefined, undefined).catch((error) => {
      outcome = error;
    });

    expect(host.lastCall().args).toEqual({});
    await vi.advanceTimersByTimeAsync(29_999);
    expect(outcome).toBe("waiting");
    await vi.advanceTimersByTimeAsync(1);
    expect(outcome).toEqual(
      new Error("igni bridge: acme_status timed out after 30000ms"),
    );
  });

  it("says the host gave no reason when it refuses without one", async () => {
    const { host, bridge } = await connected();
    const call = bridge.rpc("acme_status");
    host.send({ kind: "result", id: host.lastCall().id, ok: false });

    await expect(call).rejects.toThrow(
      new Error("the host refused the call without saying why"),
    );
  });

  it("names the method it gave up on", async () => {
    const { bridge } = await connected();
    await expect(bridge.rpc("acme_status", {}, 40)).rejects.toThrow(
      new Error("igni bridge: acme_status timed out after 40ms"),
    );
  });

  it("does not let a reply of one kind settle a request of another", async () => {
    const { host, bridge } = await connected();
    const read = bridge.host.chat.processing.get();
    const call = bridge.rpc("acme_status");

    // The host request is h1: a result naming it settles nothing.
    host.send({ kind: "result", id: "h1", ok: true, value: "wrong" });
    host.send({ kind: "host-reply", id: "2", ok: true, result: "wrong" });
    host.send({ kind: "host-reply", id: "h1", ok: true, result: true });
    host.send({ kind: "result", id: "2", ok: true, value: "right" });

    await expect(read).resolves.toBe(true);
    await expect(call).resolves.toBe("right");
  });

  it("posts each message with its kind before the nonce, as it always has", async () => {
    const { host, bridge } = await connected();
    void bridge.rpc("acme_status");
    void bridge.host.chat.processing.get();
    bridge.close();

    expect(host.posted.map((m) => Object.keys(m as object))).toEqual([
      ["igni", "kind", "nonce", "id", "method", "args"],
      ["igni", "kind", "nonce", "id", "op", "path", "window"],
      ["igni", "kind", "nonce"],
    ]);
  });

  it("ignores a reply to a call it is not waiting on", async () => {
    const { host, bridge } = await connected();
    // A late answer to something that already timed out. Nothing to
    // resolve and no one to tell, so it must not throw either.
    expect(() =>
      host.send({ kind: "result", id: "999", ok: true, value: 1 }),
    ).not.toThrow();
    void bridge;
  });
});

describe("the rest of the surface", () => {
  async function connected() {
    const host = fakeHost();
    const pending = connect();
    host.send(hello());
    return { host, bridge: await pending };
  }

  it("asks the host to navigate", async () => {
    const { host, bridge } = await connected();
    bridge.navigate("plugins");

    expect(host.posted).toContainEqual(
      expect.objectContaining({
        kind: "navigate",
        to: "plugins",
        nonce: NONCE,
      }),
    );
  });

  it("tells the host when it is finished", async () => {
    const { host, bridge } = await connected();
    bridge.close();

    expect(host.posted).toContainEqual(
      expect.objectContaining({ kind: "close", nonce: NONCE }),
    );
  });

  it("follows the host's theme, and stops when asked", async () => {
    const { host, bridge } = await connected();
    const seen: string[] = [];
    const stop = bridge.onTheme((next) => seen.push(next));

    host.send({ kind: "theme", theme: "light", tokens: { "--bg": "#ffffff" } });
    expect(bridge.theme).toBe("light");
    expect(bridge.tokens["--bg"]).toBe("#ffffff");

    stop();
    host.send({ kind: "theme", theme: "dark", tokens: { "--bg": "#262624" } });

    expect(seen).toEqual(["light"]);
    // The reading still follows even with nobody watching.
    expect(bridge.theme).toBe("dark");
  });
});

describe("the bridge as a page holds it", () => {
  async function connected(over: Record<string, unknown> = {}) {
    const host = fakeHost();
    const pending = connect();
    host.send(hello(over));
    return { host, bridge: await pending };
  }

  it("works with its methods taken off it", async () => {
    const { host, bridge } = await connected();
    const { rpc, navigate, close, setLocation, onTheme, onParams, on } =
      bridge;

    const call = rpc<number>("acme_status");
    host.send({ kind: "result", id: host.lastCall().id, ok: true, value: 7 });
    navigate("plugins");
    setLocation({ tab: "browse" });
    const themes: string[] = [];
    onTheme((theme) => themes.push(theme));
    const params: unknown[] = [];
    onParams((next) => params.push(next));
    on(bridge.host.chat.run_completed, () => {});
    host.send({ kind: "theme", theme: "light", tokens: {} });
    host.send({ kind: "params", params: { tab: "x" } });
    close();

    await expect(call).resolves.toBe(7);
    expect(themes).toEqual(["light"]);
    expect(params).toEqual([{ tab: "x" }]);
    expect(host.posted.map((m) => (m as { kind: string }).kind)).toEqual([
      "call",
      "navigate",
      "location",
      "host",
      "close",
    ]);
  });

  it("spreads into what a page uses, and nothing it keeps to itself", async () => {
    const { bridge } = await connected({ params: { tab: "browse" } });

    expect(Object.keys(bridge).sort()).toEqual(
      [
        "close",
        "extensionId",
        "host",
        "navigate",
        "on",
        "onParams",
        "onTheme",
        "params",
        "rpc",
        "service",
        "setLocation",
        "settings",
        "theme",
        "tokens",
      ].sort(),
    );
    expect({ ...bridge }.params).toEqual({ tab: "browse" });
  });

  it("numbers every request from one counter, whatever its kind", async () => {
    const { host, bridge } = await connected({
      serviceUrl: "https://notes.example",
    });

    void bridge.rpc("acme_status");
    void bridge.host.chat.processing.get();
    void bridge.service.token();
    void bridge.rpc("acme_head");

    expect(host.ids()).toEqual(["1", "h2", "s3", "4"]);
  });

  it("posts to any origin, since it does not know the host's", async () => {
    const { host, bridge } = await connected();
    bridge.navigate("plugins");
    bridge.setLocation({ tab: "browse" });

    expect(host.targets).toEqual(["*", "*"]);
  });

  it("tells the host where the user is, with the nonce", async () => {
    const { host, bridge } = await connected();
    bridge.setLocation({ tab: "browse", doc: "7" });

    expect(host.posted).toEqual([
      {
        igni: BRIDGE_VERSION,
        kind: "location",
        nonce: NONCE,
        state: { tab: "browse", doc: "7" },
      },
    ]);
  });

  it("follows the host's params, and stops when asked", async () => {
    const { host, bridge } = await connected({ params: { tab: "browse" } });
    const seen: unknown[] = [];
    const stop = bridge.onParams((next) => seen.push(next));

    host.send({ kind: "params", params: { tab: "history" } });
    expect(bridge.params).toEqual({ tab: "history" });

    // An untyped caller can tell whether it stopped anything.
    expect(stop() as unknown).toBe(true);
    expect(stop() as unknown).toBe(false);
    host.send({ kind: "params", params: { tab: "settings" } });

    expect(seen).toEqual([{ tab: "history" }]);
    expect(bridge.params).toEqual({ tab: "settings" });
  });

  it("answers whether an onTheme unsubscribe stopped anything", async () => {
    const { bridge } = await connected();
    const stop = bridge.onTheme(() => {});

    expect(stop() as unknown).toBe(true);
    expect(stop() as unknown).toBe(false);
  });

  it("passes the settings the host sent", async () => {
    const { bridge } = await connected({
      settings: { region: "eu", retries: 3 },
    });

    expect(bridge.settings).toEqual({ region: "eu", retries: 3 });
  });

  it("paints the host's tokens before it resolves, and again on a new theme", async () => {
    const host = fakeHost();
    const pending = connect();
    host.send(hello({ tokens: { "--bg": "#101010" } }));
    const bridge = await pending;
    const root = document.documentElement;
    expect(root.style.getPropertyValue("--bg")).toBe("#101010");

    host.send({ kind: "theme", theme: "light", tokens: { "--bg": "#fafafa" } });

    expect(root.style.getPropertyValue("--bg")).toBe("#fafafa");
    void bridge;
  });

  it("ignores a second hello", async () => {
    const { host, bridge } = await connected({ params: { tab: "browse" } });

    host.send(
      hello({ extensionId: "acme.other", params: { tab: "x" }, theme: "light" }),
    );

    expect(bridge.extensionId).toBe("acme.scanner");
    expect(bridge.params).toEqual({ tab: "browse" });
    expect(bridge.theme).toBe("dark");
  });

  it("ignores what another window says once connected", async () => {
    const { host, bridge } = await connected();
    const call = bridge.rpc("acme_status", {}, 40);
    const { id } = host.lastCall();

    host.send({ kind: "theme", theme: "light", tokens: {} }, { not: "host" });
    host.send({ kind: "result", id, ok: true, value: 1 }, { not: "host" });

    expect(bridge.theme).toBe("dark");
    await expect(call).rejects.toThrow(/timed out/);
  });
});

describe("requests the host never answers", () => {
  async function connected() {
    const host = fakeHost();
    const pending = connect();
    host.send(hello({ serviceUrl: "https://notes.example" }));
    return { host, bridge: await pending };
  }

  it("gives up on a host request after thirty seconds, and ignores a late reply", async () => {
    const { host, bridge } = await connected();
    const read = bridge.host.chat.processing.get();
    const outcome = read.catch((error: unknown) => error);

    vi.advanceTimersByTime(30_000);
    const error = await outcome;
    expect(error).toBeInstanceOf(HostError);
    expect(error).toMatchObject({
      code: "failed",
      message: "igni bridge: host.chat.processing timed out after 30000ms",
    });
    expect(() =>
      host.send({ kind: "host-reply", id: "h1", ok: true, result: true }),
    ).not.toThrow();
  });

  it("gives up on a service token after thirty seconds", async () => {
    const { bridge } = await connected();
    const outcome = bridge.service.token().catch((error: unknown) => error);

    vi.advanceTimersByTime(30_000);
    const error = await outcome;
    expect(error).toBeInstanceOf(ServiceError);
    expect(error).toMatchObject({
      code: "failed",
      message: "igni bridge: no service token within 30000ms",
    });
  });
});

describe("the service token from the host", () => {
  async function connected() {
    const host = fakeHost();
    const pending = connect();
    host.send(hello({ serviceUrl: "https://notes.example" }));
    return { host, bridge: await pending };
  }
  function lastAsk(host: ReturnType<typeof fakeHost>) {
    return [...host.posted]
      .reverse()
      .find((m) => (m as { kind: string }).kind === "service-token") as {
      id: string;
    };
  }

  it("is refused when the host says ok but sends no token", async () => {
    const { host, bridge } = await connected();
    const token = bridge.service.token();
    host.send({ kind: "service-token-reply", id: lastAsk(host).id, ok: true });

    await expect(token).rejects.toMatchObject({
      code: "refused",
      message: "igni gave no token for this extension's service",
    });
  });

  it("is refused in the bridge's words when the host refuses with an empty reason", async () => {
    const { host, bridge } = await connected();
    const token = bridge.service.token();
    host.send({
      kind: "service-token-reply",
      id: lastAsk(host).id,
      ok: false,
      error: "",
    });

    const error = await token.catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ServiceError);
    expect(error).toMatchObject({
      code: "refused",
      message: "igni gave no token for this extension's service",
    });
  });

  it("is asked for again when the host gave no lifetime", async () => {
    const { host, bridge } = await connected();
    const first = bridge.service.token();
    host.send({
      kind: "service-token-reply",
      id: lastAsk(host).id,
      ok: true,
      token: "t1",
    });
    await expect(first).resolves.toBe("t1");

    // No expiresIn is no time left, so the next ask goes to the host.
    const second = bridge.service.token();
    host.send({
      kind: "service-token-reply",
      id: lastAsk(host).id,
      ok: true,
      token: "t2",
    });
    await expect(second).resolves.toBe("t2");
  });
});

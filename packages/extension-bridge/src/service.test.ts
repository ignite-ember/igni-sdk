// @vitest-environment jsdom
/**
 * `bridge.service`: the page's own service, reached directly.
 *
 * The host hands the page a token for this extension's service and no
 * other; the page keeps it until shortly before it expires, attaches
 * it to `fetch`, and sends it as the first frame of a WebSocket — which
 * is how a browser socket says who it is, since it cannot set a header.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { connect } from "./bridge.js";
import { BRIDGE_VERSION } from "./protocol.js";
import { RENEW_BEFORE_MS, ServiceError, ServiceLink, authMessage } from "./service.js";

const SERVICE = "https://notes.example.com/api";

/** A WebSocket that opens when told to, and records what it was sent. */
class FakeSocket extends EventTarget {
  static made: FakeSocket[] = [];
  sent: string[] = [];
  constructor(
    readonly url: string,
    readonly protocols?: string | string[],
  ) {
    super();
    FakeSocket.made.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  open() {
    this.dispatchEvent(new Event("open"));
  }
  refuse() {
    this.dispatchEvent(new Event("close"));
  }
}

afterEach(() => {
  FakeSocket.made = [];
  Object.defineProperty(window, "parent", { value: window, configurable: true });
});

function issuing(...tokens: string[]) {
  const asked = vi.fn(async () => ({ token: tokens.shift() ?? "spent", expiresIn: 600 }));
  return asked;
}

describe("the token", () => {
  it("is fetched once and kept while it is fresh", async () => {
    let now = 0;
    const ask = issuing("t1", "t2");
    const link = new ServiceLink(SERVICE, ask, { now: () => now });

    expect(await link.token()).toBe("t1");
    now += 300_000;
    expect(await link.token()).toBe("t1");
    expect(ask).toHaveBeenCalledTimes(1);
  });

  it("is renewed in its last minute", async () => {
    let now = 0;
    const ask = issuing("t1", "t2");
    const link = new ServiceLink(SERVICE, ask, { now: () => now });

    await link.token();
    now += 600_000 - RENEW_BEFORE_MS + 1;
    expect(await link.token()).toBe("t2");
  });

  it("is one request however many ask at once", async () => {
    const ask = issuing("t1");
    const link = new ServiceLink(SERVICE, ask);
    const all = await Promise.all([link.token(), link.token(), link.token()]);
    expect(all).toEqual(["t1", "t1", "t1"]);
    expect(ask).toHaveBeenCalledTimes(1);
  });

  it("is refused outright when the extension has no service", async () => {
    const ask = issuing("t1");
    const link = new ServiceLink(null, ask);
    await expect(link.token()).rejects.toMatchObject({ code: "no_service" });
    expect(ask).not.toHaveBeenCalled();
  });
});

describe("fetch", () => {
  it("goes to a path on the service with the token", async () => {
    const seen: { url: string; auth: string | null; credentials?: RequestCredentials }[] = [];
    const fetcher = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      seen.push({
        url: String(url),
        auth: new Headers(init?.headers).get("Authorization"),
        credentials: init?.credentials,
      });
      return new Response("{}", { status: 200 });
    });
    const link = new ServiceLink(SERVICE, issuing("t1"), { fetch: fetcher as typeof fetch });

    await link.fetch("/v1/notes?x=1");

    expect(seen).toEqual([
      {
        url: "https://notes.example.com/api/v1/notes?x=1",
        auth: "Bearer t1",
        credentials: "omit",
      },
    ]);
  });

  it("never sends cookies, even when asked to", async () => {
    let credentials: RequestCredentials | undefined;
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      credentials = init?.credentials;
      return new Response("{}", { status: 200 });
    });
    const link = new ServiceLink(SERVICE, issuing("t1"), { fetch: fetcher as typeof fetch });

    await link.fetch("/v1/notes", { credentials: "include" });

    expect(credentials).toBe("omit");
  });

  it("fetches a new token once after a 401", async () => {
    const auths: (string | null)[] = [];
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      auths.push(new Headers(init?.headers).get("Authorization"));
      return new Response("", { status: auths.length === 1 ? 401 : 200 });
    });
    const link = new ServiceLink(SERVICE, issuing("old", "new"), {
      fetch: fetcher as typeof fetch,
    });

    const response = await link.fetch("v1/notes");

    expect(response.status).toBe(200);
    expect(auths).toEqual(["Bearer old", "Bearer new"]);
  });

  it.each([
    "https://elsewhere.example/steal",
    "//elsewhere.example/steal",
    "javascript:alert(1)",
  ])("never sends the token anywhere but the service: %s", async (path) => {
    const fetcher = vi.fn();
    const link = new ServiceLink(SERVICE, issuing("t1"), { fetch: fetcher as typeof fetch });
    await expect(link.fetch(path)).rejects.toMatchObject({ code: "other_origin" });
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("websocket", () => {
  it("opens wss on the service and says who it is first", async () => {
    const link = new ServiceLink(SERVICE, issuing("t1"), {
      WebSocket: FakeSocket as unknown as typeof WebSocket,
    });

    const opening = link.websocket("/v1/artifacts/shared/doc/room");
    await vi.waitFor(() => expect(FakeSocket.made).toHaveLength(1));
    const socket = FakeSocket.made[0];
    expect(socket.url).toBe("wss://notes.example.com/api/v1/artifacts/shared/doc/room");
    expect(socket.sent).toEqual([]);

    socket.open();

    expect(await opening).toBe(socket);
    expect(socket.sent.map((frame) => JSON.parse(frame))).toEqual([
      { type: "auth", token: "t1" },
    ]);
  });

  it("is ws for a plain-http service on this machine", async () => {
    const link = new ServiceLink("http://localhost:8000", issuing("t1"), {
      WebSocket: FakeSocket as unknown as typeof WebSocket,
    });
    void link.websocket("room");
    await vi.waitFor(() => expect(FakeSocket.made).toHaveLength(1));
    expect(FakeSocket.made[0].url).toBe("ws://localhost:8000/room");
  });

  it("takes another first frame when the service wants one", async () => {
    const link = new ServiceLink(SERVICE, issuing("t1"), {
      WebSocket: FakeSocket as unknown as typeof WebSocket,
    });
    const opening = link.websocket("room", { authFrame: (t) => `TOKEN ${t}` });
    await vi.waitFor(() => expect(FakeSocket.made).toHaveLength(1));
    FakeSocket.made[0].open();
    await opening;
    expect(FakeSocket.made[0].sent).toEqual(["TOKEN t1"]);
  });

  it("rejects when the socket closes before it opens", async () => {
    const link = new ServiceLink(SERVICE, issuing("t1"), {
      WebSocket: FakeSocket as unknown as typeof WebSocket,
    });
    const opening = link.websocket("room");
    await vi.waitFor(() => expect(FakeSocket.made).toHaveLength(1));
    FakeSocket.made[0].refuse();
    await expect(opening).rejects.toBeInstanceOf(ServiceError);
  });
});

describe("through the bridge", () => {
  function frameWith(serviceUrl: string | null) {
    const posted: Record<string, unknown>[] = [];
    const host = {
      postMessage: (message: Record<string, unknown>) => posted.push(message),
    } as unknown as Window;
    Object.defineProperty(window, "parent", { value: host, configurable: true });
    const send = (body: Record<string, unknown>) => {
      const event = new MessageEvent("message", { data: { igni: BRIDGE_VERSION, ...body } });
      Object.defineProperty(event, "source", { value: host });
      window.dispatchEvent(event);
    };
    const pending = connect();
    send({
      kind: "hello",
      nonce: "n",
      extensionId: "acme.notes",
      params: {},
      settings: {},
      serviceUrl,
      theme: "dark",
      tokens: {},
    });
    return { posted, send, pending };
  }

  it("names the service the host said, and asks the host for its token", async () => {
    const { posted, send, pending } = frameWith(SERVICE);
    const bridge = await pending;
    expect(bridge.service.url).toBe(SERVICE);

    const token = bridge.service.token();
    const asked = posted.find((m) => m.kind === "service-token");
    // No audience on the wire: the host decides whose service it is.
    expect(asked).toEqual({ igni: BRIDGE_VERSION, kind: "service-token", nonce: "n", id: asked?.id });

    send({ kind: "service-token-reply", id: asked?.id, ok: true, token: "t1", expiresIn: 600 });
    await expect(token).resolves.toBe("t1");
  });

  it("rejects with the host's sentence when there is no token", async () => {
    const { posted, send, pending } = frameWith(SERVICE);
    const bridge = await pending;
    const token = bridge.service.token();
    const asked = posted.find((m) => m.kind === "service-token");
    send({ kind: "service-token-reply", id: asked?.id, ok: false, error: "nobody is signed in to igni" });
    await expect(token).rejects.toThrow(/signed in/);
  });

  it("has no service when the host named none", async () => {
    const bridge = await frameWith(null).pending;
    expect(bridge.service.url).toBeNull();
    await expect(bridge.service.token()).rejects.toMatchObject({ code: "no_service" });
  });
});

describe("a link with no service", () => {
  it("rejects fetch and websocket with no_service, asking for nothing", async () => {
    const ask = issuing("t1");
    const fetcher = vi.fn();
    const link = new ServiceLink(null, ask, {
      fetch: fetcher as typeof fetch,
      WebSocket: FakeSocket as unknown as typeof WebSocket,
    });

    await expect(link.fetch("/v1/notes")).rejects.toMatchObject({ code: "no_service" });
    await expect(link.websocket("room")).rejects.toMatchObject({ code: "no_service" });
    expect(ask).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
    expect(FakeSocket.made).toEqual([]);
  });
});

describe("a ServiceError", () => {
  it("carries its code, its name and a sentence", () => {
    const error = new ServiceError("closed", "gone");
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ServiceError");
    expect(error.code).toBe("closed");
    expect(error.message).toBe("gone");
  });

  it("says in the refusal which path it would not send the token to", async () => {
    const link = new ServiceLink(SERVICE, issuing("t1"));
    await expect(link.fetch("https://evil.example/x")).rejects.toThrow(
      "'https://evil.example/x' is not on this extension's service; its token goes nowhere else",
    );
  });
});

describe("the first frame by default", () => {
  it("is the auth object with the token", () => {
    expect(authMessage("t1")).toBe('{"type":"auth","token":"t1"}');
  });
});

describe("the token, at its edges", () => {
  it("is renewed at exactly the renewal window, and kept just outside it", async () => {
    let now = 0;
    const ask = issuing("t1", "t2");
    const link = new ServiceLink(SERVICE, ask, { now: () => now });
    await link.token();

    now = 600_000 - RENEW_BEFORE_MS - 1;
    expect(await link.token()).toBe("t1");
    now = 600_000 - RENEW_BEFORE_MS;
    expect(await link.token()).toBe("t2");
  });

  it("is asked for again on every call when it expires at once", async () => {
    const ask = vi
      .fn()
      .mockResolvedValueOnce({ token: "t1", expiresIn: 0 })
      .mockResolvedValueOnce({ token: "t2", expiresIn: -5 })
      .mockResolvedValueOnce({ token: "t3", expiresIn: 600 });
    const link = new ServiceLink(SERVICE, ask, { now: () => 0 });

    expect(await link.token()).toBe("t1");
    expect(await link.token()).toBe("t2");
    expect(await link.token()).toBe("t3");
  });

  it("surfaces the host's refusal and asks again on the next call", async () => {
    const ask = vi
      .fn()
      .mockRejectedValueOnce(new Error("nobody is signed in"))
      .mockResolvedValueOnce({ token: "t1", expiresIn: 600 });
    const link = new ServiceLink(SERVICE, ask);

    await expect(link.token()).rejects.toThrow("nobody is signed in");
    expect(await link.token()).toBe("t1");
    expect(ask).toHaveBeenCalledTimes(2);
  });

  it("is refused for another origin before the host is asked for a token", async () => {
    const ask = issuing("t1");
    const link = new ServiceLink(SERVICE, ask, {
      WebSocket: FakeSocket as unknown as typeof WebSocket,
    });

    await expect(link.fetch("//evil.example/x")).rejects.toMatchObject({ code: "other_origin" });
    await expect(link.websocket("https://evil.example/x")).rejects.toMatchObject({
      code: "other_origin",
    });
    expect(ask).not.toHaveBeenCalled();
    expect(FakeSocket.made).toEqual([]);
  });
});

describe("fetch, at its edges", () => {
  function recording(statuses: number[]) {
    const calls: { url: string; headers: Headers; init?: RequestInit }[] = [];
    const fetcher = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), headers: new Headers(init?.headers), init });
      return new Response("", { status: statuses.shift() ?? 200 });
    });
    return { calls, fetcher: fetcher as unknown as typeof fetch };
  }

  it("returns a second 401 as it is, and asks for no third token", async () => {
    const { calls, fetcher } = recording([401, 401]);
    const ask = issuing("old", "new", "never");
    const link = new ServiceLink(SERVICE, ask, { fetch: fetcher });

    const response = await link.fetch("/v1/notes");

    expect(response.status).toBe(401);
    expect(calls.map((c) => c.headers.get("Authorization"))).toEqual([
      "Bearer old",
      "Bearer new",
    ]);
    expect(ask).toHaveBeenCalledTimes(2);
  });

  it("does not retry any other failure", async () => {
    const { calls, fetcher } = recording([403]);
    const link = new ServiceLink(SERVICE, issuing("t1"), { fetch: fetcher });

    expect((await link.fetch("/v1/notes")).status).toBe(403);
    expect(calls).toHaveLength(1);
  });

  it.each([
    ["an object", { "X-Trace": "7" }],
    ["a list", [["X-Trace", "7"]]],
    ["a Headers", new Headers({ "X-Trace": "7" })],
  ])("keeps the caller's headers, given as %s, and the rest of init", async (_label, headers) => {
    const { calls, fetcher } = recording([200]);
    const link = new ServiceLink(SERVICE, issuing("t1"), { fetch: fetcher });

    await link.fetch("/v1/notes", { method: "POST", body: "x", headers: headers as HeadersInit });

    expect(calls[0].headers.get("X-Trace")).toBe("7");
    expect(calls[0].headers.get("Authorization")).toBe("Bearer t1");
    expect(calls[0].init?.method).toBe("POST");
    expect(calls[0].init?.body).toBe("x");
  });

  it("overwrites an Authorization the caller sent with the service token", async () => {
    const { calls, fetcher } = recording([200]);
    const link = new ServiceLink(SERVICE, issuing("t1"), { fetch: fetcher });

    await link.fetch("/v1/notes", { headers: { authorization: "Bearer stolen" } });

    expect(calls[0].headers.get("Authorization")).toBe("Bearer t1");
  });

  it.each([
    ["/v1/notes", "https://notes.example.com/api/v1/notes"],
    ["v1/notes", "https://notes.example.com/api/v1/notes"],
    ["/v1/notes#top", "https://notes.example.com/api/v1/notes#top"],
    ["", "https://notes.example.com/api/"],
  ])("joins %j under the service's own path", async (path, expected) => {
    const { calls, fetcher } = recording([200]);
    const link = new ServiceLink(SERVICE, issuing("t1"), { fetch: fetcher });
    await link.fetch(path);
    expect(calls[0].url).toBe(expected);
  });

  it("joins under a service URL that ends in a slash without doubling it", async () => {
    const { calls, fetcher } = recording([200]);
    const link = new ServiceLink(`${SERVICE}/`, issuing("t1"), { fetch: fetcher });
    await link.fetch("/v1/notes");
    expect(calls[0].url).toBe("https://notes.example.com/api/v1/notes");
  });

  it("never leaves the service's origin, whatever the path climbs through", async () => {
    const { calls, fetcher } = recording([200, 200]);
    const link = new ServiceLink(SERVICE, issuing("t1"), { fetch: fetcher });
    await link.fetch("../../x");
    await link.fetch("\\evil.example\\x");
    for (const call of calls) {
      expect(new URL(call.url).origin).toBe("https://notes.example.com");
    }
  });
});

describe("websocket, at its edges", () => {
  const sockets = { WebSocket: FakeSocket as unknown as typeof WebSocket };

  it("hands the sub-protocols to the socket as they are", async () => {
    const link = new ServiceLink(SERVICE, issuing("t1"), sockets);
    void link.websocket("room", { protocols: ["v1", "v2"] });
    await vi.waitFor(() => expect(FakeSocket.made).toHaveLength(1));
    expect(FakeSocket.made[0].protocols).toEqual(["v1", "v2"]);
  });

  it("sends the first frame once, and says closed in its own words when the socket closes first", async () => {
    const link = new ServiceLink(SERVICE, issuing("t1"), sockets);
    const opening = link.websocket("room");
    await vi.waitFor(() => expect(FakeSocket.made).toHaveLength(1));
    const socket = FakeSocket.made[0];

    socket.refuse();
    await expect(opening).rejects.toMatchObject({
      code: "closed",
      message: "the service closed room before it opened",
    });
    // Nobody is listening any more: a late open sends nothing.
    socket.open();
    expect(socket.sent).toEqual([]);
  });

  it("does not send the frame twice, nor reject after it opened", async () => {
    const link = new ServiceLink(SERVICE, issuing("t1"), sockets);
    const opening = link.websocket("room");
    await vi.waitFor(() => expect(FakeSocket.made).toHaveLength(1));
    const socket = FakeSocket.made[0];

    socket.open();
    await opening;
    socket.open();
    socket.refuse();

    expect(socket.sent).toHaveLength(1);
  });

  it("rejects with the frame builder's own error before a socket is made", async () => {
    const link = new ServiceLink(SERVICE, issuing("t1"), sockets);
    await expect(
      link.websocket("room", {
        authFrame: () => {
          throw new Error("no frame");
        },
      }),
    ).rejects.toThrow("no frame");
    expect(FakeSocket.made).toEqual([]);
  });

  it("is wss for https even when the path carries a query", async () => {
    const link = new ServiceLink(SERVICE, issuing("t1"), sockets);
    void link.websocket("/room?doc=1");
    await vi.waitFor(() => expect(FakeSocket.made).toHaveLength(1));
    expect(FakeSocket.made[0].url).toBe("wss://notes.example.com/api/room?doc=1");
  });
});

import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir, homedir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import type { TokenSource } from "./auth/tokens.js";
import { AuthError, NotAllowed, NotSupported, Unavailable } from "./errors.js";
import { Fleet, Local, requireFleet } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

const auth: TokenSource = { token: async () => "t-ada" };
const fleet = (url = "http://gateway.test", opts = {}) => new Fleet(url, { auth, ...opts });

describe("Fleet's address", () => {
  it.each([
    ["http://gateway.test", "http://gateway.test", "ws://gateway.test/v1/connect"],
    ["https://gateway.test/", "https://gateway.test", "wss://gateway.test/v1/connect"],
    ["ws://gateway.test:8080", "http://gateway.test:8080", "ws://gateway.test:8080/v1/connect"],
    ["wss://gateway.test", "https://gateway.test", "wss://gateway.test/v1/connect"],
    ["HTTPS://gateway.test", "https://gateway.test", "wss://gateway.test/v1/connect"],
    ["https://gateway.test/fleet?x=1#top", "https://gateway.test/fleet", "wss://gateway.test/fleet/v1/connect"],
  ])("%s → base and socket", (given, base, connect) => {
    const f = fleet(given);
    expect(f.base).toBe(base);
    expect(f.connectUrl).toBe(connect);
  });

  it.each(["ftp://gateway.test", "gateway.test", "file:///gateway"])("refuses %s", (given) => {
    expect(() => fleet(given)).toThrow();
  });

  it("describes itself and says whether it is worth reopening", () => {
    const f = fleet("https://gateway.test/fleet");
    expect(f.describe()).toBe("igni in Fleet via https://gateway.test/fleet");
    expect(f.reconnects).toBe(true);
    expect(f.standing).toBe("window");
    expect(new Local({ url: "ws://127.0.0.1:9" }).describe()).toBe("igni at ws://127.0.0.1:9");
    expect(new Local({ projectDir: "/tmp/x" }).reconnects).toBe(false);
  });

  it("require_fleet gives the fleet and names what needed it otherwise", () => {
    const f = fleet();
    expect(requireFleet(f, "commands")).toBe(f);
    expect(() => requireFleet(new Local({ projectDir: "/tmp/x" }), "commands")).toThrow(NotSupported);
  });

  it("finds a local project from a home-relative or relative path", () => {
    expect(new Local({ projectDir: "~/api" }).describe()).toBe(`igni at ${join(homedir(), "api")}`);
    expect(new Local({ projectDir: "work/api" }).describe()).toBe(`igni at ${resolve("work/api")}`);
  });
});

describe("Fleet's HTTP", () => {
  it("carries the producer's token and the caller's headers, the caller winning", async () => {
    const seen: Array<{ url: string; headers: Headers }> = [];
    const fetchImpl = (async (url: string | URL, init?: RequestInit) => {
      seen.push({ url: String(url), headers: new Headers(init?.headers) });
      return new Response(null, { status: 200 });
    }) as typeof fetch;
    const f = fleet("https://gateway.test/fleet", { fetchImpl });
    await f.request("GET", "/v1/me", { headers: { "X-Trace": "7" } });
    await f.request("GET", "/v1/me", { headers: { Authorization: "Bearer other" } });
    expect(seen[0].url).toBe("https://gateway.test/fleet/v1/me");
    expect(seen[0].headers.get("Authorization")).toBe("Bearer t-ada");
    expect(seen[0].headers.get("X-Trace")).toBe("7");
    expect(seen[1].headers.get("Authorization")).toBe("Bearer other");
  });

  it("is Unavailable when the gateway cannot be reached", async () => {
    const fetchImpl = (async () => {
      throw new Error("no route");
    }) as typeof fetch;
    await expect(fleet("http://gateway.test", { fetchImpl }).request("GET", "/v1/me")).rejects.toThrow(Unavailable);
  });

  it("a streamed call carries the token it is given, and bodies go as JSON", async () => {
    const seen: Array<{ headers: Headers; body: string | null }> = [];
    const fetchImpl = (async (_url: string | URL, init?: RequestInit) => {
      seen.push({ headers: new Headers(init?.headers), body: (init?.body as string) ?? null });
      return new Response("lines", { status: 200 });
    }) as typeof fetch;
    const f = fleet("http://gateway.test", { fetchImpl });
    await f.request("POST", "/v1/x", { body: { command: "ls" } });
    await f.request("GET", "/v1/me");
    await f.stream("POST", "/v1/commands", "t-given", { body: { command: "pwd" }, headers: { "X-Trace": "9" } });
    expect(JSON.parse(seen[0].body!)).toEqual({ command: "ls" });
    expect(seen[1].body).toBeNull();
    expect(seen[2].headers.get("Authorization")).toBe("Bearer t-given");
    expect(seen[2].headers.get("X-Trace")).toBe("9");
    expect(JSON.parse(seen[2].body!)).toEqual({ command: "pwd" });
  });
});

describe("Local's lockfile", () => {
  function project(content: string | Buffer): string {
    const dir = mkdtempSync(join(tmpdir(), "igni-"));
    mkdirSync(join(dir, ".igni"));
    writeFileSync(join(dir, ".igni", "backend.lock"), content);
    return dir;
  }

  it.each([
    "not json",
    "",
    "{}",
    '{"pid": 1}',
    '{"port": "eighty"}',
    '{"port": null}',
    "[1, 2]",
    '"port"',
    '{"port": 8765, "ws_token": 7}',
  ])("a lockfile that does not hold a port is not an igni lockfile (%s)", async (content) => {
    await expect(new Local({ projectDir: project(content) }).open()).rejects.toThrow(/is not an igni lockfile/);
  });

  it("a lockfile that is not text is not an igni lockfile", async () => {
    await expect(new Local({ projectDir: project(Buffer.from([0xff, 0xfe, 0xfa])) }).open()).rejects.toThrow(
      /is not an igni lockfile/,
    );
  });

  it("a missing lockfile says no igni is running", async () => {
    const dir = mkdtempSync(join(tmpdir(), "igni-"));
    await expect(new Local({ projectDir: dir }).open()).rejects.toThrow(/no igni is running/);
  });

  it("an empty approver token is no approver token", () => {
    const before = process.env.IGNI_APPROVER_TOKEN;
    process.env.IGNI_APPROVER_TOKEN = "";
    expect(new Local({ projectDir: "/tmp/x" }).approves).toBe(false);
    process.env.IGNI_APPROVER_TOKEN = "from-the-environment";
    expect(new Local({ projectDir: "/tmp/x" }).approves).toBe(true);
    if (before === undefined) delete process.env.IGNI_APPROVER_TOKEN;
    else process.env.IGNI_APPROVER_TOKEN = before;
  });
});

describe("opening and handshake refusals", () => {
  let fake: FakeIgni;
  afterEach(() => fake?.close());

  it("an igni nobody listens for is Unavailable", async () => {
    await expect(new Local({ url: "ws://127.0.0.1:1" }).open()).rejects.toThrow(Unavailable);
  });

  it.each([
    [401, AuthError, "the gateway refused the credential: token expired"],
    [403, NotAllowed, "the gateway refused the connection: token expired"],
  ])("the gateway refusing %i maps to the right error", async (status, kind, message) => {
    fake = new FakeIgni({ handshakeStatus: status, handshakeBody: '{"error_description": "token expired"}' });
    await fake.start();
    await expect(fleet(fake.wsUrl).open()).rejects.toThrow(kind);
    await expect(fleet(fake.wsUrl).open()).rejects.toThrow(message);
  });

  it("a non-refusal status is Unavailable with what was said", async () => {
    fake = new FakeIgni({ handshakeStatus: 502, handshakeBody: '{"error": "vm asleep"}' });
    await fake.start();
    await expect(fleet(fake.wsUrl).open()).rejects.toThrow("the gateway answered 502: vm asleep");
  });

  it("a local igni refusing 401 is an AuthError, and 500 is Unavailable", async () => {
    fake = new FakeIgni({ handshakeStatus: 401, handshakeBody: "no" });
    await fake.start();
    await expect(new Local({ url: fake.wsUrl }).open()).rejects.toThrow(/refused the credential: no/);
    await fake.close();
    fake = new FakeIgni({ handshakeStatus: 500, handshakeBody: "boom" });
    await fake.start();
    await expect(new Local({ url: fake.wsUrl }).open()).rejects.toThrow(/answered 500: boom/);
  });

  it("a local igni with the dev opt-out stands the connection as its window", async () => {
    fake = new FakeIgni();
    await fake.start();
    const local = new Local({ url: fake.wsUrl });
    const socket = await local.open();
    await socket.close();
    expect(local.standing).toBe("window");
  });

  it("closing a Fleet twice is harmless", async () => {
    const f = fleet();
    await f.aclose();
    await f.aclose();
  });
});

import { describe, expect, it, vi } from "vitest";

import { TokenCache } from "./auth/tokens.js";

describe("TokenCache", () => {
  it("keeps a token until it nears its end, then fetches a fresh one", async () => {
    let now = 1000;
    const cache = new TokenCache(() => now, () => 60);
    const fetch = vi.fn(async () => ({ access_token: `t${now}`, expires_in: 600 }));
    expect(await cache.get(fetch)).toBe("t1000");
    now = 1500; // still inside the window (expires at 1000 + 600 - 60 = 1540)
    expect(await cache.get(fetch)).toBe("t1000");
    expect(fetch).toHaveBeenCalledOnce();
    now = 1600; // past the renew margin
    expect(await cache.get(fetch)).toBe("t1600");
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("forgets a token so the next get fetches again", async () => {
    const cache = new TokenCache(() => 0, () => 0);
    const fetch = vi.fn(async () => ({ access_token: "a" }));
    await cache.get(fetch);
    await cache.forget();
    await cache.get(fetch);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("shares one in-flight fetch between concurrent callers", async () => {
    const cache = new TokenCache(() => Date.now() / 1000, () => 60);
    const fetch = vi.fn(async () => ({ access_token: "once", expires_in: 600 }));
    const [a, b] = await Promise.all([cache.get(fetch), cache.get(fetch)]);
    expect([a, b]).toEqual(["once", "once"]);
    expect(fetch).toHaveBeenCalledOnce();
  });
});

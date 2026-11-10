/**
 * `HostChannel`: who the guest listens to, and the envelope on what it
 * posts.
 */
import { describe, expect, it } from "vitest";

import { HostChannel } from "./channel.js";
import { BRIDGE_VERSION } from "./protocol.js";

function stubHost() {
  const posts: { message: unknown; target: unknown }[] = [];
  const host = {
    postMessage: (message: unknown, target: unknown) =>
      posts.push({ message, target }),
  } as unknown as Window;
  return { host, posts };
}

function eventFrom(source: unknown): MessageEvent {
  return { source } as unknown as MessageEvent;
}

describe("HostChannel", () => {
  it("hears only the window it is framed in", () => {
    const { host } = stubHost();
    const channel = new HostChannel(host, "n");

    expect(channel.isFrom(eventFrom(host))).toBe(true);
    expect(channel.isFrom(eventFrom({ not: "the host" }))).toBe(false);
    expect(channel.isFrom(eventFrom(null))).toBe(false);
  });

  it("posts to any origin, in the envelope the guest always used", () => {
    const { host, posts } = stubHost();
    const channel = new HostChannel(host, "n-1");

    channel.post({ kind: "call", id: "1", method: "acme_status", args: {} });
    channel.post({ kind: "host", id: "h2", op: "get", path: "chat.processing" });
    channel.post({ kind: "service-token", id: "s3" });
    channel.post({ kind: "close" });

    expect(posts.map((p) => p.target)).toEqual(["*", "*", "*", "*"]);
    // Key order is what a serialised message or a log shows.
    expect(posts.map((p) => JSON.stringify(p.message))).toEqual([
      `{"igni":${BRIDGE_VERSION},"kind":"call","nonce":"n-1","id":"1","method":"acme_status","args":{}}`,
      `{"igni":${BRIDGE_VERSION},"kind":"host","nonce":"n-1","id":"h2","op":"get","path":"chat.processing"}`,
      `{"igni":${BRIDGE_VERSION},"kind":"service-token","nonce":"n-1","id":"s3"}`,
      `{"igni":${BRIDGE_VERSION},"kind":"close","nonce":"n-1"}`,
    ]);
  });
});

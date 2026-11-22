import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ApprovalRequested } from "./approvals.js";
import { IgniClient } from "./client.js";
import { AuthError, RunFailed, Unavailable } from "./errors.js";
import { Local } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

let fake: FakeIgni;

async function connectLocal(opts: { token?: string } = {}): Promise<IgniClient> {
  return new IgniClient(new Local({ url: fake.wsUrl, token: opts.token })).connect();
}

describe("Local connect and RPC", () => {
  beforeEach(async () => {
    fake = new FakeIgni();
    await fake.start();
  });
  afterEach(() => fake.close());

  it("connects to a loopback igni and calls a method", async () => {
    const igni = await connectLocal();
    expect(igni.clientId).toBe("c-1");
    const update = await igni.check_for_update();
    expect(update).toBeNull();
    await igni.close();
  });

  it("creates a session and collects an ask() reply", async () => {
    fake = new FakeIgni({ run: { chunks: ["Hello, ", "world"] } });
    await fake.start();
    const igni = await connectLocal();
    const session = await igni.sessions.create();
    expect(session.id).toBe("s-1");
    const reply = await session.ask("hi", { approve: false });
    expect(reply.text).toBe("Hello, world");
    expect(reply.completed?.duration).toBe(1);
    await igni.close();
  });

  it("streams send() and answers an approval inline", async () => {
    fake = new FakeIgni({
      run: {
        chunks: ["thinking"],
        pause: [{ requirement_id: "r1", tool_name: "bash", friendly_name: "Run a command" }],
        afterApproval: [" and done"],
      },
    });
    await fake.start();
    const igni = await connectLocal();
    const session = await igni.sessions.create();
    let approved = false;
    const text: string[] = [];
    for await (const ev of session.send("do it")) {
      if (ev instanceof ApprovalRequested) {
        expect(ev.requirements[0].tool_name).toBe("bash");
        await ev.allow();
        approved = true;
      } else if (ev.type === "content_delta") {
        text.push(ev.text ?? "");
      }
    }
    expect(approved).toBe(true);
    expect(text.join("")).toBe("thinking and done");
    await igni.close();
  });

  it("raises RunFailed when a run errors, and ApprovalRequired without a policy", async () => {
    fake = new FakeIgni({ run: { error: "it broke" } });
    await fake.start();
    const igni = await connectLocal();
    const session = await igni.sessions.create();
    await expect(session.ask("hi", { approve: false })).rejects.toBeInstanceOf(RunFailed);
    await igni.close();
  });

  it("maps a refused local handshake to AuthError", async () => {
    fake = new FakeIgni({ requireToken: "right" });
    await fake.start();
    await expect(
      new IgniClient(new Local({ url: fake.wsUrl, token: "wrong" })).connect(),
    ).rejects.toBeInstanceOf(AuthError);
  });

  it("is Unavailable when nothing is listening", async () => {
    await expect(
      new IgniClient(new Local({ url: "ws://127.0.0.1:1", token: "t" })).connect(),
    ).rejects.toBeInstanceOf(Unavailable);
  });
});

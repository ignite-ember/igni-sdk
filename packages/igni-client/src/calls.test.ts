import { afterEach, describe, expect, it } from "vitest";

import { read } from "./calls.js";
import { IgniClient } from "./client.js";
import { MethodFailed, UnknownMethod } from "./errors.js";
import { Local } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";
import type { WireMessage } from "./wire.js";

let fake: FakeIgni;

async function session() {
  fake = new FakeIgni({
    answers: { run_workflow: { workflow_run_id: "wf-1", ok: true } },
    streamPushes: {
      run_workflow: [
        { channel: "workflow_event", payload: { workflow_run_id: "wf-1", type: "workflow_running" } },
        { channel: "workflow_event", payload: { workflow_run_id: "wf-1", type: "workflow_completed" } },
      ],
    },
  });
  await fake.start();
  const igni = await new IgniClient(new Local({ url: fake.wsUrl })).connect();
  return { igni, session: await igni.sessions.create() };
}

describe("read()", () => {
  it("raises an error answer as the kind it is, and returns a result or a message", () => {
    expect(() => read("m", { type: "error", text: "Unknown RPC method: m" } as WireMessage)).toThrow(UnknownMethod);
    expect(() => read("m", { type: "error", text: "nope" } as WireMessage)).toThrow(MethodFailed);
    expect(read<number>("m", { type: "rpc_response", result: 3 } as WireMessage)).toBe(3);
    const msg = { type: "command_result", content: "hi" } as unknown as WireMessage;
    expect(read<{ content: string }>("m", msg).content).toBe("hi");
  });
});

describe("Call", () => {
  afterEach(() => fake.close());

  it("resolves the result when awaited", async () => {
    const { igni, session: s } = await session();
    expect((await s.workflows.run("nightly")).workflow_run_id).toBe("wf-1");
    await igni.close();
  });

  it("follows its own events when iterated, ending at the last one", async () => {
    const { igni, session: s } = await session();
    const kinds: string[] = [];
    for await (const ev of s.workflows.run("nightly")) {
      kinds.push(String((ev as { payload?: { type?: string } }).payload?.type));
    }
    expect(kinds).toEqual(["workflow_running", "workflow_completed"]);
    await igni.close();
  });

  it("sends each call under an id of its own, carrying its arguments by wire name", async () => {
    const { igni, session: s } = await session();
    await s.workflows.run("one");
    await s.workflows.run("two");
    const runs = fake.calls.filter((c) => c.method === "run_workflow");
    expect(runs.map((c) => c.args.name)).toEqual(["one", "two"]);
    expect(new Set(runs.map((c) => c.id)).size).toBe(2);
    await igni.close();
  });
});

describe("message methods", () => {
  afterEach(() => fake.close());

  it("a command returns its result", async () => {
    fake = new FakeIgni();
    await fake.start();
    const igni = await new IgniClient(new Local({ url: fake.wsUrl })).connect();
    const result = await (await igni.sessions.create()).command("/help");
    expect(result.content).toBe("ok");
    await igni.close();
  });

  it("a command igni answers with an error raises its kind", async () => {
    fake = new FakeIgni({ commandError: "the disk is full" });
    await fake.start();
    const igni = await new IgniClient(new Local({ url: fake.wsUrl })).connect();
    await expect((await igni.sessions.create()).command("/help")).rejects.toThrow(/command: the disk is full/);
    await igni.close();
  });
});

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { IgniClient } from "./client.js";
import { Local } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

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

describe("Call", () => {
  afterEach(() => fake.close());

  it("resolves the result when awaited", async () => {
    const { igni, session: s } = await session();
    const result = await s.workflows.run("nightly");
    expect(result.workflow_run_id).toBe("wf-1");
    await igni.close();
  });

  it("follows its own events when iterated, ending at the last one", async () => {
    const { igni, session: s } = await session();
    const kinds: string[] = [];
    for await (const ev of s.workflows.run("nightly")) {
      const payload = (ev as { payload?: { type?: string } }).payload;
      kinds.push(String(payload?.type));
    }
    expect(kinds).toEqual(["workflow_running", "workflow_completed"]);
    await igni.close();
  });
});

import { afterEach, describe, expect, it } from "vitest";

import { ApprovalRequested, Decision } from "./approvals.js";
import { IgniClient } from "./client.js";
import { ApprovalRequired, NotAllowed, RunFailed, RunInterrupted } from "./errors.js";
import { Local } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";
import type { Requirement } from "./models.generated.js";

let fake: FakeIgni;
const connect = () => new IgniClient(new Local({ url: fake.wsUrl })).connect();

const pausingScript = () => ({
  runScript: () => [
    { type: "run_started" },
    { type: "run_paused", requirements: [{ requirement_id: "r1", tool_name: "bash", friendly_name: "Run" }] },
    { type: "content_delta", text: "done" },
    { type: "run_completed", duration: 2 },
  ],
});

describe("runs and replies", () => {
  afterEach(() => fake.close());

  it("ask() collects text, thinking, tools and the completion", async () => {
    fake = new FakeIgni({
      runScript: () => [
        { type: "run_started" },
        { type: "content_delta", text: "thinking...", is_thinking: true },
        { type: "content_delta", text: "answer" },
        { type: "tool_completed", tool_name: "bash" },
        { type: "run_completed", duration: 3, input_tokens: 10 },
      ],
    });
    await fake.start();
    const igni = await connect();
    const reply = await (await igni.sessions.create()).ask("hi");
    expect(reply.text).toBe("answer");
    expect(reply.thinking).toBe("thinking...");
    expect(reply.tools).toHaveLength(1);
    expect((reply.tools[0] as { tool_name?: string }).tool_name).toBe("bash");
    expect(reply.completed?.duration).toBe(3);
    expect(String(reply)).toBe("answer");
    await igni.close();
  });

  it("ask(approve) answers the approval and runs to the end", async () => {
    fake = new FakeIgni(pausingScript());
    await fake.start();
    const igni = await connect();
    const reply = await (await igni.sessions.create()).ask("deploy", { approve: true });
    expect(reply.text).toBe("done");
    expect(fake.decisions[0].map((d) => d.action)).toEqual(["confirm"]);
    await igni.close();
  });

  it.each([
    ["false rejects", false, "reject"],
    ["a function returning a Decision", () => Decision.deny(), "reject"],
    ["a function returning a bool", (r: Requirement) => r.tool_name === "bash", "confirm"],
  ])("ask(approve) takes %s", async (_name, policy, action) => {
    fake = new FakeIgni(pausingScript());
    await fake.start();
    const igni = await connect();
    await (await igni.sessions.create()).ask("deploy", { approve: policy });
    expect(fake.decisions[0].map((d) => d.action)).toEqual([action]);
    await igni.close();
  });

  it("ask() without a policy raises ApprovalRequired at a pause", async () => {
    fake = new FakeIgni(pausingScript());
    await fake.start();
    const igni = await connect();
    await expect((await igni.sessions.create()).ask("deploy")).rejects.toBeInstanceOf(ApprovalRequired);
    await igni.close();
  });

  it("ask() raises RunFailed when the run errors", async () => {
    fake = new FakeIgni({ runScript: () => [{ type: "run_started" }, { type: "run_error", error: "it broke" }] });
    await fake.start();
    const igni = await connect();
    await expect((await igni.sessions.create()).ask("x")).rejects.toThrow(/it broke/);
    await igni.close();
  });

  it("ask() raises RunFailed when igni starts no run for the prompt", async () => {
    fake = new FakeIgni({ runScript: () => [{ type: "error", text: "blocked by a hook" }] });
    await fake.start();
    const igni = await connect();
    await expect((await igni.sessions.create()).ask("x")).rejects.toThrow(/blocked by a hook/);
    await igni.close();
  });

  it("send() yields an ApprovalRequested that resumes the run when answered", async () => {
    fake = new FakeIgni(pausingScript());
    await fake.start();
    const igni = await connect();
    const seen: string[] = [];
    for await (const ev of (await igni.sessions.create()).send("deploy")) {
      if (ev instanceof ApprovalRequested) {
        expect(ev.requirements[0].friendly_name).toBe("Run");
        await ev.allow();
      } else {
        seen.push(ev.type ?? "");
      }
    }
    expect(seen).toContain("content_delta");
    expect(seen).toContain("run_completed");
    await igni.close();
  });

  it("fills a waiting requirement's details when they arrive after the pause", async () => {
    fake = new FakeIgni({
      runScript: () => [
        { type: "run_started" },
        { type: "run_paused", requirements: [{ requirement_id: "r1", tool_name: "bash", details_pending: true }] },
        { type: "requirement_details", requirement_id: "r1", details: "because reasons" },
        { type: "run_completed" },
      ],
    });
    await fake.start();
    const igni = await connect();
    let waiting: ApprovalRequested | null = null;
    for await (const ev of (await igni.sessions.create()).send("x")) {
      if (ev instanceof ApprovalRequested) {
        waiting = ev;
        await ev.allow();
      }
    }
    expect(waiting!.requirements[0].details).toBe("because reasons");
    expect(waiting!.requirements[0].details_pending).toBe(false);
    await igni.close();
  });

  it("ask() takes the main run's completion, not a sub-agent's", async () => {
    fake = new FakeIgni({
      runScript: () => [
        { type: "run_started" },
        { type: "run_completed", parent_run_id: "p", duration: 9 },
        { type: "content_delta", text: "hi" },
        { type: "run_completed", duration: 1 },
      ],
    });
    await fake.start();
    const igni = await connect();
    const reply = await (await igni.sessions.create()).ask("x");
    expect(reply.text).toBe("hi");
    expect(reply.completed?.duration).toBe(1);
    await igni.close();
  });

  it("send() raises NotAllowed when igni refuses the approval answer", async () => {
    fake = new FakeIgni({ ...pausingScript(), refuseApproval: true });
    await fake.start();
    const igni = await connect();
    const run = async () => {
      for await (const ev of (await igni.sessions.create()).send("deploy")) {
        if (ev instanceof ApprovalRequested) await ev.allow();
      }
    };
    await expect(run()).rejects.toBeInstanceOf(NotAllowed);
    await igni.close();
  });

  it("send() raises RunInterrupted when igni moves mid-run", async () => {
    fake = new FakeIgni(pausingScript());
    await fake.start();
    const igni = await connect();
    const run = async () => {
      for await (const ev of (await igni.sessions.create()).send("deploy")) {
        if (ev instanceof ApprovalRequested) {
          fake.move("c-2"); // igni moved: the run in flight is interrupted
        }
      }
    };
    await expect(run()).rejects.toBeInstanceOf(RunInterrupted);
    await igni.close();
  });
});

import { describe, expect, it, vi } from "vitest";

import { ApprovalRequested, Approver, Decision } from "./approvals.js";
import { ApprovalRequired } from "./errors.js";
import type { HitlDecision, RunPaused } from "./models.generated.js";

function paused(): RunPaused {
  return {
    type: "run_paused",
    run_id: "run-1",
    requirements: [
      { requirement_id: "r1", tool_name: "bash" },
      { requirement_id: "r2", tool_name: "write" },
    ],
  } as RunPaused;
}

describe("Decision", () => {
  it("builds confirm/reject frames with the right scope", () => {
    expect(Decision.allow().choice).toBe("once");
    expect(Decision.allow("always").choice).toBe("always");
    expect(Decision.deny().choice).toBe("once");
    expect(Decision.deny(true).choice).toBe("deny");
    const frame = Decision.allow("similar").frame("r9");
    expect(frame).toMatchObject({ type: "hitl_decision", requirement_id: "r9", action: "confirm", choice: "similar" });
  });
});

describe("ApprovalRequested", () => {
  it("allow() confirms every call and sends the batch", async () => {
    const sent: HitlDecision[][] = [];
    const req = new ApprovalRequested(paused(), async (d) => void sent.push(d));
    expect(req.run_id).toBe("run-1");
    await req.allow("always");
    expect(req.answered).toBe(true);
    expect(sent[0].map((d) => d.action)).toEqual(["confirm", "confirm"]);
    expect(sent[0][0].choice).toBe("always");
  });

  it("deny() rejects every call", async () => {
    const sent: HitlDecision[][] = [];
    const req = new ApprovalRequested(paused(), async (d) => void sent.push(d));
    await req.deny(true);
    expect(sent[0].map((d) => d.choice)).toEqual(["deny", "deny"]);
  });

  it("refuses to answer twice", async () => {
    const req = new ApprovalRequested(paused(), async () => undefined);
    await req.allow();
    await expect(req.allow()).rejects.toThrow(/already answered/);
  });

  it("requires an answer for every call", async () => {
    const req = new ApprovalRequested(paused(), async () => undefined);
    await expect(req.decide(new Map([["r1", Decision.allow()]]))).rejects.toThrow(/missing/);
  });
});

describe("Approver", () => {
  it("raises ApprovalRequired with no policy", async () => {
    const req = new ApprovalRequested(paused(), async () => undefined);
    await expect(new Approver(undefined).answer(req)).rejects.toBeInstanceOf(ApprovalRequired);
  });

  it("answers from a boolean policy", async () => {
    const answer = vi.fn(async () => undefined);
    await new Approver(true).answer(new ApprovalRequested(paused(), answer));
    expect(answer).toHaveBeenCalledOnce();
  });

  it("answers from a function policy returning a Decision or a bool", async () => {
    const sent: HitlDecision[] = [];
    const req = new ApprovalRequested(paused(), async (d) => void sent.push(...d));
    await new Approver((r) => (r.tool_name === "bash" ? Decision.deny() : true)).answer(req);
    expect(sent.find((d) => d.requirement_id === "r1")?.action).toBe("reject");
    expect(sent.find((d) => d.requirement_id === "r2")?.action).toBe("confirm");
  });
});

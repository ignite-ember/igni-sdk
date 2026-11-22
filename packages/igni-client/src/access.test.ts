import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { ANSWER, REACHES, check, checkAnswer } from "./access.js";
import { ApprovalRequested } from "./approvals.js";
import { IgniClient } from "./client.js";
import { AccessRefused } from "./errors.js";
import { Local } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

let fake: FakeIgni;

function lockfile(token: string | null): string {
  const dir = mkdtempSync(join(tmpdir(), "igni-"));
  mkdirSync(join(dir, ".igni"));
  const body: Record<string, unknown> = { pid: 1, port: Number(new URL(fake.wsUrl).port), wire_version: "1" };
  if (token !== null) body.ws_token = token;
  writeFileSync(join(dir, ".igni", "backend.lock"), JSON.stringify(body));
  return dir;
}

const calls = (method: string) => fake.calls.filter((c) => c.method === method).length;
const approvalPause = () => ({
  runScript: () => [
    { type: "run_paused", requirements: [{ requirement_id: "req-x", tool_name: "run_shell_command" }] },
    { type: "run_completed" },
  ],
});

describe("access gating, end to end", () => {
  afterEach(() => fake.close());

  it("a program with the lockfile's token reaches client calls only", async () => {
    fake = new FakeIgni({ requireToken: "program", answers: { list_background_processes: [] } });
    await fake.start();
    const igni = await new IgniClient(new Local({ projectDir: lockfile("program") })).connect();
    expect(igni.target.standing).toBe("program");
    expect(await igni.processes.list()).toEqual([]);
    await expect(igni.approvers.mint_token()).rejects.toThrow(/only igni's window/);
    const session = await igni.sessions.create();
    // A followed method checks access as it builds its Call, so it throws synchronously.
    expect(() => session.plan.approve("r-1")).toThrow(AccessRefused);
    expect(calls("mint_approver_token")).toBe(0);
    expect(calls("approve_plan")).toBe(0);
    await igni.close();
  });

  it("an approver reaches approver calls but not the window's", async () => {
    fake = new FakeIgni({ requireToken: "approver", answers: { approve_plan: { ok: true } } });
    await fake.start();
    const igni = await new IgniClient(new Local({ projectDir: lockfile("program"), approverToken: "approver" })).connect();
    expect(igni.target.standing).toBe("approver");
    const session = await igni.sessions.create();
    await session.plan.approve("r-1");
    expect(() => igni.auth.login()).toThrow(AccessRefused);
    expect(calls("approve_plan")).toBe(1);
    expect(calls("login")).toBe(0);
    await igni.close();
  });

  it("an igni without a launch secret stands every connection as its window", async () => {
    fake = new FakeIgni({ answers: { mint_approver_token: { token: "t" } } });
    await fake.start();
    const igni = await new IgniClient(new Local({ projectDir: lockfile(null) })).connect();
    expect(igni.target.standing).toBe("window");
    expect((await igni.approvers.mint_token()).token).toBe("t");
    await igni.close();
  });

  it("a token given by hand is igni's to judge", async () => {
    fake = new FakeIgni({
      requireToken: "whose",
      answers: { login: () => ({ error: "login: only igni's window may do this" }) },
    });
    await fake.start();
    const igni = await new IgniClient(new Local({ url: fake.wsUrl, token: "whose" })).connect();
    expect(igni.target.standing).toBe("unknown");
    await expect(igni.auth.login()).rejects.toThrow(/only igni's window/);
    expect(calls("login")).toBe(1);
    await igni.close();
  });

  it("a reply that carries a code is classified by it, not by its words", async () => {
    fake = new FakeIgni({
      answers: { login: () => ({ error: "login: not for this connection", code: "forbidden" }) },
    });
    await fake.start();
    const igni = await new IgniClient(new Local({ url: fake.wsUrl })).connect();
    await expect(igni.auth.login()).rejects.toBeInstanceOf(AccessRefused);
    await igni.close();
  });

  it("a program's approve is refused before it is sent", async () => {
    fake = new FakeIgni({ requireToken: "program", ...approvalPause() });
    await fake.start();
    const igni = await new IgniClient(new Local({ projectDir: lockfile("program") })).connect();
    const session = await igni.sessions.create();
    for await (const ev of session.send("run it")) {
      if (ev instanceof ApprovalRequested) {
        await expect(ev.allow()).rejects.toThrow(/approver token/);
        expect(ev.answered).toBe(false);
        break;
      }
    }
    expect(fake.decisions).toEqual([]);
    await igni.close();
  });

  it("a connection whose standing is unknown sends its answer", async () => {
    fake = new FakeIgni(approvalPause());
    await fake.start();
    const igni = await new IgniClient(new Local({ url: fake.wsUrl, token: "anything" })).connect();
    expect(igni.target.standing).toBe("unknown");
    const session = await igni.sessions.create();
    for await (const ev of session.send("run it")) {
      if (ev instanceof ApprovalRequested) await ev.allow();
    }
    expect(fake.decisions.length).toBe(1);
    await igni.close();
  });

  it.each([
    ["always", (ev: ApprovalRequested) => ev.allow("always")],
    ["similar", (ev: ApprovalRequested) => ev.allow("similar")],
    ["deny-remembered", (ev: ApprovalRequested) => ev.deny(true)],
  ])("an approver saving a rule (%s) is refused before it is sent", async (_id, answer) => {
    fake = new FakeIgni({ requireToken: "approver", ...approvalPause() });
    await fake.start();
    const igni = await new IgniClient(new Local({ projectDir: lockfile("program"), approverToken: "approver" })).connect();
    const session = await igni.sessions.create();
    for await (const ev of session.send("run it")) {
      if (ev instanceof ApprovalRequested) {
        await expect(answer(ev)).rejects.toThrow(/an approver answers once/);
        expect(fake.decisions).toEqual([]);
        await ev.allow();
      }
    }
    expect(fake.decisions.map((b) => b.map((d) => d.choice))).toEqual([["once"]]);
    await igni.close();
  });
});

describe("check() and the standings table", () => {
  it("knows what each standing reaches", () => {
    expect(REACHES.program).toEqual(new Set(["client"]));
    expect(REACHES.approver).toEqual(new Set(["client", "approver"]));
    expect(REACHES.window).toEqual(new Set(["client", "approver", "window"]));
    expect(REACHES.unknown).toBeNull();
  });

  it("passes what a standing reaches and refuses what it does not", () => {
    for (const access of ["client", "approver", "window"] as const) {
      check("m", access, "window");
      check("m", access, "unknown");
    }
    check("m", "approver", "approver");
    expect(() => check("m", "approver", "program")).toThrow(AccessRefused);
  });

  it("names the method and says who may", () => {
    try {
      check("login", "window", "approver");
      throw new Error("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(AccessRefused);
      expect((e as AccessRefused).method).toBe("login");
      expect((e as AccessRefused).detail).toBe("only igni's window may do this");
    }
    expect(() => check("approve_plan", "approver", "program")).toThrow(/approverToken/);
  });

  it("falls back to a generic reason for an access with none, and never refuses an unknown standing", () => {
    expect(() => check("open_page", "page", "window")).toThrow(/a page call/);
    expect(() => check("x", "platform", "window")).toThrow(/a platform call/);
    check("m", "page", "unknown");
    check("m", "window", "unknown");
  });

  it("checkAnswer gates approving and rule-saving", () => {
    expect(ANSWER).toBe("hitl_response_batch");
    checkAnswer("unknown");
    checkAnswer("window", ["always"]);
    checkAnswer("approver", ["once"]);
    expect(() => checkAnswer("program")).toThrow(/approver token/);
    expect(() => checkAnswer("approver", ["always"])).toThrow(/answers once/);
  });
});

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ApprovalRequested } from "./approvals.js";
import { IgniClient } from "./client.js";
import { Local } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

let fake: FakeIgni;

function client(): IgniClient {
  return new IgniClient(new Local({ url: fake.wsUrl }));
}

function echoScript(text: string) {
  return [
    { type: "run_started" },
    { type: "content_delta", text: `echo: ${text}` },
    { type: "run_completed", duration: 1 },
  ];
}

describe("sessions", () => {
  afterEach(() => fake.close());

  it("knows its id and the project igni bound it to", async () => {
    fake = new FakeIgni();
    await fake.start();
    const igni = await client().connect();
    const session = await igni.sessions.create("/work/api");
    expect(session.toString()).toBe(`Session(${session.id})`);
    expect(session.projectDir).toBe("/work/api");
    expect((await igni.sessions.open(session.id)).projectDir).toBe("/work/api");
    await igni.close();
  });

  it("the default session is a new one when igni has none open", async () => {
    fake = new FakeIgni();
    await fake.start();
    const igni = await client().connect();
    const opened = await igni.sessions.default();
    fake.answers.get_session_id = "";
    const fresh = await igni.sessions.default();
    expect(opened.id).toBe("s-default");
    expect(["", "s-default"]).not.toContain(fresh.id);
    const attaches = fake.calls.filter((c) => c.method === "attach_session");
    expect(attaches.at(-1)!.args.session_id ?? "").toBe("");
    await igni.close();
  });

  it("a session's events are its own and not another session's", async () => {
    fake = new FakeIgni({ runScript: echoScript });
    await fake.start();
    const igni = await client().connect();
    const mine = await igni.sessions.create();
    const other = await igni.sessions.create();
    const heard: Array<{ session_id: string; type: string; text: string }> = [];
    const listening = (async () => {
      for await (const ev of mine.events()) {
        if (ev instanceof ApprovalRequested) continue;
        heard.push({ session_id: ev.session_id ?? "", type: ev.type ?? "", text: (ev as { text?: string }).text ?? "" });
        if (ev.type === "run_completed") return;
      }
    })();
    await new Promise((r) => setTimeout(r, 20));
    await other.ask("theirs");
    await mine.ask("mine");
    await listening;
    expect(new Set(heard.map((e) => e.session_id))).toEqual(new Set([mine.id]));
    expect(heard.filter((e) => e.type === "content_delta").map((e) => e.text).join("")).toBe("echo: mine");
    await igni.close();
  });

  it("an approval answered from events() goes to igni in its own session", async () => {
    fake = new FakeIgni();
    await fake.start();
    const igni = await client().connect();
    const session = await igni.sessions.create();
    setTimeout(() => {
      fake.broadcast({
        type: "run_paused",
        session_id: session.id,
        run_id: "r-1",
        requirements: [{ requirement_id: "req-deploy", tool_name: "deploy" }],
      });
    }, 20);
    for await (const ev of session.events()) {
      if (ev instanceof ApprovalRequested) {
        await ev.allow();
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 20));
    const batch = fake.frames.find((f) => f.type === "hitl_response_batch")!;
    expect(batch.session_id).toBe(session.id);
    expect(String(batch.id)).toMatch(/^hitl-/);
    expect((batch.decisions as Array<{ requirement_id: string }>).map((d) => d.requirement_id)).toEqual(["req-deploy"]);
    await igni.close();
  });

  it("an error on the prompt's own stream is yielded, not taken for a refusal", async () => {
    fake = new FakeIgni({
      runScript: (t) => [
        { type: "error", text: "the model hiccuped" },
        ...echoScript(t),
      ],
    });
    await fake.start();
    const igni = await client().connect();
    const session = await igni.sessions.create();
    const events: Array<{ type: string; text?: string }> = [];
    for await (const ev of session.send("go")) {
      if (ev instanceof ApprovalRequested) continue;
      events.push({ type: ev.type ?? "", text: (ev as { text?: string }).text });
    }
    expect(events.filter((e) => e.type === "error").map((e) => e.text)).toEqual(["the model hiccuped"]);
    expect(events.at(-1)!.type).toBe("run_completed");
    await igni.close();
  });

  it("details for a requirement nobody waits on change nothing and are still yielded", async () => {
    fake = new FakeIgni({
      runScript: () => [
        { type: "requirement_details", requirement_id: "req-deploy", details: "too early" },
        { type: "run_paused", requirements: [{ requirement_id: "req-deploy", tool_name: "deploy" }] },
        { type: "requirement_details", requirement_id: "req-elsewhere", details: "not this one" },
        { type: "run_completed" },
      ],
    });
    await fake.start();
    const igni = await client().connect();
    const session = await igni.sessions.create();
    const details: string[] = [];
    let waiting: ApprovalRequested | null = null;
    for await (const ev of session.send("deploy")) {
      if (ev instanceof ApprovalRequested) {
        waiting = ev;
        ev.requirements[0].details_pending = true;
        await ev.allow();
      } else if (ev.type === "requirement_details") {
        details.push(String((ev as { details?: string }).details));
      }
    }
    expect(waiting!.requirements[0].details ?? "").toBe("");
    expect(waiting!.requirements[0].details_pending).toBe(true);
    expect(details).toEqual(["too early", "not this one"]);
    await igni.close();
  });

  it("reattaching attaches every session again with its project", async () => {
    fake = new FakeIgni();
    await fake.start();
    const igni = await client().connect();
    const first = await igni.sessions.create("/work/a");
    const second = await igni.sessions.create("/work/b");
    const third = await igni.sessions.create();
    const before = fake.calls.length;
    await igni.sessions.reattach();
    const again = fake.calls
      .slice(before)
      .filter((c) => c.method === "attach_session")
      .map((c) => [c.args.session_id, c.args.project_dir ?? ""]);
    expect(again).toEqual([
      [first.id, "/work/a"],
      [second.id, "/work/b"],
      [third.id, ""],
    ]);
    await igni.close();
  });

  it("a prompt and a file go to igni byte for byte, and queue() queues", async () => {
    const prompt = "\n  fix the \t build  \r\n\n";
    const files = { " a b.py ": "\n  x = 1 \n\n" };
    fake = new FakeIgni({ runScript: echoScript });
    await fake.start();
    const igni = await client().connect();
    const session = await igni.sessions.create();
    await session.ask(prompt, { files });
    await session.queue(prompt);
    await new Promise((r) => setTimeout(r, 20));
    const sent = fake.frames.find((f) => f.type === "user_message")!;
    const queued = fake.frames.find((f) => f.type === "queue_message")!;
    expect(sent.text).toBe(prompt);
    expect(sent.file_contents).toEqual(files);
    expect(queued.text).toBe(prompt);
    await igni.close();
  });

  it("lists the sessions igni keeps, as SessionListEntry", async () => {
    fake = new FakeIgni({
      answers: { list_sessions: { sessions: [{ session_id: "s-1", name: "one" }, { session_id: "s-2", name: "two" }] } },
    });
    await fake.start();
    const igni = await client().connect();
    const listed = await igni.sessions.list();
    expect(listed.map((s) => s.session_id)).toEqual(["s-1", "s-2"]);
    expect(listed[0].name).toBe("one");
    await igni.close();
  });
});

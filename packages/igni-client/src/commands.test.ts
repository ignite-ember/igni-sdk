import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Commands } from "./commands.js";
import { AuthError, GroupIsLocalOnly, NotAllowed, Unavailable } from "./errors.js";
import { Fleet } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

let fake: FakeIgni;
const commands = () => new Commands(new Fleet(fake.httpUrl, { auth: { token: async () => "t" } }));

describe("commands", () => {
  afterEach(() => fake.close());

  it("me() reports the producer, org and VM state", async () => {
    fake = new FakeIgni();
    await fake.start();
    const me = await commands().me();
    expect(me.producer).toBe("person:p1");
    expect(me.org).toBe("o1");
    expect(me.vm).toEqual({ state: "running", signed_in: true });
  });

  it("run() with an explicit producer streams its output and how it ended", async () => {
    fake = new FakeIgni();
    await fake.start();
    const run = await commands().run("echo hi", { producer: "person:p1" });
    const chunks: string[] = [];
    for await (const out of run) chunks.push(out.text);
    expect(chunks.join("")).toBe("hi\n");
    expect(run.stdout).toBe("hi\n");
    expect(run.finished?.exit_code).toBe(0);
    expect(run.finished?.ok).toBe(true);
  });

  it("run() defaults the producer to the one me() reports", async () => {
    fake = new FakeIgni();
    await fake.start();
    const run = await commands().run("echo hi");
    await run.wait();
    expect(fake.frames).toBeDefined(); // ran through /v1/me then /v1/commands
    expect(run.finished?.ok).toBe(true);
  });

  it("accumulates stdout and stderr separately", async () => {
    fake = new FakeIgni({
      commandLines: [
        { stream: "stdout", data_b64: Buffer.from("out").toString("base64") },
        { stream: "stderr", data_b64: Buffer.from("err").toString("base64") },
        { done: true, exit_code: 2 },
      ],
    });
    await fake.start();
    const run = await commands().run("x", { producer: "person:p1" });
    const finished = await run.wait();
    expect(run.stdout).toBe("out");
    expect(run.stderr).toBe("err");
    expect(finished.exit_code).toBe(2);
    expect(finished.ok).toBe(false);
  });

  it("ignores command/woken/unknown lines and reports no result when none arrives", async () => {
    fake = new FakeIgni({
      commandLines: [
        { command: { command_id: "c1", state: "running" } },
        { woken: { how: "cold", node: "n1" } },
        { nonsense: 1 },
        { stream: "stdout", data_b64: Buffer.from("hi").toString("base64") },
      ],
    });
    await fake.start();
    const run = await commands().run("x", { producer: "person:p1" });
    const out: string[] = [];
    for await (const o of run) out.push(o.text);
    expect(out).toEqual(["hi"]);
    expect(run.finished?.error).toMatch(/without a result/);
  });

  it("a command's output can be read once", async () => {
    fake = new FakeIgni();
    await fake.start();
    const run = await commands().run("x", { producer: "person:p1" });
    await run.wait();
    await expect((async () => {
      for await (const _ of run) void _;
    })()).rejects.toThrow(/read once/);
  });

  it("maps a gateway refusal of commands to the right error", async () => {
    fake = new FakeIgni({ commandStatus: 403 });
    await fake.start();
    const run = await commands().run("x", { producer: "person:p1" });
    await expect(run.wait()).rejects.toBeInstanceOf(GroupIsLocalOnly);
  });

  it.each([
    [401, AuthError],
    [403, NotAllowed],
    [404, NotAllowed],
    [500, Unavailable],
  ])("maps a %i from me() to the right error", async (status, kind) => {
    fake = new FakeIgni({ meStatus: status });
    await fake.start();
    await expect(commands().me()).rejects.toBeInstanceOf(kind);
  });

  it("checks the command and the timeout, and the producer form", async () => {
    fake = new FakeIgni();
    await fake.start();
    const c = commands();
    await expect(c.run("", { producer: "person:p1" })).rejects.toThrow(/1 byte to 16 KiB/);
    await expect(c.run("x", { producer: "person:p1", timeoutS: 0 })).rejects.toThrow(/1 to 3600/);
    await expect(c.run("x", { producer: "person:p1", timeoutS: 5000 })).rejects.toThrow(/1 to 3600/);
    await expect(c.run("x", { producer: "nope" })).rejects.toThrow(/person:<id>/);
  });
});

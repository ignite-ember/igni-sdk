import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Person } from "./auth/person.js";
import { IgniClient } from "./client.js";
import { NotAllowed, NotSupported } from "./errors.js";
import { Fleet, Local } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

let fake: FakeIgni;

function fleetClient(): IgniClient {
  return new IgniClient(new Fleet(fake.httpUrl, { auth: new Person("tok") }));
}

async function tick(predicate: () => boolean, tries = 50): Promise<void> {
  for (let i = 0; i < tries && !predicate(); i++) {
    await new Promise((r) => setTimeout(r, 10));
  }
}

describe("Fleet", () => {
  beforeEach(async () => {
    fake = new FakeIgni({ requireBearer: "tok" });
    await fake.start();
  });
  afterEach(() => fake.close());

  it("connects through the gateway with a bearer and reports me()", async () => {
    const igni = await fleetClient().connect();
    const me = await igni.me();
    expect(me.producer).toBe("person:p1");
    expect(me.vm?.state).toBe("running");
    await igni.close();
  });

  it("runs a command over the gateway's NDJSON stream", async () => {
    const igni = await fleetClient().connect();
    const run = await igni.commands.run("echo hi", { producer: "person:p1" });
    const finished = await run.wait();
    expect(run.stdout).toBe("hi\n");
    expect(finished.exit_code).toBe(0);
    expect(finished.ok).toBe(true);
    await igni.close();
  });

  it("re-attaches its sessions after a second welcome (igni moved)", async () => {
    const igni = await fleetClient().connect();
    await igni.sessions.create();
    expect(fake.attachCalls.length).toBe(1);
    fake.move("c-2");
    await tick(() => fake.attachCalls.length >= 2);
    expect(fake.attachCalls.length).toBeGreaterThanOrEqual(2);
    expect(igni.clientId).toBe("c-2");
    await igni.close();
  });

  it("refuses commands on a local target with NotSupported", () => {
    const igni = new IgniClient(new Local({ url: fake.wsUrl }));
    expect(() => igni.commands).toThrow(NotSupported);
  });

  it("maps a gateway refusal of me() to the right error", async () => {
    await fake.close();
    fake = new FakeIgni({ requireBearer: "tok", meStatus: 403 });
    await fake.start();
    const igni = await fleetClient().connect();
    await expect(igni.me()).rejects.toBeInstanceOf(NotAllowed);
    await igni.close();
  });
});

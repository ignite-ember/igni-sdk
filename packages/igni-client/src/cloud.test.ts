import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Person } from "./auth/person.js";
import {
  CloudIgni,
  checkedGateway,
  discover,
  insecureGatewayAllowed,
  setEventsOwner,
} from "./cloud.js";
import { AuthError, GroupIsLocalOnly, NotAllowed, NotSupported } from "./errors.js";
import { Fleet } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

const SCHEMA = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../contracts/cloud-discovery.schema.json", import.meta.url)),
    "utf-8",
  ),
) as { $defs: { CloudDiscovery: { examples: Array<Record<string, unknown>> } } };

const auth = new Person("tok");
let fake: FakeIgni;

describe("CloudIgni.read (lenient, per the contract)", () => {
  it("reads unknown enum values the safe way", () => {
    const c = CloudIgni.read({ cloud: "maybe", mode: "hybrid", events_owner: "both", reason: "new_reason", gateway_url: "https://g" });
    expect(c.cloud).toBe("unavailable");
    expect(c.mode).toBe("local");
    expect(c.eventsOwner).toBe("local");
    expect(c.reason).toBe("new_reason");
  });

  it("keeps fields a newer igni server adds", () => {
    const c = CloudIgni.read({ cloud: "available", mode: "cloud", gateway_url: "https://g", vm_profile: "big" });
    expect(c.extra.vm_profile).toBe("big");
  });

  it("reads each of the schema's own examples and judges availability", () => {
    for (const example of SCHEMA.$defs.CloudDiscovery.examples) {
      const c = CloudIgni.read(example);
      expect(c.available).toBe(example.cloud === "available" && example.mode !== "local" && Boolean(example.gateway_url));
      if (!c.available) {
        expect(c.refusal()).not.toBeNull();
      } else {
        expect(c.refusal()).toBeNull();
      }
    }
  });

  it("turns each unavailable kind into the right error", () => {
    expect(CloudIgni.read({ cloud: "unavailable", reason: "group_local_only", mode: "local" }).refusal()).toBeInstanceOf(GroupIsLocalOnly);
    expect(CloudIgni.read({ cloud: "unavailable", reason: "fleet_not_configured", mode: "local_and_cloud" }).refusal()).toBeInstanceOf(NotSupported);
    expect(CloudIgni.read({ cloud: "unavailable", reason: "inactive", gateway_url: "https://g", mode: "local_and_cloud" }).refusal()).toBeInstanceOf(NotAllowed);
  });
});

describe("discover()", () => {
  beforeEach(async () => {
    fake = new FakeIgni();
    await fake.start();
  });
  afterEach(() => fake.close());

  it("returns the person's cloud igni", async () => {
    const cloud = await discover(fake.httpUrl, auth);
    expect(cloud.available).toBe(true);
    expect(cloud.gatewayUrl).toBe(fake.httpUrl);
    expect(cloud.group?.name).toBe("Eng");
  });

  it("falls back to igni_gateway on a 404 from an older server", async () => {
    fake = new FakeIgni({ cloudStatus: 404 });
    await fake.start();
    const cloud = await discover(fake.httpUrl, auth);
    expect(cloud.available).toBe(true);
    expect(cloud.gatewayUrl).toBe(fake.httpUrl);
  });

  it("is fleet_not_configured on a 404 with no igni_gateway", async () => {
    fake = new FakeIgni({ cloudStatus: 404, noGateway: true });
    await fake.start();
    const cloud = await discover(fake.httpUrl, auth);
    expect(cloud.reason).toBe("fleet_not_configured");
    expect(cloud.refusal()).toBeInstanceOf(NotSupported);
  });

  it("maps 401 to AuthError and 403 to NotAllowed", async () => {
    fake = new FakeIgni({ cloudStatus: 401 });
    await fake.start();
    await expect(discover(fake.httpUrl, auth)).rejects.toBeInstanceOf(AuthError);
    await fake.close();
    fake = new FakeIgni({ cloudStatus: 403 });
    await fake.start();
    await expect(discover(fake.httpUrl, auth)).rejects.toBeInstanceOf(NotAllowed);
  });
});

describe("setEventsOwner()", () => {
  beforeEach(async () => {
    fake = new FakeIgni();
    await fake.start();
  });
  afterEach(() => fake.close());

  it("sets the owner and returns the cloud igni", async () => {
    const cloud = await setEventsOwner(fake.httpUrl, auth, "cloud");
    expect(cloud.available).toBe(true);
  });

  it("refuses an owner the group's mode forbids", async () => {
    fake = new FakeIgni({ modeForbids: true });
    await fake.start();
    await expect(setEventsOwner(fake.httpUrl, auth, "cloud")).rejects.toBeInstanceOf(NotAllowed);
  });

  it("rejects an owner that is neither cloud nor local", async () => {
    await expect(setEventsOwner(fake.httpUrl, auth, "both" as "cloud")).rejects.toThrow(/cloud.*local/);
  });
});

describe("checkedGateway / insecureGatewayAllowed", () => {
  it("passes an https gateway and refuses plain http unless allowed", () => {
    const https = CloudIgni.read({ cloud: "available", mode: "cloud", gateway_url: "https://g" });
    expect(checkedGateway(https, { allowHttp: false })).toBe("https://g");
    const http = CloudIgni.read({ cloud: "available", mode: "cloud", gateway_url: "http://g" });
    expect(() => checkedGateway(http, { allowHttp: false })).toThrow(NotAllowed);
    expect(checkedGateway(http, { allowHttp: true })).toBe("http://g");
  });

  it("raises the cloud's own refusal when it is unavailable", () => {
    const local = CloudIgni.read({ cloud: "unavailable", reason: "group_local_only", mode: "local" });
    expect(() => checkedGateway(local, { allowHttp: true })).toThrow(GroupIsLocalOnly);
  });

  it("honours IGNI_DEV_GATEWAY_INSECURE", () => {
    const before = process.env.IGNI_DEV_GATEWAY_INSECURE;
    process.env.IGNI_DEV_GATEWAY_INSECURE = "1";
    expect(insecureGatewayAllowed()).toBe(true);
    delete process.env.IGNI_DEV_GATEWAY_INSECURE;
    expect(insecureGatewayAllowed()).toBe(false);
    if (before !== undefined) process.env.IGNI_DEV_GATEWAY_INSECURE = before;
  });
});

describe("Fleet.fromServer()", () => {
  beforeEach(async () => {
    fake = new FakeIgni({ requireBearer: "tok" });
    await fake.start();
  });
  afterEach(() => fake.close());

  it("discovers the gateway and connects (http lab gateway allowed)", async () => {
    const fleet = await Fleet.fromServer(fake.httpUrl, { auth, allowHttp: true });
    expect(fleet.discovered?.available).toBe(true);
    expect(fleet.connectUrl).toContain("/v1/connect");
  });

  it("raises GroupIsLocalOnly for a local-only group", async () => {
    fake = new FakeIgni({ cloud: { cloud: "unavailable", reason: "group_local_only", mode: "local", gateway_url: null } });
    await fake.start();
    await expect(Fleet.fromServer(fake.httpUrl, { auth })).rejects.toBeInstanceOf(GroupIsLocalOnly);
  });

  it("raises NotSupported when igni server has no Fleet", async () => {
    fake = new FakeIgni({ cloud: { cloud: "unavailable", reason: "fleet_not_configured", mode: "local_and_cloud", gateway_url: null } });
    await fake.start();
    await expect(Fleet.fromServer(fake.httpUrl, { auth })).rejects.toBeInstanceOf(NotSupported);
  });
});

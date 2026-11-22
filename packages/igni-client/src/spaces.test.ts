import { generateKeyPairSync } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { App } from "./auth/app.js";
import { NotAllowed } from "./errors.js";
import { FakeIgni } from "./testing/fakeIgni.js";

let fake: FakeIgni;

function appSpaces() {
  const pem = generateKeyPairSync("rsa", { modulusLength: 2048 }).privateKey.export({ type: "pkcs8", format: "pem" }).toString();
  const app = new App("app-1", { server: fake.httpUrl, keyPem: pem });
  const jwk = app.publicJwks().keys[0];
  fake.setApp({ n: jwk.n, e: jwk.e, kid: jwk.kid });
  return app.spaces;
}

describe("Spaces", () => {
  beforeEach(async () => {
    fake = new FakeIgni();
    await fake.start();
  });
  afterEach(() => fake.close());

  it("declares, reads, lists and deletes", async () => {
    const spaces = appSpaces();
    const declared = await spaces.declare("u1");
    expect(declared.spaceId).toBe("sp-u1");
    expect(declared.externalId).toBe("u1");
    expect((await spaces.get("u1"))?.spaceId).toBe("sp-u1");
    expect(await spaces.get("missing")).toBeNull();
    expect((await spaces.list()).map((s) => s.space_id)).toEqual(["sp-1"]);
    await expect(spaces.delete("u1")).resolves.toBeUndefined();
    await expect(spaces.delete("missing")).resolves.toBeUndefined(); // a 404 on delete is fine
  });

  it("maps a refused space call to NotAllowed", async () => {
    const spaces = appSpaces();
    await expect(spaces.get("refused")).rejects.toBeInstanceOf(NotAllowed);
    await expect(spaces.declare("refused")).rejects.toBeInstanceOf(NotAllowed);
  });

  it("validates the external id", async () => {
    const spaces = appSpaces();
    await expect(spaces.declare("")).rejects.toThrow(/external id/);
    await expect(spaces.declare("a/b")).rejects.toThrow(/external id/);
    await expect(spaces.declare("x".repeat(201))).rejects.toThrow(/external id/);
    expect(() => spaces.space("")).toThrow(/space id/);
  });

  it("a Space with no record has an empty external id", () => {
    const space = appSpaces().space("sp-9");
    expect(space.spaceId).toBe("sp-9");
    expect(space.externalId).toBe("");
  });
});

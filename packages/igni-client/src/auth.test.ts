import { generateKeyPairSync } from "node:crypto";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { App } from "./auth/app.js";
import { ApiKey, Person } from "./auth/person.js";
import { AuthError } from "./errors.js";
import { IgniClient } from "./client.js";
import { Fleet } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

let fake: FakeIgni;

function pem(): string {
  const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  return privateKey.export({ type: "pkcs8", format: "pem" }).toString();
}

function newApp(keyPem: string, bearer?: string): App {
  const app = new App("app-1", { server: fake.httpUrl, keyPem });
  const jwk = app.publicJwks().keys[0];
  fake.setApp({ n: jwk.n, e: jwk.e, kid: jwk.kid });
  void bearer;
  return app;
}

describe("auth sources", () => {
  beforeEach(async () => {
    fake = new FakeIgni();
    await fake.start();
  });
  afterEach(() => fake.close());

  it("Person holds an explicit token and refuses an empty one", async () => {
    expect(await new Person("the-token").token()).toBe("the-token");
    expect(() => new Person("  ")).toThrow(AuthError);
  });

  it("Person.fromCli reads the stored session", () => {
    const dir = mkdtempSync(join(tmpdir(), "igni-"));
    const file = join(dir, "credentials.json");
    writeFileSync(file, JSON.stringify({ access_token: "stored-token" }));
    expect(Person.fromCli(file)).toBeInstanceOf(Person);
  });

  it("ApiKey exchanges an igpak1. key for a short session", async () => {
    const key = new ApiKey("igpak1.secret", { server: fake.httpUrl });
    const token = await key.token();
    expect(token).toBe("tok-urn:igni:params:oauth:grant-type:api-key");
    expect(fake.tokenForms[0].grant_type).toBe("urn:igni:params:oauth:grant-type:api-key");
    expect(() => new ApiKey("nope", { server: fake.httpUrl })).toThrow(AuthError);
  });

  it("App signs a private_key_jwt the server accepts (no silent 401)", async () => {
    const app = newApp(pem());
    const token = await app.token();
    expect(token).toBe("tok-client_credentials");
    expect(fake.tokenForms[0].grant_type).toBe("client_credentials");
  });

  it("Space exchanges the app token for the space's", async () => {
    const app = newApp(pem());
    const space = app.spaces.space("sp-1");
    const token = await space.token();
    expect(token).toBe("tok-urn:ietf:params:oauth:grant-type:token-exchange");
  });

  it("App auth drives a Fleet connection", async () => {
    await fake.close();
    fake = new FakeIgni({ requireBearer: "tok-client_credentials" });
    await fake.start();
    const app = newApp(pem());
    const igni = await new IgniClient(new Fleet(fake.httpUrl, { auth: app })).connect();
    expect(igni.clientId).toBe("c-1");
    await igni.close();
  });

  it("Spaces declare, read, list and delete an app's spaces", async () => {
    const spaces = newApp(pem()).spaces;
    const declared = await spaces.declare("u1");
    expect(declared.spaceId).toBe("sp-u1");
    expect(declared.externalId).toBe("u1");
    expect((await spaces.get("u1"))?.spaceId).toBe("sp-u1");
    expect(await spaces.get("missing")).toBeNull();
    expect(await spaces.list()).toHaveLength(1);
    await expect(spaces.delete("u1")).resolves.toBeUndefined();
    expect(() => spaces.space("")).toThrow(/space id/);
    await expect(spaces.declare("a/b")).rejects.toThrow(/external id/);
  });
});

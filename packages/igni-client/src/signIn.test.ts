import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Person } from "./auth/person.js";
import { IgniClient } from "./client.js";
import { GroupIsLocalOnly, NotSupported } from "./errors.js";
import { signIn, SignedIn } from "./signIn.js";
import { Fleet, Local } from "./targets.js";
import { FakeIgni } from "./testing/fakeIgni.js";

let fake: FakeIgni;
const fleet = () => new Fleet(fake.httpUrl, { auth: new Person("tok") });

describe("signIn", () => {
  beforeEach(async () => {
    fake = new FakeIgni({ requireBearer: "tok" });
    await fake.start();
  });
  afterEach(() => fake.close());

  it("signs the person in and reports the credential is ready", async () => {
    const result = await signIn(fleet());
    expect(result).toBeInstanceOf(SignedIn);
    expect(result.producer).toBe("person:p1");
    expect(result.ready).toBe(true);
  });

  it("is reachable from the client and is not ready for a needs_sign_in credential", async () => {
    fake = new FakeIgni({ requireBearer: "tok", signedIn: { producer: "person:p1", credential: { state: "needs_sign_in" } } });
    await fake.start();
    const igni = await new IgniClient(fleet()).connect();
    const result = await igni.signIn();
    expect(result.ready).toBe(false);
    expect(result.credential?.state).toBe("needs_sign_in");
    await igni.close();
  });

  it("maps a gateway refusal to GroupIsLocalOnly", async () => {
    fake = new FakeIgni({ requireBearer: "tok", signInStatus: 403 });
    await fake.start();
    await expect(signIn(fleet())).rejects.toBeInstanceOf(GroupIsLocalOnly);
  });

  it("is NotSupported on a local target", async () => {
    const igni = new IgniClient(new Local({ url: fake.wsUrl }));
    await expect(igni.signIn()).rejects.toBeInstanceOf(NotSupported);
  });
});

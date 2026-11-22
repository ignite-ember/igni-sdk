// @ignite-ember/igni-client/testing — test a program that drives igni without a real igni.
//
// `FakeIgni` is a loopback backend that speaks igni's wire on a real socket, and
// stands in for Fleet's gateway (/v1/connect, /v1/me, /v1/commands) and igni
// server's token endpoints too. Point a `Local` or `Fleet` target at it and the
// client runs against the real protocol, not a mock.
//
//   import { FakeIgni } from "@ignite-ember/igni-client/testing";
//   const fake = new FakeIgni({ run: { chunks: ["hi"] } });
//   await fake.start();
//   const igni = await new IgniClient(new Local({ url: fake.wsUrl })).connect();
//   // ...drive it...
//   await igni.close();
//   await fake.close();

export { FakeIgni } from "./fakeIgni.js";
export type { FakeOptions, RunScript } from "./fakeIgni.js";

/** A sample message of a given wire `type`, with its envelope filled in. */
export function sample(type: string, fields: Record<string, unknown> = {}): Record<string, unknown> {
  return { type, id: "", session_id: "", event_seq: 0, ...fields };
}

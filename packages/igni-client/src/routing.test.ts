import { describe, expect, it } from "vitest";

import { RunInterrupted } from "./errors.js";
import { parseEvent } from "./events.js";
import { AsyncQueue } from "./asyncQueue.js";
import { Interruption, Router } from "./routing.js";
import type { StreamItem } from "./routing.js";

async function drain<T>(queue: AsyncQueue<T>): Promise<T[]> {
  const out: T[] = [];
  while (!queue.empty) {
    out.push(await queue.get());
  }
  return out;
}

describe("Router", () => {
  it("makes a request id from a prefix, its own tag and a count", () => {
    const router = new Router();
    const first = router.newId("run");
    const second = router.newId("hitl");
    const m = /^run-([0-9a-f]{8})-1$/.exec(first);
    expect(m).not.toBeNull();
    expect(second).toBe(`hitl-${m![1]}-2`);
    expect(new Router().newId("run")).not.toBe(first);
  });

  it("answers a message-reply call with a message, not an rpc_response or an echoed request", () => {
    const router = new Router();
    const answer = router.expect("req-1", "message");
    const stream = router.openStream("req-1");
    router.deliver(parseEvent({ type: "rpc_response", id: "req-1", result: 1 }));
    expect(answer.done).toBe(false);
    router.deliver(parseEvent({ type: "rpc_request", id: "req-1", method: "echoed" }));
    expect(answer.done).toBe(false);
    router.deliver(parseEvent({ type: "info", id: "req-1", text: "done" }));
    expect(answer.done).toBe(true);
    return drain(stream).then((items) => {
      expect((items as { type: string }[]).map((e) => e.type)).toEqual(["rpc_response", "rpc_request"]);
    });
  });

  it("answers an rpc_response call with the response or an error", async () => {
    const router = new Router();
    const refused = router.expect("req-1");
    const streamed = router.openStream("req-1");
    router.deliver(parseEvent({ type: "info", id: "req-1", text: "streamed" }));
    expect(refused.done).toBe(false);
    router.deliver(parseEvent({ type: "error", id: "req-1", text: "refused" }));
    expect((await refused.promise).type).toBe("error");
    expect((await drain(streamed)).map((e) => (e as { type: string }).type)).toEqual(["info"]);
  });

  it("lets a forgotten call's id go to its stream", async () => {
    const router = new Router();
    router.expect("req-1", "message");
    const stream = router.openStream("req-1");
    router.forget("req-1");
    router.deliver(parseEvent({ type: "info", id: "req-1", text: "later" }));
    expect((await drain(stream)).map((e) => (e as { type: string }).type)).toEqual(["info"]);
  });

  it("a follower hears everything and the interruption until it unfollows", async () => {
    const router = new Router();
    const follower = router.follow();
    const listener = router.listen();
    router.deliver(parseEvent({ type: "info", text: "no id" }));
    router.deliver(parseEvent({ type: "info", id: "nobody-waits", text: "x" }));
    const moved = new RunInterrupted("igni moved");
    router.interrupt(moved);
    const heard = await drain(follower);
    expect((heard.slice(0, 2) as { text?: string }[]).map((i) => i.text)).toEqual(["no id", "x"]);
    expect(heard[2]).toBeInstanceOf(Interruption);
    expect((heard[2] as Interruption).error).toBe(moved);
    expect((await drain(listener)).length).toBe(2); // a listener never hears an interruption
    router.unfollow(follower);
    router.unfollow(follower); // twice, or a queue never followed, is silent
    router.deliver(parseEvent({ type: "info", text: "after" }));
    router.interrupt(moved);
    expect(follower.empty).toBe(true);
  });

  it("drops a message with no waiter and no stream (listeners still hear it)", async () => {
    const router = new Router();
    const listener = router.listen();
    router.deliver(parseEvent({ type: "info", id: "nobody", text: "x" }));
    expect((await drain(listener)).length).toBe(1);
  });

  it("leaves a call already answered as it was when interrupted", async () => {
    const router = new Router();
    const answered = router.expect("req-1");
    router.deliver(parseEvent({ type: "rpc_response", id: "req-1", result: 1 }));
    router.interrupt(new RunInterrupted("igni moved"));
    expect((await answered.promise).type).toBe("rpc_response");
  });

  it("remembers the latest requests it sent, answered or not", () => {
    const router = new Router();
    expect(router.asked("req-1")).toBe(false);
    router.expect("req-1");
    router.forget("req-1");
    expect(router.asked("req-1")).toBe(true);
    for (let n = 0; n < Router.ASKED_KEPT; n++) {
      router.expect(`later-${n}`);
    }
    expect(router.asked("req-1")).toBe(false);
    expect(router.asked("later-0")).toBe(true);
    expect(router.asked(`later-${Router.ASKED_KEPT - 1}`)).toBe(true);
  });

  it("delivers a stream item union of events and interruptions", () => {
    const item: StreamItem = new Interruption(new RunInterrupted("x"));
    expect(item).toBeInstanceOf(Interruption);
  });
});

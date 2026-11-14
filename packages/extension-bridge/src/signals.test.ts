/**
 * `SignalSubscriptions`: who handles which host signal, and when the
 * host is asked to start or stop sending it.
 *
 * The request here is a stub the test settles by hand; through the
 * bridge, host.test.ts drives the same thing over the wire.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HostError, Signal } from "./hostModel.js";
import { BRIDGE_VERSION, type HostSignalMessage } from "./protocol.js";
import { SignalSubscriptions } from "./signals.js";

function stubHost() {
  const asked: {
    op: string;
    signal: string;
    refuse: (error: HostError) => void;
  }[] = [];
  const subscriptions = new SignalSubscriptions(
    (op, signal) =>
      new Promise((_resolve, reject) => {
        asked.push({ op, signal, refuse: reject });
      }),
  );
  return { asked, subscriptions };
}

function signal(name: string, value: unknown): HostSignalMessage {
  return { igni: BRIDGE_VERSION, kind: "signal", signal: name, value };
}

const completed = new Signal<{ run: string }>("chat.run_completed");
const switched = new Signal<{ session_id: string }>("session.switched");

let warn: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  warn.mockRestore();
});

describe("SignalSubscriptions", () => {
  it("asks the host once per signal, whoever handles it", () => {
    const { asked, subscriptions } = stubHost();

    subscriptions.on(completed, () => {});
    subscriptions.on(completed, () => {});
    subscriptions.on(switched, () => {});

    expect(asked.map(({ op, signal }) => [op, signal])).toEqual([
      ["subscribe", "chat.run_completed"],
      ["subscribe", "session.switched"],
    ]);
  });

  it("hands a signal only to its own handlers, and drops one nobody handles", () => {
    const { subscriptions } = stubHost();
    const seen: unknown[] = [];
    subscriptions.on(completed, (value) => seen.push(value));

    subscriptions.deliver(signal("session.switched", { session_id: "s" }));
    subscriptions.deliver(signal("tasks.changed", {}));
    subscriptions.deliver(signal("chat.run_completed", { run: "r1" }));

    expect(seen).toEqual([{ run: "r1" }]);
  });

  it("does not tell onRefused about a refused unsubscribe, only the console", async () => {
    const { asked, subscriptions } = stubHost();
    const refused: HostError[] = [];
    const off = subscriptions.on(completed, () => {}, (error) =>
      refused.push(error),
    );

    off();
    asked[1].refuse(new HostError("failed", "the window closed"));

    await vi.waitFor(() => expect(warn).toHaveBeenCalledTimes(1));
    expect(warn).toHaveBeenCalledWith(
      "igni bridge: unsubscribing from chat.run_completed failed: the window closed",
    );
    expect(refused).toEqual([]);
  });

  it("still reports a refused subscribe whose handler has already gone", async () => {
    const { asked, subscriptions } = stubHost();
    const refused: string[] = [];
    const off = subscriptions.on(completed, () => {}, (error) =>
      refused.push(error.message),
    );

    off();
    asked[0].refuse(new HostError("not_granted", "chat is not granted"));

    await vi.waitFor(() => expect(refused).toEqual(["chat is not granted"]));
  });

  it("says a refused subscribe on the console in its own words", async () => {
    const { asked, subscriptions } = stubHost();
    subscriptions.on(completed, () => {});

    asked[0].refuse(new HostError("not_granted", "chat is not granted"));

    await vi.waitFor(() => expect(warn).toHaveBeenCalledTimes(1));
    expect(warn).toHaveBeenCalledWith(
      "igni bridge: subscribing to chat.run_completed failed: chat is not granted",
    );
  });

  it("asks nothing more when an unsubscribe for a signal already let go is called", () => {
    const { asked, subscriptions } = stubHost();
    const offFirst = subscriptions.on(completed, () => {});
    const offSecond = subscriptions.on(completed, () => {});

    offFirst();
    offFirst();
    expect(asked.map(({ op }) => op)).toEqual(["subscribe"]);
    offSecond();
    offSecond();
    expect(asked.map(({ op }) => op)).toEqual(["subscribe", "unsubscribe"]);
  });
});

describe("SignalSubscriptions through a handler's whole life", () => {
  it("asks the host again when a signal is handled anew after its last handler left", () => {
    const { asked, subscriptions } = stubHost();
    const off = subscriptions.on(completed, () => {});
    off();
    subscriptions.on(completed, () => {});

    expect(asked.map(({ op }) => op)).toEqual(["subscribe", "unsubscribe", "subscribe"]);
  });

  it("holds the same function once: one off lets it go and unsubscribes", () => {
    const { asked, subscriptions } = stubHost();
    const seen: unknown[] = [];
    const fn = (value: { run: string }) => seen.push(value);
    const offFirst = subscriptions.on(completed, fn);
    subscriptions.on(completed, fn);

    subscriptions.deliver(signal("chat.run_completed", { run: "r1" }));
    expect(seen).toEqual([{ run: "r1" }]);

    offFirst();
    expect(asked.map(({ op }) => op)).toEqual(["subscribe", "unsubscribe"]);
    subscriptions.deliver(signal("chat.run_completed", { run: "r2" }));
    expect(seen).toEqual([{ run: "r1" }]);
  });

  it("stops at a handler that throws, and tells the ones before it", () => {
    const { subscriptions } = stubHost();
    const seen: string[] = [];
    subscriptions.on(completed, () => seen.push("first"));
    subscriptions.on(completed, () => {
      throw new Error("broken handler");
    });
    subscriptions.on(completed, () => seen.push("third"));

    expect(() =>
      subscriptions.deliver(signal("chat.run_completed", { run: "r" })),
    ).toThrow("broken handler");
    expect(seen).toEqual(["first"]);
  });

  it("does not tell a handler that left while an earlier one was being told", () => {
    const { subscriptions } = stubHost();
    const seen: string[] = [];
    let offSecond = () => {};
    subscriptions.on(completed, () => {
      seen.push("first");
      offSecond();
    });
    offSecond = subscriptions.on(completed, () => seen.push("second"));

    subscriptions.deliver(signal("chat.run_completed", { run: "r" }));

    expect(seen).toEqual(["first"]);
  });

  it("gives onRefused the host's own error, and keeps the console quiet", async () => {
    const { asked, subscriptions } = stubHost();
    const refused: HostError[] = [];
    subscriptions.on(completed, () => {}, (error) => refused.push(error));
    const error = new HostError("not_granted", "chat is not granted");

    asked[0].refuse(error);

    await vi.waitFor(() => expect(refused).toEqual([error]));
    expect(warn).not.toHaveBeenCalled();
  });
});

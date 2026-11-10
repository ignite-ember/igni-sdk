/**
 * `Correlator`: one kind of request the guest is waiting on, matched to
 * its reply by id.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Correlator } from "./correlator.js";

function counter() {
  let n = 0;
  return () => ++n;
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

const timedOut = () => new Error("timed out");

describe("Correlator", () => {
  it("numbers its ids from the counter it was given, after its prefix", () => {
    const next = counter();
    const calls = new Correlator("", next);
    const hosts = new Correlator("h", next);
    const ids: string[] = [];

    void calls.send(null, timedOut, (id) => ids.push(id));
    void hosts.send(null, timedOut, (id) => ids.push(id));
    void calls.send(null, timedOut, (id) => ids.push(id));

    expect(ids).toEqual(["1", "h2", "3"]);
  });

  it("settles a request with its own reply, and only once", async () => {
    const correlator = new Correlator("", counter());
    let id = "";
    const sent = correlator.send<string>(1000, timedOut, (given) => {
      id = given;
    });

    correlator.resolve(id, "first");
    correlator.resolve(id, "second");
    correlator.reject(id, new Error("too late"));

    await expect(sent).resolves.toBe("first");
  });

  it("rejects with the error the reply carried", async () => {
    const correlator = new Correlator("", counter());
    let id = "";
    const sent = correlator.send(1000, timedOut, (given) => {
      id = given;
    });

    correlator.reject(id, new TypeError("refused"));

    await expect(sent).rejects.toThrow(new TypeError("refused"));
  });

  it("gives up after its time with the error it was told to give, and ignores a late reply", async () => {
    const correlator = new Correlator("", counter());
    let id = "";
    const sent = correlator.send(50, () => new Error("gave up"), (given) => {
      id = given;
    });
    const outcome = sent.catch((error: unknown) => error);

    vi.advanceTimersByTime(50);
    expect(await outcome).toEqual(new Error("gave up"));
    expect(() => correlator.resolve(id, "late")).not.toThrow();
  });

  it("waits for as long as the reply takes when given no time", async () => {
    const correlator = new Correlator("", counter());
    let id = "";
    const sent = correlator.send<string>(null, timedOut, (given) => {
      id = given;
    });

    vi.advanceTimersByTime(24 * 60 * 60_000);
    correlator.resolve(id, "answered");
    correlator.resolve(id, "again");

    await expect(sent).resolves.toBe("answered");
  });

  it("ignores a reply nobody is waiting on, including another correlator's id", async () => {
    const next = counter();
    const calls = new Correlator("", next);
    const hosts = new Correlator("h", next);
    let hostId = "";
    const host = hosts.send<string>(1000, timedOut, (given) => {
      hostId = given;
    });

    calls.resolve(hostId, "wrong kind");
    calls.resolve("999", "noise");
    hosts.resolve(hostId, "right kind");

    await expect(host).resolves.toBe("right kind");
  });

  it("posts the request only once it is waiting, so an immediate reply lands", async () => {
    const correlator = new Correlator("", counter());
    const sent = correlator.send<string>(1000, timedOut, (id) =>
      correlator.resolve(id, "at once"),
    );

    await expect(sent).resolves.toBe("at once");
  });
});

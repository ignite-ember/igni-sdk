import { describe, expect, it, vi } from "vitest";

import type { Bridge } from "@ignite-ember/extension-bridge";

import { messageOf, ScannerClient, SEVERITIES, WireError } from "./scanner";

/** A bridge whose `rpc` answers with what the test hands it. */
function bridge(answer: unknown) {
  const rpc = vi.fn(async () => {
    if (answer instanceof Error) throw answer;
    return answer;
  });
  return { rpc, client: new ScannerClient({ rpc } as unknown as Bridge) };
}

const row = (over: Record<string, unknown> = {}) => ({
  id: "v1",
  rule: "no-secrets",
  severity: "high",
  path: "a.py",
  line: 3,
  ...over,
});

async function refusal(promise: Promise<unknown>): Promise<WireError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(WireError);
    return error as WireError;
  }
  throw new Error("expected a WireError");
}

describe("SEVERITIES", () => {
  it("is worst first", () => {
    expect([...SEVERITIES]).toEqual(["critical", "high", "medium", "low"]);
  });
});

describe("WireError", () => {
  it("names the method and the detail", () => {
    const error = new WireError("ext.x.y", "nope");
    expect(error.message).toBe("ext.x.y returned something unexpected: nope");
    expect(error.name).toBe("WireError");
    expect(error.method).toBe("ext.x.y");
    expect(error).toBeInstanceOf(Error);
  });
});

describe("ScannerClient.violations", () => {
  it("calls the list method and returns an empty list as is", async () => {
    const { rpc, client } = bridge([]);
    expect(await client.violations()).toEqual([]);
    expect(rpc).toHaveBeenCalledWith("ext.acme.scanner.list", undefined);
  });

  it("sorts by severity rank, then path, then line", async () => {
    const { client } = bridge([
      row({ id: "a", severity: "low", path: "a" }),
      row({ id: "b", severity: "critical", path: "z" }),
      row({ id: "c", severity: "high", path: "b", line: 9 }),
      row({ id: "d", severity: "high", path: "b", line: 2 }),
      row({ id: "e", severity: "high", path: "a", line: 50 }),
      row({ id: "f", severity: "medium", path: "a" }),
    ]);
    expect((await client.violations()).map((v) => v.id)).toEqual([
      "b",
      "e",
      "d",
      "c",
      "f",
      "a",
    ]);
  });

  it("orders paths with localeCompare and keeps equal rows in order", async () => {
    const { client } = bridge([
      row({ id: "1", path: "é" }),
      row({ id: "2", path: "e" }),
      row({ id: "3", path: "f" }),
      row({ id: "4", path: "f" }),
    ]);
    expect((await client.violations()).map((v) => v.id)).toEqual([
      "2",
      "1",
      "3",
      "4",
    ]);
  });

  it("drops fields it does not know and accepts any finite line", async () => {
    const { client } = bridge([row({ line: -4, extra: "x" }), row({ id: "z", line: 0 })]);
    const result = await client.violations();
    expect(result[0]).toEqual({
      id: "v1",
      rule: "no-secrets",
      severity: "high",
      path: "a.py",
      line: -4,
    });
    expect(result[1].line).toBe(0);
  });

  it.each([null, {}, "list", 3, undefined])("refuses %j as not an array", async (raw) => {
    const error = await refusal(bridge(raw).client.violations());
    expect(error.method).toBe("ext.acme.scanner.list");
    expect(error.message).toBe(
      "ext.acme.scanner.list returned something unexpected: not an array",
    );
  });

  it.each([null, [], "x", 4])("refuses a row that is %j, naming its index", async (bad) => {
    const error = await refusal(bridge([row(), bad]).client.violations());
    expect(error.message).toContain("[1] is not an object");
  });

  it.each(["id", "rule", "path", "severity"])("refuses a row with no %s", async (key) => {
    const bad = row();
    delete (bad as Record<string, unknown>)[key];
    const error = await refusal(bridge([bad]).client.violations());
    expect(error.message).toContain(`${key} should be a string, got undefined`);
  });

  it("refuses a field of the wrong type, naming the type", async () => {
    const error = await refusal(bridge([row({ rule: 7 })]).client.violations());
    expect(error.message).toContain("rule should be a string, got number");
  });

  it.each(["urgent", "HIGH", "", "High"])(
    "refuses the severity %j by name instead of filing it as low",
    async (severity) => {
      const error = await refusal(bridge([row({ severity })]).client.violations());
      expect(error.message).toContain(
        `[0] has severity ${JSON.stringify(severity)}, which this version does not know about`,
      );
    },
  );

  it("refuses a severity that is not a string", async () => {
    const error = await refusal(bridge([row({ severity: 1 })]).client.violations());
    expect(error.message).toContain("severity should be a string, got number");
  });

  it.each([Number.NaN, Infinity, -Infinity, "3", null, undefined])(
    "refuses the line %j",
    async (line) => {
      const error = await refusal(bridge([row(), row({ line })]).client.violations());
      expect(error.message).toContain("[1] has a line that is not a number");
    },
  );

  it("lets an rpc rejection through unchanged", async () => {
    const denied = new Error("extension acme.scanner may not call list");
    await expect(bridge(denied).client.violations()).rejects.toBe(denied);
  });
});

describe("ScannerClient.status", () => {
  it("calls the status method", async () => {
    const { rpc, client } = bridge({ state: "idle", lastFinished: "t" });
    await client.status();
    expect(rpc).toHaveBeenCalledWith("ext.acme.scanner.status", undefined);
  });

  it("reads idle, with lastFinished null unless it is a string", async () => {
    expect(await bridge({ state: "idle", lastFinished: "2026-01-01" }).client.status()).toEqual({
      state: "idle",
      lastFinished: "2026-01-01",
    });
    for (const last of [undefined, null, 5]) {
      expect(await bridge({ state: "idle", lastFinished: last }).client.status()).toEqual({
        state: "idle",
        lastFinished: null,
      });
    }
  });

  it("reads running, keeping a percent in range", async () => {
    expect(
      await bridge({ state: "running", step: "parsing", percent: 40 }).client.status(),
    ).toEqual({ state: "running", step: "parsing", percent: 40 });
    expect(await bridge({ state: "running", step: "s", percent: 0 }).client.status()).toMatchObject({
      percent: 0,
    });
  });

  it.each([
    [-5, 0],
    [250, 100],
    [100, 100],
    [Number.NaN, null],
    [Infinity, null],
    ["50", null],
    [undefined, null],
    [null, null],
  ])("turns a running percent of %j into %j", async (percent, expected) => {
    const status = await bridge({ state: "running", step: "s", percent }).client.status();
    expect(status).toEqual({ state: "running", step: "s", percent: expected });
  });

  it("refuses a running scan with no step", async () => {
    const error = await refusal(bridge({ state: "running", percent: 1 }).client.status());
    expect(error.method).toBe("ext.acme.scanner.status");
    expect(error.message).toContain("step should be a string, got undefined");
  });

  it("reads failed, and refuses one with no message", async () => {
    expect(await bridge({ state: "failed", message: "boom" }).client.status()).toEqual({
      state: "failed",
      message: "boom",
    });
    const error = await refusal(bridge({ state: "failed" }).client.status());
    expect(error.message).toContain("message should be a string, got undefined");
  });

  it("refuses an unknown state and a non-object", async () => {
    const unknown = await refusal(bridge({ state: "paused" }).client.status());
    expect(unknown.message).toContain('state "paused" is not a state');
    for (const raw of [null, [], "idle"]) {
      const error = await refusal(bridge(raw).client.status());
      expect(error.message).toContain("status is not an object");
    }
  });

  it("lets an rpc rejection through unchanged", async () => {
    const timeout = new Error("timed out");
    await expect(bridge(timeout).client.status()).rejects.toBe(timeout);
  });
});

describe("ScannerClient.startScan and accept", () => {
  it("startScan calls scan with no arguments and resolves to nothing", async () => {
    const { rpc, client } = bridge({ ignored: true });
    expect(await client.startScan()).toBeUndefined();
    expect(rpc).toHaveBeenCalledTimes(1);
    expect(rpc.mock.calls[0]).toEqual(["ext.acme.scanner.scan"]);
  });

  it("accept sends the id and the justification", async () => {
    const { rpc, client } = bridge(null);
    expect(await client.accept("v9", "  because  ")).toBeUndefined();
    expect(rpc).toHaveBeenCalledWith("ext.acme.scanner.accept", {
      id: "v9",
      justification: "  because  ",
    });
  });

  it("let a rejection propagate unchanged", async () => {
    const refused = new Error("refused");
    await expect(bridge(refused).client.startScan()).rejects.toBe(refused);
    await expect(bridge(refused).client.accept("a", "b")).rejects.toBe(refused);
  });
});

describe("messageOf", () => {
  it("returns an Error's message as is and stringifies anything else", () => {
    expect(messageOf(new Error("denied"))).toBe("denied");
    expect(messageOf("text")).toBe("text");
    expect(messageOf(null)).toBe("null");
    expect(messageOf(undefined)).toBe("undefined");
    expect(messageOf({})).toBe("[object Object]");
    expect(messageOf(42)).toBe("42");
  });
});

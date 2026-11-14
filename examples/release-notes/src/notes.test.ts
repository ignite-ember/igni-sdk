/**
 * The Release Notes client: what it sends and what it refuses to
 * read. The panel renders whatever this hands back, so a wire shape
 * that slips through here becomes a blank row or a crash there.
 */
import { describe, expect, it, vi } from "vitest";

import type { Bridge } from "@ignite-ember/extension-bridge";

import {
  ConflictError,
  messageOf,
  NotesClient,
  STATES,
  WireError,
} from "./notes";

function clientAnswering(answer: unknown) {
  const rpc = vi.fn(async (_method: string, _args?: Record<string, unknown>) => answer);
  return { client: new NotesClient({ rpc } as unknown as Bridge), rpc };
}

function clientRejecting(error: unknown) {
  const rpc = vi.fn(async () => {
    throw error;
  });
  return new NotesClient({ rpc } as unknown as Bridge);
}

const release = { version: "2.4.0", state: "draft", publishedAt: null };
const note = { version: "2.4.0", body: "# 2.4.0", revision: "r1" };
const comment = { id: "c1", version: "2.4.0", author: "Maya", body: "Nice", resolved: true };

describe("STATES", () => {
  it("lists the three states a release can be in", () => {
    expect([...STATES]).toEqual(["draft", "published", "superseded"]);
  });
});

describe("releases", () => {
  it("calls ext.acme.notes.releases with no arguments and keeps the server's order", async () => {
    const rows = [
      { version: "2.3.1", state: "published", publishedAt: "2026-10-20T09:00:00Z" },
      release,
      { version: "1.0.0", state: "superseded", publishedAt: "2025-01-01T00:00:00Z" },
    ];
    const { client, rpc } = clientAnswering(rows);
    expect(await client.releases()).toEqual(rows);
    expect(rpc).toHaveBeenCalledWith("ext.acme.notes.releases", undefined);
  });

  it("answers an empty list when there are no releases", async () => {
    expect(await clientAnswering([]).client.releases()).toEqual([]);
  });

  it.each([undefined, null, {}, "x", 3])("refuses %j, which is not an array", async (answer) => {
    const error = await clientAnswering(answer).client.releases().catch((e) => e);
    expect(error).toBeInstanceOf(WireError);
    expect(error.method).toBe("ext.acme.notes.releases");
    expect(error.message).toBe(
      "ext.acme.notes.releases returned something unexpected: not an array",
    );
  });

  it("reads publishedAt as null when it is missing, null or not a string", async () => {
    const rows = [
      { version: "a", state: "draft" },
      { version: "b", state: "draft", publishedAt: null },
      { version: "c", state: "draft", publishedAt: 5 },
      { version: "d", state: "published", publishedAt: "2026-01-01T00:00:00Z" },
    ];
    const got = await clientAnswering(rows).client.releases();
    expect(got.map((r) => r.publishedAt)).toEqual([null, null, null, "2026-01-01T00:00:00Z"]);
  });

  it("names the index and the state of a release it does not know", async () => {
    const rows = [release, { version: "9", state: "archived", publishedAt: null }];
    const error = await clientAnswering(rows).client.releases().catch((e) => e);
    expect(error).toBeInstanceOf(WireError);
    expect(error.message).toContain('[1] has state "archived"');
  });

  it.each([null, [], 7, "x"])("refuses a row that is %j", async (row) => {
    const error = await clientAnswering([row]).client.releases().catch((e) => e);
    expect(error).toBeInstanceOf(WireError);
    expect(error.message).toContain("[0] is not an object");
  });

  it("names the key and the type of a missing or non-string field", async () => {
    const noVersion = await clientAnswering([{ state: "draft" }]).client.releases().catch((e) => e);
    expect(noVersion.message).toContain("version should be a string, got undefined");
    const numeric = await clientAnswering([{ version: 1, state: "draft" }])
      .client.releases()
      .catch((e) => e);
    expect(numeric.message).toContain("version should be a string, got number");
    const noState = await clientAnswering([{ version: "1" }]).client.releases().catch((e) => e);
    expect(noState.message).toContain("state should be a string, got undefined");
  });
});

describe("note", () => {
  it("sends the version and returns version, body and revision", async () => {
    const { client, rpc } = clientAnswering({ ...note, extra: "ignored" });
    expect(await client.note("2.4.0")).toEqual(note);
    expect(rpc).toHaveBeenCalledWith("ext.acme.notes.note", { version: "2.4.0" });
  });

  it("passes unicode and a very large body through untouched", async () => {
    const body = "héllo 🚀 ".repeat(50_000);
    const got = await clientAnswering({ ...note, body }).client.note("2.4.0");
    expect(got.body).toBe(body);
  });

  it.each([null, [], "x"])("refuses an answer that is %j", async (answer) => {
    const error = await clientAnswering(answer).client.note("v").catch((e) => e);
    expect(error).toBeInstanceOf(WireError);
    expect(error.message).toBe(
      "ext.acme.notes.note returned something unexpected: note is not an object",
    );
  });

  it.each(["version", "body", "revision"])("refuses a note without %s", async (key) => {
    const broken: Record<string, unknown> = { ...note };
    delete broken[key];
    const error = await clientAnswering(broken).client.note("v").catch((e) => e);
    expect(error).toBeInstanceOf(WireError);
    expect(error.message).toContain(`${key} should be a string, got undefined`);
  });
});

describe("comments", () => {
  it("sends the version and maps every field", async () => {
    const { client, rpc } = clientAnswering([comment]);
    expect(await client.comments("2.4.0")).toEqual([comment]);
    expect(rpc).toHaveBeenCalledWith("ext.acme.notes.comments", { version: "2.4.0" });
  });

  it("answers an empty list when nobody has commented", async () => {
    expect(await clientAnswering([]).client.comments("v")).toEqual([]);
  });

  it("treats resolved as true only when it is exactly true", async () => {
    const rows = [
      { ...comment, id: "1", resolved: true },
      { ...comment, id: "2", resolved: false },
      { ...comment, id: "3", resolved: "true" },
      { ...comment, id: "4", resolved: 1 },
      { ...comment, id: "5", resolved: undefined },
    ];
    const got = await clientAnswering(rows).client.comments("v");
    expect(got.map((c) => c.resolved)).toEqual([true, false, false, false, false]);
  });

  it.each(["id", "version", "author", "body"])("refuses a comment without %s", async (key) => {
    const broken: Record<string, unknown> = { ...comment };
    delete broken[key];
    const error = await clientAnswering([broken]).client.comments("v").catch((e) => e);
    expect(error).toBeInstanceOf(WireError);
    expect(error.message).toContain(`${key} should be a string, got undefined`);
  });

  it.each([null, {}, "x"])("refuses %j, which is not an array", async (answer) => {
    const error = await clientAnswering(answer).client.comments("v").catch((e) => e);
    expect(error).toBeInstanceOf(WireError);
    expect(error.method).toBe("ext.acme.notes.comments");
  });

  it("refuses a comment that is not an object", async () => {
    const error = await clientAnswering([null]).client.comments("v").catch((e) => e);
    expect(error.message).toContain("[0] is not an object");
  });
});

describe("save", () => {
  it("sends version, body and revision and returns the note with its new revision", async () => {
    const saved = { version: "2.4.0", body: "new", revision: "r2" };
    const { client, rpc } = clientAnswering(saved);
    expect(await client.save("2.4.0", "new", "r1")).toEqual(saved);
    expect(rpc).toHaveBeenCalledWith("ext.acme.notes.save", {
      version: "2.4.0",
      body: "new",
      revision: "r1",
    });
  });

  it("sends an empty body as it is", async () => {
    const { client, rpc } = clientAnswering({ ...note, body: "" });
    await client.save("2.4.0", "", "r1");
    expect(rpc.mock.calls[0]?.[1]).toMatchObject({ body: "" });
  });

  it("throws ConflictError carrying their revision when the server answers a conflict", async () => {
    const error = await clientAnswering({ conflict: "r7" })
      .client.save("v", "b", "r1")
      .catch((e) => e);
    expect(error).toBeInstanceOf(ConflictError);
    expect(error).toBeInstanceOf(Error);
    expect(error.theirRevision).toBe("r7");
    expect(error.name).toBe("ConflictError");
    expect(error.message).toContain("Somebody else saved this note");
  });

  it("does not take a non-string conflict for one", async () => {
    const error = await clientAnswering({ conflict: 123 }).client.save("v", "b", "r1").catch((e) => e);
    expect(error).toBeInstanceOf(WireError);
    expect(error.method).toBe("ext.acme.notes.save");
  });

  it.each([null, "ok", [], { version: "v" }])("refuses the answer %j as a WireError", async (answer) => {
    const error = await clientAnswering(answer).client.save("v", "b", "r1").catch((e) => e);
    expect(error).toBeInstanceOf(WireError);
    expect(error.name).toBe("WireError");
    expect(error.message).toMatch(/^ext\.acme\.notes\.save returned something unexpected: /);
  });
});

describe("publish", () => {
  it("sends the version and resolves with nothing, whatever the server answers", async () => {
    const { client, rpc } = clientAnswering({ version: "2.4.0", state: "published" });
    expect(await client.publish("2.4.0")).toBeUndefined();
    expect(rpc).toHaveBeenCalledWith("ext.acme.notes.publish", { version: "2.4.0" });
  });
});

describe("a failing rpc", () => {
  it("propagates the bridge's own error unchanged from every method", async () => {
    const boom = new Error("timed out");
    const client = clientRejecting(boom);
    const calls = [
      () => client.releases(),
      () => client.note("v"),
      () => client.comments("v"),
      () => client.save("v", "b", "r"),
      () => client.publish("v"),
    ];
    for (const call of calls) {
      const error = await call().catch((e) => e);
      expect(error).toBe(boom);
      expect(error).not.toBeInstanceOf(WireError);
    }
  });
});

describe("WireError", () => {
  it("is an Error named WireError that exposes the method", () => {
    const error = new WireError("ext.acme.notes.note", "bad");
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("WireError");
    expect(error.method).toBe("ext.acme.notes.note");
    expect(error.message).toBe("ext.acme.notes.note returned something unexpected: bad");
  });
});

describe("messageOf", () => {
  it("is an Error's message", () => {
    expect(messageOf(new Error("nope"))).toBe("nope");
    expect(messageOf(new WireError("m", "d"))).toBe("m returned something unexpected: d");
  });

  it("is the string form of anything else", () => {
    expect(messageOf("plain")).toBe("plain");
    expect(messageOf(null)).toBe("null");
    expect(messageOf(undefined)).toBe("undefined");
    expect(messageOf({})).toBe("[object Object]");
  });
});

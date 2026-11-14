/**
 * The host object model's own classes: what a call sends, how a path is
 * built, and what a refusal looks like.
 */
import { describe, expect, it } from "vitest";

import { HostError, type HostLink } from "./hostModel.js";
import { Host } from "./hostModel.generated.js";

function recordingLink() {
  const sent: {
    op: string;
    path: string;
    options: Record<string, unknown>;
  }[] = [];
  const link: HostLink = {
    request: async (op, path, options) => {
      sent.push({ op, path, options: { ...options } });
      return "answer";
    },
  };
  return { link, sent };
}

describe("HostError", () => {
  it("is an Error named HostError that carries its code and message", () => {
    const error = new HostError("not_granted", "no grant");

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("HostError");
    expect(error.code).toBe("not_granted");
    expect(error.message).toBe("no grant");
  });
});

describe("a call on the host model", () => {
  it("leaves out a parameter that is undefined or null, and keeps false, zero and empty", async () => {
    const { link, sent } = recordingLink();
    const host = new Host(link);

    await host.ui.set_sidebar(false, 0, "");
    await host.ui.set_sidebar(true);
    await host.ui.set_sidebar(true, undefined, null as unknown as string);

    expect(sent.map((s) => s.options.params)).toStrictEqual([
      { open: false, width: 0, section: "" },
      { open: true },
      { open: true },
    ]);
  });

  it("returns the host's answer and names the member under its owner's path", async () => {
    const { link, sent } = recordingLink();
    const host = new Host(link);

    const answer = await host.ui.set_sidebar(true);

    expect(answer).toBe("answer");
    expect(sent[0]).toMatchObject({ op: "call", path: "ui.set_sidebar" });
  });

  it("names a member of the root object by its bare name", async () => {
    const { link, sent } = recordingLink();
    const host = new Host(link);

    await host.decide({ text: "x" }, []);

    expect(sent[0].path).toBe("decide");
  });

  it("addresses the window and session the object was made for", async () => {
    const { link, sent } = recordingLink();
    const host = new Host(link);

    await host.windows.ui("w-2").set_sidebar(true);
    await host.ui.set_sidebar(true);

    expect(sent[0].options).toMatchObject({ window: "w-2" });
    expect(sent[1].options).toMatchObject({ window: null, session: null });
  });
});

describe("a property on the host model", () => {
  it("refuses a write with a read_only HostError, without asking the host", async () => {
    const { link, sent } = recordingLink();
    const host = new Host(link);

    const error = await host.chat.processing.set(true).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(HostError);
    expect(error).toMatchObject({
      code: "read_only",
      message: "host.chat.processing cannot be set",
    });
    expect(sent).toEqual([]);
  });

  it("reads through the host with its full path", async () => {
    const { link, sent } = recordingLink();
    const host = new Host(link);

    await expect(host.chat.processing.get()).resolves.toBe("answer");

    expect(sent[0]).toMatchObject({ op: "get", path: "chat.processing" });
  });
});

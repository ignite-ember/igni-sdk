// @vitest-environment jsdom
/**
 * The ticket-lookup example's page script, run the way the host runs it.
 *
 * `examples/ticket-lookup/extension/ui/main.js` is what a user copies out
 * of docs/YOUR_FIRST_EXTENSION.md. Nothing else loads it, so this does:
 * it evaluates the real file in a jsdom page whose parent is a stub host,
 * answers as the host would, and reads what the page shows. The wire it
 * speaks is held to the SDK's own guard (`isGuestMessage`), and the one
 * RPC it calls to the manifest that grants it.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  isGuestMessage,
  methodAllowed,
} from "../extension-bridge/src/protocol.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const example = join(root, "examples", "ticket-lookup", "extension");
const script = readFileSync(join(example, "ui", "main.js"), "utf8");
const html = readFileSync(join(example, "ui", "index.html"), "utf8");
const manifest = JSON.parse(readFileSync(join(example, "manifest.json"), "utf8"));

type Call = {
  igni: number;
  kind: string;
  nonce: string | null;
  id: string;
  method: string;
  args: { ticket_id: string };
};

const listeners: [string, EventListenerOrEventListenerObject][] = [];
const realAdd = window.addEventListener.bind(window);

/** Load the page with a stub host as its parent. */
function load() {
  const posted: Call[] = [];
  const targets: unknown[] = [];
  const host = {
    postMessage: (message: Call, target: unknown) => {
      posted.push(message);
      targets.push(target);
    },
  } as unknown as Window;
  Object.defineProperty(window, "parent", { value: host, configurable: true });
  document.body.innerHTML = html.slice(html.indexOf("<body"), html.indexOf("<script"));
  (0, eval)(script);
  const send = (body: unknown, source: unknown = host) => {
    const event = new MessageEvent("message", { data: body });
    Object.defineProperty(event, "source", { value: source });
    window.dispatchEvent(event);
  };
  const out = () => document.getElementById("out")!.textContent;
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
  return { posted, targets, host, send, out, settle };
}

const hello = (nonce = "n1") => ({ igni: 1, kind: "hello", nonce });

beforeEach(() => {
  window.addEventListener = ((type: string, fn: EventListenerOrEventListenerObject) => {
    listeners.push([type, fn]);
    realAdd(type, fn);
  }) as typeof window.addEventListener;
});

afterEach(() => {
  for (const [type, fn] of listeners.splice(0)) window.removeEventListener(type, fn);
  window.addEventListener = realAdd;
});

describe("the ticket-lookup page script", () => {
  it("looks up the input's ticket as soon as the host says hello", () => {
    const page = load();
    expect(page.posted).toEqual([]);
    page.send(hello("abc"));
    expect(page.posted).toHaveLength(1);
    expect(page.posted[0]).toEqual({
      igni: 1,
      kind: "call",
      nonce: "abc",
      id: expect.any(String),
      method: "ext.acme.tickets.lookup_ticket",
      args: { ticket_id: "T-1001" },
    });
    expect(page.targets).toEqual(["*"]);
  });

  it("posts calls the SDK's own guard accepts", () => {
    const page = load();
    page.send(hello());
    expect(isGuestMessage(page.posted[0])).toBe(true);
  });

  it("calls only the RPC the manifest grants", () => {
    const page = load();
    page.send(hello());
    expect(methodAllowed(page.posted[0]!.method, manifest.permissions.rpc)).toBe(true);
    expect(manifest.permissions.tools.map((t: { name: string }) => `ext.${t.name}`)).toContain(
      page.posted[0]!.method,
    );
  });

  it("ignores messages from any window but its parent", () => {
    const page = load();
    page.send(hello(), {});
    page.send(hello(), window);
    page.send(hello(), null);
    expect(page.posted).toEqual([]);
  });

  it("ignores messages that are not igni version 1, or not objects", () => {
    const page = load();
    page.send({ kind: "hello", nonce: "x" });
    page.send({ igni: 2, kind: "hello", nonce: "x" });
    page.send(null);
    page.send("hello");
    page.send(7);
    expect(page.posted).toEqual([]);
  });

  it("shows the result pretty-printed once the host answers", async () => {
    const page = load();
    expect(page.out()).toBe("Loading…");
    page.send(hello());
    const value = { id: "T-1001", status: "open" };
    page.send({ igni: 1, kind: "result", id: page.posted[0]!.id, ok: true, value });
    await page.settle();
    expect(page.out()).toBe(JSON.stringify(value, null, 2));
  });

  it("shows 'error: <message>' when the call fails", async () => {
    const page = load();
    page.send(hello());
    page.send({ igni: 1, kind: "result", id: page.posted[0]!.id, ok: false, error: "no such ticket" });
    await page.settle();
    expect(page.out()).toBe("error: no such ticket");
  });

  it("ignores a result for an unknown id, and a second result for a settled one", async () => {
    const page = load();
    page.send(hello());
    const id = page.posted[0]!.id;
    page.send({ igni: 1, kind: "result", id: "999", ok: true, value: "stray" });
    await page.settle();
    expect(page.out()).toBe("Loading…");
    page.send({ igni: 1, kind: "result", id, ok: true, value: "first" });
    await page.settle();
    page.send({ igni: 1, kind: "result", id, ok: false, error: "second" });
    await page.settle();
    expect(page.out()).toBe('"first"');
  });

  it("ignores a result from a window that is not the host", async () => {
    const page = load();
    page.send(hello());
    page.send({ igni: 1, kind: "result", id: page.posted[0]!.id, ok: true, value: "forged" }, {});
    await page.settle();
    expect(page.out()).toBe("Loading…");
  });

  it("gives every call its own id and answers each by its own", async () => {
    const page = load();
    page.send(hello());
    const form = document.getElementById("f")!;
    (document.getElementById("q") as HTMLInputElement).value = "T-2";
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    const [first, second] = page.posted;
    expect(first!.id).not.toBe(second!.id);
    page.send({ igni: 1, kind: "result", id: second!.id, ok: true, value: "two" });
    await page.settle();
    expect(page.out()).toBe('"two"');
    page.send({ igni: 1, kind: "result", id: first!.id, ok: true, value: "one" });
    await page.settle();
    expect(page.out()).toBe('"one"');
  });

  it("cancels the form's submit and looks up the current input", () => {
    const page = load();
    page.send(hello("nn"));
    (document.getElementById("q") as HTMLInputElement).value = "T-77";
    const submit = new Event("submit", { cancelable: true });
    document.getElementById("f")!.dispatchEvent(submit);
    expect(submit.defaultPrevented).toBe(true);
    expect(page.posted).toHaveLength(2);
    expect(page.posted[1]!.args).toEqual({ ticket_id: "T-77" });
    expect(page.posted[1]!.nonce).toBe("nn");
  });

  it("writes results as text, never as markup", async () => {
    const page = load();
    page.send(hello());
    const value = { note: "<img src=x onerror=alert(1)>" };
    page.send({ igni: 1, kind: "result", id: page.posted[0]!.id, ok: true, value });
    await page.settle();
    expect(document.querySelector("#out img")).toBeNull();
    expect(page.out()).toContain("<img src=x onerror=alert(1)>");
  });

  it("looks up again on every hello, with the newest nonce", () => {
    const page = load();
    page.send(hello("one"));
    page.send(hello("two"));
    expect(page.posted.map((p) => p.nonce)).toEqual(["one", "two"]);
  });
});

describe("the tutorial's copy of the page", () => {
  const doc = readFileSync(join(root, "docs", "YOUR_FIRST_EXTENSION.md"), "utf8");

  function listing(file: string, fence: string): string {
    const start = doc.indexOf(`<!-- file: ${file} -->`);
    expect(start, `${file} is not in the tutorial`).toBeGreaterThan(-1);
    const open = doc.indexOf("```" + fence + "\n", start) + 4 + fence.length;
    return doc.slice(open, doc.indexOf("\n```", open) + 1);
  }

  it("is byte for byte main.js", () => {
    expect(listing("examples/ticket-lookup/extension/ui/main.js", "javascript")).toBe(script);
  });

  it("is byte for byte index.html", () => {
    expect(listing("examples/ticket-lookup/extension/ui/index.html", "html")).toBe(html);
  });
});

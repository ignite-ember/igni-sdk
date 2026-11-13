// @vitest-environment jsdom
/**
 * The release-notes panel, rendered against a backend that answers
 * what each test says. It is the second shape an author copies, so what
 * it promises (a selection the host's URL remembers, a draft that is
 * never replaced by somebody else's, a save that waits for the typing
 * to stop, a publish that asks first) is held here.
 */
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Bridge } from "@ignite-ember/extension-bridge";

import type { Comment, Note, NotesClient, Release } from "./notes";

const bridge = vi.hoisted(() => ({
  connect: vi.fn((): Promise<unknown> => new Promise(() => {})),
}));
vi.mock("@ignite-ember/extension-bridge", () => ({ connect: bridge.connect }));

type Panel = typeof import("./panel");

/** panel.tsx runs `main()` when imported, so `#root` must exist first. */
async function importPanel(withRoot = true): Promise<Panel> {
  vi.resetModules();
  document.body.innerHTML = withRoot ? '<div id="root"></div>' : "";
  return import("./panel");
}

const rel = (version: string, state: Release["state"] = "draft"): Release => ({
  version,
  state,
  publishedAt: null,
});
const noteOf = (version: string, body = `body of ${version}`, revision = "r1"): Note => ({
  version,
  body,
  revision,
});
const comment = (id: string, over: Partial<Comment> = {}): Comment => ({
  id,
  version: "2.4.0",
  author: "Maya Okonkwo",
  body: `comment ${id}`,
  resolved: false,
  ...over,
});

interface Backend {
  releases: () => Promise<Release[]>;
  note: (version: string) => Promise<Note>;
  comments: (version: string) => Promise<Comment[]>;
  save: (version: string, body: string, revision: string) => Promise<Note>;
  publish: (version: string) => Promise<void>;
}

function fakeClient(over: Partial<Backend> = {}) {
  const backend: Backend = {
    releases: async () => [rel("2.4.0"), rel("2.3.1", "published")],
    note: async (version) => noteOf(version),
    comments: async () => [],
    save: async (version, body) => noteOf(version, body, "r2"),
    publish: async () => undefined,
    ...over,
  };
  return {
    releases: vi.fn(() => backend.releases()),
    note: vi.fn((v: string) => backend.note(v)),
    comments: vi.fn((v: string) => backend.comments(v)),
    save: vi.fn((v: string, b: string, r: string) => backend.save(v, b, r)),
    publish: vi.fn((v: string) => backend.publish(v)),
  };
}
type Fake = ReturnType<typeof fakeClient>;

function fakeBridge(params: Record<string, unknown> = {}) {
  const unsubscribe = vi.fn();
  const listeners: Array<(p: Record<string, unknown>) => void> = [];
  const igni = {
    params,
    setLocation: vi.fn(),
    onParams: vi.fn((fn: (p: Record<string, unknown>) => void) => {
      listeners.push(fn);
      return unsubscribe;
    }),
  };
  return { igni, unsubscribe, emit: (p: Record<string, unknown>) => listeners.forEach((l) => l(p)) };
}
type FakeBridge = ReturnType<typeof fakeBridge>;

async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function mount(client: Fake, host: FakeBridge = fakeBridge()) {
  const { NotesPanel } = await importPanel();
  const { ToastHost } = await import("@ignite-ember/ui-react");
  const view = render(
    <ToastHost>
      <NotesPanel client={client as unknown as NotesClient} igni={host.igni as unknown as Bridge} />
    </ToastHost>,
  );
  await flush();
  return view;
}

const editor = () => screen.getByRole("textbox", { name: "Notes" }) as HTMLTextAreaElement;
const type = (text: string) => fireEvent.change(editor(), { target: { value: text } });
const publishButton = () => screen.getByRole("button", { name: "Publish" }) as HTMLButtonElement;
const selectedRows = () => document.querySelectorAll('.ui-item[aria-selected="true"]');
const toneOf = (element: HTMLElement) => element.closest("[data-tone]")?.getAttribute("data-tone");

beforeEach(() => {
  vi.useFakeTimers();
  bridge.connect.mockImplementation(() => new Promise(() => {}));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("the release list", () => {
  it("shows a spinner while loading and none after", async () => {
    const { NotesPanel } = await importPanel();
    let release: (r: Release[]) => void = () => {};
    const client = fakeClient({ releases: () => new Promise((resolve) => (release = resolve)) });
    const { igni } = fakeBridge();
    const { ToastHost } = await import("@ignite-ember/ui-react");
    render(
      <ToastHost>
        <NotesPanel client={client as unknown as NotesClient} igni={igni as unknown as Bridge} />
      </ToastHost>,
    );
    expect(screen.getByText("Loading releases")).toBeTruthy();
    release([rel("1.0.0")]);
    await flush();
    expect(screen.queryByText("Loading releases")).toBeNull();
  });

  it("shows each version with its state", async () => {
    await mount(fakeClient());
    expect(screen.getByText("2.4.0", { selector: "span" })).toBeTruthy();
    expect(screen.getByText("draft")).toBeTruthy();
    expect(screen.getByText("published")).toBeTruthy();
  });

  it("gives draft, published and superseded the neutral, success and warning tones", async () => {
    await mount(
      fakeClient({
        releases: async () => [rel("3", "draft"), rel("2", "published"), rel("1", "superseded")],
      }),
    );
    expect(toneOf(screen.getByText("draft"))).toBe("neutral");
    expect(toneOf(screen.getByText("published"))).toBe("success");
    expect(toneOf(screen.getByText("superseded"))).toBe("warning");
  });

  it("says No releases yet. for an empty list and selects nothing", async () => {
    await mount(fakeClient({ releases: async () => [] }));
    expect(screen.getByText("No releases yet.")).toBeTruthy();
    expect(screen.getByText("Pick a release to see its notes.")).toBeTruthy();
  });

  it("shows a refused load as a danger banner with the message", async () => {
    await mount(fakeClient({ releases: () => Promise.reject(new Error("rpc denied")) }));
    expect(toneOf(screen.getByText("rpc denied"))).toBe("danger");
    expect(screen.queryByText("Loading releases")).toBeNull();
  });

  it("ignores a note that answers after another release was picked", async () => {
    let late: (n: Note) => void = () => {};
    const client = fakeClient({
      note: (v) => (v === "2.4.0" ? new Promise((resolve) => (late = resolve)) : Promise.resolve(noteOf(v))),
    });
    await mount(client);
    fireEvent.click(screen.getByText("2.3.1", { selector: "span" }));
    await flush();
    late(noteOf("2.4.0", "stale text"));
    await flush();
    expect(editor().value).toBe("body of 2.3.1");
  });
});

describe("selection", () => {
  it("opens the newest release when the host asked for none", async () => {
    const client = fakeClient();
    await mount(client);
    expect(client.note).toHaveBeenCalledWith("2.4.0");
    expect(selectedRows().length).toBe(1);
    expect(screen.getByRole("heading", { name: "2.4.0" })).toBeTruthy();
  });

  it("opens the release in igni.params.version, not the newest", async () => {
    const client = fakeClient();
    await mount(client, fakeBridge({ version: "2.3.1" }));
    expect(client.note).toHaveBeenCalledWith("2.3.1");
    expect(client.note).not.toHaveBeenCalledWith("2.4.0");
  });

  it("ignores a version param that is not a string", async () => {
    const client = fakeClient();
    await mount(client, fakeBridge({ version: 5 }));
    expect(client.note).toHaveBeenCalledWith("2.4.0");
  });

  it("marks only the picked row aria-selected", async () => {
    await mount(fakeClient());
    const selected = selectedRows();
    expect(selected.length).toBe(1);
    expect(within(selected[0] as HTMLElement).getByText("2.4.0")).toBeTruthy();
  });

  it("picking a release selects it and tells the host with setLocation", async () => {
    const client = fakeClient();
    const host = fakeBridge();
    await mount(client, host);
    fireEvent.click(screen.getByText("2.3.1", { selector: "span" }));
    await flush();
    expect(client.note).toHaveBeenCalledWith("2.3.1");
    expect(host.igni.setLocation).toHaveBeenCalledWith({ version: "2.3.1" });
    expect(screen.getByRole("heading", { name: "2.3.1" })).toBeTruthy();
  });

  it("follows the host when its params change to a version", async () => {
    const client = fakeClient();
    const host = fakeBridge();
    await mount(client, host);
    act(() => host.emit({ version: "2.3.1" }));
    await flush();
    expect(screen.getByRole("heading", { name: "2.3.1" })).toBeTruthy();
  });

  it("keeps the selection when the host's params carry no string version", async () => {
    const host = fakeBridge();
    await mount(fakeClient(), host);
    act(() => host.emit({ version: 3, other: "x" }));
    await flush();
    expect(screen.getByRole("heading", { name: "2.4.0" })).toBeTruthy();
  });

  it("releases its onParams subscription on unmount", async () => {
    const host = fakeBridge();
    const view = await mount(fakeClient(), host);
    expect(host.unsubscribe).not.toHaveBeenCalled();
    view.unmount();
    expect(host.unsubscribe).toHaveBeenCalledTimes(1);
  });

  it("shows a failed note as a danger banner when the version is not in the list", async () => {
    const client = fakeClient({ note: () => Promise.reject(new Error("no note for 9.9.9")) });
    await mount(client, fakeBridge({ version: "9.9.9" }));
    expect(toneOf(screen.getByText("no note for 9.9.9"))).toBe("danger");
  });
});

describe("the split", () => {
  const separator = () => screen.getByRole("separator", { name: "Resize the release list" });

  it("starts from igni.params.width", async () => {
    await mount(fakeClient(), fakeBridge({ width: "400" }));
    expect(separator().getAttribute("aria-valuenow")).toBe("400");
  });

  it.each([["abc"], [undefined], [400]])("falls back to 280 for the width %j", async (width) => {
    await mount(fakeClient(), fakeBridge({ width }));
    expect(separator().getAttribute("aria-valuenow")).toBe("280");
  });

  it("stores the new width in the host's URL beside the version, as a string", async () => {
    const host = fakeBridge();
    await mount(fakeClient(), host);
    fireEvent.keyDown(separator(), { key: "Home" });
    expect(host.igni.setLocation).toHaveBeenCalledWith({ version: "2.4.0", width: "160" });
  });

  it("says nothing to the host about a width while nothing is selected", async () => {
    const host = fakeBridge();
    await mount(fakeClient({ releases: async () => [] }), host);
    fireEvent.keyDown(separator(), { key: "Home" });
    expect(host.igni.setLocation).not.toHaveBeenCalled();
  });
});

describe("the note", () => {
  it("loads the note and the comments together and shows the three tabs", async () => {
    const client = fakeClient({ comments: async () => [comment("c1"), comment("c2")] });
    await mount(client);
    expect(client.note).toHaveBeenCalledWith("2.4.0");
    expect(client.comments).toHaveBeenCalledWith("2.4.0");
    expect(editor().value).toBe("body of 2.4.0");
    expect(screen.getByRole("tab", { name: "Write" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Preview" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Comments (2)" })).toBeTruthy();
  });

  it.each([
    ["note", { note: () => Promise.reject(new Error("note broke")) }, "note broke"],
    ["comments", { comments: () => Promise.reject(new Error("comments broke")) }, "comments broke"],
  ] as const)("shows a danger banner when the %s request fails", async (_which, over, message) => {
    await mount(fakeClient(over));
    expect(toneOf(screen.getByText(message))).toBe("danger");
    expect(screen.queryByRole("textbox", { name: "Notes" })).toBeNull();
  });

  it("drops the draft when another release is picked", async () => {
    const client = fakeClient();
    await mount(client);
    type("half typed");
    fireEvent.click(screen.getByText("2.3.1", { selector: "span" }));
    await flush();
    expect(editor().value).toBe("body of 2.3.1");
    // Nothing of the old editor's state follows: not its unsaved flag,
    // and so not its revision either.
    expect(publishButton().disabled).toBe(false);
    type("next");
    await flush(1_500);
    expect(client.save).toHaveBeenCalledWith("2.3.1", "next", "r1");
  });

  it("previews the draft as Markdown", async () => {
    await mount(fakeClient({ note: async (v) => noteOf(v, "# Big\n\ntext") }));
    type("# Changed");
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    expect(screen.getByRole("heading", { name: "Changed" })).toBeTruthy();
  });

  it("lists comments with author, resolved badge and body", async () => {
    await mount(
      fakeClient({
        comments: async () => [comment("c1", { resolved: true }), comment("c2", { author: "Sam" })],
      }),
    );
    fireEvent.click(screen.getByRole("tab", { name: "Comments (2)" }));
    expect(screen.getByText("Maya Okonkwo")).toBeTruthy();
    expect(screen.getByText("comment c1")).toBeTruthy();
    expect(screen.getByText("Sam")).toBeTruthy();
    expect(screen.getAllByText("resolved").length).toBe(1);
  });

  it("says No comments yet. when there are none", async () => {
    await mount(fakeClient());
    fireEvent.click(screen.getByRole("tab", { name: "Comments (0)" }));
    expect(screen.getByText("No comments yet.")).toBeTruthy();
  });
});

describe("autosave", () => {
  it("saves 1.5s after the last keystroke with the revision it loaded", async () => {
    const client = fakeClient();
    await mount(client);
    type("a");
    await flush(1_000);
    type("ab");
    await flush(1_499);
    expect(client.save).not.toHaveBeenCalled();
    await flush(1);
    expect(client.save).toHaveBeenCalledTimes(1);
    expect(client.save).toHaveBeenCalledWith("2.4.0", "ab", "r1");
  });

  it("holds the new revision for the next save and goes back to Saved", async () => {
    const client = fakeClient();
    await mount(client);
    type("one");
    expect(screen.getAllByText("Unsaved changes").length).toBeGreaterThan(0);
    await flush(1_500);
    expect(screen.getAllByText("Saved").length).toBeGreaterThan(0);
    type("two");
    await flush(1_500);
    expect(client.save).toHaveBeenLastCalledWith("2.4.0", "two", "r2");
  });

  it("keeps a typed change dirty when it lands while an earlier save is in flight", async () => {
    let finish: (n: Note) => void = () => {};
    const client = fakeClient({ save: () => new Promise((resolve) => (finish = resolve)) });
    await mount(client);
    type("first");
    await flush(1_500);
    expect(client.save).toHaveBeenCalledTimes(1);
    type("first and more");
    finish(noteOf("2.4.0", "first", "r2"));
    await flush();
    // The save answered for "first"; "first and more" has not been saved.
    await flush(1_500);
    expect(client.save).toHaveBeenCalledTimes(2);
    expect(client.save).toHaveBeenLastCalledWith("2.4.0", "first and more", "r2");
  });

  it("on a conflict keeps the draft, says so, stops saving and disables Publish", async () => {
    // Imported when called: the panel's module graph is reloaded for each
    // test, and `instanceof` only holds within one.
    const client = fakeClient({
      save: async () => {
        const { ConflictError } = await import("./notes");
        throw new ConflictError("r9");
      },
    });
    await mount(client);
    type("mine");
    await flush(1_500);
    expect(toneOf(screen.getByText(/Somebody else saved this note/))).toBe("danger");
    expect(editor().value).toBe("mine");
    type("mine again");
    await flush(10_000);
    expect(client.save).toHaveBeenCalledTimes(1);
    expect(publishButton().disabled).toBe(true);
  });

  it("toasts any other save error as danger and keeps the draft dirty", async () => {
    const client = fakeClient({ save: () => Promise.reject(new Error("disk full")) });
    await mount(client);
    type("mine");
    await flush(1_500);
    expect(toneOf(screen.getByText("disk full"))).toBe("danger");
    expect(editor().value).toBe("mine");
    expect(publishButton().disabled).toBe(true);
  });
});

describe("the unsaved-work warning", () => {
  it("is registered only while the draft is dirty and removed once saved", async () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    await mount(fakeClient());
    const warns = () => add.mock.calls.filter((c) => c[0] === "beforeunload");
    expect(warns().length).toBe(0);
    type("x");
    expect(warns().length).toBe(1);
    const handler = warns()[0]?.[1];
    await flush(1_500);
    expect(remove.mock.calls.some((c) => c[0] === "beforeunload" && c[1] === handler)).toBe(true);
  });

  it("asks the browser to hold the page", async () => {
    await mount(fakeClient());
    type("x");
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("does not hold the page when nothing is unsaved", async () => {
    await mount(fakeClient());
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("is removed when the panel unmounts dirty", async () => {
    const view = await mount(fakeClient());
    type("x");
    view.unmount();
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});

describe("publishing", () => {
  const open = async () => {
    fireEvent.click(publishButton());
    await flush();
    return screen.getByRole("dialog");
  };
  const confirm = (dialog: HTMLElement) => within(dialog).getByRole("button", { name: "Publish" });

  it("is disabled while the draft has unsaved changes", async () => {
    await mount(fakeClient());
    expect(publishButton().disabled).toBe(false);
    type("x");
    expect(publishButton().disabled).toBe(true);
  });

  it("asks first, with a word count", async () => {
    const client = fakeClient({ note: async (v) => noteOf(v, "  one two\nthree  ") });
    await mount(client);
    const dialog = await open();
    expect(within(dialog).getByText("Publish 2.4.0?")).toBeTruthy();
    expect(within(dialog).getByText("3 words.")).toBeTruthy();
    expect(client.publish).not.toHaveBeenCalled();
  });

  it("says This note is empty. for an empty or whitespace-only note", async () => {
    await mount(fakeClient({ note: async (v) => noteOf(v, " \n\t ") }));
    const dialog = await open();
    expect(within(dialog).getByText("This note is empty.")).toBeTruthy();
  });

  it("counts what was saved, not the text as first loaded", async () => {
    await mount(fakeClient({ note: async (v) => noteOf(v, "") }));
    type("now there are five whole words");
    await flush(1_500);
    const dialog = await open();
    expect(within(dialog).getByText("6 words.")).toBeTruthy();
  });

  it("publishes on confirm, then closes and toasts success", async () => {
    const client = fakeClient();
    await mount(client);
    const dialog = await open();
    fireEvent.click(confirm(dialog));
    await flush();
    expect(client.publish).toHaveBeenCalledWith("2.4.0");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(toneOf(screen.getByText("2.4.0 published"))).toBe("success");
  });

  it("toasts a failure and leaves the dialog open", async () => {
    const client = fakeClient({ publish: () => Promise.reject(new Error("not allowed")) });
    await mount(client);
    const dialog = await open();
    fireEvent.click(confirm(dialog));
    await flush();
    expect(toneOf(screen.getByText("not allowed"))).toBe("danger");
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("closes without publishing on Cancel", async () => {
    const client = fakeClient();
    await mount(client);
    const dialog = await open();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(client.publish).not.toHaveBeenCalled();
  });
});

describe("main", () => {
  it("writes why igni could not be reached, as text", async () => {
    bridge.connect.mockRejectedValueOnce(new Error("<b>not framed</b>"));
    await importPanel();
    await flush();
    const root = document.getElementById("root") as HTMLElement;
    expect(root.textContent).toBe("Could not reach igni: <b>not framed</b>");
    expect(root.querySelector("b")).toBeNull();
  });

  it("stringifies a non-Error rejection", async () => {
    bridge.connect.mockRejectedValueOnce("timeout");
    await importPanel();
    await flush();
    expect(document.getElementById("root")?.textContent).toBe("Could not reach igni: timeout");
  });

  it("refuses a page with no #root", async () => {
    const rejections: unknown[] = [];
    const catcher = (reason: unknown) => rejections.push(reason);
    process.on("unhandledRejection", catcher);
    try {
      await importPanel(false);
      await flush();
    } finally {
      process.off("unhandledRejection", catcher);
    }
    expect(bridge.connect).not.toHaveBeenCalled();
  });

  it("renders the panel over the connected bridge", async () => {
    const rpc = vi.fn(async (method: string) => {
      if (method.endsWith(".releases")) return [rel("2.4.0")];
      if (method.endsWith(".note")) return noteOf("2.4.0");
      return [];
    });
    const host = fakeBridge();
    bridge.connect.mockResolvedValueOnce({ ...host.igni, rpc });
    await importPanel();
    await flush();
    expect(rpc).toHaveBeenCalledWith("ext.acme.notes.releases", undefined);
    expect(screen.getByRole("heading", { name: "Release notes" })).toBeTruthy();
    expect(editor().value).toBe("body of 2.4.0");
  });

  it("logs a render crash under [acme.notes] instead of leaving a blank frame", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    // The wire checks keep a bad comment out; a render throw needs a
    // client that hands one over.
    const { NotesClient: Real, ...rest } = await vi.importActual<typeof import("./notes")>("./notes");
    vi.doMock("./notes", () => ({
      ...rest,
      NotesClient: class extends Real {
        override async comments() {
          return [{ ...comment("c1"), body: { not: "a string" } as unknown as string }];
        }
      },
    }));
    const rpc = async (method: string) => {
      if (method.endsWith(".releases")) return [rel("2.4.0")];
      return noteOf("2.4.0");
    };
    bridge.connect.mockResolvedValueOnce({ ...fakeBridge().igni, rpc });
    await importPanel();
    await flush();
    fireEvent.click(screen.getByRole("tab", { name: "Comments (1)" }));
    vi.doUnmock("./notes");
    expect(error.mock.calls.some((call) => call[0] === "[acme.notes]")).toBe(true);
  });
});

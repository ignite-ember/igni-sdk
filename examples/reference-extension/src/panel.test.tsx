// @vitest-environment jsdom
/**
 * The reference extension's panel, rendered against a backend that
 * answers what each test says. The panel is what an author copies, so
 * what it promises (a poll that never overlaps, a list that survives a
 * flaky poll, a dialog that keeps what was typed) is held here.
 */
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ScanStatus, ScannerClient, Violation } from "./scanner";

const bridge = vi.hoisted(() => ({
  connect: vi.fn((): Promise<unknown> => new Promise(() => {})),
}));
vi.mock("@ignite-ember/extension-bridge", () => ({ connect: bridge.connect }));

type Panel = typeof import("./panel");

/**
 * panel.tsx runs `main()` when imported, so it is imported only once
 * `#root` exists, and afresh each time.
 */
async function importPanel(withRoot = true): Promise<Panel> {
  vi.resetModules();
  document.body.innerHTML = withRoot ? '<div id="root"></div>' : "";
  return import("./panel");
}

const v = (id: string, over: Partial<Violation> = {}): Violation => ({
  id,
  rule: `rule-${id}`,
  severity: "high",
  path: `src/${id}.py`,
  line: 1,
  ...over,
});

const IDLE: ScanStatus = { state: "idle", lastFinished: null };

function fakeClient(
  list: () => Promise<Violation[]>,
  status: () => Promise<ScanStatus> = async () => IDLE,
) {
  return {
    violations: vi.fn(list),
    status: vi.fn(status),
    startScan: vi.fn(async () => undefined),
    accept: vi.fn(async (_id: string, _why: string) => undefined),
  };
}

type Fake = ReturnType<typeof fakeClient>;

async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function mount(client: Fake) {
  const { CompliancePanel } = await importPanel();
  const view = render(<CompliancePanel client={client as unknown as ScannerClient} />);
  await flush();
  return view;
}

const ok = (rows: Violation[]) => () => Promise.resolve(rows);
const dataRows = () => screen.getAllByRole("row").slice(1);
const ruleOrder = () => dataRows().map((r) => within(r).getByRole("rowheader").textContent);

beforeEach(() => {
  vi.useFakeTimers();
  bridge.connect.mockImplementation(() => new Promise(() => {}));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("loading and failing", () => {
  it("says Loading… until the first poll answers", async () => {
    const { CompliancePanel } = await importPanel();
    let release: (rows: Violation[]) => void = () => {};
    const client = fakeClient(() => new Promise((resolve) => (release = resolve)));
    render(<CompliancePanel client={client as unknown as ScannerClient} />);
    expect(screen.getByText("Loading…")).toBeTruthy();
    release([v("a")]);
    await flush();
    expect(screen.queryByText("Loading…")).toBeNull();
    expect(screen.getByRole("table")).toBeTruthy();
  });

  it("shows a refused first load as a failure, not an empty table", async () => {
    await mount(fakeClient(() => Promise.reject(new Error("rpc denied"))));
    expect(screen.getByText("rpc denied")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("No violations found.")).toBeNull();
  });

  it("disables Scan repository while the load has failed", async () => {
    await mount(fakeClient(() => Promise.reject(new Error("rpc denied"))));
    const scan = screen.getByRole("button", { name: "Scan repository" }) as HTMLButtonElement;
    expect(scan.disabled).toBe(true);
  });
});

describe("the poll", () => {
  it("asks for the list and the status every 2s", async () => {
    const client = fakeClient(ok([v("a")]));
    await mount(client);
    expect(client.violations).toHaveBeenCalledTimes(1);
    expect(client.status).toHaveBeenCalledTimes(1);
    await flush(1_999);
    expect(client.violations).toHaveBeenCalledTimes(1);
    await flush(1);
    expect(client.violations).toHaveBeenCalledTimes(2);
    await flush(2_000);
    expect(client.violations).toHaveBeenCalledTimes(3);
  });

  it("never overlaps: the next poll waits for the slow one", async () => {
    let calls = 0;
    const client = fakeClient(
      () =>
        new Promise((resolve) => {
          calls += 1;
          setTimeout(() => resolve([v("a")]), 5_000);
        }),
    );
    await mount(client);
    await flush(4_000);
    expect(calls).toBe(1);
    await flush(1_000); // answered at 5s; the next is scheduled 2s later
    expect(calls).toBe(1);
    await flush(2_000);
    expect(calls).toBe(2);
  });

  it("backs off to 10s after a failed poll", async () => {
    const client = fakeClient(() => Promise.reject(new Error("denied")));
    await mount(client);
    await flush(9_999);
    expect(client.violations).toHaveBeenCalledTimes(1);
    await flush(1);
    expect(client.violations).toHaveBeenCalledTimes(2);
  });

  it("stops when the panel unmounts, even with a poll in flight", async () => {
    const client = fakeClient(ok([v("a")]));
    const view = await mount(client);
    view.unmount();
    await flush(60_000);
    expect(client.violations).toHaveBeenCalledTimes(1);

    let release: (rows: Violation[]) => void = () => {};
    const slow = fakeClient(() => new Promise((resolve) => (release = resolve)));
    const { CompliancePanel } = await importPanel();
    const second = render(<CompliancePanel client={slow as unknown as ScannerClient} />);
    second.unmount();
    release([]);
    await flush(60_000);
    expect(slow.violations).toHaveBeenCalledTimes(1);
  });

  it("keeps the list on screen when a later poll fails", async () => {
    let fail = false;
    const client = fakeClient(async () => {
      if (fail) throw new Error("flaky");
      return [v("a")];
    });
    await mount(client);
    fail = true;
    await flush(2_000);
    expect(client.violations).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.queryByText("flaky")).toBeNull();
  });

  it("shows the list with a failed scan when only the status fails", async () => {
    const client = fakeClient(ok([v("a")]), () => Promise.reject(new Error("no status")));
    await mount(client);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("The last scan failed: no status");
    await flush(2_000);
    expect(client.status).toHaveBeenCalledTimes(2);
  });
});

describe("the table", () => {
  const rows = [
    v("a", { rule: "zeta", severity: "low", path: "b.py", line: 9 }),
    v("b", { rule: "alpha", severity: "critical", path: "b.py", line: 2 }),
    v("c", { rule: "mid", severity: "medium", path: "a.py", line: 5 }),
    v("d", { rule: "beta", severity: "high", path: "b.py", line: 1 }),
  ];

  it("lists severity by rank first, ascending, and flips on click", async () => {
    await mount(fakeClient(ok(rows)));
    expect(ruleOrder()).toEqual(["alpha", "beta", "mid", "zeta"]);
    fireEvent.click(screen.getByRole("button", { name: /Severity/ }));
    expect(ruleOrder()).toEqual(["zeta", "mid", "beta", "alpha"]);
    expect(screen.getByRole("columnheader", { name: /Severity/ }).getAttribute("aria-sort")).toBe(
      "descending",
    );
  });

  it("sorts by rule and by location, path then line, in both directions", async () => {
    await mount(fakeClient(ok(rows)));
    fireEvent.click(screen.getByRole("button", { name: /Rule/ }));
    expect(ruleOrder()).toEqual(["alpha", "beta", "mid", "zeta"]);
    fireEvent.click(screen.getByRole("button", { name: /Rule/ }));
    expect(ruleOrder()).toEqual(["zeta", "mid", "beta", "alpha"]);

    fireEvent.click(screen.getByRole("button", { name: /Location/ }));
    expect(ruleOrder()).toEqual(["mid", "beta", "alpha", "zeta"]);
    fireEvent.click(screen.getByRole("button", { name: /Location/ }));
    expect(ruleOrder()).toEqual(["zeta", "alpha", "beta", "mid"]);
    expect(screen.getByRole("columnheader", { name: /Rule/ }).getAttribute("aria-sort")).toBe(
      "none",
    );
  });

  it("renders severity as a tone, the rule as row header and path:line", async () => {
    await mount(fakeClient(ok(rows)));
    const first = dataRows()[0];
    expect(within(first).getByText("critical").getAttribute("data-tone")).toBe("danger");
    expect(within(first).getByText("b.py:2")).toBeTruthy();
    const tones = dataRows().map((r) => {
      const cells = within(r).getAllByRole("cell");
      return (cells[0].firstElementChild as HTMLElement).getAttribute("data-tone");
    });
    expect(tones).toEqual(["danger", "danger", "warning", "neutral"]);
    expect(screen.getByRole("button", { name: "Review alpha" })).toBeTruthy();
    expect(screen.getByText("Policy violations, most severe first").tagName).toBe("CAPTION");
  });

  it("renders hostile strings as text", async () => {
    const rule = '<img src=x onerror="boom()">';
    await mount(fakeClient(ok([v("a", { rule })])));
    expect(screen.getByRole("rowheader").textContent).toBe(rule);
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("the filter and the live region", () => {
  const rows = [
    v("a", { severity: "critical" }),
    v("b", { severity: "low" }),
    v("c", { severity: "low" }),
  ];
  const select = () => screen.getByLabelText("Filter by severity") as HTMLSelectElement;
  const live = () => document.querySelector("[aria-live]")?.textContent;

  it("offers All plus the four severities, capitalised", async () => {
    await mount(fakeClient(ok(rows)));
    expect(Array.from(select().options).map((o) => o.textContent)).toEqual([
      "All severities",
      "Critical",
      "High",
      "Medium",
      "Low",
    ]);
  });

  it("narrows the rows and announces the count, singular for one", async () => {
    await mount(fakeClient(ok(rows)));
    expect(live()).toBe("3 violations shown");
    fireEvent.change(select(), { target: { value: "low" } });
    expect(dataRows()).toHaveLength(2);
    expect(live()).toBe("2 violations shown");
    fireEvent.change(select(), { target: { value: "critical" } });
    expect(live()).toBe("1 violation shown");
  });

  it("says nothing while loading", async () => {
    const { CompliancePanel } = await importPanel();
    const client = fakeClient(() => new Promise(() => {}));
    render(<CompliancePanel client={client as unknown as ScannerClient} />);
    expect(live()).toBe("");
  });

  it("explains a filter that hides everything and offers all severities", async () => {
    await mount(fakeClient(ok(rows)));
    fireEvent.change(select(), { target: { value: "medium" } });
    expect(screen.getByText("No medium violations. 3 at other severities.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Run a scan" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show all severities" }));
    expect(select().value).toBe("all");
    expect(dataRows()).toHaveLength(3);
  });

  it("empties the filtered view when a poll removes the last of that severity", async () => {
    let list = rows;
    await mount(fakeClient(async () => list));
    fireEvent.change(select(), { target: { value: "critical" } });
    list = rows.slice(1);
    await flush(2_000);
    expect(screen.getByText("No critical violations. 2 at other severities.")).toBeTruthy();
  });

  it("says No violations found. for an empty list and offers a scan", async () => {
    const client = fakeClient(ok([]));
    await mount(client);
    expect(screen.getByText("No violations found.")).toBeTruthy();
    expect(live()).toBe("0 violations shown");
    fireEvent.click(screen.getByRole("button", { name: "Run a scan" }));
    await flush();
    expect(client.startScan).toHaveBeenCalledTimes(1);
  });
});

describe("scanning", () => {
  it("starts a scan, clears the old error and refreshes", async () => {
    const client = fakeClient(ok([v("a")]));
    client.startScan.mockRejectedValueOnce(new Error("scan refused"));
    await mount(client);
    const button = () => screen.getByRole("button", { name: "Scan repository" }) as HTMLButtonElement;
    fireEvent.click(button());
    await flush();
    expect(screen.getByRole("alert").textContent).toBe("scan refused");
    expect(button().disabled).toBe(false);

    const before = client.violations.mock.calls.length;
    fireEvent.click(button());
    await flush();
    expect(client.startScan).toHaveBeenCalledTimes(2);
    expect(client.violations.mock.calls.length).toBe(before + 1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("disables the button while a startScan is pending", async () => {
    const client = fakeClient(ok([v("a")]));
    let finish: () => void = () => {};
    client.startScan.mockImplementationOnce(() => new Promise<undefined>((r) => (finish = () => r(undefined))));
    await mount(client);
    const button = screen.getByRole("button", { name: "Scan repository" }) as HTMLButtonElement;
    fireEvent.click(button);
    await flush();
    expect(button.disabled).toBe(true);
    finish();
    await flush();
    expect(button.disabled).toBe(false);
  });

  it("shows a spinner, a labelled bar and the step while running, and disables the button", async () => {
    const status = async (): Promise<ScanStatus> => ({ state: "running", step: "parsing", percent: 40 });
    await mount(fakeClient(ok([v("a")]), status));
    expect(document.querySelector(".ui-spinner")?.textContent).toBe("Scanning repository");
    const bar = screen.getByRole("progressbar", { name: "Scanning: parsing" });
    expect(bar.getAttribute("aria-valuenow")).toBe("40");
    expect(screen.getByText("parsing")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Scan repository" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows an indeterminate bar when the percent is unknown", async () => {
    const status = async (): Promise<ScanStatus> => ({ state: "running", step: "listing", percent: null });
    await mount(fakeClient(ok([v("a")]), status));
    const bar = screen.getByRole("progressbar", { name: "Scanning: listing" });
    expect(bar.getAttribute("aria-valuenow")).toBeNull();
  });

  it("reports a failed scan and leaves the button usable", async () => {
    const status = async (): Promise<ScanStatus> => ({ state: "failed", message: "disk full" });
    await mount(fakeClient(ok([v("a")]), status));
    expect(screen.getByRole("alert").textContent).toBe("The last scan failed: disk full");
    expect((screen.getByRole("button", { name: "Scan repository" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("accepting a violation", () => {
  const rows = [v("a"), v("b", { severity: "low" })];
  const justification = () => screen.getByLabelText("Justification") as HTMLTextAreaElement;
  const type = (text: string) => fireEvent.change(justification(), { target: { value: text } });
  const accept = () => screen.getByRole("button", { name: /^Accept/ }) as HTMLButtonElement;
  const REFUSAL = "Say why, in a sentence somebody auditing this will understand.";

  async function open(client: Fake, rule = "rule-a") {
    await mount(client);
    fireEvent.click(screen.getByRole("button", { name: `Review ${rule}` }));
  }

  it("opens a dialog for that violation", async () => {
    await open(fakeClient(ok(rows)), "rule-b");
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("rule-b")).toBeTruthy();
    expect(within(dialog).getByText("src/b.py:1")).toBeTruthy();
  });

  it.each([["   \n  "], ["123456789"], ["  123456789  "]])(
    "rejects the justification %j and does not call accept",
    async (text) => {
      const client = fakeClient(ok(rows));
      await open(client);
      type(text);
      fireEvent.click(accept());
      await flush();
      expect(screen.getByText(REFUSAL)).toBeTruthy();
      expect(client.accept).not.toHaveBeenCalled();
    },
  );

  it("clears the message as the user types", async () => {
    await open(fakeClient(ok(rows)));
    fireEvent.click(accept());
    expect(screen.getByText(REFUSAL)).toBeTruthy();
    type("a");
    expect(screen.queryByText(REFUSAL)).toBeNull();
  });

  it("accepts exactly ten characters, sending the raw text, then closes and refreshes", async () => {
    let list = rows;
    const client = fakeClient(async () => list);
    await open(client);
    type("  1234567890 ");
    list = [rows[1]];
    fireEvent.click(accept());
    await flush();
    expect(client.accept).toHaveBeenCalledWith("a", "  1234567890 ");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(dataRows()).toHaveLength(1);
  });

  it("returns focus to the Review button after accepting", async () => {
    const client = fakeClient(ok(rows));
    await open(client);
    type("a long enough reason");
    fireEvent.click(accept());
    await flush();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Review rule-a" }));
  });

  it("labels the button Accepting… and disables it while busy", async () => {
    const client = fakeClient(ok(rows));
    let finish: () => void = () => {};
    client.accept.mockImplementationOnce(() => new Promise<undefined>((r) => (finish = () => r(undefined))));
    await open(client);
    type("a long enough reason");
    fireEvent.click(accept());
    await flush();
    expect(accept().textContent).toBe("Accepting…");
    expect(accept().disabled).toBe(true);
    finish();
    await flush();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the dialog and its text when accept fails, and shows the error", async () => {
    const client = fakeClient(ok(rows));
    client.accept.mockRejectedValueOnce(new Error("conflict"));
    await open(client);
    type("a long enough reason");
    fireEvent.click(accept());
    await flush();
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(justification().value).toBe("a long enough reason");
    expect(screen.getByText("conflict")).toBeTruthy();
    expect(accept().textContent).toBe("Accept");
    expect(accept().disabled).toBe(false);
  });

  it("dismisses on Cancel and on Escape", async () => {
    await open(fakeClient(ok(rows)));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Review rule-a" }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("starts a second violation's dialog with an empty draft", async () => {
    await open(fakeClient(ok(rows)));
    type("the first draft here");
    // Without closing in between: the dialog is swapped for the other row's.
    fireEvent.click(screen.getByRole("button", { name: "Review rule-b" }));
    expect(within(screen.getByRole("dialog")).getByText("rule-b")).toBeTruthy();
    expect(justification().value).toBe("");
  });

  it("keeps the dialog open when a poll drops its row", async () => {
    let list = rows;
    await open(fakeClient(async () => list));
    type("a long enough reason");
    list = [rows[1]];
    await flush(2_000);
    expect(screen.queryByRole("button", { name: "Review rule-a" })).toBeNull();
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(justification().value).toBe("a long enough reason");
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

  it("renders the panel over the connected bridge", async () => {
    const rpc = vi.fn(async (method: string) =>
      method.endsWith(".list")
        ? [{ id: "x", rule: "r-x", severity: "low", path: "p", line: 1 }]
        : { state: "idle", lastFinished: null },
    );
    bridge.connect.mockResolvedValueOnce({ rpc });
    await importPanel();
    await flush();
    expect(rpc).toHaveBeenCalledWith("ext.acme.scanner.list", undefined);
    expect(screen.getByRole("heading", { name: "Compliance" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Review r-x" })).toBeTruthy();
  });

  it("logs a render crash under [acme.scanner] instead of leaving a blank frame", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    // The wire checks keep a bad row out; a render throw needs a client
    // that hands one over.
    const { ScannerClient: Real, ...rest } = await vi.importActual<typeof import("./scanner")>("./scanner");
    vi.doMock("./scanner", () => ({
      ...rest,
      ScannerClient: class extends Real {
        override async violations() {
          return [{ ...v("x"), rule: { not: "a string" } as unknown as string }];
        }
      },
    }));
    bridge.connect.mockResolvedValueOnce({ rpc: async () => ({ state: "idle", lastFinished: null }) });
    await importPanel();
    await flush();
    vi.doUnmock("./scanner");
    expect(error.mock.calls.some((call) => call[0] === "[acme.scanner]")).toBe(true);
  });

  it("throws when there is no #root", async () => {
    vi.useRealTimers();
    const seen: unknown[] = [];
    const saved = process.listeners("unhandledRejection");
    process.removeAllListeners("unhandledRejection");
    const handler = (reason: unknown) => seen.push(reason);
    process.on("unhandledRejection", handler);
    try {
      await importPanel(false);
      await new Promise((resolve) => setImmediate(resolve));
    } finally {
      process.off("unhandledRejection", handler);
      for (const fn of saved) process.on("unhandledRejection", fn as never);
    }
    expect(String(seen[0])).toContain("index.html has no #root");
  });
});

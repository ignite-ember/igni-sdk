/**
 * What `@ignite-ember/extension-bridge` offers at run time. The parts
 * the bridge is built from (GuestBridge, HostChannel, Correlator,
 * SignalSubscriptions, Watchers, DEFAULT_TIMEOUT_MS) are not among them:
 * once published, anything here is a name an extension may lean on.
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import * as root from "./index.js";

describe("the package root", () => {
  it("exports exactly these names", () => {
    expect(Object.keys(root).sort()).toEqual([
      "Host",
      "HostAccount",
      "HostAgents",
      "HostApp",
      "HostAppState",
      "HostChat",
      "HostChatApprovals",
      "HostChatViews",
      "HostCommands",
      "HostError",
      "HostExtensions",
      "HostHooks",
      "HostLoop",
      "HostMcp",
      "HostModels",
      "HostNotifications",
      "HostObject",
      "HostPermissions",
      "HostPlan",
      "HostPlugins",
      "HostPolicy",
      "HostProcesses",
      "HostScheduler",
      "HostSelf",
      "HostSessions",
      "HostTasks",
      "HostUi",
      "HostWindows",
      "HostWorkflows",
      "HostWorkspace",
      "Property",
      "RENEW_BEFORE_MS",
      "SCHEMA_VERSION",
      "ServiceError",
      "ServiceLink",
      "Signal",
      "authMessage",
      "connect",
    ]);
  });
});

describe("the compiled build", () => {
  it("imports its own modules by the name they are published under, with .js", () => {
    // Node's ESM resolver, which runs the published dist/, does not add
    // an extension: `from "./hostModel"` would work from src/ under a
    // bundler and be a module-not-found for everyone who installs it.
    const here = dirname(fileURLToPath(import.meta.url));
    const sources = readdirSync(here).filter(
      (name) => name.endsWith(".ts") && !name.endsWith(".test.ts"),
    );
    expect(sources.length).toBeGreaterThan(5);
    const bare: string[] = [];
    for (const name of sources) {
      const text = readFileSync(join(here, name), "utf8");
      for (const match of text.matchAll(/(?:from|import\()\s*"(\.\.?\/[^"]*)"/g)) {
        if (!match[1].endsWith(".js")) bare.push(`${name}: ${match[1]}`);
      }
    }
    expect(bare).toEqual([]);
  });
});

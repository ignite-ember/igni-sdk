/**
 * What `@ignite-ember/extension-bridge` offers at run time. The parts
 * the bridge is built from (GuestBridge, HostChannel, Correlator,
 * SignalSubscriptions, Watchers, DEFAULT_TIMEOUT_MS) are not among them:
 * once published, anything here is a name an extension may lean on.
 */
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

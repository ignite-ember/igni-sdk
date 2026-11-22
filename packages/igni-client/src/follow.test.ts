import { describe, expect, it } from "vitest";

import { RULES, isOurs, newContext } from "./follow.js";
import type { WireMessage } from "./wire.js";

function ctx(args: Record<string, unknown>, result?: Record<string, unknown>, sessionId = "") {
  const c = newContext(args, sessionId, "req-1", (id) => id === "other-req");
  if (result) {
    c.result = result;
    c.hasResult = true;
  }
  return c;
}

const push = (channel: string, payload: Record<string, unknown>): WireMessage => ({
  type: "push_notification",
  channel,
  payload,
});

describe("follow rules and the contract's correlation", () => {
  it("run_workflow: matches its workflow_run_id and ends on workflow_completed", () => {
    const c = ctx({}, { workflow_run_id: "wf1" });
    const mine = push("workflow_event", { workflow_run_id: "wf1", type: "workflow_running" });
    const other = push("workflow_event", { workflow_run_id: "wf2", type: "workflow_running" });
    const end = push("workflow_event", { workflow_run_id: "wf1", type: "workflow_completed" });
    expect(isOurs(RULES.run_workflow, c, mine, "run_workflow")).toBe(true);
    expect(isOurs(RULES.run_workflow, c, other, "run_workflow")).toBe(false);
    expect(RULES.run_workflow.last(c, end)).toBe(true);
    expect(RULES.run_workflow.last(c, mine)).toBe(false);
  });

  it("cancel_workflow: reads the id from the args", () => {
    const c = ctx({ workflow_run_id: "wf9" });
    expect(isOurs(RULES.cancel_workflow, c, push("workflow_event", { workflow_run_id: "wf9", type: "x" }), "cancel_workflow")).toBe(true);
    expect(RULES.cancel_workflow.endsWith({ ...c, result: { cancelled: false }, hasResult: true })).toBe(true);
  });

  it("stop_background_process: matches its pid and ends on background_process_done", () => {
    const c = ctx({ pid: 7 });
    const line = push("process_line", { pid: 7, line: "hi" });
    const done = push("background_process_done", { pid: 7 });
    expect(isOurs(RULES.stop_background_process, c, line, "stop_background_process")).toBe(true);
    expect(isOurs(RULES.stop_background_process, c, push("process_line", { pid: 8 }), "stop_background_process")).toBe(false);
    expect(RULES.stop_background_process.last(c, done)).toBe(true);
  });

  it("approve_plan: correlates plan_decided by run_id", () => {
    const c = ctx({ run_id: "r1" });
    expect(isOurs(RULES.approve_plan, c, push("plan_decided", { run_id: "r1" }), "approve_plan")).toBe(true);
    expect(isOurs(RULES.approve_plan, c, push("plan_decided", { run_id: "r2" }), "approve_plan")).toBe(false);
  });

  it("cancel_run: the turn's info then the stream_end of that stream", () => {
    const c = ctx({}, undefined, "s1");
    const info: WireMessage = { type: "info", id: "run-1", session_id: "s1" };
    const end: WireMessage = { type: "stream_end", id: "run-1", session_id: "s1" };
    const elsewhere: WireMessage = { type: "info", id: "other-req", session_id: "s1" };
    expect(isOurs(RULES.cancel_run, c, info, "cancel_run")).toBe(true);
    expect(RULES.cancel_run.last(c, end)).toBe(true);
    expect(isOurs(RULES.cancel_run, ctx({}, undefined, "s1"), elsewhere, "cancel_run")).toBe(false);
  });

  it("run_shell: ends on the result unless it was backgrounded", () => {
    expect(RULES.run_shell.endsWith({ ...ctx({}), hasResult: true, result: { backgrounded: false } })).toBe(true);
    expect(RULES.run_shell.endsWith({ ...ctx({}), hasResult: true, result: { backgrounded: true } })).toBe(false);
    expect(RULES.run_shell.last(ctx({}), push("background_process_done", {}))).toBe(true);
  });

  it("login: correlates by flow_id and ends on login_result", () => {
    const c = ctx({}, { flow_id: "f1" });
    expect(isOurs(RULES.login, c, push("login_status", { flow_id: "f1" }), "login")).toBe(true);
    expect(isOurs(RULES.login, c, push("login_status", { flow_id: "f2" }), "login")).toBe(false);
    expect(RULES.login.last(c, push("login_result", { flow_id: "f1" }))).toBe(true);
  });

  it("attach_session / scheduler / visualization / notifications hold together", () => {
    const c = ctx({ action: "go", params: {} }, undefined, "s1");
    expect(RULES.attach_session.last(c, { type: "stream_end" })).toBe(true);
    expect(isOurs(RULES.start_scheduler, c, { type: "push_notification", channel: "scheduler_started", payload: {}, session_id: "s1" }, "start_scheduler")).toBe(true);
    expect(isOurs(RULES.dispatch_visualization_action, c, { type: "push_notification", channel: "visualization_action_dispatched", payload: { action: "go", params: {} }, session_id: "s1" }, "dispatch_visualization_action")).toBe(true);
    expect(RULES.notifications_list.endsWith({ ...c, hasResult: true })).toBe(true);
  });

  it("an rpc_response is never one of a call's events", () => {
    expect(isOurs(RULES.run_workflow, ctx({}, { workflow_run_id: "wf1" }), { type: "rpc_response", id: "req-1" }, "run_workflow")).toBe(false);
  });
});

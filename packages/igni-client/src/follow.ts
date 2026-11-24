// How a followed call's events are told from every other call's.
//
// igni broadcasts: every client sees every session's messages. A `Call` picks
// out its own by what they carry — a workflow run's id, a process's pid, a
// plan's run id — and knows when there are no more. One rule per followed
// method, here; the generated METHODS table says which methods are followed.
//
// What the events carry is the contract's business (the per-method `correlate`
// and `streams`); this reads that and applies it. What the contract cannot say
// — when a stream has no more to come — is what each rule adds.

import { METHODS } from "./api.generated.js";
import type { Correlation } from "./methodSpec.js";
import type { WireMessage } from "./wire.js";

const PUSH_PREFIX = "push_notification:";

/** What a rule reads: the call's arguments, its session, its request id, its result. */
export interface Context {
  args: Record<string, unknown>;
  sessionId: string;
  requestId: string;
  result: Record<string, unknown> | null;
  hasResult: boolean;
  ended: boolean;
  sentElsewhere: (id: string) => boolean;
  streamId: string | null;
}

export function newContext(
  args: Record<string, unknown>,
  sessionId: string,
  requestId: string,
  sentElsewhere: (id: string) => boolean,
): Context {
  return {
    args,
    sessionId,
    requestId,
    result: null,
    hasResult: false,
    ended: false,
    sentElsewhere,
    streamId: null,
  };
}

type Test = (context: Context, event: WireMessage) => boolean;

/** Which events are this call's, and when there are no more. */
export interface Rule {
  match: Test;
  last: Test;
  endsWith: (context: Context) => boolean;
  needsResult: boolean;
}

function rule(partial: Partial<Rule>): Rule {
  return {
    match: partial.match ?? (() => true),
    last: partial.last ?? (() => false),
    endsWith: partial.endsWith ?? (() => false),
    needsResult: partial.needsResult ?? false,
  };
}

// ── Reading places the contract names ──

function channel(event: WireMessage, ...names: string[]): boolean {
  return (
    event.type === "push_notification" &&
    typeof event.channel === "string" &&
    names.includes(event.channel)
  );
}

function payload(event: WireMessage, key: string): unknown {
  const data = (event as { payload?: unknown }).payload;
  if (data && typeof data === "object") {
    return (data as Record<string, unknown>)[key];
  }
  return undefined;
}

function arg(context: Context, key: string): unknown {
  return context.args[key];
}

function result(context: Context, key: string): unknown {
  return context.result ? context.result[key] : undefined;
}

function place(event: WireMessage, where: string): unknown {
  if (where.startsWith("payload.")) {
    return payload(event, where.slice("payload.".length));
  }
  if (where === "channel") {
    return (event as { channel?: unknown }).channel;
  }
  return (event as Record<string, unknown>)[where];
}

function callPlace(context: Context, where: string): unknown {
  if (where === "request.id") {
    return context.requestId;
  }
  if (where === "request.session_id") {
    return context.sessionId;
  }
  if (where.startsWith("args.")) {
    return arg(context, where.slice("args.".length));
  }
  if (where.startsWith("result.")) {
    const field = where.slice("result.".length);
    return context.hasResult ? result(context, field) : arg(context, field);
  }
  return undefined;
}

function correlated(correlation: Correlation, context: Context, event: WireMessage): boolean {
  if (correlation.equals) {
    return place(event, correlation.by) === correlation.equals;
  }
  if (!correlation.source) {
    return true;
  }
  const wanted = callPlace(context, correlation.source);
  if (wanted === undefined || wanted === null) {
    return false;
  }
  return place(event, correlation.by) === wanted;
}

function causedBy(causes: string[], event: WireMessage): boolean {
  const chan = (event as { channel?: unknown }).channel;
  for (const cause of causes) {
    if (cause.startsWith(PUSH_PREFIX)) {
      if (chan === cause.slice(PUSH_PREFIX.length)) {
        return true;
      }
    } else if (event.type === cause) {
      return true;
    }
  }
  return false;
}

function correlationOf(method: string): Correlation | null {
  return METHODS[method]?.correlate ?? null;
}

function causesOf(method: string): string[] {
  const spec = METHODS[method];
  if (!spec) {
    return [];
  }
  return [...spec.streams, ...spec.mayStream];
}

/** Whether `event` is `method`'s own, as the contract and the rule say. */
export function isOurs(r: Rule, context: Context, event: WireMessage, method: string): boolean {
  if (event.type === "rpc_response") {
    return false;
  }
  const correlation = correlationOf(method);
  if (correlation !== null) {
    const causes = causesOf(method);
    if (causes.length && !causedBy(causes, event)) {
      return false;
    }
    if (!correlated(correlation, context, event)) {
      return false;
    }
  }
  return r.match(context, event);
}

// ── Rules, by their shape ──

function sameSession(context: Context, event: WireMessage): boolean {
  return Boolean(context.sessionId) && event.session_id === context.sessionId;
}

const WORKFLOW_ENDS = ["workflow_completed", "workflow_failed"];

function workflowMatch(runId: (c: Context) => unknown): Test {
  return (context, event) =>
    channel(event, "workflow_event") && payload(event, "workflow_run_id") === runId(context);
}

function workflowLast(runId: (c: Context) => unknown): Test {
  const match = workflowMatch(runId);
  return (context, event) =>
    match(context, event) && WORKFLOW_ENDS.includes(String(payload(event, "type")));
}

function processMatch(context: Context, event: WireMessage): boolean {
  return (
    channel(event, "process_line", "process_exited", "background_process_done") &&
    payload(event, "pid") === arg(context, "pid")
  );
}

function planDecided(context: Context, event: WireMessage): boolean {
  return channel(event, "plan_decided") && payload(event, "run_id") === arg(context, "run_id");
}

function visualization(context: Context, event: WireMessage): boolean {
  return (
    channel(event, "visualization_action_dispatched") &&
    sameSession(context, event) &&
    payload(event, "action") === arg(context, "action")
  );
}

function streamEnd(_context: Context, event: WireMessage): boolean {
  return event.type === "stream_end";
}

function ofTheStoppedTurn(context: Context, event: WireMessage): boolean {
  const id = String((event as { id?: unknown }).id ?? "");
  if (id && context.sentElsewhere(id)) {
    return false;
  }
  if (event.type === "info") {
    context.streamId = id;
    return true;
  }
  return context.streamId !== null && id === context.streamId;
}

const PLAN = rule({ match: planDecided, last: planDecided, endsWith: (c) => result(c, "ok") === false });

const RUN_WORKFLOW = rule({
  match: workflowMatch((c) => result(c, "workflow_run_id")),
  last: workflowLast((c) => result(c, "workflow_run_id")),
  needsResult: true,
});

const CANCEL_WORKFLOW = rule({
  match: workflowMatch((c) => arg(c, "workflow_run_id")),
  last: workflowLast((c) => arg(c, "workflow_run_id")),
  endsWith: (c) => result(c, "cancelled") === false,
});

const STOP_PROCESS = rule({
  match: processMatch,
  last: (c, e) => processMatch(c, e) && channel(e, "background_process_done"),
  endsWith: (c) => result(c, "killed") === false,
});

const VISUALIZATION = rule({ match: visualization, last: visualization });

const SCHEDULER = rule({
  match: (c, e) => channel(e, "scheduler_started", "scheduler_completed") && sameSession(c, e),
});

const LOGIN = rule({
  match: (_c, e) => channel(e, "login_status", "login_result"),
  last: (_c, e) => channel(e, "login_result"),
  needsResult: true,
});

const ATTACH_SESSION = rule({ last: streamEnd, endsWith: (c) => c.ended });

const CANCEL_RUN = rule({
  match: ofTheStoppedTurn,
  last: streamEnd,
  endsWith: (c) => result(c, "cancelled") === false,
});

const SCHEDULED_TASK = rule({ endsWith: (c) => c.hasResult });
const NOTIFICATIONS = rule({ endsWith: (c) => c.hasResult });
const SESSION_STATES = rule({ endsWith: (c) => c.hasResult });
const WORKSPACE_TRUST = rule({ needsResult: true, endsWith: (c) => c.hasResult });
const WINDOW_MODEL = rule({ endsWith: (c) => c.hasResult });
const RUN_SHELL = rule({
  needsResult: true,
  last: (_c, e) => channel(e, "background_process_done"),
  endsWith: (c) => c.hasResult && result(c, "backgrounded") !== true,
});

/** The rule of every followed method, by wire name. */
export const RULES: Record<string, Rule> = {
  approve_plan: PLAN,
  dismiss_plan: PLAN,
  run_workflow: RUN_WORKFLOW,
  cancel_workflow: CANCEL_WORKFLOW,
  stop_background_process: STOP_PROCESS,
  dispatch_visualization_action: VISUALIZATION,
  start_scheduler: SCHEDULER,
  login: LOGIN,
  attach_session: ATTACH_SESSION,
  cancel_run: CANCEL_RUN,
  execute_scheduled_task: SCHEDULED_TASK,
  notifications_list: NOTIFICATIONS,
  notifications_mark_read: NOTIFICATIONS,
  clear_cloud_credentials: NOTIFICATIONS,
  mark_session_seen: SESSION_STATES,
  set_workspace_trust: WORKSPACE_TRUST,
  window_model: WINDOW_MODEL,
  run_shell: RUN_SHELL,
};

export const DEFAULT_RULE = rule({});

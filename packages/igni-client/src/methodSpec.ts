// The shape of the generated METHODS table, and the contract's correlation.
//
// api.generated.ts fills this in from igni-core's RPC contract; the hand-written
// core (calls, follow) reads it.

/** How a client tells which of the messages igni streams are a call's own. */
export interface Correlation {
  /** Where in the streamed message the value is: `id`, `session_id`, `run_id`, `payload.<field>` or `channel`. */
  by: string;
  /** Where in the call the value comes from: `request.id`, `args.<field>`, `result.<field>`. */
  source?: string;
  /** A fixed value the message must carry. */
  equals?: string;
}

/** One method, as igni-core's contract describes it. */
export interface MethodSpec {
  /** Its name on the wire. */
  wire: string;
  /** Where it lives on the client: `igni.processes.tail`, `session.plan.approve`. */
  python: string;
  /** `igni` (igni as a whole) or `session` (one session). */
  scope: "igni" | "session";
  /** Who may call it: `client`, `approver` or `window`. */
  access: "client" | "approver" | "window";
  /** `rpc_response`, or `message` when igni answers with a message of its own. */
  reply: "rpc_response" | "message";
  /** The messages and push channels it streams. */
  streams: string[];
  /** The push channels it may cause while it runs, beyond those it streams. */
  mayStream: string[];
  /** How long it takes: `instant`, `io`, `network`, `long` or `person`. */
  duration: string;
  /** A timeout that leaves a healthy call room; `null`: none (wait as long as it takes). */
  timeoutSeconds: number | null;
  /** How its events are told from every other call's; `null` where the contract says nothing. */
  correlate: Correlation | null;
  /** Whether its `Call` follows those. */
  followed: boolean;
}

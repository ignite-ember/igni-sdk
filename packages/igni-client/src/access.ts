// Which of igni's methods a connection reaches, by how it attached.
//
// igni-core's contract says, per method, who may call it (`client`, `approver`,
// `window`). A connection's standing is decided when it attaches. igni-client
// refuses a call the connection cannot make before sending it, with
// `AccessRefused`, wherever it knows the standing; where it does not, it sends
// the call and igni decides.

import { AccessRefused } from "./errors.js";

export type Access = "client" | "approver" | "window";
export type Standing = "program" | "approver" | "window" | "unknown";

/** What each standing reaches. `null` (unknown) is left for igni to check. */
export const REACHES: Record<Standing, ReadonlySet<Access> | null> = {
  program: new Set<Access>(["client"]),
  approver: new Set<Access>(["client", "approver"]),
  window: new Set<Access>(["client", "approver", "window"]),
  unknown: null,
};

const WHY: Record<string, string> = {
  approver:
    "only igni's window, or a program holding an approver token the window minted, " +
    "may do this (new Local({ approverToken }))",
  window: "only igni's window may do this",
};

/** Throw `AccessRefused` when a connection of `standing` cannot call `method`. */
export function check(method: string, access: string, standing: Standing): void {
  const reached = REACHES[standing];
  if (reached === null || reached.has(access as Access)) {
    return;
  }
  throw new AccessRefused(method, WHY[access] ?? `a ${access} call`);
}

/** The message an approval's answer travels in, as igni names it when it refuses. */
export const ANSWER = "hitl_response_batch";

/** Throw `AccessRefused` when a connection of `standing` cannot send this answer. */
export function checkAnswer(standing: Standing, choices: Iterable<string> = []): void {
  const reached = REACHES[standing];
  if (reached === null) {
    return;
  }
  if (!reached.has("approver")) {
    throw new AccessRefused(
      ANSWER,
      "a program answers approval requests only with an approver token, which the " +
        "person makes in igni's window (new Local({ approverToken }))",
    );
  }
  if (!reached.has("window") && [...choices].some((choice) => choice !== "once")) {
    throw new AccessRefused(ANSWER, "an approver answers once; only igni's window saves a rule");
  }
}

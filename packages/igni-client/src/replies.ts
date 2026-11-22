// What `Session.ask()` returns: a run's whole answer, gathered from its stream.

import { ApprovalRequested, Approver } from "./approvals.js";
import { CredentialRefused, RunFailed } from "./errors.js";
import type { Event } from "./events.js";
import type {
  ContentDelta,
  RunCompleted,
  ToolCompleted,
  VmCredentialState,
} from "./models.generated.js";
import type { RunItem } from "./runs.js";

/** The answer, and what happened on the way. */
export class Reply {
  text = "";
  thinking = "";
  tools: ToolCompleted[] = [];
  /** The main run's completion, with its token counts and duration. */
  completed: RunCompleted | null = null;

  toString(): string {
    return this.text;
  }

  /** Follow `events` to their end, answering each approval with `approver`. */
  static async collect(
    events: AsyncIterable<RunItem>,
    approver: Approver,
    credential: () => VmCredentialState | null = () => null,
    where = "igni",
  ): Promise<Reply> {
    const reply = new Reply();
    const text: string[] = [];
    const thinking: string[] = [];
    let started = false;
    let unstarted: Event | null = null;
    for await (const event of events) {
      if (event instanceof ApprovalRequested) {
        await approver.answer(event);
        continue;
      }
      switch (event.type) {
        case "run_started":
          started = true;
          break;
        case "error":
          if (unstarted === null) {
            unstarted = event;
          }
          break;
        case "content_delta": {
          const delta = event as ContentDelta;
          (delta.is_thinking ? thinking : text).push(delta.text ?? "");
          break;
        }
        case "tool_completed":
          reply.tools.push(event as ToolCompleted);
          break;
        case "run_completed":
          if (!(event as RunCompleted).parent_run_id) {
            reply.completed = event as RunCompleted;
          }
          break;
        case "run_error": {
          const failed = new RunFailed(String((event as { error?: unknown }).error ?? "") || "the run failed");
          const known = credential();
          const refused = known === null ? null : CredentialRefused.of(known.state ?? "", known.message ?? "", where);
          throw refused ?? failed;
        }
      }
    }
    if (unstarted !== null && !started) {
      throw new RunFailed(String((unstarted as { text?: unknown }).text ?? "") || "igni started no run for the prompt");
    }
    reply.text = text.join("");
    reply.thinking = thinking.join("");
    return reply;
  }
}

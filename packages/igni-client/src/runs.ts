// A run: one prompt, followed from the first token to the end, approvals included.
//
// A run is a stream of events across every stream it opens: the prompt's, and one
// for each answered approval.

import * as access from "./access.js";
import { ApprovalRequested } from "./approvals.js";
import { AsyncQueue } from "./asyncQueue.js";
import type { Connection } from "./connection.js";
import { NotAllowed } from "./errors.js";
import type { Event } from "./events.js";
import type { HitlDecision, RunPaused } from "./models.generated.js";
import { Interruption } from "./routing.js";
import type { StreamItem } from "./routing.js";
import type { WireMessage } from "./wire.js";

export type RunItem = Event | ApprovalRequested;

/** Follows one run across the streams it opens: the prompt's, and each approval's. */
export class Run {
  private readonly queue = new AsyncQueue<StreamItem>();
  private readonly open = new Set<string>();
  private readonly answers = new Set<string>();
  private pending: ApprovalRequested | null = null;

  constructor(
    private readonly conn: Connection,
    private readonly sessionId: string,
  ) {}

  async *stream(frame: WireMessage): AsyncGenerator<RunItem> {
    try {
      await this.startStream(frame);
      while (this.open.size) {
        const item = await this.queue.get();
        if (item instanceof Interruption) {
          throw item.error;
        }
        if (item.type === "error" && item.id && this.answers.has(item.id)) {
          throw new NotAllowed(String((item as { text?: unknown }).text ?? "") || "igni refused the approval");
        }
        if (item.type === "stream_end") {
          const id = item.id ?? "";
          this.open.delete(id);
          this.conn.router.closeStream(id);
          continue;
        }
        if (item.type === "run_paused") {
          this.pending = new ApprovalRequested(item as unknown as RunPaused, (d) => this.answer(d));
          yield this.pending;
          continue;
        }
        if (item.type === "requirement_details" && this.pending) {
          const rid = (item as { requirement_id?: string }).requirement_id;
          for (const requirement of this.pending.requirements) {
            if (requirement.requirement_id === rid) {
              requirement.details = String((item as { details?: unknown }).details ?? "");
              requirement.details_pending = false;
            }
          }
        }
        yield item as unknown as Event;
      }
    } finally {
      for (const id of this.open) {
        this.conn.router.closeStream(id);
      }
      this.open.clear();
    }
  }

  private async startStream(frame: WireMessage): Promise<void> {
    this.conn.router.openStream(frame.id ?? "", this.queue);
    this.open.add(frame.id ?? "");
    await this.conn.send(frame);
  }

  private async answer(decisions: HitlDecision[]): Promise<void> {
    access.checkAnswer(
      this.conn.target.standing,
      decisions.map((d) => d.choice ?? "once"),
    );
    const requestId = this.conn.router.newId("hitl");
    this.answers.add(requestId);
    await this.startStream({
      type: "hitl_response_batch",
      id: requestId,
      session_id: this.sessionId,
      decisions,
    });
  }
}

/** How to answer a pause seen outside a run of this client's (Session.events()). */
export function answerElsewhere(
  conn: Connection,
  sessionId: string,
): (decisions: HitlDecision[]) => Promise<void> {
  return async (decisions) => {
    access.checkAnswer(
      conn.target.standing,
      decisions.map((d) => d.choice ?? "once"),
    );
    await conn.send({
      type: "hitl_response_batch",
      id: conn.router.newId("hitl"),
      session_id: sessionId,
      decisions,
    });
  };
}

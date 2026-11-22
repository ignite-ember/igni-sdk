// Approvals: a paused run's tool calls, and the answers that resume it.
//
// When the agent wants a tool that needs a person's yes, igni pauses the run and
// the stream yields an `ApprovalRequested`. Answer it in the loop — `allow()`,
// `deny()` or `decide()` — and the same loop carries on with the resumed run.
// A loop that ends without answering leaves the run waiting on igni's side.

import { ApprovalRequired } from "./errors.js";
import type { HitlDecision, Requirement, RunPaused } from "./models.generated.js";

/** How far an allowed call's answer reaches. */
export type Choice = "once" | "always" | "similar";
/** How far any answer reaches: a `Choice`, or `deny`. */
export type Scope = "once" | "always" | "similar" | "deny";

/** The answer to one tool call waiting for approval. */
export class Decision {
  constructor(
    readonly action: "confirm" | "reject",
    readonly choice: Scope = "once",
  ) {}

  /** Let the call run. `always`/`similar` save a permission rule. */
  static allow(choice: Choice = "once"): Decision {
    return new Decision("confirm", choice);
  }

  /** Refuse the call. `remember` saves a rule refusing it from now on. */
  static deny(remember = false): Decision {
    return new Decision("reject", remember ? "deny" : "once");
  }

  frame(requirementId: string): HitlDecision {
    return { type: "hitl_decision", requirement_id: requirementId, action: this.action, choice: this.choice };
  }
}

export type Answer = boolean | Decision;
export type Policy = boolean | ((req: Requirement) => Answer | Promise<Answer>);

type AnswerFn = (decisions: HitlDecision[]) => Promise<void>;

/** The run paused: these tool calls wait for a yes or a no. */
export class ApprovalRequested {
  readonly kind = "approvalRequested" as const;
  answered = false;
  private sending = false;

  constructor(
    readonly paused: RunPaused,
    private readonly answer: AnswerFn,
  ) {}

  get run_id(): string {
    return this.paused.run_id ?? "";
  }

  get requirements(): Requirement[] {
    return this.paused.requirements ?? [];
  }

  /** Let every call run. */
  async allow(choice: Choice = "once"): Promise<void> {
    await this.decide(new Map(this.requirements.map((r) => [r.requirement_id!, Decision.allow(choice)])));
  }

  /** Refuse every call. */
  async deny(remember = false): Promise<void> {
    await this.decide(
      new Map(this.requirements.map((r) => [r.requirement_id!, Decision.deny(remember)])),
    );
  }

  /** Answer each call by its `requirement_id`. Every one must be answered. */
  async decide(decisions: Map<string, Decision>): Promise<void> {
    if (this.answered || this.sending) {
      throw new Error("this approval was already answered");
    }
    const missing = this.requirements
      .map((r) => r.requirement_id ?? "")
      .filter((id) => !decisions.has(id));
    if (missing.length) {
      throw new Error(`every call needs an answer; missing ${JSON.stringify(missing)}`);
    }
    const frames = this.requirements.map((r) => decisions.get(r.requirement_id!)!.frame(r.requirement_id!));
    this.sending = true;
    try {
      await this.answer(frames);
    } finally {
      this.sending = false;
    }
    this.answered = true;
  }
}

/** Answers every approval a run asks for with one `Policy`, as `ask(approve)` does. */
export class Approver {
  constructor(private readonly policy: Policy | null | undefined) {}

  async answer(request: ApprovalRequested): Promise<void> {
    if (this.policy === null || this.policy === undefined) {
      throw new ApprovalRequired(request.requirements);
    }
    const decisions = new Map<string, Decision>();
    for (const requirement of request.requirements) {
      decisions.set(requirement.requirement_id!, await this.decision(this.policy, requirement));
    }
    await request.decide(decisions);
  }

  private async decision(policy: Policy, requirement: Requirement): Promise<Decision> {
    let answer: Answer;
    if (typeof policy === "boolean") {
      answer = policy;
    } else {
      answer = await policy(requirement);
    }
    if (answer instanceof Decision) {
      return answer;
    }
    return answer ? Decision.allow() : Decision.deny();
  }
}

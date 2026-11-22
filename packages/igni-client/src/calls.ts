// Calling igni's methods: `Caller` sends them, `Call` follows the ones that stream.
//
// Every generated method goes through a `Caller`. A method that streams returns
// a `Call`: `await call` sends it and resolves its result; `for await (const ev
// of call)` sends it and yields this call's events, told apart by what they
// carry (see follow.ts), ending when igni has no more to send for it.

import * as access from "./access.js";
import { AsyncQueue } from "./asyncQueue.js";
import type { Connection } from "./connection.js";
import type { WireMessage } from "./wire.js";
import { RpcError } from "./errors.js";
import { DEFAULT_RULE, RULES, isOurs, newContext } from "./follow.js";
import type { Context, Rule } from "./follow.js";
import { METHODS } from "./api.generated.js";
import { Interruption } from "./routing.js";
import type { StreamItem } from "./routing.js";

/** A marker put on a `Call`'s queue when its result has settled. */
const SETTLED = Symbol("settled");

/** Calls igni's methods for one session — or, with no session, for igni as a whole. */
export class Caller {
  constructor(
    readonly conn: Connection,
    readonly sessionId = "",
  ) {}

  get clientId(): string {
    return this.conn.clientId;
  }

  /** An id of this client's own making, for a call that takes one. */
  newId(prefix: string): string {
    return this.conn.router.newId(prefix);
  }

  /** Call `method` with `values` and read its answer. */
  async rpc<R>(method: string, values: Record<string, unknown>): Promise<R> {
    access.check(method, METHODS[method]?.access ?? "client", this.conn.target.standing);
    return this.answer<R>(method, values);
  }

  /** A `Call` of `method`: await it for the result, or iterate it to follow its events too. */
  follow<R, E>(method: string, values: Record<string, unknown>): Call<R, E> {
    access.check(method, METHODS[method]?.access ?? "client", this.conn.target.standing);
    return new Call<R, E>(this, method, values, RULES[method] ?? DEFAULT_RULE);
  }

  /** Send the call and read what igni answers. */
  async answer<R>(method: string, values: Record<string, unknown>, requestId = ""): Promise<R> {
    const spec = METHODS[method];
    const reply = await this.conn.ask(method, values, {
      sessionId: this.sessionId,
      timeout: spec ? spec.timeoutSeconds : undefined,
      requestId,
      reply: spec?.reply ?? "rpc_response",
    });
    return read<R>(method, reply);
  }

  /** Send a message igni answers nothing to. */
  async sendMessage(method: string, values: Record<string, unknown>): Promise<void> {
    await this.conn.send(this.message(method, values, ""));
  }

  /** Send a message igni answers with a message of its own, carrying its id. */
  async request<R>(method: string, values: Record<string, unknown>): Promise<R> {
    const requestId = this.conn.router.newId("msg");
    const frame = this.message(method, values, requestId);
    const answer = await this.conn.exchange(frame, requestId, method);
    if (answer.type === "error") {
      throw RpcError.of(method, String((answer as { text?: unknown }).text ?? ""));
    }
    return read<R>(method, answer);
  }

  private message(method: string, values: Record<string, unknown>, requestId: string): WireMessage {
    const frame: WireMessage = { type: method, ...values };
    if (this.sessionId) {
      frame.session_id = this.sessionId;
    }
    if (requestId) {
      frame.id = requestId;
    }
    return frame;
  }
}

/** The result in `reply`: an `rpc_response`'s, or the message igni answered with. */
export function read<R>(method: string, reply: WireMessage): R {
  if (reply.type === "error") {
    throw RpcError.of(method, String((reply as { text?: unknown }).text ?? ""));
  }
  if (reply.type === "rpc_response") {
    return (reply as { result?: unknown }).result as R;
  }
  return reply as unknown as R;
}

/** One call of a method that streams: awaitable for its result, iterable for its events. */
export class Call<R, E> implements PromiseLike<R> {
  private readonly requestId: string;
  private readonly context: Context;
  private queue: AsyncQueue<StreamItem | typeof SETTLED> | null = null;
  private task: Promise<R> | null = null;
  private taskResult: R | undefined;
  private taskError: unknown;
  private taskFailed = false;

  constructor(
    private readonly caller: Caller,
    readonly method: string,
    private readonly values: Record<string, unknown>,
    private readonly rule: Rule,
  ) {
    const router = caller.conn.router;
    this.requestId = router.newId("rpc");
    this.context = newContext(
      values,
      caller.sessionId,
      this.requestId,
      (other) => other !== this.requestId && router.asked(other),
    );
  }

  /** The call's result: sent now when the call was not iterated, else awaited. */
  async result(): Promise<R> {
    if (this.task === null) {
      return this.caller.answer<R>(this.method, this.values, this.requestId);
    }
    return this.task;
  }

  then<TResult1 = R, TResult2 = never>(
    onfulfilled?: ((value: R) => TResult1 | PromiseLike<TResult1>) | null,
    onrejected?: ((reason: unknown) => TResult2 | PromiseLike<TResult2>) | null,
  ): PromiseLike<TResult1 | TResult2> {
    return this.result().then(onfulfilled, onrejected);
  }

  async *[Symbol.asyncIterator](): AsyncIterator<E> {
    if (this.task === null) {
      this.start();
    }
    const queue = this.queue!;
    const ready: E[] = [];
    const held: WireMessage[] = [];
    let settled = false;
    let done = false;

    const consider = (event: WireMessage): void => {
      if (done || !isOurs(this.rule, this.context, event, this.method)) {
        return;
      }
      ready.push(event as unknown as E);
      if (this.rule.last(this.context, event)) {
        this.context.ended = true;
        done = true;
      }
    };
    const take = (item: StreamItem): void => {
      if (item instanceof Interruption) {
        done = true;
        throw item.error;
      }
      if (this.rule.needsResult && !settled) {
        held.push(item);
        return;
      }
      consider(item);
    };
    const settle = (): void => {
      settled = true;
      if (this.taskFailed) {
        done = true;
        throw this.taskError;
      }
      this.context.result = (this.taskResult ?? null) as Record<string, unknown> | null;
      this.context.hasResult = true;
      const pending = held.splice(0);
      for (const event of pending) {
        consider(event);
      }
      if (this.rule.endsWith(this.context)) {
        done = true;
      }
    };

    try {
      for (;;) {
        if (ready.length) {
          yield ready.shift()!;
          continue;
        }
        if (done) {
          return;
        }
        const item = await queue.get();
        if (item === SETTLED) {
          if (!settled) {
            settle();
          }
          continue;
        }
        take(item);
      }
    } finally {
      this.caller.conn.router.unfollow(queue as unknown as AsyncQueue<StreamItem>);
    }
  }

  private start(): void {
    const queue = this.caller.conn.router.follow() as unknown as AsyncQueue<
      StreamItem | typeof SETTLED
    >;
    this.queue = queue;
    this.task = this.caller.answer<R>(this.method, this.values, this.requestId);
    this.task.then(
      (value) => {
        this.taskResult = value;
        queue.put(SETTLED);
      },
      (error: unknown) => {
        this.taskFailed = true;
        this.taskError = error;
        queue.put(SETTLED);
      },
    );
  }
}

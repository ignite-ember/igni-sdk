// Where each message from igni goes: the call waiting for it, a run's stream,
// every listener.
//
// igni sends every message to every client attached to it, so nothing here
// assumes a message is for us: a reply is matched by the `id` of the request it
// answers, and everything goes to whoever listens.

import { AsyncQueue, Deferred } from "./asyncQueue.js";
import type { IgniClientError } from "./errors.js";
import type { WireMessage } from "./wire.js";

/** Put on a stream's queue when its run can no longer be followed. */
export class Interruption {
  constructor(readonly error: IgniClientError) {}
}

export type StreamItem = WireMessage | Interruption;

/** The requests in flight, the streams open and the listeners, by request id. */
export class Router {
  /** How many of the latest requests' ids `asked` remembers. */
  static readonly ASKED_KEPT = 1024;

  private readonly tag = randomTag();
  private ids = 0;
  private readonly waiting = new Map<string, Deferred<WireMessage>>();
  private readonly replies = new Map<string, string>();
  private readonly streams = new Map<string, AsyncQueue<StreamItem>>();
  private readonly listeners = new Set<AsyncQueue<WireMessage>>();
  private readonly followers = new Set<AsyncQueue<StreamItem>>();
  private readonly askedIds: string[] = [];
  private readonly askedSet = new Set<string>();

  /** A request id no other client of the same igni sends: `rpc-1f2e3d4c-1`. */
  newId(prefix: string): string {
    this.ids += 1;
    return `${prefix}-${this.tag}-${this.ids}`;
  }

  // ── Calls ──

  expect(requestId: string, reply = "rpc_response"): Deferred<WireMessage> {
    const deferred = new Deferred<WireMessage>();
    this.waiting.set(requestId, deferred);
    this.replies.set(requestId, reply);
    this.remember(requestId);
    return deferred;
  }

  asked(requestId: string): boolean {
    return this.askedSet.has(requestId);
  }

  forget(requestId: string): void {
    this.waiting.delete(requestId);
    this.replies.delete(requestId);
  }

  private remember(requestId: string): void {
    if (!this.askedSet.has(requestId)) {
      this.askedSet.add(requestId);
      this.askedIds.push(requestId);
      while (this.askedIds.length > Router.ASKED_KEPT) {
        const dropped = this.askedIds.shift();
        if (dropped !== undefined) {
          this.askedSet.delete(dropped);
        }
      }
    }
  }

  // ── Streams and listeners ──

  openStream(requestId: string, queue?: AsyncQueue<StreamItem>): AsyncQueue<StreamItem> {
    const stream = queue ?? new AsyncQueue<StreamItem>();
    this.streams.set(requestId, stream);
    return stream;
  }

  closeStream(requestId: string): void {
    this.streams.delete(requestId);
  }

  listen(): AsyncQueue<WireMessage> {
    const queue = new AsyncQueue<WireMessage>();
    this.listeners.add(queue);
    return queue;
  }

  unlisten(queue: AsyncQueue<WireMessage>): void {
    this.listeners.delete(queue);
  }

  follow(): AsyncQueue<StreamItem> {
    const queue = new AsyncQueue<StreamItem>();
    this.followers.add(queue);
    return queue;
  }

  unfollow(queue: AsyncQueue<StreamItem>): void {
    this.followers.delete(queue);
  }

  // ── Delivering ──

  deliver(event: WireMessage): void {
    for (const queue of this.listeners) {
      queue.put(event);
    }
    for (const follower of this.followers) {
      follower.put(event);
    }
    const id = event.id;
    if (!id) {
      return;
    }
    const waiter = this.waiting.get(id);
    if (waiter && event.type !== "rpc_request" && this.isAnswer(id, event)) {
      waiter.resolve(event);
      return;
    }
    const stream = this.streams.get(id);
    if (stream) {
      stream.put(event);
    }
  }

  private isAnswer(requestId: string, event: WireMessage): boolean {
    if ((this.replies.get(requestId) ?? "rpc_response") === "rpc_response") {
      return event.type === "rpc_response" || event.type === "error";
    }
    return event.type !== "rpc_response";
  }

  /** End every call and run in flight: they cannot be followed any more. */
  interrupt(error: IgniClientError): void {
    for (const waiter of this.waiting.values()) {
      waiter.reject(error);
    }
    const item = new Interruption(error);
    for (const stream of this.streams.values()) {
      stream.put(item);
    }
    for (const follower of this.followers) {
      follower.put(item);
    }
  }
}

function randomTag(): string {
  return Math.floor(Math.random() * 0xffffffff)
    .toString(16)
    .padStart(8, "0");
}

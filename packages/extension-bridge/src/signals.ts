/**
 * The host signals a page handles: `bridge.on(signal, fn)`.
 *
 * The first handler of a signal subscribes to it; removing the last one
 * unsubscribes. A refused subscription is reported, not swallowed: to
 * the handler's `onRefused` when it gave one, to the console otherwise.
 */

import type { HostError, Signal } from "./hostModel.js";
import type { HostSignalMessage } from "./protocol.js";

/** Asks the host to start or stop sending one signal. */
export type SignalRequest = (
  op: "subscribe" | "unsubscribe",
  signal: string,
) => Promise<unknown>;

export class SignalSubscriptions {
  private readonly handlers = new Map<string, Set<(value: unknown) => void>>();

  constructor(private readonly request: SignalRequest) {}

  on<T>(
    signal: Signal<T>,
    fn: (value: T) => void,
    onRefused?: (error: HostError) => void,
  ): () => void {
    const wire = signal.name;
    let handlers = this.handlers.get(wire);
    if (handlers === undefined) {
      handlers = new Set();
      this.handlers.set(wire, handlers);
      this.request("subscribe", wire).catch((error: HostError) => {
        if (onRefused) onRefused(error);
        else
          console.warn(
            `igni bridge: subscribing to ${wire} failed: ${error.message}`,
          );
      });
    }
    const handler = fn as (value: unknown) => void;
    handlers.add(handler);
    return () => this.off(wire, handler);
  }

  /** Hand a signal the host sent to everything handling it. */
  deliver(message: HostSignalMessage): void {
    const handlers = this.handlers.get(message.signal);
    if (handlers === undefined) return;
    for (const fn of handlers) fn(message.value);
  }

  private off(wire: string, handler: (value: unknown) => void): void {
    const current = this.handlers.get(wire);
    if (current === undefined) return;
    current.delete(handler);
    if (current.size > 0) return;
    this.handlers.delete(wire);
    this.request("unsubscribe", wire).catch((error: HostError) => {
      console.warn(
        `igni bridge: unsubscribing from ${wire} failed: ${error.message}`,
      );
    });
  }
}

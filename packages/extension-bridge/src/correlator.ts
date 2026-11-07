/**
 * Requests the guest sent and is waiting on, matched to their replies by
 * id.
 *
 * Each kind of request the guest makes — an RPC call, a host-model
 * request, a service token — has its own `Correlator`, so a reply of
 * one kind can never settle a request of another.
 */

interface Waiter {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  /** `undefined` for a request with no limit (one the person answers). */
  timer: ReturnType<typeof setTimeout> | undefined;
}

export class Correlator {
  private readonly waiting = new Map<string, Waiter>();
  private counter = 0;

  /** `prefix` tells this correlator's ids apart from another's in a log. */
  constructor(private readonly prefix: string) {}

  /**
   * Send one request and wait for its reply.
   *
   * `timeoutMs` null waits for as long as the reply takes; otherwise the
   * request is given up on with `timedOut()` and a late reply is ignored.
   */
  send<T>(
    timeoutMs: number | null,
    timedOut: () => Error,
    post: (id: string) => void,
  ): Promise<T> {
    const id = `${this.prefix}${++this.counter}`;
    return new Promise<T>((resolve, reject) => {
      const timer =
        timeoutMs === null
          ? undefined
          : setTimeout(() => {
              this.waiting.delete(id);
              reject(timedOut());
            }, timeoutMs);
      this.waiting.set(id, {
        resolve: resolve as (value: unknown) => void,
        reject,
        timer,
      });
      post(id);
    });
  }

  /** The reply to `id` succeeded. */
  resolve(id: string, value: unknown): void {
    this.take(id)?.resolve(value);
  }

  /** The reply to `id` refused. */
  reject(id: string, error: Error): void {
    this.take(id)?.reject(error);
  }

  /**
   * Stop waiting on `id`. An id nobody is waiting on is either a late
   * reply to something that timed out, or noise; either way there is no
   * one to tell.
   */
  private take(id: string): Waiter | undefined {
    const waiter = this.waiting.get(id);
    if (waiter === undefined) return undefined;
    this.waiting.delete(id);
    clearTimeout(waiter.timer);
    return waiter;
  }
}

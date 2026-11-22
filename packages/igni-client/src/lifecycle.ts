// Where the connection to igni is: opening, open, down, failed for good, or closed.

import { Deferred, sleep } from "./asyncQueue.js";
import { Unavailable } from "./errors.js";
import type { IgniClientError } from "./errors.js";
import type { Welcome } from "./models.generated.js";
import type { Socket } from "./socket.js";

export enum Phase {
  Down = "down",
  Opening = "opening",
  Open = "open",
  Failed = "failed",
  Closed = "closed",
}

/** One socket opened to igni, and the `welcome` it waits for. */
export class Link {
  readonly welcomed = new Deferred<Welcome>();
  constructor(readonly socket: Socket) {}
}

/** The connection's phase, the latest socket, and — once it failed — why. */
export class Lifecycle {
  phase = Phase.Down;
  link: Link | null = null;
  failure: IgniClientError | null = null;
  private open = new Deferred<void>();

  opening(link: Link): void {
    this.phase = Phase.Opening;
    this.link = link;
  }

  opened(): void {
    this.phase = Phase.Open;
    this.failure = null;
    this.open.resolve();
  }

  /** `link` closed. True when it was the live one. */
  lost(link: Link): boolean {
    if (this.link !== link || (this.phase !== Phase.Opening && this.phase !== Phase.Open)) {
      return false;
    }
    this.phase = Phase.Down;
    this.open = new Deferred<void>();
    return true;
  }

  failed(error: IgniClientError): void {
    this.phase = Phase.Failed;
    this.failure = error;
  }

  close(): Link | null {
    this.phase = Phase.Closed;
    return this.link;
  }

  /** The latest link's `welcome`, while it has not arrived. */
  pendingWelcome(): Deferred<Welcome> | null {
    if (this.link === null || this.link.welcomed.done) {
      return null;
    }
    return this.link.welcomed;
  }

  /** The open socket, waiting up to `timeout` seconds while it is being opened again. */
  async socket(timeout: number, where: string): Promise<Socket> {
    if (this.failure !== null && this.phase !== Phase.Open) {
      throw this.failure;
    }
    if (this.phase === Phase.Open && this.link !== null) {
      return this.link.socket;
    }
    if (this.phase === Phase.Closed) {
      throw new Unavailable(`${where} was closed by the client`);
    }
    const timedOut = Symbol("timeout");
    const result = await Promise.race([
      this.open.promise.then(() => undefined),
      sleep(timeout).then(() => timedOut),
    ]);
    if (result === timedOut || this.phase !== Phase.Open || this.link === null) {
      throw this.failure ?? new Unavailable(`${where} is not connected`);
    }
    return this.link.socket;
  }
}

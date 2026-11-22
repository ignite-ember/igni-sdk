// `IgniClient`: one connection to one igni, and everything done through it.

import { IgniApi } from "./api.generated.js";
import { Backoff } from "./backoff.js";
import { Caller } from "./calls.js";
import { Commands } from "./commands.js";
import type { Me } from "./commands.js";
import { Connection } from "./connection.js";
import type { Event } from "./events.js";
import type { VmCredentialState } from "./models.generated.js";
import { Router } from "./routing.js";
import { Sessions } from "./sessions.js";
import { signIn, type SignedIn } from "./signIn.js";
import { Fleet, requireFleet, type Target } from "./targets.js";

/** A connection to one igni — a producer's in Fleet, or one on this machine. */
export class IgniClient extends IgniApi {
  /** igni's sessions: create, open, list — and `attach`, igni's own call. */
  readonly sessions: Sessions;
  readonly target: Target;
  private readonly conn: Connection;
  private commandsValue: Commands | null = null;

  constructor(target: Target, opts: { backoff?: Backoff } = {}) {
    const conn = new Connection(target, opts.backoff ?? new Backoff(), new Router());
    super(new Caller(conn));
    this.target = target;
    this.conn = conn;
    this.sessions = new Sessions(conn);
    this.conn.onResync(() => this.sessions.reattach());
  }

  /** Open the connection. */
  async connect(): Promise<this> {
    await this.conn.open();
    return this;
  }

  async close(): Promise<void> {
    await this.conn.close();
  }

  async [Symbol.asyncDispose](): Promise<void> {
    await this.close();
  }

  /** igni's name for this connection; its own messages carry it. */
  get clientId(): string {
    return this.conn.clientId;
  }

  /** Shell commands in the VM, through Fleet's gateway. Not available for a local igni. */
  get commands(): Commands {
    if (this.commandsValue === null) {
      this.commandsValue = new Commands(requireFleet(this.target, "commands"));
    }
    return this.commandsValue;
  }

  /** What igni on a Fleet VM last said of its own credential, or `null` before it said anything. */
  get vmCredential(): VmCredentialState | null {
    return this.conn.vmCredential;
  }

  /** Who the gateway says this client is — producer, organisation, group — and its VM's state. */
  async me(): Promise<Me> {
    requireFleet(this.target, "me");
    return this.commands.me();
  }

  /** Sign the person in to the igni in their Fleet VM again: the gateway's POST /v1/sign-in. */
  async signIn(): Promise<SignedIn> {
    return signIn(requireFleet(this.target, "sign_in"));
  }

  /** Every message igni sends from now on, from every session and every client attached. */
  async *events(): AsyncGenerator<Event> {
    const queue = this.conn.router.listen();
    try {
      for (;;) {
        yield (await queue.get()) as unknown as Event;
      }
    } finally {
      this.conn.router.unlisten(queue);
    }
  }
}

export { Fleet };

// One connection to igni's socket: requests out, messages routed back.
//
// igni sends every message to every client attached to it, so nothing here
// assumes a message is for us. Replies are matched by the `id` of the request
// they answer; everything else goes to whoever is listening.
//
// What can happen to the socket (Fleet only, unless noted):
//  * igni moved — a second `welcome` arrives on the same socket: runs and calls
//    in flight end with RunInterrupted and the client re-attaches its sessions.
//  * the socket closed — 1013 (busy) / 1011 / a dropped line are opened again
//    with a fresh token, backing off; 1008 is final (NotAllowed / GroupIsLocalOnly),
//    except `1008 token_expired`, which is opened again. A local igni that closed
//    has stopped (Unavailable).

import { Backoff } from "./backoff.js";
import { sleep } from "./asyncQueue.js";
import {
  AuthError,
  GROUP_LOCAL_ONLY,
  GroupIsLocalOnly,
  IgniClientError,
  NotAllowed,
  RpcError,
  RunInterrupted,
  TOKEN_EXPIRED,
  Unavailable,
  reasonToken,
} from "./errors.js";
import { parseEvent } from "./events.js";
import { Lifecycle, Link, Phase } from "./lifecycle.js";
import { NOT_FOR_CLIENTS } from "./api.generated.js";
import type { VmCredentialState, Welcome } from "./models.generated.js";
import { Router } from "./routing.js";
import type { Socket } from "./socket.js";
import type { Target } from "./targets.js";
import type { WireMessage } from "./wire.js";
import { toWire } from "./wire.js";

const UNBOUND = "igni is not bound to a producer yet; retry shortly";
const BUSY = 1013;
const NOT_A_PRODUCER = 1008;

export type Resync = () => Promise<void>;

/** igni's socket, kept open. `router` hands out what comes back. */
export class Connection {
  static readonly WELCOME_TIMEOUT = 45.0;
  static readonly RPC_TIMEOUT = 60.0;
  static readonly UNBOUND_RETRY_SECONDS = 1.0;
  static readonly UNBOUND_RETRIES = 30;

  clientId = "";
  vmCredential: VmCredentialState | null = null;
  readonly router: Router;
  private readonly lifecycle = new Lifecycle();
  private readonly resyncs: Resync[] = [];

  constructor(
    readonly target: Target,
    private readonly backoff: Backoff,
    router: Router,
  ) {
    this.router = router;
  }

  // ── Lifecycle ──

  async open(): Promise<void> {
    const delays = this.backoff.delays();
    for (;;) {
      try {
        await this.openOnce();
        return;
      } catch (error) {
        if (error instanceof AuthError || error instanceof NotAllowed) {
          throw error;
        }
        if (!(error instanceof Unavailable)) {
          throw error;
        }
        const next = delays.next();
        if (!this.target.reconnects || next.done) {
          throw error;
        }
        await sleep(next.value);
      }
    }
  }

  async close(): Promise<void> {
    const link = this.lifecycle.close();
    if (link) {
      await this.hangUp(link.socket);
    }
    this.failAll(new Unavailable("the client was closed"));
    await this.target.aclose();
  }

  onResync(callback: Resync): void {
    this.resyncs.push(callback);
  }

  private async openOnce(): Promise<void> {
    const link = new Link(await this.target.open());
    this.lifecycle.opening(link);
    this.read(link);
    let welcome: Welcome;
    const timedOut = Symbol("timeout");
    try {
      const race = await Promise.race([
        link.welcomed.promise,
        sleep(Connection.WELCOME_TIMEOUT).then(() => timedOut),
      ]);
      if (race === timedOut) {
        await this.hangUp(link.socket);
        throw new Unavailable(`${this.target.describe()} did not say welcome`);
      }
      welcome = race as Welcome;
    } catch (error) {
      if (error instanceof IgniClientError) {
        await this.hangUp(link.socket);
      }
      throw error;
    }
    this.clientId = welcome.client_id ?? "";
    this.lifecycle.opened();
  }

  private async hangUp(socket: Socket): Promise<void> {
    try {
      await socket.close();
    } catch {
      // a socket that cannot be closed is already gone
    }
  }

  // ── Sending ──

  async send(frame: WireMessage): Promise<void> {
    const socket = await this.lifecycle.socket(Connection.WELCOME_TIMEOUT, this.target.describe());
    try {
      socket.send(toWire(frame));
    } catch (error) {
      throw new Unavailable(`${this.target.describe()} went away: ${String(error)}`);
    }
  }

  async ask(
    method: string,
    args: Record<string, unknown> = {},
    opts: {
      sessionId?: string;
      timeout?: number | null;
      requestId?: string;
      reply?: string;
    } = {},
  ): Promise<WireMessage> {
    if (NOT_FOR_CLIENTS.has(method)) {
      throw new Error(`${method} is not a client's to send`);
    }
    const wait = opts.timeout === undefined ? Connection.RPC_TIMEOUT : opts.timeout;
    const reply = opts.reply ?? "rpc_response";
    for (let i = 0; i < Connection.UNBOUND_RETRIES; i++) {
      const sentAs = opts.requestId || this.router.newId("rpc");
      const envelope = opts.sessionId ? { session_id: opts.sessionId } : {};
      const request: WireMessage = {
        type: "rpc_request",
        id: sentAs,
        method,
        args,
        ...envelope,
      };
      const answer = await this.exchangeFrame(request, sentAs, method, wait, reply);
      if (answer.type === "rpc_response" && answer.error) {
        if (answer.error === UNBOUND) {
          await sleep(Connection.UNBOUND_RETRY_SECONDS);
          continue;
        }
        throw RpcError.of(
          method,
          String(answer.error),
          typeof answer.code === "string" ? answer.code : null,
        );
      }
      return answer;
    }
    throw new Unavailable(
      `${this.target.describe()} was not bound to its producer in time`,
    );
  }

  /** Send `frame` and return the first message igni answers it with, by `requestId`. */
  async exchange(frame: WireMessage, requestId: string, what: string): Promise<WireMessage> {
    return this.exchangeFrame(frame, requestId, what, Connection.RPC_TIMEOUT, "message");
  }

  private async exchangeFrame(
    frame: WireMessage,
    requestId: string,
    what: string,
    timeout: number | null,
    reply: string,
  ): Promise<WireMessage> {
    const answer = this.router.expect(requestId, reply);
    try {
      await this.send(frame);
      if (timeout === null) {
        return await answer.promise;
      }
      const timedOut = Symbol("timeout");
      const race = await Promise.race([
        answer.promise,
        sleep(timeout).then(() => timedOut),
      ]);
      if (race === timedOut) {
        throw new Unavailable(`${what} got no answer from ${this.target.describe()}`);
      }
      return race as WireMessage;
    } finally {
      this.router.forget(requestId);
    }
  }

  // ── Reading ──

  private read(link: Link): void {
    const where = this.target.describe();
    link.socket.onMessage((raw) => {
      let decoded: unknown;
      try {
        decoded = JSON.parse(raw);
      } catch {
        return;
      }
      if (typeof decoded !== "object" || decoded === null || Array.isArray(decoded)) {
        return;
      }
      this.route(parseEvent(decoded as WireMessage));
    });
    link.socket.onClose(() => {
      if (!this.lifecycle.lost(link)) {
        return;
      }
      if (!link.welcomed.done) {
        link.welcomed.reject(this.closeError(link.socket));
      } else {
        void this.closed(link.socket);
      }
    });
  }

  private closeError(socket: Socket): IgniClientError {
    const code = socket.closeCode;
    const reason = socket.closeReason || "";
    const where = this.target.describe();
    if (this.tokenExpired(socket)) {
      return new Unavailable(`${where} closed the connection as its token expired: ${reason}`);
    }
    if (code === NOT_A_PRODUCER && reasonToken(reason) === GROUP_LOCAL_ONLY) {
      return new GroupIsLocalOnly(
        `${where} closed the connection: the person's group runs igni only on their own ` +
          `computer (${reason}); use the local igni`,
      );
    }
    if (code === NOT_A_PRODUCER) {
      return new NotAllowed(`${where} closed the connection: ${reason || "not allowed"}`);
    }
    if (code === BUSY) {
      return new Unavailable(`${where} is busy; retry (${reason || "busy"})`);
    }
    return new Unavailable(`${where} closed the connection (${code}): ${reason}`);
  }

  private route(event: WireMessage): void {
    if (event.type === "push_notification" && event.channel === "vm_credential") {
      this.vmCredential = (event.payload as VmCredentialState | undefined) ?? null;
    }
    if (event.type !== "welcome") {
      this.router.deliver(event);
      return;
    }
    const welcomed = this.lifecycle.pendingWelcome();
    if (welcomed !== null) {
      welcomed.resolve(event as unknown as Welcome);
      return;
    }
    // igni moved behind the gateway: a new igni, the same socket.
    this.clientId = (event as unknown as Welcome).client_id ?? "";
    this.router.interrupt(
      new RunInterrupted("igni moved while this was going; it may have finished"),
    );
    void this.runResync();
  }

  private async closed(socket: Socket): Promise<void> {
    const code = socket.closeCode;
    const where = this.target.describe();
    const final = code === NOT_A_PRODUCER && !this.tokenExpired(socket);
    if (final || !this.target.reconnects) {
      this.fail(this.closeError(socket));
      return;
    }
    this.router.interrupt(
      new RunInterrupted(`the connection to ${where} dropped (${code}); it may have finished`),
    );
    let attempt = 0;
    for (const delay of this.backoff.delays()) {
      attempt += 1;
      await sleep(delay);
      try {
        await this.openOnce();
      } catch (error) {
        if (error instanceof AuthError || error instanceof NotAllowed) {
          this.fail(error);
          return;
        }
        continue;
      }
      await this.runResync();
      return;
    }
    this.fail(new Unavailable(`${where} could not be reached again after it closed (${code})`));
  }

  private tokenExpired(socket: Socket): boolean {
    return (
      socket.closeCode === NOT_A_PRODUCER &&
      reasonToken(socket.closeReason || "") === TOKEN_EXPIRED
    );
  }

  private async runResync(): Promise<void> {
    for (const callback of [...this.resyncs]) {
      try {
        await callback();
      } catch {
        // a re-attach that failed is logged on igni's side; the next run retries
      }
    }
  }

  private fail(error: IgniClientError): void {
    this.lifecycle.failed(error);
    this.failAll(error);
  }

  private failAll(error: IgniClientError): void {
    this.router.interrupt(error);
    const welcomed = this.lifecycle.pendingWelcome();
    welcomed?.reject(error);
  }

  get phase(): Phase {
    return this.lifecycle.phase;
  }
}

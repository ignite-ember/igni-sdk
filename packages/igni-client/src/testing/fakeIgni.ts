// A loopback backend that speaks igni's wire, for the client's own tests.
//
// It stands in for igni (a local socket), for Fleet's gateway (/v1/connect,
// /v1/me, /v1/commands) and for igni server's token endpoints, over one real
// http.Server with a real `ws` upgrade — so the client is exercised against the
// protocol on a real socket, not a mock. This module is test-only: it is not
// built into `dist` and not published.

import { createHash, createVerify } from "node:crypto";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { WebSocketServer, type WebSocket } from "ws";
import { METHODS } from "../api.generated.js";

interface Jwk {
  n: string;
  e: string;
  kid: string;
}

/** What the fake does when a run starts: its events, and whether it pauses. */
export interface RunScript {
  /** Content chunks streamed before (and, after an approval, after) the pause. */
  chunks?: string[];
  /** When set, the run pauses for approval of these tool calls. */
  pause?: Array<{ requirement_id: string; tool_name: string; friendly_name?: string }>;
  /** Chunks streamed after the approval is answered. */
  afterApproval?: string[];
  /** When set, the run ends with this `run_error` instead of completing. */
  error?: string;
}

type Ev = Record<string, unknown>;
type Answer = unknown | ((args: Record<string, unknown>) => unknown | Promise<unknown>);

export interface FakeOptions {
  /** A local socket needs this token offered as `igni-token.<t>`; omit for a dev backend. */
  requireToken?: string;
  /** Fleet's /v1/connect requires this bearer; omit to accept any. */
  requireBearer?: string;
  /** rpc_request answers, by method name. A value is `result`; a function gets the args. */
  answers?: Record<string, Answer>;
  /** The run the fake plays for a user_message. */
  run?: RunScript;
  /** A full event list to stream for a user_message (fills session_id/id/run_id). */
  runScript?: (text: string) => Ev[];
  /** The gateway's /v1/me body. */
  me?: Record<string, unknown>;
  /** The app public JWK the fake verifies a client assertion against. */
  appJwk?: Jwk;
  /** The issuer the fake advertises and checks a client assertion's `aud` against. */
  issuer?: string;
  /** Pushes to emit right after answering a given rpc method, for following a Call. */
  streamPushes?: Record<string, Array<{ channel: string; payload: Record<string, unknown> }>>;
  /** A status to answer /v1/me with instead of 200 (for testing the refusal mapping). */
  meStatus?: number;
  /** The /v1/me/cloud 200 body (cloud discovery). */
  cloud?: Record<string, unknown>;
  /** A status to answer /v1/me/cloud with instead of 200. */
  cloudStatus?: number;
  /** Omit `igni_gateway` from discovery (an igni server with no Fleet). */
  noGateway?: boolean;
  /** The /v1/me/cloud/events-owner answer; 409 mode_forbids when `modeForbids`. */
  modeForbids?: boolean;
  /** The /v1/sign-in 200 body; defaults to a ready credential. */
  signedIn?: Record<string, unknown>;
  /** A status to answer /v1/sign-in with instead of 200. */
  signInStatus?: number;
  /** Refuse every ws handshake with this status (and `handshakeBody`). */
  handshakeStatus?: number;
  /** The body of a refused handshake. */
  handshakeBody?: string;
  /** The NDJSON lines /v1/commands streams; defaults to a short successful run. */
  commandLines?: Ev[];
  /** A status to answer /v1/commands with instead of 200. */
  commandStatus?: number;
  /** Refuse an approval answer with an error on its own stream (igni said no). */
  refuseApproval?: boolean;
  /** When set, a `command` message is answered with this error instead of a result. */
  commandError?: string;
}

const DEFAULT_ANSWERS: Record<string, Answer> = {
  get_session_id: "s-default",
  list_sessions: { sessions: [{ session_id: "s-1", title: "one" }] },
  check_for_update: null,
};

/** A running fake. `close()` when done. */
export class FakeIgni {
  readonly server: Server;
  readonly wss: WebSocketServer;
  /** rpc_request answers, by method name — mutable, read live per request. */
  readonly answers: Record<string, Answer>;
  /** Every attach_session the fake answered, by its args. */
  readonly attachCalls: Array<Record<string, unknown>> = [];
  /** Every rpc_request, in order. */
  readonly calls: Array<{ method: string; args: Record<string, unknown>; id: string }> = [];
  /** Every message the client sent, raw. */
  readonly frames: Ev[] = [];
  /** Every approval batch the client sent (its decisions). */
  readonly decisions: Ev[][] = [];
  /** Every token request's form, for asserting the grant. */
  readonly tokenForms: Array<Record<string, string>> = [];
  readonly sockets = new Set<WebSocket>();
  private port = 0;
  private pending: { events: Ev[]; next: number; id: string; session: string } | null = null;
  private projects = new Map<string, string>();
  private seq = 0;

  constructor(private readonly opts: FakeOptions = {}) {
    this.answers = { ...DEFAULT_ANSWERS, ...(opts.answers ?? {}) };
    if (!(opts.answers && "attach_session" in opts.answers)) {
      this.answers.attach_session = (args: Record<string, unknown>) => {
        const id = String(args.session_id || `s-${(this.seq += 1)}`);
        const project = String(args.project_dir || this.projects.get(id) || "");
        this.projects.set(id, project);
        return { session_id: id, project_dir: project };
      };
    }
    this.server = createServer((req, res) => this.http(req, res));
    this.wss = new WebSocketServer({ noServer: true });
    this.server.on("upgrade", (req, socket, head) => {
      const path = (req.url ?? "/").split("?")[0];
      if (opts.handshakeStatus) {
        const body = opts.handshakeBody ?? "";
        socket.write(
          `HTTP/1.1 ${opts.handshakeStatus} Refused\r\nContent-Length: ${Buffer.byteLength(body)}\r\n\r\n${body}`,
        );
        socket.destroy();
        return;
      }
      if (path === "/v1/connect" && opts.requireBearer) {
        if (req.headers.authorization !== `Bearer ${opts.requireBearer}`) {
          socket.write("HTTP/1.1 401 Unauthorized\r\n\r\n");
          socket.destroy();
          return;
        }
      }
      if (path === "/" && opts.requireToken) {
        const protocols = String(req.headers["sec-websocket-protocol"] ?? "");
        if (!protocols.includes(`igni-token.${opts.requireToken}`)) {
          socket.write("HTTP/1.1 403 Forbidden\r\n\r\n");
          socket.destroy();
          return;
        }
      }
      this.wss.handleUpgrade(req, socket, head, (ws) => this.connected(ws));
    });
  }

  async start(): Promise<void> {
    await new Promise<void>((resolve) => this.server.listen(0, "127.0.0.1", resolve));
    this.port = (this.server.address() as AddressInfo).port;
  }

  get wsUrl(): string {
    return `ws://127.0.0.1:${this.port}`;
  }

  get httpUrl(): string {
    return `http://127.0.0.1:${this.port}`;
  }

  /** Tell the fake to verify an app's client assertions against this public JWK. */
  setApp(jwk: Jwk): void {
    this.opts.appJwk = jwk;
  }

  /** Broadcast a raw message to every open socket (as igni does). */
  broadcast(ev: Ev): void {
    for (const ws of this.sockets) {
      ws.send(JSON.stringify(ev));
    }
  }

  /** Send a second `welcome` on every open socket: igni moved behind the gateway. */
  move(clientId = "c-moved"): void {
    this.broadcast({ type: "welcome", client_id: clientId });
  }

  async close(): Promise<void> {
    for (const ws of this.sockets) {
      ws.close();
    }
    this.wss.close();
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }

  private connected(ws: WebSocket): void {
    this.sockets.add(ws);
    ws.on("close", () => this.sockets.delete(ws));
    ws.send(JSON.stringify({ type: "welcome", client_id: "c-1" }));
    ws.on("message", (data) => void this.onMessage(ws, String(data)));
  }

  private async onMessage(ws: WebSocket, raw: string): Promise<void> {
    const msg = JSON.parse(raw) as Record<string, unknown>;
    this.frames.push(msg);
    const type = String(msg.type ?? "");
    if (type === "rpc_request") {
      await this.answer(ws, msg);
    } else if (type === "user_message") {
      this.playRun(ws, String(msg.id ?? ""), String(msg.session_id ?? ""), String(msg.text ?? ""));
    } else if (type === "hitl_response_batch") {
      this.decisions.push((msg.decisions as Ev[]) ?? []);
      if (this.opts.refuseApproval) {
        ws.send(JSON.stringify({ type: "error", id: msg.id, session_id: msg.session_id, text: "igni refused" }));
        return;
      }
      this.resume(ws, String(msg.id ?? ""), String(msg.session_id ?? ""));
    } else if (type === "command") {
      if (this.opts.commandError) {
        ws.send(JSON.stringify({ type: "error", id: msg.id, text: this.opts.commandError }));
      } else {
        ws.send(JSON.stringify({ type: "command_result", id: msg.id, content: "ok", action: "" }));
      }
    }
  }

  private async answer(ws: WebSocket, msg: Record<string, unknown>): Promise<void> {
    const method = String(msg.method ?? "");
    const args = (msg.args as Record<string, unknown>) ?? {};
    this.calls.push({ method, args, id: String(msg.id ?? "") });
    if (method === "attach_session") {
      this.attachCalls.push(args);
    }
    const canned = method in this.answers ? this.answers[method] : null;
    let result: unknown = canned;
    if (typeof canned === "function") {
      result = await (canned as (a: Record<string, unknown>) => unknown | Promise<unknown>)(args);
    }
    const asMessage = METHODS[method]?.reply === "message";
    if (isErrorAnswer(result)) {
      if (asMessage) {
        ws.send(JSON.stringify({ type: "error", id: msg.id, text: result.error }));
      } else {
        ws.send(JSON.stringify({ type: "rpc_response", id: msg.id, error: result.error, code: result.code }));
      }
      return;
    }
    if (asMessage) {
      const body = result && typeof result === "object" ? result : {};
      ws.send(JSON.stringify({ ...(body as object), type: `${method}_result`, id: msg.id }));
    } else {
      ws.send(JSON.stringify({ type: "rpc_response", id: msg.id, result }));
    }
    for (const push of this.opts.streamPushes?.[method] ?? []) {
      ws.send(JSON.stringify({ type: "push_notification", channel: push.channel, payload: push.payload }));
    }
  }

  private playRun(ws: WebSocket, id: string, session: string, text: string): void {
    if (this.opts.runScript) {
      this.pending = { events: this.opts.runScript(text), next: 0, id, session };
      this.stream(ws);
      return;
    }
    const run = this.opts.run ?? { chunks: ["hello"] };
    const send = (ev: Ev) => ws.send(JSON.stringify({ session_id: session, id, ...ev }));
    send({ type: "run_started", run_id: id });
    for (const chunk of run.chunks ?? []) {
      send({ type: "content_delta", run_id: id, text: chunk });
    }
    if (run.pause) {
      this.pending = { events: [], next: 0, id, session };
      send({ type: "run_paused", run_id: id, requirements: run.pause });
      return;
    }
    this.endRun(ws, id, session, run);
  }

  private resume(ws: WebSocket, hitlId: string, session: string): void {
    if (this.opts.runScript && this.pending) {
      this.stream(ws, hitlId);
      return;
    }
    const id = this.pending?.id ?? "";
    const run = this.opts.run ?? {};
    const send = (ev: Ev) => ws.send(JSON.stringify({ session_id: session, id, ...ev }));
    for (const chunk of run.afterApproval ?? ["done"]) {
      send({ type: "content_delta", run_id: id, text: chunk });
    }
    this.endRun(ws, id, session, run);
    ws.send(JSON.stringify({ type: "stream_end", id: hitlId, session_id: session }));
  }

  /** Walk the scripted events, pausing at a run_paused until an answer resumes it. */
  private stream(ws: WebSocket, hitlId = ""): void {
    const s = this.pending!;
    const send = (ev: Ev) => ws.send(JSON.stringify({ session_id: s.session, id: s.id, run_id: s.id, ...ev }));
    for (let i = s.next; i < s.events.length; i++) {
      const ev = s.events[i];
      send(ev);
      if (ev.type === "run_paused") {
        s.next = i + 1;
        return; // wait for the answer
      }
    }
    send({ type: "stream_end" });
    if (hitlId) {
      ws.send(JSON.stringify({ type: "stream_end", id: hitlId, session_id: s.session }));
    }
    this.pending = null;
  }

  private endRun(ws: WebSocket, id: string, session: string, run: RunScript): void {
    const send = (ev: Ev) => ws.send(JSON.stringify({ session_id: session, id, ...ev }));
    if (run.error) {
      send({ type: "run_error", run_id: id, error: run.error });
    } else {
      send({ type: "run_completed", run_id: id, duration: 1 });
    }
    send({ type: "stream_end" });
    this.pending = null;
  }

  // ── HTTP: gateway + igni server ──

  private http(req: IncomingMessage, res: ServerResponse): void {
    const path = (req.url ?? "/").split("?")[0];
    if (path === "/v1/me") {
      if (this.opts.meStatus && this.opts.meStatus !== 200) {
        res.writeHead(this.opts.meStatus, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ detail: "no" }));
        return;
      }
      return this.json(res, this.opts.me ?? { producer: "person:p1", org: "o1", group: null, expires_at: 0, vm: { state: "running", signed_in: true } });
    }
    if (path === "/v1/me/cloud/events-owner") {
      if (this.opts.modeForbids) {
        res.writeHead(409, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "mode_forbids" }));
        return;
      }
      return this.json(res, this.opts.cloud ?? this.defaultCloud());
    }
    if (path === "/v1/me/cloud") {
      return this.cloud(res);
    }
    if (path === "/v1/sign-in") {
      return this.signIn(res);
    }
    if (path === "/v1/commands") {
      return this.commands(res);
    }
    if (path === "/.well-known/openid-configuration") {
      const body: Record<string, unknown> = { issuer: this.opts.issuer ?? this.httpUrl };
      if (!this.opts.noGateway) {
        body.igni_gateway = this.httpUrl;
      }
      return this.json(res, body);
    }
    if (path === "/v1/oauth/token") {
      return this.token(req, res);
    }
    const spaces = /^\/v1\/apps\/[^/]+\/spaces(?:\/(.+))?$/.exec(path);
    if (spaces) {
      return this.spaces(req, res, spaces[1] ? decodeURIComponent(spaces[1]) : "");
    }
    res.writeHead(404).end();
  }

  private spaces(req: IncomingMessage, res: ServerResponse, externalId: string): void {
    if (req.method === "GET" && !externalId) {
      return this.json(res, { spaces: [{ space_id: "sp-1", external_id: "u1" }], next: null });
    }
    if (externalId === "missing" && req.method === "GET") {
      res.writeHead(404).end();
      return;
    }
    if (externalId === "refused") {
      res.writeHead(403, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "no" }));
      return;
    }
    if (req.method === "DELETE") {
      res.writeHead(204).end();
      return;
    }
    this.json(res, { space_id: `sp-${externalId}`, external_id: externalId, app_id: "app-1", org_id: "o1" });
  }

  private defaultCloud(): Record<string, unknown> {
    return {
      cloud: "available",
      reason: null,
      gateway_url: this.httpUrl,
      mode: "local_and_cloud",
      events_owner: "local",
      group: { id: "g1", name: "Eng" },
      producer: "person:p1",
    };
  }

  private cloud(res: ServerResponse): void {
    if (this.opts.cloudStatus && this.opts.cloudStatus !== 200) {
      res.writeHead(this.opts.cloudStatus, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "refused" }));
      return;
    }
    this.json(res, this.opts.cloud ?? this.defaultCloud());
  }

  private signIn(res: ServerResponse): void {
    if (this.opts.signInStatus && this.opts.signInStatus !== 200) {
      res.writeHead(this.opts.signInStatus, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "group_local_only", detail: "local only" }));
      return;
    }
    this.json(
      res,
      this.opts.signedIn ?? { producer: "person:p1", node: "n1", how: "cold", credential: { state: "ready" } },
    );
  }

  private commands(res: ServerResponse): void {
    if (this.opts.commandStatus && this.opts.commandStatus !== 200) {
      res.writeHead(this.opts.commandStatus, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "group_local_only", detail: "refused" }));
      return;
    }
    const lines = this.opts.commandLines ?? [
      { command: { command_id: "cmd-1", state: "running" } },
      { woken: { how: "cold", node: "n1" } },
      { stream: "stdout", data_b64: Buffer.from("hi\n").toString("base64") },
      { done: true, exit_code: 0, duration_ms: 5 },
    ];
    res.writeHead(200, { "Content-Type": "application/x-ndjson" });
    for (const line of lines) {
      res.write(JSON.stringify(line) + "\n");
    }
    res.end();
  }

  private token(req: IncomingMessage, res: ServerResponse): void {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      const form = Object.fromEntries(new URLSearchParams(body)) as Record<string, string>;
      this.tokenForms.push(form);
      if (form.grant_type === "client_credentials" && this.opts.appJwk) {
        if (!this.verifyAssertion(form.client_assertion ?? "")) {
          res.writeHead(401, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "invalid_client", error_description: "bad assertion" }));
          return;
        }
      }
      this.json(res, { access_token: `tok-${form.grant_type}`, expires_in: 900 });
    });
  }

  private verifyAssertion(jwt: string): boolean {
    const [header, payload, signature] = jwt.split(".");
    if (!header || !payload || !signature) {
      return false;
    }
    const jwk = this.opts.appJwk!;
    const claims = JSON.parse(Buffer.from(payload, "base64url").toString()) as { aud?: string };
    if (claims.aud !== (this.opts.issuer ?? this.httpUrl)) {
      return false;
    }
    const key = { kty: "RSA", n: jwk.n, e: jwk.e };
    const ok = createVerify("RSA-SHA256")
      .update(`${header}.${payload}`)
      .verify({ key: key as never, format: "jwk" }, Buffer.from(signature, "base64url"));
    const head = JSON.parse(Buffer.from(header, "base64url").toString()) as { kid?: string };
    const thumbprint = createHash("sha256")
      .update(JSON.stringify({ e: jwk.e, kty: "RSA", n: jwk.n }))
      .digest("base64url");
    return ok && head.kid === thumbprint;
  }

  private json(res: ServerResponse, body: unknown): void {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(body));
  }
}

/** An answer shaped `{ error, code? }` makes the fake reply with an rpc error. */
function isErrorAnswer(value: unknown): value is { error: string; code?: string } {
  return Boolean(value) && typeof value === "object" && typeof (value as { error?: unknown }).error === "string";
}

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

export interface FakeOptions {
  /** A local socket needs this token offered as `igni-token.<t>`; omit for a dev backend. */
  requireToken?: string;
  /** Fleet's /v1/connect requires this bearer; omit to accept any. */
  requireBearer?: string;
  /** rpc_request answers, by method name. A value is `result`; a function gets the args. */
  answers?: Record<string, unknown | ((args: Record<string, unknown>) => unknown)>;
  /** The run the fake plays for a user_message. */
  run?: RunScript;
  /** The gateway's /v1/me body. */
  me?: Record<string, unknown>;
  /** The app public JWK the fake verifies a client assertion against. */
  appJwk?: Jwk;
  /** The issuer the fake advertises and checks a client assertion's `aud` against. */
  issuer?: string;
}

const DEFAULT_ANSWERS: Record<string, unknown> = {
  attach_session: { session_id: "s-1", project_dir: "/work" },
  get_session_id: "s-1",
  list_sessions: { sessions: [{ session_id: "s-1", title: "one" }] },
  check_for_update: null,
};

/** A running fake. `close()` when done. */
export class FakeIgni {
  readonly server: Server;
  readonly wss: WebSocketServer;
  /** Every attach_session the fake answered, by its args. */
  readonly attachCalls: Array<Record<string, unknown>> = [];
  /** Every token request's form, for asserting the grant. */
  readonly tokenForms: Array<Record<string, string>> = [];
  readonly sockets = new Set<WebSocket>();
  private port = 0;

  constructor(private readonly opts: FakeOptions = {}) {
    this.server = createServer((req, res) => this.http(req, res));
    this.wss = new WebSocketServer({ noServer: true });
    this.server.on("upgrade", (req, socket, head) => {
      const url = req.url ?? "/";
      const path = url.split("?")[0];
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

  /** Send a second `welcome` on every open socket: igni moved behind the gateway. */
  move(clientId = "c-moved"): void {
    for (const ws of this.sockets) {
      ws.send(JSON.stringify({ type: "welcome", client_id: clientId }));
    }
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
    ws.on("message", (data) => this.onMessage(ws, String(data)));
  }

  private onMessage(ws: WebSocket, raw: string): void {
    const msg = JSON.parse(raw) as Record<string, unknown>;
    const type = String(msg.type ?? "");
    if (type === "rpc_request") {
      this.answer(ws, msg);
    } else if (type === "user_message") {
      void this.playRun(ws, String(msg.id ?? ""), String(msg.session_id ?? ""));
    } else if (type === "hitl_response_batch") {
      void this.resume(ws, String(msg.id ?? ""), String(msg.session_id ?? ""));
    }
  }

  private answer(ws: WebSocket, msg: Record<string, unknown>): void {
    const method = String(msg.method ?? "");
    const args = (msg.args as Record<string, unknown>) ?? {};
    if (method === "attach_session") {
      this.attachCalls.push(args);
    }
    const answers = { ...DEFAULT_ANSWERS, ...(this.opts.answers ?? {}) };
    const canned = method in answers ? answers[method] : null;
    const result = typeof canned === "function" ? (canned as (a: Record<string, unknown>) => unknown)(args) : canned;
    ws.send(JSON.stringify({ type: "rpc_response", id: msg.id, result }));
  }

  private runId = "";
  private runSession = "";

  private async playRun(ws: WebSocket, id: string, session: string): Promise<void> {
    this.runId = id;
    this.runSession = session;
    const run = this.opts.run ?? { chunks: ["hello"] };
    const send = (ev: Record<string, unknown>) => ws.send(JSON.stringify({ session_id: session, id, ...ev }));
    send({ type: "run_started", run_id: id });
    for (const chunk of run.chunks ?? []) {
      send({ type: "content_delta", run_id: id, text: chunk });
    }
    if (run.pause) {
      send({ type: "run_paused", run_id: id, requirements: run.pause });
      return; // wait for hitl_response_batch
    }
    this.endRun(ws, id, session, run);
  }

  private resume(ws: WebSocket, hitlId: string, session: string): void {
    const id = this.runId;
    const run = this.opts.run ?? {};
    const send = (ev: Record<string, unknown>) => ws.send(JSON.stringify({ session_id: session, id, ...ev }));
    for (const chunk of run.afterApproval ?? ["done"]) {
      send({ type: "content_delta", run_id: id, text: chunk });
    }
    this.endRun(ws, id, session, run);
    // close the answer's own stream too
    ws.send(JSON.stringify({ type: "stream_end", id: hitlId, session_id: session }));
  }

  private endRun(ws: WebSocket, id: string, session: string, run: RunScript): void {
    const send = (ev: Record<string, unknown>) => ws.send(JSON.stringify({ session_id: session, id, ...ev }));
    if (run.error) {
      send({ type: "run_error", run_id: id, error: run.error });
    } else {
      send({ type: "run_completed", run_id: id, duration: 1 });
    }
    send({ type: "stream_end" });
  }

  // ── HTTP: gateway + igni server ──

  private http(req: IncomingMessage, res: ServerResponse): void {
    const path = (req.url ?? "/").split("?")[0];
    if (path === "/v1/me") {
      return this.json(res, this.opts.me ?? { producer: "person:p1", org: "o1", group: null, expires_at: 0, vm: { state: "running", signed_in: true } });
    }
    if (path === "/v1/commands") {
      return this.commands(res);
    }
    if (path === "/.well-known/openid-configuration") {
      return this.json(res, { issuer: this.opts.issuer ?? this.httpUrl, igni_gateway: this.wsUrl });
    }
    if (path === "/v1/oauth/token") {
      return this.token(req, res);
    }
    res.writeHead(404).end();
  }

  private commands(res: ServerResponse): void {
    res.writeHead(200, { "Content-Type": "application/x-ndjson" });
    res.write(JSON.stringify({ command: { command_id: "cmd-1", state: "running" } }) + "\n");
    res.write(JSON.stringify({ woken: { how: "cold", node: "n1" } }) + "\n");
    res.write(JSON.stringify({ stream: "stdout", data_b64: Buffer.from("hi\n").toString("base64") }) + "\n");
    res.write(JSON.stringify({ done: true, exit_code: 0, duration_ms: 5 }) + "\n");
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
    const claims = JSON.parse(Buffer.from(payload, "base64url").toString()) as { aud?: string; iss?: string; sub?: string };
    if (claims.aud !== (this.opts.issuer ?? this.httpUrl)) {
      return false;
    }
    const key = { kty: "RSA", n: jwk.n, e: jwk.e };
    const ok = createVerify("RSA-SHA256")
      .update(`${header}.${payload}`)
      .verify({ key: key as never, format: "jwk" }, Buffer.from(signature, "base64url"));
    // and the header's kid must be the key's thumbprint
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

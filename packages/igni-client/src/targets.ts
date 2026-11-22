// Where an igni is: on this machine, or in Fleet behind its gateway.
//
// A target knows how to open igni's socket, and what to do when it closes. Both
// speak the same protocol once open — the gateway relays igni's frames unchanged
// — so everything above the target is the same code.

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import type { Standing } from "./access.js";
import type { TokenSource } from "./auth/tokens.js";
import { checkedGateway, discover, insecureGatewayAllowed, type CloudIgni } from "./cloud.js";
import {
  AuthError,
  GROUP_LOCAL_ONLY,
  GroupIsLocalOnly,
  NotAllowed,
  NotSupported,
  Unavailable,
  reasonToken,
} from "./errors.js";
import { HandshakeError, nodeSocketFactory } from "./socket.js";
import type { Socket, SocketFactory } from "./socket.js";

const SUBPROTOCOL = "igni.v1";
const TOKEN_PROTOCOL_PREFIX = "igni-token.";
const APPROVER_TOKEN_ENV = "IGNI_APPROVER_TOKEN";

/** Expand a leading `~` to the home directory, as Python's `expanduser` does. */
function expandHome(path: string): string {
  if (path === "~") {
    return homedir();
  }
  if (path.startsWith("~/")) {
    return join(homedir(), path.slice(2));
  }
  return path;
}

/** How to reach one igni. */
export interface Target {
  /** Whether a closed socket is worth opening again (Fleet wakes the VM; a local igni stopped). */
  readonly reconnects: boolean;
  open(): Promise<Socket>;
  aclose(): Promise<void>;
  describe(): string;
  /** What igni lets this connection do, where it is known. */
  readonly standing: Standing;
}

/** What a refused handshake body says: OAuth's description or code, else the body. */
function reasonIn(body: string): string {
  try {
    const parsed = JSON.parse(body) as { error_description?: unknown; error?: unknown };
    return String(parsed.error_description ?? parsed.error ?? body);
  } catch {
    return body;
  }
}

function localOnlyBody(body: string): boolean {
  try {
    const parsed = JSON.parse(body) as { error_description?: unknown; error?: unknown };
    return [reasonToken(String(parsed.error ?? "")), reasonToken(String(parsed.error_description ?? ""))].includes(
      GROUP_LOCAL_ONLY,
    );
  } catch {
    return reasonToken(body) === GROUP_LOCAL_ONLY;
  }
}

function refusal(status: number, body: string, where: string): Error {
  const detail = reasonIn(body.trim());
  if (status === 401) {
    return new AuthError(`${where} refused the credential: ${detail || "unauthorized"}`);
  }
  if (status === 403 && localOnlyBody(body)) {
    return new GroupIsLocalOnly(
      `${where} refused the connection: the person's group runs igni only on their own ` +
        `computer (${detail}); use the local igni`,
    );
  }
  if (status === 403) {
    return new NotAllowed(`${where} refused the connection: ${detail || "forbidden"}`);
  }
  return new Unavailable(`${where} answered ${status}: ${detail}`);
}

export interface LocalOptions {
  projectDir?: string;
  url?: string;
  token?: string;
  approverToken?: string;
  socketFactory?: SocketFactory;
}

/** An igni running on this machine — the desktop app's, or one started by hand. */
export class Local implements Target {
  readonly reconnects = false;
  private readonly projectDir: string;
  private readonly url?: string;
  private readonly token?: string;
  private readonly approverToken?: string;
  private readonly factory: SocketFactory;
  private standingValue: Standing = "unknown";

  constructor(opts: LocalOptions = {}) {
    this.projectDir = resolve(expandHome(opts.projectDir ?? "."));
    this.url = opts.url;
    this.token = opts.token;
    this.approverToken = opts.approverToken || process.env[APPROVER_TOKEN_ENV] || undefined;
    this.factory = opts.socketFactory ?? nodeSocketFactory;
  }

  get approves(): boolean {
    return this.approverToken !== undefined;
  }

  get standing(): Standing {
    if (this.approverToken !== undefined) {
      return "approver";
    }
    return this.standingValue;
  }

  private stand(token: string | undefined, given: boolean): void {
    if (token === undefined) {
      this.standingValue = "window";
    } else {
      this.standingValue = given ? "unknown" : "program";
    }
  }

  private resolveTarget(): { url: string; token: string | undefined } {
    if (this.url !== undefined) {
      this.stand(this.token, true);
      return { url: this.url, token: this.approverToken ?? this.token };
    }
    const lock = resolve(this.projectDir, ".igni", "backend.lock");
    let raw: string;
    try {
      raw = readFileSync(lock, "utf-8");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") {
        throw new Unavailable(
          `no igni is running for ${this.projectDir} (no ${lock}); open the project in igni, or pass url=`,
        );
      }
      throw new Unavailable(`${lock} is not an igni lockfile`);
    }
    let payload: { port?: unknown; ws_token?: unknown };
    try {
      payload = JSON.parse(raw) as { port?: unknown; ws_token?: unknown };
    } catch {
      throw new Unavailable(`${lock} is not an igni lockfile`);
    }
    if (typeof payload !== "object" || payload === null || typeof payload.port !== "number") {
      throw new Unavailable(`${lock} is not an igni lockfile`);
    }
    if (payload.ws_token !== undefined && payload.ws_token !== null && typeof payload.ws_token !== "string") {
      throw new Unavailable(`${lock} is not an igni lockfile`);
    }
    const lockToken = (payload.ws_token as string) || undefined;
    this.stand(lockToken ?? this.token, lockToken === undefined);
    return {
      url: `ws://127.0.0.1:${payload.port}`,
      token: this.approverToken ?? lockToken ?? this.token,
    };
  }

  async open(): Promise<Socket> {
    const { url, token } = this.resolveTarget();
    const protocols = [SUBPROTOCOL];
    if (token) {
      protocols.push(`${TOKEN_PROTOCOL_PREFIX}${token}`);
    }
    try {
      return await this.factory.open(url, protocols);
    } catch (error) {
      if (error instanceof HandshakeError) {
        if (error.status === 403) {
          if (this.approverToken !== undefined) {
            throw new AuthError(
              `igni at ${url} refused the approver token: it was revoked, or igni restarted ` +
                "since it was made; make a new one with /programs",
            );
          }
          throw new AuthError(`igni at ${url} refused the connection: its token was missing or wrong`);
        }
        throw refusal(error.status, error.body, `igni at ${url}`);
      }
      throw new Unavailable(`igni at ${url} did not answer: ${String(error)}`);
    }
  }

  async aclose(): Promise<void> {
    // nothing to close: Local owns no HTTP client
  }

  describe(): string {
    return `igni at ${this.url ?? this.projectDir}`;
  }
}

export interface FleetOptions {
  auth: TokenSource;
  socketFactory?: SocketFactory;
  fetchImpl?: typeof fetch;
}

/** A producer's igni in Fleet, reached through the gateway. */
export class Fleet implements Target {
  readonly reconnects = true;
  readonly base: string;
  readonly connectUrl: string;
  readonly auth: TokenSource;
  /** What igni server said of the person's cloud igni, for a Fleet made by `fromServer`. */
  discovered: CloudIgni | null = null;
  private readonly factory: SocketFactory;
  private readonly fetchImpl: typeof fetch;

  constructor(url: string, opts: FleetOptions) {
    const parsed = new URL(url.replace(/\/+$/, ""));
    if (!["http:", "https:", "ws:", "wss:"].includes(parsed.protocol)) {
      throw new Error("the gateway's URL is http(s):// or ws(s)://");
    }
    const secure = parsed.protocol === "https:" || parsed.protocol === "wss:";
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    this.base = `${secure ? "https" : "http"}://${parsed.host}${path}`;
    this.connectUrl = `${secure ? "wss" : "ws"}://${parsed.host}${path}/v1/connect`;
    this.auth = opts.auth;
    this.factory = opts.socketFactory ?? nodeSocketFactory;
    this.fetchImpl = opts.fetchImpl ?? fetch;
  }

  /**
   * The person's igni in Fleet, its gateway found from igni server at `server`.
   *
   * igni server's `/v1/me/cloud` names the gateway and says whether the person
   * may use it. When they may not, this raises what connecting would:
   * `GroupIsLocalOnly`, `NotSupported` (no Fleet) or `NotAllowed`. The gateway
   * must be https; `allowHttp` (or `IGNI_DEV_GATEWAY_INSECURE=1`) takes a lab one.
   */
  static async fromServer(
    server: string,
    opts: FleetOptions & { allowHttp?: boolean },
  ): Promise<Fleet> {
    const cloud = await discover(server, opts.auth, { fetchImpl: opts.fetchImpl });
    const allowed = opts.allowHttp ?? insecureGatewayAllowed();
    const fleet = new Fleet(checkedGateway(cloud, { allowHttp: allowed }), opts);
    fleet.discovered = cloud;
    return fleet;
  }

  get standing(): Standing {
    // igni on a Fleet VM takes no token and stands every connection as its window.
    return "window";
  }

  async open(): Promise<Socket> {
    const token = await this.auth.token();
    try {
      return await this.factory.open(this.connectUrl, [SUBPROTOCOL], {
        Authorization: `Bearer ${token}`,
      });
    } catch (error) {
      if (error instanceof HandshakeError) {
        throw refusal(error.status, error.body, "the gateway");
      }
      throw new Unavailable(`the gateway at ${this.base} did not answer: ${String(error)}`);
    }
  }

  /** A call to the gateway's HTTP API, as this producer; `body` goes as JSON. */
  async request(
    method: string,
    path: string,
    opts: { body?: unknown; headers?: Record<string, string> } = {},
  ): Promise<Response> {
    const token = await this.auth.token();
    try {
      return await this.fetchImpl(`${this.base}${path}`, {
        method,
        headers: this.headers(token, opts.headers, opts.body !== undefined),
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      });
    } catch (error) {
      throw new Unavailable(`the gateway at ${this.base} did not answer: ${String(error)}`);
    }
  }

  /** A streamed call to the gateway's HTTP API (the caller supplies the token). */
  stream(
    method: string,
    path: string,
    token: string,
    opts: { body?: unknown; headers?: Record<string, string> } = {},
  ): Promise<Response> {
    return this.fetchImpl(`${this.base}${path}`, {
      method,
      headers: this.headers(token, opts.headers, opts.body !== undefined),
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  }

  private headers(token: string, extra: Record<string, string> | undefined, json: boolean): Record<string, string> {
    return {
      Authorization: `Bearer ${token}`,
      ...(json ? { "Content-Type": "application/json" } : {}),
      ...(extra ?? {}),
    };
  }

  async aclose(): Promise<void> {
    // nothing to close: fetch keeps no connection of ours
  }

  describe(): string {
    return `igni in Fleet via ${this.base}`;
  }
}

/** `target` as a `Fleet`, or `NotSupported` naming what needed the gateway. */
export function requireFleet(target: Target, what: string): Fleet {
  if (target instanceof Fleet) {
    return target;
  }
  throw new NotSupported(`${what} needs Fleet's gateway; ${target.describe()} has none`);
}

// A person: by the session `igni login` keeps, a session handed over, or an API key.

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { resolve } from "node:path";
import { AuthError, Unavailable } from "../errors.js";
import { apiKeyGrant } from "./grants.js";
import { IgniServer } from "./server.js";
import { TokenCache, type IssuedToken, type TokenSource } from "./tokens.js";

const CLI_CREDENTIALS = ".igni/credentials.json";

export interface ApiKeyOptions {
  server: string;
  fetchImpl?: typeof fetch;
  clock?: () => number;
}

/** A person, by their igni session (pinned to an organisation). */
export class Person implements TokenSource {
  private readonly value: string;

  constructor(token: string) {
    const trimmed = token.trim();
    if (!trimmed) {
      throw new AuthError("a person needs a session token");
    }
    this.value = trimmed;
  }

  /** A person by their API key — the way to give a program their access. */
  static fromApiKey(key?: string, opts: Partial<ApiKeyOptions> = {}): ApiKey {
    const theKey = key ?? process.env.IGNI_API_KEY ?? "";
    const server = opts.server ?? process.env.IGNI_SERVER_URL ?? "";
    if (!theKey) {
      throw new AuthError("no API key: pass one, or set IGNI_API_KEY");
    }
    if (!server) {
      throw new AuthError("where is igni server? pass server, or set IGNI_SERVER_URL");
    }
    return new ApiKey(theKey, { ...opts, server });
  }

  /** The session `igni login` stored: `~/.igni/credentials.json`, or the file at `path`. */
  static fromCli(path?: string): Person {
    const storedAt = path ?? resolve(homedir(), CLI_CREDENTIALS);
    let text: string;
    try {
      text = readFileSync(storedAt, "utf-8");
    } catch {
      throw new AuthError("no igni session on this machine; run `igni login`");
    }
    let stored: { access_token?: unknown; expires_at?: unknown };
    try {
      stored = JSON.parse(text) as { access_token?: unknown; expires_at?: unknown };
    } catch {
      throw new AuthError(`${storedAt} is not an igni credentials file`);
    }
    if (typeof stored.access_token !== "string" || !stored.access_token) {
      throw new AuthError(`${storedAt} is not an igni credentials file`);
    }
    if (expired(typeof stored.expires_at === "string" ? stored.expires_at : "")) {
      throw new AuthError(`the session in ${storedAt} has expired; run \`igni login\``);
    }
    return new Person(stored.access_token);
  }

  token(): Promise<string> {
    return Promise.resolve(this.value);
  }
}

function expired(expiresAt: string): boolean {
  if (!expiresAt) {
    return false;
  }
  const when = Date.parse(expiresAt);
  if (Number.isNaN(when)) {
    return false;
  }
  return Date.now() >= when;
}

/** A person's API key, exchanged for short 15-minute sessions as them. */
export class ApiKey implements TokenSource {
  static readonly RENEW_BEFORE = 60;
  private readonly key: string;
  private readonly server: IgniServer;
  private readonly tokens: TokenCache;

  constructor(key: string, opts: ApiKeyOptions) {
    if (!key.trim().startsWith("igpak1.")) {
      throw new AuthError("not an igni API key (they start with 'igpak1.')");
    }
    this.key = key.trim();
    this.server = new IgniServer(opts.server, opts.fetchImpl);
    const clock = opts.clock ?? (() => Date.now() / 1000);
    this.tokens = new TokenCache(clock, () => ApiKey.RENEW_BEFORE);
  }

  token(): Promise<string> {
    return this.tokens.get(() => this.session());
  }

  private async session(): Promise<IssuedToken> {
    const response = await this.server.call("POST", "/v1/oauth/token", "the key's session", {
      form: apiKeyGrant(this.key),
    });
    if ([400, 401, 403].includes(response.status)) {
      throw new AuthError(`igni server refused the API key: ${await IgniServer.reason(response)}`);
    }
    if (response.status !== 200) {
      throw new Unavailable(`igni server answered the key's exchange with ${response.status}`);
    }
    return this.server.parseToken(response, "the key's session");
  }
}

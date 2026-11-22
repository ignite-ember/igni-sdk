// An app of an organisation, signing in as itself.

import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { clientCredentialsGrant, spaceExchangeGrant } from "./grants.js";
import { AppKey, type JwkSet } from "./keys.js";
import { IgniServer } from "./server.js";
import { Spaces } from "./spaces.js";
import { TokenCache, type IssuedToken, type TokenSource } from "./tokens.js";

export interface AppOptions {
  server: string;
  keyFile?: string;
  keyPem?: string;
  fetchImpl?: typeof fetch;
  clock?: () => number;
}

/** An app of an organisation, signing in as itself (`client_credentials` + `private_key_jwt`). */
export class App implements TokenSource {
  static readonly RENEW_BEFORE = 60;
  static readonly ASSERTION_LIFETIME = 60;
  readonly appId: string;
  readonly clock: () => number;
  private readonly key: AppKey;
  private readonly server: IgniServer;
  private readonly tokens: TokenCache;

  constructor(appId: string, opts: AppOptions) {
    if (!appId) {
      throw new Error("an app needs its app id");
    }
    let pem: string;
    if (opts.keyFile !== undefined && opts.keyPem === undefined) {
      pem = readFileSync(opts.keyFile, "utf-8");
    } else if (opts.keyPem !== undefined && opts.keyFile === undefined) {
      pem = opts.keyPem;
    } else {
      throw new Error("give the app's key as exactly one of keyFile or keyPem");
    }
    this.appId = appId;
    this.clock = opts.clock ?? (() => Date.now() / 1000);
    this.key = AppKey.fromPem(pem);
    this.server = new IgniServer(opts.server, opts.fetchImpl);
    this.tokens = new TokenCache(() => this.clock(), () => App.RENEW_BEFORE);
  }

  /** Seconds before a token runs out at which a space renews its own. */
  get renewBefore(): number {
    return App.RENEW_BEFORE;
  }

  /** Make a new RSA key for an app and write it to `path`, readable by its owner only. */
  static generateKey(path: string): string {
    return AppKey.generate(path);
  }

  /** The key's RFC 7638 thumbprint: its `kid`, and what an admin compares. */
  thumbprint(): string {
    return this.key.thumbprint();
  }

  /** The public key as a JWK set: what an org admin registers for this app. */
  publicJwks(): JwkSet {
    return this.key.jwks();
  }

  /** The app's own token (`token_use=app`), renewed shortly before it runs out. */
  token(): Promise<string> {
    return this.tokens.get(() => this.signIn());
  }

  /** The app's token exchanged for the token of its space `spaceId` (`token_use=space`). */
  async exchange(spaceId: string): Promise<IssuedToken> {
    return this.server.grant(spaceExchangeGrant(await this.token(), spaceId), "the space's token");
  }

  /** A call to igni server as this app, retried once with a fresh token on a 401. */
  async request(
    method: string,
    path: string,
    opts: { what: string; params?: Record<string, string | number> },
  ): Promise<Response> {
    const response = await this.server.call(method, path, opts.what, {
      bearer: await this.token(),
      params: opts.params,
    });
    if (response.status !== 401) {
      return response;
    }
    await this.tokens.forget();
    return this.server.call(method, path, opts.what, {
      bearer: await this.token(),
      params: opts.params,
    });
  }

  /** This app's spaces: its end users, each a producer with an igni of its own. */
  get spaces(): Spaces {
    return new Spaces(this);
  }

  private async signIn(): Promise<IssuedToken> {
    return this.server.grant(clientCredentialsGrant(await this.assertion()), "the app's token");
  }

  private async assertion(): Promise<string> {
    const now = Math.floor(this.clock());
    return this.key.sign({
      iss: this.appId,
      sub: this.appId,
      aud: await this.server.issuer(),
      iat: now,
      exp: now + App.ASSERTION_LIFETIME,
      jti: randomUUID().replace(/-/g, ""),
    });
  }
}

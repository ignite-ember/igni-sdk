// A bearer token source, and the cache that keeps a short-lived token.

/** Anything a target can ask for a bearer token. */
export interface TokenSource {
  token(): Promise<string>;
}

/** igni server's answer to a token request. */
export interface IssuedToken {
  access_token: string;
  expires_in?: number;
}

/** One bearer token, kept until `renewBefore` seconds before it runs out. */
export class TokenCache {
  private token: string | null = null;
  private expiresAt = 0;
  private inflight: Promise<string> | null = null;

  constructor(
    private readonly clock: () => number,
    private readonly renewBefore: () => number,
  ) {}

  async get(fetch: () => Promise<IssuedToken>): Promise<string> {
    if (this.token !== null && this.clock() < this.expiresAt) {
      return this.token;
    }
    if (this.inflight) {
      return this.inflight;
    }
    this.inflight = (async () => {
      try {
        const issued = await fetch();
        this.token = issued.access_token;
        this.expiresAt = this.clock() + Math.max(0, (issued.expires_in ?? 600) - this.renewBefore());
        return this.token;
      } finally {
        this.inflight = null;
      }
    })();
    return this.inflight;
  }

  async forget(): Promise<void> {
    this.token = null;
  }
}

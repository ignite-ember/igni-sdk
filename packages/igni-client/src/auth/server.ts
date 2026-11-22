// igni server, as the client's auth reaches it: discovery and the token endpoint.

import { AuthError, Unavailable } from "../errors.js";
import type { IssuedToken } from "./tokens.js";

export interface ServerCall {
  bearer?: string;
  form?: Record<string, string>;
  params?: Record<string, string | number>;
  json?: unknown;
}

/** igni server's address and the fetch that reaches it. */
export class IgniServer {
  url: string;
  private issuerUrl: string | null = null;

  constructor(
    url: string,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {
    this.url = url.replace(/\/+$/, "");
  }

  async call(method: string, path: string, what: string, opts: ServerCall = {}): Promise<Response> {
    const headers: Record<string, string> = {};
    if (opts.bearer !== undefined) {
      headers.Authorization = `Bearer ${opts.bearer}`;
    }
    let body: BodyInit | undefined;
    if (opts.form) {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
      body = new URLSearchParams(opts.form).toString();
    } else if (opts.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.json);
    }
    const query = opts.params
      ? "?" + new URLSearchParams(Object.entries(opts.params).map(([k, v]) => [k, String(v)])).toString()
      : "";
    try {
      return await this.fetchImpl(`${this.url}${path}${query}`, { method, headers, body });
    } catch (error) {
      throw new Unavailable(`could not reach igni server for ${what}: ${String(error)}`);
    }
  }

  /** A token for `grant`; `AuthError`, with igni server's answer, when it refuses it. */
  async grant(form: Record<string, string>, what: string): Promise<IssuedToken> {
    const response = await this.call("POST", "/v1/oauth/token", what, { form });
    if ([400, 401, 403].includes(response.status)) {
      throw new AuthError(`igni server refused ${what}: ${await response.text()}`);
    }
    if (response.status !== 200) {
      throw new Unavailable(`igni server answered ${what} with ${response.status}`);
    }
    return this.parseToken(response, what);
  }

  async parseToken(response: Response, what: string): Promise<IssuedToken> {
    try {
      const value = (await response.json()) as IssuedToken;
      if (typeof value.access_token !== "string") {
        throw new Error("no access_token");
      }
      return value;
    } catch {
      throw new Unavailable(`igni server answered ${what} with something else`);
    }
  }

  /** igni server's issuer URL, from its discovery document; asked once. */
  async issuer(): Promise<string> {
    if (this.issuerUrl === null) {
      const discovery = await this.discovery();
      const issuer = typeof discovery.issuer === "string" ? discovery.issuer : "";
      if (!issuer) {
        throw new Unavailable("igni server published no issuer");
      }
      this.issuerUrl = issuer;
    }
    return this.issuerUrl;
  }

  /** The Fleet gateway igni server advertises, or `null` when it has no Fleet. */
  async gateway(): Promise<string | null> {
    const discovery = await this.discovery();
    const gateway = discovery.igni_gateway;
    return typeof gateway === "string" && gateway ? gateway : null;
  }

  private async discovery(): Promise<{ issuer?: unknown; igni_gateway?: unknown }> {
    const response = await this.call("GET", "/.well-known/openid-configuration", "discovery");
    if (response.status !== 200) {
      return {};
    }
    try {
      return (await response.json()) as { issuer?: unknown; igni_gateway?: unknown };
    } catch {
      return {};
    }
  }

  /** Why igni server refused: its `error_description`, or else its whole answer. */
  static async reason(response: Response): Promise<string> {
    const text = await response.text();
    try {
      const described = (JSON.parse(text) as { error_description?: unknown }).error_description;
      return String(described ?? text);
    } catch {
      return text;
    }
  }
}

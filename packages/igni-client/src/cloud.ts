// Finding a person's cloud igni from igni server: discover() and setEventsOwner().
//
// igni server's GET /v1/me/cloud answers, for a person's session, whether they
// have a cloud igni they may use, the gateway's address, their group's mode and
// who pulls their service events. The shape is contracts/cloud-discovery.schema.json.
// An igni server older than the endpoint answers 404; its igni_gateway (in
// /.well-known/openid-configuration) is then all there is to go on.

import { IgniServer } from "./auth/server.js";
import type { TokenSource } from "./auth/tokens.js";
import {
  AuthError,
  GROUP_LOCAL_ONLY,
  GroupIsLocalOnly,
  IgniClientError,
  NotAllowed,
  NotSupported,
  Unavailable,
} from "./errors.js";

/** Whether the person has a cloud igni they may use from the desktop. */
export type CloudState = "available" | "unavailable";
/** Where the person's group runs igni: only on the desktop, only in the cloud, or either. */
export type Mode = "local" | "cloud" | "local_and_cloud";
/** Which side pulls the person's service events: the desktop, or the gateway for the VM. */
export type EventsOwner = "local" | "cloud";

/** Why a cloud igni is unavailable, as igni server says it today; the set is open. */
export const REASONS = ["fleet_not_configured", "group_local_only", "inactive", "not_licensed"];

export const CLOUD_PATH = "/v1/me/cloud";
export const EVENTS_OWNER_PATH = "/v1/me/cloud/events-owner";
/** Set to `1` to take a plain-HTTP gateway, as the desktop's development build does. */
export const INSECURE_GATEWAY_ENV = "IGNI_DEV_GATEWAY_INSECURE";

function known<T extends string>(value: unknown, values: readonly T[], safe: T): T {
  return (values as readonly string[]).includes(value as string) ? (value as T) : safe;
}

/** The person's group, for display. */
export interface CloudGroup {
  id: string;
  name: string;
  [key: string]: unknown;
}

/**
 * What igni server says of a person's cloud igni (GET /v1/me/cloud).
 *
 * Read leniently, as the contract asks: a `cloud` value this version does not
 * know reads as `unavailable`, a `mode` or `events_owner` as `local`, and a
 * `reason` is kept as sent. Fields igni server adds later are kept.
 */
export class CloudIgni {
  readonly cloud: CloudState;
  readonly reason: string | null;
  readonly gatewayUrl: string | null;
  readonly mode: Mode;
  readonly eventsOwner: EventsOwner;
  readonly group: CloudGroup | null;
  readonly producer: string;
  /** Fields igni server added that this version does not name. */
  readonly extra: Record<string, unknown>;

  constructor(fields: {
    cloud?: CloudState;
    reason?: string | null;
    gatewayUrl?: string | null;
    mode?: Mode;
    eventsOwner?: EventsOwner;
    group?: CloudGroup | null;
    producer?: string;
    extra?: Record<string, unknown>;
  } = {}) {
    this.cloud = fields.cloud ?? "unavailable";
    this.reason = fields.reason ?? null;
    this.gatewayUrl = fields.gatewayUrl ?? null;
    this.mode = fields.mode ?? "local";
    this.eventsOwner = fields.eventsOwner ?? "local";
    this.group = fields.group ?? null;
    this.producer = fields.producer ?? "";
    this.extra = fields.extra ?? {};
  }

  /** Read one `/v1/me/cloud` body the lenient way the contract asks for. */
  static read(raw: Record<string, unknown>): CloudIgni {
    const {
      cloud,
      reason,
      gateway_url: gatewayUrl,
      mode,
      events_owner: eventsOwner,
      group,
      producer,
      ...extra
    } = raw;
    return new CloudIgni({
      cloud: known(cloud, ["available", "unavailable"] as const, "unavailable"),
      reason: typeof reason === "string" ? reason : null,
      gatewayUrl: typeof gatewayUrl === "string" ? gatewayUrl : null,
      mode: known(mode, ["local", "cloud", "local_and_cloud"] as const, "local"),
      eventsOwner: known(eventsOwner, ["local", "cloud"] as const, "local"),
      group: isGroup(group) ? (group as CloudGroup) : null,
      producer: typeof producer === "string" ? producer : "",
      extra,
    });
  }

  /** Whether there is a cloud igni to connect to: available, a gateway, and a group that allows it. */
  get available(): boolean {
    return this.cloud === "available" && this.mode !== "local" && Boolean(this.gatewayUrl);
  }

  /** Whether the group lets the person run igni on their own computer. */
  get allowsLocal(): boolean {
    return this.mode !== "cloud";
  }

  /** What connecting to the cloud igni would raise, or `null` when it is available. */
  refusal(): IgniClientError | null {
    if (this.available) {
      return null;
    }
    if (this.reason === GROUP_LOCAL_ONLY || this.mode === "local") {
      return new GroupIsLocalOnly(
        "igni server says the person's group runs igni only on their own computer " +
          "(group_local_only); use the local igni",
      );
    }
    if (this.reason === "fleet_not_configured" || !this.gatewayUrl) {
      return new NotSupported("igni server has no Fleet: there is no cloud igni to connect to");
    }
    return new NotAllowed(
      `igni server says the person has no cloud igni to use (${this.reason ?? "unavailable"})`,
    );
  }
}

function isGroup(value: unknown): boolean {
  return Boolean(value) && typeof value === "object" && typeof (value as { id?: unknown }).id === "string";
}

function refusalReason(body: string): string {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown; error_description?: unknown; error?: unknown };
    return String(parsed.detail ?? parsed.error_description ?? parsed.error ?? "");
  } catch {
    return body.trim();
  }
}

async function answerOf(response: Response, what: string): Promise<CloudIgni> {
  const text = await response.text();
  if (response.status === 200) {
    try {
      return CloudIgni.read(JSON.parse(text) as Record<string, unknown>);
    } catch {
      throw new Unavailable(`igni server answered ${what} with something else`);
    }
  }
  const reason = refusalReason(text);
  if (response.status === 401) {
    throw new AuthError(`igni server refused the session for ${what}: ${reason}`);
  }
  if (response.status === 403) {
    throw new NotAllowed(
      `igni server refused ${what}: it answers only a person's session, never an app's, ` +
        `a space's or a VM's (${reason || "forbidden"})`,
    );
  }
  if (response.status === 409 && safeError(text) === "mode_forbids") {
    throw new NotAllowed(
      `igni server refused ${what}: the group's mode does not allow that owner (mode_forbids)`,
    );
  }
  throw new Unavailable(`igni server answered ${what} with ${response.status}`);
}

function safeError(text: string): string {
  try {
    return String((JSON.parse(text) as { error?: unknown }).error ?? "");
  } catch {
    return "";
  }
}

/** Ask igni server at `server` about the person's cloud igni. */
export async function discover(
  server: string,
  auth: TokenSource,
  opts: { fetchImpl?: typeof fetch } = {},
): Promise<CloudIgni> {
  const igniServer = new IgniServer(server, opts.fetchImpl);
  const token = await auth.token();
  const response = await igniServer.call("GET", CLOUD_PATH, "cloud discovery", { bearer: token });
  if (response.status !== 404) {
    return answerOf(response, "cloud discovery");
  }
  const gateway = await igniServer.gateway();
  if (gateway === null) {
    return new CloudIgni({ cloud: "unavailable", reason: "fleet_not_configured", mode: "local_and_cloud" });
  }
  return new CloudIgni({ cloud: "available", gatewayUrl: gateway, mode: "local_and_cloud" });
}

/** Choose who pulls the person's service events from now on: `"cloud"` or `"local"`. */
export async function setEventsOwner(
  server: string,
  auth: TokenSource,
  owner: EventsOwner,
  opts: { fetchImpl?: typeof fetch } = {},
): Promise<CloudIgni> {
  if (owner !== "cloud" && owner !== "local") {
    throw new Error("the events owner is 'cloud' or 'local'");
  }
  const igniServer = new IgniServer(server, opts.fetchImpl);
  const token = await auth.token();
  const response = await igniServer.call("PUT", EVENTS_OWNER_PATH, "the events owner", {
    bearer: token,
    json: { owner },
  });
  return answerOf(response, "the events owner");
}

/** Whether `IGNI_DEV_GATEWAY_INSECURE=1` lets a plain-HTTP gateway through. */
export function insecureGatewayAllowed(): boolean {
  return process.env[INSECURE_GATEWAY_ENV] === "1";
}

/** The gateway to connect to, or what connecting would raise. */
export function checkedGateway(cloud: CloudIgni, opts: { allowHttp: boolean }): string {
  const refusal = cloud.refusal();
  if (refusal !== null) {
    throw refusal;
  }
  const url = cloud.gatewayUrl!;
  const scheme = new URL(url).protocol;
  if (scheme === "https:" || (scheme === "http:" && opts.allowHttp)) {
    return url;
  }
  throw new NotAllowed(
    `igni server named a gateway that is not https (${url}); the person's session goes only ` +
      `over TLS (set ${INSECURE_GATEWAY_ENV}=1 for a lab gateway)`,
  );
}

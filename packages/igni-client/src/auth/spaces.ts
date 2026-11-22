// An app's spaces: its end users, each one a token source of its own.

import type { App } from "./app.js";
import { NotAllowed, Unavailable } from "../errors.js";
import { TokenCache, type TokenSource } from "./tokens.js";

/** One space of an app, as igni server keeps it. */
export interface SpaceRecord {
  space_id: string;
  app_id?: string;
  org_id?: string;
  external_id?: string;
  created_at?: string;
}

interface SpacePage {
  spaces: SpaceRecord[];
  next: string | null;
}

/** The spaces of one app: declare, look up, list and delete them, and act as one. */
export class Spaces {
  constructor(private readonly app: App) {}

  /** The space for `externalId`, made if it is new. Idempotent. */
  async declare(externalId: string): Promise<Space> {
    checkedId(externalId);
    const what = "declaring a space";
    const response = await this.app.request("PUT", this.path(externalId), { what });
    return this.space(await parsed<SpaceRecord>(response, what));
  }

  /** The space for `externalId`, or `null` when the app has none. */
  async get(externalId: string): Promise<Space | null> {
    checkedId(externalId);
    const what = "reading a space";
    const response = await this.app.request("GET", this.path(externalId), { what });
    if (response.status === 404) {
      return null;
    }
    return this.space(await parsed<SpaceRecord>(response, what));
  }

  /** Every space of this app. */
  async list(limit = 100): Promise<SpaceRecord[]> {
    const what = "listing spaces";
    const found: SpaceRecord[] = [];
    let after: string | null = null;
    for (;;) {
      const params: Record<string, string | number> = { limit };
      if (after) {
        params.after = after;
      }
      const response = await this.app.request("GET", this.path(), { what, params });
      const page = await parsed<SpacePage>(response, what);
      found.push(...page.spaces);
      if (!page.next) {
        return found;
      }
      after = page.next;
    }
  }

  /** Delete a space: its credential stops working and its VM is erased. */
  async delete(externalId: string): Promise<void> {
    checkedId(externalId);
    const what = "deleting a space";
    const response = await this.app.request("DELETE", this.path(externalId), { what });
    if (response.status !== 404) {
      await checked(response, what);
    }
  }

  /** Act as a space you already know the id of. */
  space(record: SpaceRecord | string): Space {
    if (typeof record === "string") {
      return new Space(this.app, record);
    }
    return new Space(this.app, record.space_id, record);
  }

  private path(externalId = ""): string {
    const base = `/v1/apps/${encodeURIComponent(this.app.appId)}/spaces`;
    return externalId ? `${base}/${encodeURIComponent(externalId)}` : base;
  }
}

/** One space of an app, as a token source: the app's token exchanged for the space's. */
export class Space implements TokenSource {
  private readonly tokens: TokenCache;

  constructor(
    readonly app: App,
    readonly spaceId: string,
    readonly record: SpaceRecord | null = null,
  ) {
    if (!spaceId) {
      throw new Error("a space needs its space id");
    }
    this.tokens = new TokenCache(() => app.clock(), () => app.renewBefore);
  }

  get externalId(): string {
    return this.record?.external_id ?? "";
  }

  token(): Promise<string> {
    return this.tokens.get(() => this.app.exchange(this.spaceId));
  }
}

function checkedId(externalId: string): void {
  if (!externalId || externalId.includes("/") || externalId.length > 200) {
    throw new Error("a space's external id is 1 to 200 characters, without '/'");
  }
}

async function checked(response: Response, what: string): Promise<void> {
  if ([400, 403, 409].includes(response.status)) {
    throw new NotAllowed(`igni server refused ${what}: ${await response.text()}`);
  }
  if (response.status >= 300) {
    throw new Unavailable(`igni server answered ${what} with ${response.status}`);
  }
}

async function parsed<T>(response: Response, what: string): Promise<T> {
  await checked(response, what);
  try {
    return (await response.json()) as T;
  } catch {
    throw new Unavailable(`igni server answered ${what} with something else`);
  }
}

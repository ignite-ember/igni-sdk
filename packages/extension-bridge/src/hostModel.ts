/**
 * The pieces `bridge.host` is built from: objects, properties, signals,
 * calls. `hostModel.generated.ts` is generated from igni's host schema
 * and is made of these.
 *
 *   await bridge.host.chat.processing.get();      // read a property
 *   await bridge.host.sessions.current.set(id);   // write one
 *   await bridge.host.chat.post("Done.");         // call a method
 *   bridge.on(bridge.host.chat.run_completed, (run) => { … });
 *
 * How a request reaches igni is the `HostLink`'s business — the bridge
 * forwards it to the window this page is framed in, which forwards it to
 * the host. Names are the schema's, snake_case, in both SDKs.
 */

/** Any JSON value: the host's report of something not yet typed. */
export type JsonValue = unknown;

/** Why the host refused or failed — the same codes the Python SDK raises. */
export type HostErrorCode =
  | "not_granted"
  | "not_found"
  | "invalid"
  | "read_only"
  | "stage_2"
  | "refused"
  | "unavailable"
  | "failed";

/** The host said no, or it went wrong there. `code` is for code; the message, for people. */
export class HostError extends Error {
  /**
   * The failure, as the host reported it.
   *
   * @param code — why it failed: one of the {@link HostErrorCode}s, or
   *   whatever the host said.
   * @param message — a sentence for a person to read.
   */
  constructor(
    /** Why it failed: one of the {@link HostErrorCode}s, or the host's own. */
    readonly code: HostErrorCode | string,
    message: string,
  ) {
    super(message);
    this.name = "HostError";
  }
}

/** How requests reach the igni host. */
export interface HostLink {
  /**
   * Send one request to the host.
   *
   * @param op — what to do: read a property, write one, or call a method.
   * @param path — where in the model, as `chat.processing`: the path without the leading `host.`.
   * @param options — the window or session it is about, the arguments
   *   of a call, and the value of a write.
   * @returns — whatever the host answered with.
   */
  request(
    op: "get" | "set" | "call",
    path: string,
    options: {
      /** The window to ask about, when it is not this page's own. */
      window?: string | null;
      /** The session to ask about, when it is not the one on screen. */
      session?: string | null;
      /** The arguments of a call, by name. */
      params?: Record<string, unknown>;
      /** The value of a write. */
      value?: unknown;
    },
  ): Promise<unknown>;
}

/** One object of the host model: `host.chat`, `host.windows.ui(id)`, `host.sessions.chat(id)`. */
export class HostObject {
  /**
   * One object of the model, bound to a host.
   *
   * A page never builds one: `bridge.host` is already the right one,
   * and a second would be a second conversation.
   *
   * @param link — how requests reach the host.
   * @param path — where in the model this object sits.
   * @param window — the window it belongs to, when it belongs to one.
   * @param session — the session it belongs to, when it belongs to one.
   */
  constructor(
    /** How requests reach the host. */
    protected readonly link: HostLink,
    /** Where in the model this object sits: `chat`, without the leading `host.`. */
    readonly path: string,
    /** The window it belongs to, when it belongs to one. */
    protected readonly window: string | null = null,
    /** The session it belongs to, when it belongs to one. */
    protected readonly session: string | null = null,
  ) {}

  /** @internal */
  memberPath(name: string): string {
    return this.path ? `${this.path}.${name}` : name;
  }

  /** @internal — for `Property`. */
  hostLink(): HostLink {
    return this.link;
  }

  /** @internal — for `Property`. */
  windowId(): string | null {
    return this.window;
  }

  /** @internal — for `Property`. */
  sessionId(): string | null {
    return this.session;
  }

  /**
   * Call a method on the host.
   *
   * @param name — the method's name, as the schema spells it.
   * @param params — its arguments, by name.
   * @returns — whatever the host answered with.
   */
  protected async call<T>(
    name: string,
    params: Record<string, unknown>,
  ): Promise<T> {
    const sent: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) sent[key] = value;
    }
    return (await this.link.request("call", this.memberPath(name), {
      window: this.window,
      session: this.session,
      params: sent,
    })) as T;
  }
}

/** A value of a host object: `get()` reads it, `set()` writes it. */
export class Property<T> {
  /**
   * One value of one host object.
   *
   * @param owner — the object it belongs to.
   * @param name — its name, as the schema spells it.
   * @param writable — whether it may be written.
   */
  constructor(
    /** The object it belongs to. */
    private readonly owner: HostObject,
    /** Its name, as the schema spells it. */
    readonly name: string,
    /** Whether it may be written. */
    readonly writable: boolean,
  ) {}

  /** Where in the model this value sits: `chat.processing`, without the leading `host.`. */
  get path(): string {
    return this.owner.memberPath(this.name);
  }

  /**
   * Read it.
   *
   * @returns — the value the host holds right now.
   */
  async get(): Promise<T> {
    return (await this.owner.hostLink().request("get", this.path, {
      window: this.owner.windowId(),
      session: this.owner.sessionId(),
    })) as T;
  }

  /**
   * Write it, as the person's UI would. Refused where theirs would be.
   *
   * @param value — what the host should hold for it from now on.
   */
  async set(value: T): Promise<void> {
    if (!this.writable) {
      throw new HostError("read_only", `host.${this.path} cannot be set`);
    }
    await this.owner.hostLink().request("set", this.path, {
      window: this.owner.windowId(),
      session: this.owner.sessionId(),
      value,
    });
  }
}

/**
 * One signal of one host object; `T` is what it carries. `name` is its
 * wire name — `chat.run_completed`, or for the four events that predate
 * the model their topic strings (`session.switched`, …).
 */
export class Signal<T> {
  /** Only for the type parameter; never set. */
  declare readonly carries?: T;

  /**
   * One signal of one host object.
   *
   * @param name — its wire name, as the host sends it.
   */
  constructor(
    /** Its wire name, as the host sends it: `chat.run_completed`. */
    readonly name: string,
  ) {}
}

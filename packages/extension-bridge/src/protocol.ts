/**
 * What crosses the gap between the host app and an extension's frame.
 *
 * One envelope type, versioned, with the host and the guest reading
 * the same definition. The guest half of this file is the part that
 * becomes a published package when somebody outside this repository
 * writes an extension; until then both sides import it from here, so
 * there is one description of the wire rather than two that agree
 * until they don't.
 *
 * The frame is the untrusted party. Everything the host accepts from
 * it is checked — the origin it came from, the window it came from,
 * the nonce it was issued, and whether the method is one this
 * extension was granted. None of those checks live in the guest.
 */

/** Bumped only for a change the other side cannot ignore. */
export const BRIDGE_VERSION = 1;

/**
 * Where inside an extension the user is: a deep link, replayed from
 * `location`. Its keys are the extension's own, which is why the bridge
 * cannot name them; an extension names them through `connect<P>()`.
 */
export type LaunchParams = { readonly [key: string]: unknown };

/**
 * How an extension is set up: `contributes.settings`, as an
 * administrator left it. Keyed by the setting names the extension's
 * manifest declares; an extension names them through `connect<P, S>()`.
 */
export type ExtensionSettings = { readonly [setting: string]: unknown };

/** A backend RPC's arguments, by name, as its schema defines them. */
export type RpcArgs = { readonly [name: string]: unknown };

/** Where the user is, in strings, for the host to fold into its URL. */
export type LocationState = { readonly [key: string]: string };

/** Host → guest, once, before anything else is accepted. */
export interface HelloMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "hello";
  /** Issued per frame, per session. Every guest message must carry it. */
  nonce: string;
  /** The extension this frame is, so a guest can label its own logs. */
  extensionId: string;
  /** Opaque per-extension launch parameters, from the host. */
  params: LaunchParams;
  /**
   * What `contributes.settings` is configured to, as an
   * administrator left it.
   *
   * Separate from `params` on purpose. `params` is where you are —
   * a deep link, replayed from `location`. This is how you are set
   * up. Merging them would mean a setting called `doc` and a link
   * carrying `?doc=` were the same key, and whichever the host
   * wrote last would win silently.
   *
   * Sent in `hello` and nowhere else: a change applies at the next
   * mount. Reconfiguring a frame mid-render is a harder promise
   * than it is worth until somebody asks for it, and the host's
   * `set_extension_settings` says the same thing. Empty when
   * nothing is configured.
   *
   * Optional on the wire: it was added after the envelope shipped,
   * and a guest built against this version may be framed by a host
   * that predates it. Missing reads as empty.
   */
  settings?: ExtensionSettings;
  /**
   * The extension's own service, as its page reaches it
   * (`bridge.service.url`) — the one origin beyond declared egress its
   * frame's `connect-src` admits. Null: it has none. Optional on the
   * wire for the same reason `settings` is; missing reads as null.
   */
  serviceUrl?: string | null;
  /** `"light"` or `"dark"`, following the host. */
  theme: string;
  /**
   * The published design tokens, as the host currently computes them.
   *
   * Sent rather than fetched: the guest is a different origin and its
   * own CSP refuses a cross-origin stylesheet. Sent rather than
   * baked into the guest's package, because a copy of a theme defined
   * across forty-five blocks drifts within a release.
   */
  tokens: Record<string, string>;
}

/** Host → guest, whenever the host's theme changes. */
export interface ThemeMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "theme";
  /** `"light"` or `"dark"`, following the host. */
  theme: string;
  /** The published design tokens, as the host currently computes them. */
  tokens: Record<string, string>;
}

/**
 * Host → guest: the launch parameters changed under a mounted frame.
 *
 * `params` used to arrive exactly once, inside `hello`, and there
 * was no way to send new ones. That is the difference between a
 * widget and a page: a page can be linked to, and a link that
 * resolves while the frame is already mounted had nowhere to land.
 * The host would have had to tear the frame down and rebuild it,
 * losing whatever state it held, to deliver a changed query string.
 */
export interface ParamsMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "params";
  /** Where inside the extension the user is now, changed under a mounted frame. */
  params: LaunchParams;
}

/**
 * Guest → host: where I am now.
 *
 * **Not a navigation.** `navigate` asks the host to go somewhere
 * else; this says "I am still here, and here is now this". The host
 * folds it into its own URL and replays it in the next `hello`, so a
 * reload or a shared link comes back to the same place inside the
 * extension.
 *
 * It exists because an extension has no other way to be addressable.
 * It cannot write the address bar — `allow-top-navigation` is
 * deliberately absent from the frame's sandbox — and it cannot
 * persist anything, because each extension is served from an
 * ephemeral port, a port is part of an origin, and so `localStorage`
 * is wiped whenever the backend restarts.
 *
 * Strings only, and the host is free to cap or drop them: this ends
 * up in a URL, and an extension that puts its whole state here would
 * be writing an unbounded value into the host's address bar.
 */
export interface LocationMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "location";
  /** Issued per frame, per session. Every guest message must carry it. */
  nonce: string;
  /** Where the user is, in strings, for the host to fold into its URL. */
  state: LocationState;
}

/** Guest → host: call a backend RPC. */
export interface CallMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "call";
  /** Issued per frame, per session. Every guest message must carry it. */
  nonce: string;
  /** Correlates the reply. Generated by the guest; echoed, never trusted. */
  id: string;
  /** The backend method to call, as its schema names it. */
  method: string;
  /** The method's arguments, by name. */
  args: RpcArgs;
}

/** Guest → host: ask the host app to go somewhere. */
export interface NavigateMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "navigate";
  /** Issued per frame, per session. Every guest message must carry it. */
  nonce: string;
  /** A page the host knows. The host decides whether it exists. */
  to: string;
}

/** Guest → host: this surface is finished. */
export interface CloseMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "close";
  /** Issued per frame, per session. Every guest message must carry it. */
  nonce: string;
}

/** Host → guest: the answer to one `call`. */
export interface ResultMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "result";
  /** Correlates the reply. Generated by the guest; echoed, never trusted. */
  id: string;
  /** Whether the call succeeded. */
  ok: boolean;
  /** What the call answered with, when it succeeded. */
  value?: unknown;
  /** Present when `ok` is false. Always a sentence, never an object. */
  error?: string;
}

/**
 * Guest → host: one request to the host object model (`bridge.host…`).
 *
 * The host side of the bridge forwards it to the backend with this
 * extension as the caller and its own window as the page's home, and the
 * backend checks it against the manifest's `permissions.host`. Nothing
 * here is trusted.
 */
export interface HostRequestMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "host";
  /** Issued per frame, per session. Every guest message must carry it. */
  nonce: string;
  /** Correlates the reply. Generated by the guest; echoed, never trusted. */
  id: string;
  /** What to do: read a property, write one, call a method, subscribe, unsubscribe. */
  op: "get" | "set" | "call" | "subscribe" | "unsubscribe";
  /** `chat.processing`, `chat.post`; empty for subscribe. */
  path: string;
  /** A window other than this page's own, for `host.windows.ui(id)`. */
  window?: string | null;
  /** A session other than the one on screen, for `host.sessions.chat(id)`. */
  session?: string | null;
  /** The arguments of a call, by name. */
  params?: Record<string, unknown>;
  /** The value of a write. */
  value?: unknown;
  /** Signal wire names, for subscribe and unsubscribe. */
  signals?: string[];
}

/**
 * Guest → host: a token for this extension's own service
 * (`bridge.service`).
 *
 * Carries no audience, on purpose: the host asks the backend as this
 * frame's extension, and the backend answers for the service recorded
 * on that extension's own origin. A page cannot ask for anybody
 * else's.
 */
export interface ServiceTokenMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "service-token";
  /** Issued per frame, per session. Every guest message must carry it. */
  nonce: string;
  /** Correlates the reply. Generated by the guest; echoed, never trusted. */
  id: string;
}

/** Host → guest: the answer to one `service-token`. */
export interface ServiceTokenReplyMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "service-token-reply";
  /** Correlates the reply. Generated by the guest; echoed, never trusted. */
  id: string;
  /** Whether a token was issued. */
  ok: boolean;
  /** The bearer token, when `ok`. */
  token?: string;
  /** Seconds it has left, when `ok`. */
  expiresIn?: number;
  /** Why not — nobody signed in, no service. A sentence. */
  error?: string;
}

/** Host → guest: the answer to one host-model request. */
export interface HostReplyMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "host-reply";
  /** Correlates the reply. Generated by the guest; echoed, never trusted. */
  id: string;
  /** Whether the request succeeded. */
  ok: boolean;
  /** What the request answered with, when it succeeded. */
  result?: unknown;
  /** Why not, when it did not: the host's code and a sentence for a person. */
  error?: { code: string; message: string };
}

/** Host → guest: a host-model signal this extension subscribed to. */
export interface HostSignalMessage {
  /** The wire's version: the same constant on both sides. */
  igni: typeof BRIDGE_VERSION;
  /** Which message this is. */
  kind: "signal";
  /** The signal's wire name. */
  signal: string;
  /** What the signal carries. */
  value: unknown;
}

const HOST_OPS = new Set(["get", "set", "call", "subscribe", "unsubscribe"]);

/**
 * Anything the host says to a page.
 *
 * The whole vocabulary of the host's side of the wire, in one union:
 * the greeting, the theme, the launch parameters, the answers to the
 * page's calls, the signals it subscribed to, and the tokens for the
 * extension's own service.
 */
export type HostMessage =
  | HelloMessage
  | ThemeMessage
  | ParamsMessage
  | ResultMessage
  | HostReplyMessage
  | HostSignalMessage
  | ServiceTokenReplyMessage;

/**
 * Anything a page says to the host.
 *
 * The whole vocabulary of the guest's side of the wire: the calls it
 * makes, where it wants to go, where it is, that it is finished, the
 * host-model requests it makes, and the service token it hands back.
 */
export type GuestMessage =
  | CallMessage
  | NavigateMessage
  | LocationMessage
  | CloseMessage
  | HostRequestMessage
  | ServiceTokenMessage;

/**
 * Is this a message from a guest, shaped the way we require?
 *
 * Written as a narrowing guard rather than a schema check because the
 * host has to answer this about `unknown` arriving from a frame, and
 * the answer has to be "no" for everything that is not exactly right.
 * A message that fails here is dropped without a reply: a guest that
 * can tell malformed from unauthorised has learned something.
 */
export function isGuestMessage(data: unknown): data is GuestMessage {
  if (typeof data !== "object" || data === null) return false;
  const m = data as Record<string, unknown>;
  if (m.igni !== BRIDGE_VERSION) return false;
  if (typeof m.nonce !== "string" || m.nonce.length === 0) return false;
  switch (m.kind) {
    case "call":
      return (
        typeof m.id === "string" &&
        m.id.length > 0 &&
        typeof m.method === "string" &&
        m.method.length > 0 &&
        typeof m.args === "object" &&
        m.args !== null &&
        !Array.isArray(m.args)
      );
    case "navigate":
      return typeof m.to === "string" && m.to.length > 0;
    case "location":
      // Every value a string, checked rather than assumed: this goes
      // into the host's own URL, and a guest is the untrusted party.
      return (
        typeof m.state === "object" &&
        m.state !== null &&
        !Array.isArray(m.state) &&
        Object.values(m.state as Record<string, unknown>).every(
          (value) => typeof value === "string",
        )
      );
    case "close":
      return true;
    case "service-token":
      return typeof m.id === "string" && m.id.length > 0;
    case "host":
      return (
        typeof m.id === "string" &&
        m.id.length > 0 &&
        typeof m.op === "string" &&
        HOST_OPS.has(m.op) &&
        typeof m.path === "string" &&
        (m.window === undefined ||
          m.window === null ||
          typeof m.window === "string") &&
        (m.session === undefined ||
          m.session === null ||
          typeof m.session === "string") &&
        (m.params === undefined ||
          (typeof m.params === "object" &&
            m.params !== null &&
            !Array.isArray(m.params))) &&
        (m.signals === undefined ||
          (Array.isArray(m.signals) &&
            m.signals.every((one) => typeof one === "string")))
      );
    default:
      return false;
  }
}

/** Is this a message from the host, shaped the way the guest requires? */
export function isHostMessage(data: unknown): data is HostMessage {
  if (typeof data !== "object" || data === null) return false;
  const m = data as Record<string, unknown>;
  if (m.igni !== BRIDGE_VERSION) return false;
  switch (m.kind) {
    case "hello":
      return (
        typeof m.nonce === "string" &&
        typeof m.extensionId === "string" &&
        typeof m.theme === "string" &&
        typeof m.params === "object" &&
        m.params !== null &&
        (m.settings === undefined || (typeof m.settings === "object" && m.settings !== null)) &&
        (m.serviceUrl === undefined || m.serviceUrl === null || typeof m.serviceUrl === "string") &&
        typeof m.tokens === "object" &&
        m.tokens !== null
      );
    case "theme":
      return (
        typeof m.theme === "string" &&
        typeof m.tokens === "object" &&
        m.tokens !== null
      );
    case "params":
      return (
        typeof m.params === "object" &&
        m.params !== null &&
        !Array.isArray(m.params)
      );
    case "result":
      return typeof m.id === "string" && typeof m.ok === "boolean";
    case "host-reply":
      return typeof m.id === "string" && typeof m.ok === "boolean";
    case "service-token-reply":
      return (
        typeof m.id === "string" &&
        typeof m.ok === "boolean" &&
        (m.token === undefined || typeof m.token === "string") &&
        (m.expiresIn === undefined || typeof m.expiresIn === "number")
      );
    case "signal":
      return typeof m.signal === "string" && m.signal.length > 0;
    default:
      return false;
  }
}

/**
 * May this extension call this method?
 *
 * Exact names, or a `*`-suffixed prefix. No regular expressions and no
 * `*` anywhere but the end: a permission list is read by whoever
 * approves an install, and a pattern language it cannot be read in is
 * a permission nobody actually granted.
 */
export function methodAllowed(
  method: string,
  allow: readonly string[],
): boolean {
  return allow.some((pattern) =>
    pattern.endsWith("*")
      ? method.startsWith(pattern.slice(0, -1))
      : method === pattern,
  );
}

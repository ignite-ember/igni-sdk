/**
 * The bridge an extension's page holds once the host has said hello.
 *
 * It owns everything the page learned from the host — params, theme,
 * tokens — and the three kinds of request it can be waiting on, each
 * with its own {@link Correlator}. Messages from the host are routed by
 * kind through one table, {@link GuestBridge.handlers}.
 */

import type { HostChannel } from "./channel.js";
import type { Bridge } from "./contract.js";
import { Correlator } from "./correlator.js";
import { HostError, type HostLink, type Signal } from "./hostModel.js";
import { Host } from "./hostModel.generated.js";
import type {
  ExtensionSettings,
  HelloMessage,
  HostMessage,
  HostReplyMessage,
  HostRequestMessage,
  LaunchParams,
  LocationState,
  ParamsMessage,
  ResultMessage,
  RpcArgs,
  ServiceTokenReplyMessage,
  ThemeMessage,
} from "./protocol.js";
import { type IssuedToken, ServiceError, ServiceLink } from "./service.js";
import { SignalSubscriptions } from "./signals.js";
import { applyThemeTokens, type ThemeTokens } from "./tokens.js";
import { Watchers } from "./watchers.js";

/** How long a request waits before giving up. The host has its own. */
export const DEFAULT_TIMEOUT_MS = 30_000;

/** Members whose answer is the person's, so no timeout applies to them. */
const WAITS_ON_THE_PERSON = new Set(["ui.show_dialog"]);

/** One handler per kind of message the host sends. */
type HostMessageHandlers = {
  [K in HostMessage["kind"]]: (
    message: Extract<HostMessage, { kind: K }>,
  ) => void;
};

/** A host-model request, without the envelope and the id. */
type HostRequestBody = Omit<
  HostRequestMessage,
  "igni" | "kind" | "nonce" | "id"
>;

export class GuestBridge<
  P extends LaunchParams,
  S extends ExtensionSettings,
> implements Bridge<P, S> {
  readonly extensionId: string;
  readonly settings: S;
  readonly host: Host;
  readonly service: ServiceLink;

  private currentParams: P;
  private currentTheme: string;
  private currentTokens: ThemeTokens;
  private readonly themeWatchers = new Watchers<string>();
  private readonly paramWatchers = new Watchers<P>();
  /** One numbering for every request, whatever its kind. */
  private requestCount = 0;
  private readonly nextRequest = () => ++this.requestCount;
  private readonly calls = new Correlator("", this.nextRequest);
  private readonly hostRequests = new Correlator("h", this.nextRequest);
  private readonly tokenRequests = new Correlator("s", this.nextRequest);
  private readonly signals = new SignalSubscriptions((op, signal) =>
    this.hostRequest({ op, path: "", signals: [signal] }),
  );

  private readonly handlers: HostMessageHandlers = {
    // Connecting already consumed the greeting; a repeat changes nothing.
    hello: () => {},
    theme: (message) => this.applyTheme(message),
    params: (message) => this.applyParams(message),
    signal: (message) => this.signals.deliver(message),
    "host-reply": (message) => this.settleHostRequest(message),
    "service-token-reply": (message) => this.settleTokenRequest(message),
    result: (message) => this.settleCall(message),
  };

  /**
   * `params` and `settings` are the extension's to name (`P`, `S`): the
   * host sends what the extension's own links and manifest put there.
   */
  constructor(
    private readonly channel: HostChannel,
    hello: HelloMessage,
  ) {
    this.extensionId = hello.extensionId;
    this.settings = (hello.settings ?? {}) as S;
    this.currentParams = hello.params as P;
    this.currentTheme = hello.theme;
    this.currentTokens = hello.tokens;
    const link: HostLink = {
      request: (op, path, options) =>
        this.hostRequest({
          op,
          path,
          window: options.window ?? null,
          ...(options.session ? { session: options.session } : {}),
          ...(options.params !== undefined ? { params: options.params } : {}),
          ...(op === "set" ? { value: options.value } : {}),
        }),
    };
    this.host = new Host(link);
    this.service = new ServiceLink(hello.serviceUrl ?? null, () => this.askForToken());
    // Applied before the page renders anything, so an extension never
    // paints once in the fallback palette and again in the real one.
    applyThemeTokens(this.currentTokens, document.documentElement);
  }

  get params(): P {
    return this.currentParams;
  }

  get theme(): string {
    return this.currentTheme;
  }

  get tokens(): ThemeTokens {
    return this.currentTokens;
  }

  /** Act on one message the host sent. */
  receive(message: HostMessage): void {
    // The table is keyed by kind, so this handler takes this message;
    // TypeScript cannot follow that correlation through an index.
    const handle = this.handlers[message.kind] as (
      message: HostMessage,
    ) => void;
    handle(message);
  }

  rpc<T = unknown>(
    method: string,
    args: RpcArgs = {},
    timeoutMs: number = DEFAULT_TIMEOUT_MS,
  ): Promise<T> {
    // `Number`, not `timeoutMs` as it is: null means "no limit" to a
    // correlator, but an untyped caller's null (or "500") reaches a
    // call's timer the way `setTimeout` always read it — as 0 (or 500).
    return this.calls.send<T>(
      Number(timeoutMs),
      () => new Error(`igni bridge: ${method} timed out after ${timeoutMs}ms`),
      (id) => this.channel.post({ kind: "call", id, method, args }),
    );
  }

  navigate(to: string): void {
    this.channel.post({ kind: "navigate", to });
  }

  close(): void {
    this.channel.post({ kind: "close" });
  }

  onTheme(fn: (theme: string) => void): () => void {
    return this.themeWatchers.add(fn);
  }

  onParams(fn: (params: P) => void): () => void {
    return this.paramWatchers.add(fn);
  }

  setLocation(state: LocationState): void {
    this.channel.post({ kind: "location", state });
  }

  on<T>(
    signal: Signal<T>,
    fn: (value: T) => void,
    onRefused?: (error: HostError) => void,
  ): () => void {
    return this.signals.on(signal, fn, onRefused);
  }

  private applyTheme(message: ThemeMessage): void {
    this.currentTheme = message.theme;
    this.currentTokens = message.tokens;
    applyThemeTokens(this.currentTokens, document.documentElement);
    this.themeWatchers.emit(this.currentTheme);
  }

  private applyParams(message: ParamsMessage): void {
    this.currentParams = message.params as P;
    this.paramWatchers.emit(this.currentParams);
  }

  private hostRequest(body: HostRequestBody): Promise<unknown> {
    // A dialog waits on the person, for as long as they take.
    const waits = WAITS_ON_THE_PERSON.has(body.path);
    return this.hostRequests.send(
      waits ? null : DEFAULT_TIMEOUT_MS,
      () =>
        new HostError(
          "failed",
          `igni bridge: host.${body.path || body.op} timed out after ${DEFAULT_TIMEOUT_MS}ms`,
        ),
      (id) => this.channel.post({ kind: "host", id, ...body }),
    );
  }

  /** One token request to the host, which asks igni as this extension. */
  private askForToken(): Promise<IssuedToken> {
    return this.tokenRequests.send<IssuedToken>(
      DEFAULT_TIMEOUT_MS,
      () =>
        new ServiceError(
          "failed",
          `igni bridge: no service token within ${DEFAULT_TIMEOUT_MS}ms`,
        ),
      (id) => this.channel.post({ kind: "service-token", id }),
    );
  }

  private settleCall(reply: ResultMessage): void {
    if (reply.ok) this.calls.resolve(reply.id, reply.value);
    else
      this.calls.reject(
        reply.id,
        new Error(
          reply.error || "the host refused the call without saying why",
        ),
      );
  }

  private settleHostRequest(reply: HostReplyMessage): void {
    if (reply.ok) this.hostRequests.resolve(reply.id, reply.result);
    else
      this.hostRequests.reject(
        reply.id,
        new HostError(
          reply.error?.code ?? "failed",
          reply.error?.message ?? "the host refused without saying why",
        ),
      );
  }

  private settleTokenRequest(reply: ServiceTokenReplyMessage): void {
    if (reply.ok && typeof reply.token === "string")
      this.tokenRequests.resolve(reply.id, {
        token: reply.token,
        expiresIn: reply.expiresIn ?? 0,
      });
    else
      this.tokenRequests.reject(
        reply.id,
        new ServiceError(
          "refused",
          reply.error || "igni gave no token for this extension's service",
        ),
      );
  }
}

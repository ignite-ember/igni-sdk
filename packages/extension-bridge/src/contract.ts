/**
 * What an extension's page is handed by `connect()`.
 *
 * `P` and `S` are the extension's own launch parameters and settings:
 * the host sends whatever the extension's links and manifest put there,
 * so the extension is the one that can name them.
 */

import type { HostError, Signal } from "./hostModel";
import type { Host } from "./hostModel.generated";
import type {
  ExtensionSettings,
  LaunchParams,
  LocationState,
  RpcArgs,
} from "./protocol";
import type { ServiceBridge } from "./service";
import type { ThemeTokens } from "./tokens";

/** What an extension's page is handed. */
export interface Bridge<
  P extends LaunchParams = LaunchParams,
  S extends ExtensionSettings = ExtensionSettings,
> {
  /** The id this frame is, as the host named it. */
  readonly extensionId: string;
  /** Launch parameters, as the host passed them. */
  readonly params: P;
  /**
   * What `contributes.settings` is configured to.
   *
   * Fixed for the life of this frame — a change applies at the next
   * mount, so there is no `onSettings`. Separate from {@link params}
   * because that is *where you are* and this is *how you are set
   * up*; one namespace for both would make a setting and a query
   * key with the same name the same thing.
   */
  readonly settings: S;
  /** The host's theme now. Use `onTheme` to follow it. */
  readonly theme: string;
  /**
   * The published design tokens, already applied to this document's
   * root. Here as a reading for anything that needs a value rather
   * than a CSS variable — a canvas, a chart library.
   */
  readonly tokens: ThemeTokens;
  /** Call a backend RPC. Rejects with the host's refusal, as a sentence. */
  rpc<T = unknown>(
    method: string,
    args?: RpcArgs,
    timeoutMs?: number,
  ): Promise<T>;
  /** Ask the host app to navigate. It decides whether to. */
  navigate(to: string): void;
  /** Tell the host this surface is finished. */
  close(): void;
  /** Follow the host's theme. Returns an unsubscribe. */
  onTheme(fn: (theme: string) => void): () => void;
  /**
   * Follow the launch parameters.
   *
   * They arrive in `hello` and can change afterwards — a link
   * resolved while this frame was already mounted, or the host
   * restoring a saved location. Without this the host would have to
   * rebuild the frame to deliver a changed parameter, losing
   * whatever state it held.
   *
   * Fires only on change, never for the initial value; read
   * {@link params} for that.
   */
  onParams(fn: (params: P) => void): () => void;
  /**
   * Tell the host where inside this extension the user now is.
   *
   * Not a navigation — {@link navigate} is that. This says "still
   * here, and here is now this". The host folds it into its own URL
   * and replays it in the next `hello`, which is the only way an
   * extension can be linked to or restored: the frame cannot write
   * the address bar, and its `localStorage` dies with the ephemeral
   * port it was served from.
   *
   * Strings only, and keep it small — it ends up in the host's URL.
   * Call it when the user lands somewhere worth returning to, not on
   * every keystroke.
   */
  setLocation(state: LocationState): void;

  /**
   * igni, as this extension sees it: the host object model
   * (`docs/HOST_OBJECT_MODEL.md` in igni). The same model the
   * extension's process reaches as `ext.host`.
   *
   *   const busy = await bridge.host.chat.processing.get();
   *   await bridge.host.chat.post("Two issues in the files you changed.");
   *
   * A page's `host.ui` is the window it is framed in. Every object needs
   * its grant in the manifest's `permissions.host`; one that is not
   * granted rejects with a `HostError` whose `code` is `not_granted`.
   */
  readonly host: Host;

  /**
   * Handle a host signal: `bridge.on(bridge.host.chat.run_completed, fn)`.
   *
   * The first handler of a signal subscribes to it; removing the last
   * one unsubscribes. A signal whose object is not granted never
   * arrives; the refusal goes to `onRefused`, or to the console when
   * there is none. Returns an unsubscribe.
   */
  on<T>(
    signal: Signal<T>,
    fn: (value: T) => void,
    onRefused?: (error: HostError) => void,
  ): () => void;

  /**
   * The extension's own service, reached directly, as the signed-in
   * person:
   *
   *   const res = await bridge.service.fetch("/v1/notes");
   *   const socket = await bridge.service.websocket("/v1/rooms/a");
   *
   * The host fetches a token whose audience is this extension's service
   * and nothing else; it is kept and renewed before it expires. No
   * `permissions.host` grant: having a service is the grant — see
   * `docs/HOST_OBJECT_MODEL.md` in igni. `url` is `null` when the
   * extension has none.
   */
  readonly service: ServiceBridge;
}

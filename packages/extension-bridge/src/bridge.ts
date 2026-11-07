/**
 * The guest half: what an extension's page imports to reach igni.
 *
 * This is the file that becomes a published package. Nothing in it
 * imports from the rest of the app, and nothing in it is trusted by
 * the host — every check is on the other side. What it owes an
 * extension author is an object that behaves like the client they
 * would have had if their panel were part of the app, so that porting
 * one is not a rewrite.
 *
 * The shape it presents is `rpc(method, args, timeoutMs)`, which is
 * the whole surface the first panel ported behind it used. Everything else here —
 * navigate, close, theme, params — is what a panel needed from the
 * app around it and used to get by being inside it.
 */

import { HostChannel } from "./channel";
import type { Bridge } from "./contract";
import { DEFAULT_TIMEOUT_MS, GuestBridge } from "./guestBridge";
import {
  type ExtensionSettings,
  type LaunchParams,
  isHostMessage,
} from "./protocol";

/**
 * Wait for the host's `hello`, then hand back the bridge.
 *
 * Connecting is asynchronous because the host issues the nonce, and
 * without one there is nothing to say. An extension that renders
 * before awaiting this is rendering before it knows which extension
 * it is.
 *
 * `P` and `S` name the extension's own launch parameters and settings;
 * the bridge passes on what the host sent without checking it against
 * them.
 */
export function connect<
  P extends LaunchParams = LaunchParams,
  S extends ExtensionSettings = ExtensionSettings,
>(options: { timeoutMs?: number } = {}): Promise<Bridge<P, S>> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const host = window.parent;
  if (host === window) {
    return Promise.reject(
      new Error(
        "igni bridge: this page is not framed by a host, so there is nothing to connect to",
      ),
    );
  }

  return new Promise<Bridge<P, S>>((resolve, reject) => {
    const timer = setTimeout(() => {
      window.removeEventListener("message", onHello);
      reject(
        new Error(`igni bridge: no hello from the host within ${timeoutMs}ms`),
      );
    }, timeoutMs);

    function onHello(event: MessageEvent) {
      if (event.source !== host) return;
      if (!isHostMessage(event.data) || event.data.kind !== "hello") return;
      clearTimeout(timer);
      window.removeEventListener("message", onHello);
      const channel = new HostChannel(host, event.data.nonce);
      const bridge = new GuestBridge<P, S>(channel, event.data);
      window.addEventListener("message", (message: MessageEvent) => {
        if (!channel.isFrom(message) || !isHostMessage(message.data)) return;
        bridge.receive(message.data);
      });
      resolve(bridge);
    }

    window.addEventListener("message", onHello);
  });
}

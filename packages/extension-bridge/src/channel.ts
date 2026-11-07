/**
 * The guest's line to the window it is framed in: who that window is,
 * and the nonce every message to it must carry.
 */

import { BRIDGE_VERSION, type GuestMessage } from "./protocol";

/** A guest message without the envelope `HostChannel` adds. */
export type GuestBody = {
  [K in GuestMessage["kind"]]: Omit<
    Extract<GuestMessage, { kind: K }>,
    "igni" | "nonce"
  >;
}[GuestMessage["kind"]];

export class HostChannel {
  constructor(
    private readonly host: Window,
    private readonly nonce: string,
  ) {}

  /**
   * Did this event come from the host? The host is the only window that
   * can reach this frame's parent slot, so the source is the check that
   * matters. The origin is not pinned: the guest does not know which
   * origin the app is served from, and learning it from the message
   * would make the check circular.
   */
  isFrom(event: MessageEvent): boolean {
    return event.source === this.host;
  }

  post(body: GuestBody): void {
    // Targeted at "*" deliberately: the guest does not know the host's
    // origin, and guessing one would mean a message silently going
    // nowhere the first time the app is served from somewhere else.
    // Nothing secret travels in this direction — the host authorises,
    // the guest only asks.
    this.host.postMessage(
      { igni: BRIDGE_VERSION, nonce: this.nonce, ...body },
      "*",
    );
  }
}

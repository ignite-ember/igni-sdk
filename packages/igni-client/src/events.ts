// What igni sends: the typed event union, and the lightweight parser that turns
// one decoded frame into it.
//
// Validation is deliberately light (no runtime schema library). A message is
// matched by its `type` (and, for a push, its `channel`); its fields are read
// with fallbacks where they are read. A wire `type` this version does not know
// still arrives — everything it carried is kept — so an older client keeps
// working against a newer igni; it just does not have a typed shape for it.

import { EVENT_TYPES, PUSH_CHANNELS } from "./models.generated.js";
import type { JsonValue, ServerEvent } from "./models.generated.js";
import type { WireMessage } from "./wire.js";

/** A message this version of igni-client has no typed shape for. Every field is kept. */
export interface Unknown {
  type: string;
  id: string;
  session_id: string;
  event_seq: number;
  [key: string]: JsonValue | undefined;
}

/** Any message igni may send that this client knows, as a discriminated union on `type`. */
export type Event = ServerEvent;

/** The envelope a message about one run carries (the base of RunStarted, RunCompleted, …). */
export interface RunEvent {
  type: string;
  id?: string;
  session_id?: string;
  event_seq?: number;
  run_id?: string;
  parent_run_id?: string;
}

/** Whether this client knows the wire `type` of a message. */
export function isKnownEvent(type: string): boolean {
  return EVENT_TYPES.has(type);
}

/** Whether a known channel types this push. */
export function isTypedPush(channel: string | undefined): boolean {
  return channel !== undefined && PUSH_CHANNELS.has(channel);
}

/**
 * One decoded frame, with its envelope filled in. Never throws. The result is a
 * loose `WireMessage`; the public surfaces narrow it to a typed `Event`.
 */
export function parseEvent(raw: WireMessage): WireMessage {
  return {
    ...raw,
    type: String(raw.type ?? ""),
    id: String(raw.id ?? ""),
    session_id: String(raw.session_id ?? ""),
    event_seq: typeof raw.event_seq === "number" ? raw.event_seq : 0,
  };
}

export type { ServerEvent } from "./models.generated.js";

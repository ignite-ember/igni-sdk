// The bytes on igni's socket: what a frame serialises to, and the loose shape
// of a message read back.

import type { JsonValue } from "./models.generated.js";

/** One message a client sends: a `type` and the fields given a value. */
export type Frame = { type: string } & Record<string, unknown>;

/**
 * A message read off the socket, before it is narrowed to a typed `Event`.
 *
 * Every field is optional: a message a newer igni sends may carry more, and one
 * this version reads may carry less. Readers fill in with `?? default`.
 */
export interface WireMessage {
  type: string;
  id?: string;
  session_id?: string;
  event_seq?: number;
  run_id?: string;
  parent_run_id?: string;
  channel?: string;
  payload?: unknown;
  client_id?: string;
  result?: JsonValue;
  error?: string | null;
  code?: string | null;
  text?: string;
  [key: string]: unknown;
}

/**
 * `frame` as igni reads it: its `type` and every field given a value.
 *
 * A field left `undefined` is dropped, so igni applies the contract's default.
 */
export function toWire(frame: Frame): string {
  const out: Record<string, unknown> = { type: frame.type };
  for (const [key, value] of Object.entries(frame)) {
    if (key !== "type" && value !== undefined) {
      out[key] = value;
    }
  }
  return JSON.stringify(out);
}

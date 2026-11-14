/**
 * The note editor as one state machine.
 *
 * The draft, the revision it will be saved against, and where the save
 * stands are one value with one writer, so "unsaved", "may publish" and
 * "may autosave" are all read off the same phase instead of being
 * re-derived from separate flags.
 */

import type { Note } from "./notes";

/** Where the draft stands against the server. */
export type SavePhase =
  /** The server holds exactly what the editor shows. */
  | { kind: "saved" }
  /** Edited since the last save; autosave is armed. */
  | { kind: "dirty" }
  /** A save is out. Typing meanwhile is kept and saved next. */
  | { kind: "saving" }
  /**
   * The last save failed for a reason other than a conflict. Nothing
   * retries until the draft is edited again.
   */
  | { kind: "failed" }
  /**
   * Somebody else saved first. Autosave stops for good: the draft is
   * kept so its author can copy it, and nothing overwrites theirs.
   */
  | { kind: "conflict"; theirRevision: string };

export interface EditorState {
  draft: string;
  revision: string;
  save: SavePhase;
}

export type EditorEvent =
  | { type: "edited"; body: string }
  | { type: "saveStarted" }
  | { type: "saved"; sent: string; revision: string }
  | { type: "saveFailed" }
  | { type: "conflicted"; theirRevision: string };

export function initialEditor(note: Note): EditorState {
  return { draft: note.body, revision: note.revision, save: { kind: "saved" } };
}

/** What an edit does to the save phase. */
function afterEdit(save: SavePhase): SavePhase {
  // In flight: the answer decides. In conflict: nothing saves again.
  if (save.kind === "saving" || save.kind === "conflict") return save;
  return { kind: "dirty" };
}

export function editorReducer(state: EditorState, event: EditorEvent): EditorState {
  switch (event.type) {
    case "edited":
      return { ...state, draft: event.body, save: afterEdit(state.save) };
    case "saveStarted":
      return { ...state, save: { kind: "saving" } };
    case "saved":
      // Only what was sent is saved; typing during the round trip
      // leaves the draft dirty against the revision just received.
      return {
        ...state,
        revision: event.revision,
        save: { kind: state.draft === event.sent ? "saved" : "dirty" },
      };
    case "saveFailed":
      return { ...state, save: { kind: "failed" } };
    case "conflicted":
      return { ...state, save: { kind: "conflict", theirRevision: event.theirRevision } };
  }
}

/** Anything the server does not hold yet. */
export function isUnsaved(save: SavePhase): boolean {
  return save.kind !== "saved";
}

/** The status line, for the toolbar and the live region alike. */
export function saveStatus(save: SavePhase): "Saving" | "Unsaved changes" | "Saved" {
  if (save.kind === "saving") return "Saving";
  return isUnsaved(save) ? "Unsaved changes" : "Saved";
}

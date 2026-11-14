/**
 * The editor's behaviour: the state machine, the debounced autosave
 * that drives it, and the unsaved-work warning.
 */

import { useCallback, useEffect, useReducer } from "react";

import { useToast } from "@ignite-ember/ui-react";

import { editorReducer, initialEditor, isUnsaved, type EditorState } from "./editor";
import { ConflictError, messageOf, type Note, type NotesClient } from "./notes";

/** How long after the last keystroke to save. */
export const AUTOSAVE_MS = 1_500;

export interface NoteEditor {
  state: EditorState;
  edit: (body: string) => void;
}

export function useNoteEditor(client: NotesClient, version: string, note: Note): NoteEditor {
  const [state, dispatch] = useReducer(editorReducer, note, initialEditor);
  const toast = useToast();
  const { draft, revision } = state;
  const phase = state.save.kind;

  // Autosave, armed only while the draft is dirty. A save in flight, a
  // failed one and a conflict all leave it disarmed, so nothing retries
  // on its own: the next keystroke is what arms it again.
  useEffect(() => {
    if (phase !== "dirty") return;
    const timer = setTimeout(() => {
      dispatch({ type: "saveStarted" });
      client.save(version, draft, revision).then(
        (saved) => dispatch({ type: "saved", sent: draft, revision: saved.revision }),
        (cause: unknown) => {
          if (cause instanceof ConflictError) {
            dispatch({ type: "conflicted", theirRevision: cause.theirRevision });
            return;
          }
          toast.show(messageOf(cause), { tone: "danger" });
          dispatch({ type: "saveFailed" });
        },
      );
    }, AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [client, version, draft, revision, phase, toast]);

  // `beforeunload` covers a reload of this frame only. The host
  // navigating away is not covered: `HostMessage` has no "about to
  // close" for a guest to veto (see the README).
  const unsaved = isUnsaved(state.save);
  useEffect(() => {
    if (!unsaved) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);

  const edit = useCallback((body: string) => dispatch({ type: "edited", body }), []);
  return { state, edit };
}

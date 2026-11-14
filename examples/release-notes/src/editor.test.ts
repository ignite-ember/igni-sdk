/** The editor's state machine, without React. */
import { describe, expect, it } from "vitest";

import { editorReducer, initialEditor, isUnsaved, saveStatus, type EditorState } from "./editor";

const start = (): EditorState => initialEditor({ version: "1", body: "a", revision: "r1" });

describe("editorReducer", () => {
  it("starts saved with the note's body and revision", () => {
    expect(start()).toEqual({ draft: "a", revision: "r1", save: { kind: "saved" } });
  });

  it("an edit makes a saved, dirty or failed draft dirty", () => {
    for (const kind of ["saved", "dirty", "failed"] as const) {
      const next = editorReducer({ ...start(), save: { kind } }, { type: "edited", body: "b" });
      expect(next).toEqual({ draft: "b", revision: "r1", save: { kind: "dirty" } });
    }
  });

  it("an edit during a save or a conflict keeps the phase and the text", () => {
    const saving = editorReducer({ ...start(), save: { kind: "saving" } }, { type: "edited", body: "b" });
    expect(saving.save).toEqual({ kind: "saving" });
    expect(saving.draft).toBe("b");
    const conflict = { kind: "conflict", theirRevision: "r9" } as const;
    const kept = editorReducer({ ...start(), save: conflict }, { type: "edited", body: "b" });
    expect(kept.save).toEqual(conflict);
    expect(kept.draft).toBe("b");
  });

  it("a save answered for the text on screen is saved, for older text dirty", () => {
    const saving: EditorState = { draft: "b", revision: "r1", save: { kind: "saving" } };
    expect(editorReducer(saving, { type: "saved", sent: "b", revision: "r2" })).toEqual({
      draft: "b",
      revision: "r2",
      save: { kind: "saved" },
    });
    expect(editorReducer(saving, { type: "saved", sent: "a", revision: "r2" }).save).toEqual({ kind: "dirty" });
  });

  it("records a failure and a conflict as their own phases", () => {
    expect(editorReducer(start(), { type: "saveFailed" }).save).toEqual({ kind: "failed" });
    expect(editorReducer(start(), { type: "conflicted", theirRevision: "r9" }).save).toEqual({
      kind: "conflict",
      theirRevision: "r9",
    });
    expect(editorReducer(start(), { type: "saveStarted" }).save).toEqual({ kind: "saving" });
  });
});

describe("the status read off the phase", () => {
  it.each([
    [{ kind: "saved" }, false, "Saved"],
    [{ kind: "dirty" }, true, "Unsaved changes"],
    [{ kind: "saving" }, true, "Saving"],
    [{ kind: "failed" }, true, "Unsaved changes"],
    [{ kind: "conflict", theirRevision: "r9" }, true, "Unsaved changes"],
  ] as const)("%j is unsaved=%s and reads %s", (save, unsaved, status) => {
    expect(isUnsaved(save)).toBe(unsaved);
    expect(saveStatus(save)).toBe(status);
  });
});

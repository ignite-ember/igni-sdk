/**
 * Release Notes — the second shape.
 *
 * The reference extension is a single view, mostly reading, one pane,
 * no prose. This is the opposite of all four: a two-pane browser over
 * editable documents with comments, and its job is to find what that
 * costs. The README has what it found.
 *
 * - `setLocation` / `onParams` make an extension addressable. Picking
 *   a version writes it into the host's URL; a reload or a shared
 *   link comes back to the same note.
 * - `AppShell` + `Split` + `Scroll` give two independently scrolling
 *   panes.
 * - The one thing still hand-rolled is an unsaved-work guard:
 *   `HostMessage` has no "about to close" for a guest to veto, so
 *   `beforeunload` covers a reload of this frame and not the host
 *   navigating away.
 *
 * Modules: `notes.ts` is the backend client, `ReleaseList.tsx` the left
 * pane, `NoteView.tsx` the right, `editor.ts` + `useNoteEditor.ts` the
 * editor's state machine and autosave, `PublishDialog.tsx` the publish.
 *
 * It is not bundled: `igni-ui.css` (from `@ignite-ember/ui-css`) has
 * to be copied in beside the source. Type-checked and tested in CI.
 */

import { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { connect, type Bridge } from "@ignite-ember/extension-bridge";
import {
  AppShell,
  Banner,
  Empty,
  ErrorBoundary,
  Heading,
  Scroll,
  Spinner,
  Split,
  ToastHost,
  Toolbar,
} from "@ignite-ember/ui-react";

import { messageOf, NotesClient } from "./notes";
import { NoteView } from "./NoteView";
import { ReleaseList } from "./ReleaseList";
import { useReleases } from "./useReleases";

import "./igni-ui.css";
import "./panel.css";

/** The list's width, restored from the host's URL: the one place that survives the backend restarting. */
function initialWidth(params: Bridge["params"]): number {
  const raw = params.width;
  const parsed = typeof raw === "string" ? Number.parseInt(raw, 10) : NaN;
  return Number.isFinite(parsed) ? parsed : 280;
}

function versionParam(params: Bridge["params"]): string | null {
  return typeof params.version === "string" ? params.version : null;
}

export function NotesPanel({ client, igni }: { client: NotesClient; igni: Bridge }) {
  const { load, refresh } = useReleases(client);
  const [selected, setSelected] = useState<string | null>(() => versionParam(igni.params));
  const [asideWidth, setAsideWidth] = useState(() => initialWidth(igni.params));
  const releases = load.state === "ready" ? load.releases : [];
  const newest = releases[0]?.version ?? null;

  // Nothing picked and nothing asked for: the newest, so the right
  // pane is never an empty frame on first paint. Pinned once, so a
  // refresh that brings back a different newest does not re-point
  // (and remount) the note that is open.
  useEffect(() => {
    if (newest !== null) setSelected((current) => current ?? newest);
  }, [newest]);

  // A link resolved while this frame is mounted: followed in place,
  // without losing what is being edited.
  useEffect(
    () =>
      igni.onParams((params) => {
        const version = versionParam(params);
        if (version !== null) setSelected(version);
      }),
    [igni],
  );

  const pick = useCallback(
    (version: string) => {
      setSelected(version);
      // Not `navigate`: "still here, and here is now this", which the
      // host folds into its own URL so a reload comes back.
      igni.setLocation({ version });
    },
    [igni],
  );

  return (
    <AppShell
      header={
        <Toolbar>
          <Heading level={2}>Release notes</Heading>
          {load.state === "loading" ? <Spinner label="Loading releases" /> : null}
        </Toolbar>
      }
    >
      {load.state === "failed" ? <Banner tone="danger">{load.message}</Banner> : null}
      {load.state === "ready" && load.refreshError !== null ? (
        <Banner tone="danger">{`Could not refresh the releases: ${load.refreshError}`}</Banner>
      ) : null}

      <Split
        aside={
          <Scroll>
            <ReleaseList
              releases={releases}
              selected={selected}
              onPick={pick}
              loading={load.state === "loading"}
            />
          </Scroll>
        }
        label="Resize the release list"
        defaultWidth={asideWidth}
        onResize={(width) => {
          setAsideWidth(width);
          // An extension's localStorage dies with its ephemeral port;
          // the host's URL does not.
          if (selected !== null) {
            igni.setLocation({ version: selected, width: String(width) });
          }
        }}
      >
        {selected === null ? (
          <Empty>Pick a release to see its notes.</Empty>
        ) : (
          // Keyed so a different version remounts the editor: a draft
          // held above it would be saved against the wrong revision.
          <NoteView key={selected} client={client} version={selected} onPublished={refresh} />
        )}
      </Split>
    </AppShell>
  );
}

async function main() {
  const root = document.getElementById("root");
  if (!root) throw new Error("index.html has no #root");

  let igni: Bridge;
  try {
    igni = await connect();
  } catch (cause) {
    root.textContent = `Could not reach igni: ${messageOf(cause)}`;
    return;
  }

  createRoot(root).render(
    <ErrorBoundary onError={(error) => console.error("[acme.notes]", error)}>
      <ToastHost>
        <NotesPanel client={new NotesClient(igni)} igni={igni} />
      </ToastHost>
    </ErrorBoundary>,
  );
}

void main();

/** One release's note, its comments, and the editor. */

import { useEffect, useState } from "react";

import {
  AppShell,
  Banner,
  Button,
  Field,
  Heading,
  LiveRegion,
  Markdown,
  Scroll,
  Tabs,
  TabPanel,
  Text,
  Textarea,
  Toolbar,
} from "@ignite-ember/ui-react";

import { CommentList } from "./CommentList";
import { saveStatus } from "./editor";
import { messageOf, type Comment, type Note, type NotesClient } from "./notes";
import { PublishDialog } from "./PublishDialog";
import { useNoteEditor } from "./useNoteEditor";

type NoteLoad =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "ready"; note: Note; comments: Comment[] };

interface NoteViewProps {
  client: NotesClient;
  version: string;
  /** Called after a publish lands, so the release list can catch up. */
  onPublished: () => void;
}

export function NoteView({ client, version, onPublished }: NoteViewProps) {
  const [load, setLoad] = useState<NoteLoad>({ state: "loading" });

  useEffect(() => {
    let alive = true;
    Promise.all([client.note(version), client.comments(version)]).then(
      ([note, comments]) => {
        if (alive) setLoad({ state: "ready", note, comments });
      },
      (error: unknown) => {
        if (alive) setLoad({ state: "failed", message: messageOf(error) });
      },
    );
    return () => {
      alive = false;
    };
  }, [client, version]);

  if (load.state === "loading") return <Text tone="muted">Loading…</Text>;
  if (load.state === "failed") return <Banner tone="danger">{load.message}</Banner>;
  return (
    <NoteEditor
      client={client}
      version={version}
      onPublished={onPublished}
      note={load.note}
      comments={load.comments}
    />
  );
}

function NoteEditor({
  client,
  version,
  onPublished,
  note,
  comments,
}: NoteViewProps & { note: Note; comments: Comment[] }) {
  const { state, edit } = useNoteEditor(client, version, note);
  const [confirming, setConfirming] = useState(false);
  const [tab, setTab] = useState("write");
  const status = saveStatus(state.save);
  // The strip and its panels have to agree on an id prefix, so a
  // caller with panels passes one to both.
  const base = `note-${version}`;

  return (
    <AppShell
      header={
        <Toolbar>
          <Heading level={3}>{version}</Heading>
          <Text tone="muted">{status === "Saving" ? "Saving…" : status}</Text>
          <Button
            variant="primary"
            disabled={state.save.kind !== "saved"}
            onClick={() => setConfirming(true)}
          >
            Publish
          </Button>
        </Toolbar>
      }
    >
      {state.save.kind === "conflict" ? (
        <Banner tone="danger">
          Somebody else saved this note while you were editing it. Your text is
          still here — copy what you need, then reload.
        </Banner>
      ) : null}

      <LiveRegion>{status}</LiveRegion>

      <Tabs
        base={base}
        label={`Notes for ${version}`}
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "write", label: "Write" },
          { id: "preview", label: "Preview" },
          { id: "comments", label: `Comments (${comments.length})` },
        ]}
      />

      <TabPanel base={base} id="write" active={tab}>
        <Field label="Notes" htmlFor="body" hint="Markdown. Saved as you type.">
          <Textarea
            id="body"
            className="note-editor"
            value={state.draft}
            onChange={(event) => edit(event.target.value)}
          />
        </Field>
      </TabPanel>

      <TabPanel base={base} id="preview" active={tab}>
        <Scroll>
          <Markdown>{state.draft}</Markdown>
        </Scroll>
      </TabPanel>

      <TabPanel base={base} id="comments" active={tab}>
        <Scroll>
          <CommentList comments={comments} />
        </Scroll>
      </TabPanel>

      {confirming ? (
        <PublishDialog
          client={client}
          version={version}
          draft={state.draft}
          onClose={() => setConfirming(false)}
          onPublished={() => {
            setConfirming(false);
            onPublished();
          }}
        />
      ) : null}
    </AppShell>
  );
}

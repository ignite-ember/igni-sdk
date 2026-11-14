/** The confirmation in front of a publish, and the publish itself. */

import { useState } from "react";

import { Button, Dialog, Text, useToast } from "@ignite-ember/ui-react";

import { messageOf, type NotesClient } from "./notes";

/** While a publish is out the confirm button is disabled, which is also the guard against a second one. */
type PublishStep = "confirming" | "publishing";

function wordCount(text: string): string {
  const trimmed = text.trim();
  return trimmed.length === 0 ? "This note is empty." : `${trimmed.split(/\s+/).length} words.`;
}

export function PublishDialog({
  client,
  version,
  draft,
  onClose,
  onPublished,
}: {
  client: NotesClient;
  version: string;
  draft: string;
  onClose: () => void;
  onPublished: () => void;
}) {
  const [step, setStep] = useState<PublishStep>("confirming");
  const toast = useToast();

  const publish = () => {
    if (step === "publishing") return;
    setStep("publishing");
    client.publish(version).then(
      () => {
        toast.show(`${version} published`, { tone: "success" });
        onPublished();
      },
      (error: unknown) => {
        toast.show(messageOf(error), { tone: "danger" });
        setStep("confirming");
      },
    );
  };

  return (
    <Dialog
      title={`Publish ${version}?`}
      sub="Everyone with access sees this version. The draft is kept."
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={step === "publishing"}
            aria-busy={step === "publishing"}
            onClick={publish}
          >
            Publish
          </Button>
        </>
      }
    >
      <Text tone="muted">{wordCount(draft)}</Text>
    </Dialog>
  );
}

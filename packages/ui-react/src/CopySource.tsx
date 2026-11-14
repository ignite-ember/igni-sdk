/**
 * Copies a diagram's fenced source, not the rendered SVG.
 *
 * What somebody wants from a diagram is the text that made it —
 * to paste into another document, or to fix. Nobody wants the
 * markup a renderer produced.
 *
 * A blocked clipboard says so, on the button itself: a click that
 * appears to work and leaves nothing to paste is worse than one
 * that admits it failed.
 */
import { useEffect, useRef, useState } from "react";

import { MenuIcon } from "./MenuIcon.js";

type CopyState = "idle" | "copied" | "failed";

/** How long "Copied" or "Copy failed" stays before the button resets. */
const FEEDBACK_MS = 1300;

const LABEL: Record<CopyState, string> = {
  idle: "Copy source",
  copied: "Copied",
  failed: "Copy failed — the clipboard is blocked",
};

export function CopySource({ source }: { source: string }) {
  const [state, setState] = useState<CopyState>("idle");

  const timer = useRef<number | undefined>(undefined);

  // A pending reset must not outlive the button, nor cut a later
  // click's feedback short.
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      window.clearTimeout(timer.current);
    };
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(source);
      setState("copied");
    } catch {
      setState("failed");
    }
    if (!alive.current) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), FEEDBACK_MS);
  };

  return (
    <button
      type="button"
      className="diagram-copy"
      data-state={state}
      title={LABEL[state]}
      aria-label={LABEL[state]}
      onClick={() => void copy()}
    >
      <MenuIcon name={state === "copied" ? "check" : "copy"} />
    </button>
  );
}

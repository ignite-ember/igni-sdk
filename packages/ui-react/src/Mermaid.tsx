/**
 * Mermaid diagrams.
 *
 * ```mermaid``` becomes a diagram, in a document exactly as it
 * already does in chat.
 *
 * **A fence, deliberately.** This is what lets a document carry a
 * diagram while staying markdown: the source is a code block, so it
 * diffs a line at a time, chunks for search, survives the editor's
 * round trip untouched, and reads as its own source in any other
 * markdown tool. The alternative — embedding HTML, or a bespoke
 * node type — would cost every one of those. ``fenceInfo`` is the
 * helper that spots one.
 *
 * Shared by the chat and the document view rather than copied.
 * There was one mermaid renderer living inside ``ChatItems`` and a
 * document could not reach it, which is the usual way two renderers
 * of the same thing start disagreeing about what it looks like.
 *
 * **`mermaid` is a peer dependency**, loaded on demand. An
 * extension that never renders a diagram never downloads it; one
 * that does must have it installed. This is the only export under
 * the floor that asks anything of your package.json.
 *
 * ``SpecBlock`` used to live here and does not any more: it reaches
 * into the app for the ``json-render`` renderer, so it could not be
 * published without publishing that too. It is app code now.
 */
import { useEffect, useRef, useState } from "react";

import { CopySource } from "./CopySource";

type MermaidTheme = "default" | "dark";

interface MermaidConfig {
  startOnLoad: boolean;
  securityLevel: "strict";
  theme: MermaidTheme;
  themeVariables: { fontFamily: string; background: string };
}

interface MermaidLib {
  initialize: (config: MermaidConfig) => void;
  render: (id: string, src: string) => Promise<{ svg: string }>;
}

// Mermaid draws into a scratch element by id, and the id becomes the
// SVG's own and scopes the <style> it injects. One counter for the
// page, so no two renders anywhere on it share one — not across
// blocks, not across React roots, not across an edit in flight.
let mermaidId = 0;

/**
 * A mermaid theme matching igni's.
 *
 * ``default`` is the colourful light palette and ``dark`` its dark
 * counterpart. Both run in colour — ``neutral``, which reads like
 * the safe choice, is what made every diagram grey.
 */
function mermaidTheme(): MermaidTheme {
  if (typeof document === "undefined") return "default";
  const explicit = document.documentElement.dataset.theme;
  if (explicit === "dark") return "dark";
  if (explicit === "light") return "default";
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "default";
  }
  return "default";
}

/**
 * Mermaid, configured for the theme in force right now.
 *
 * Mermaid is about 700KB, so it arrives only if a document has one;
 * the bundler caches the module, so asking again costs nothing.
 * Configured on every call rather than once, because the theme is
 * read when it is configured — a diagram drawn after a switch to
 * dark has to be drawn in dark.
 */
export async function loadMermaid(): Promise<MermaidLib> {
  // Inline on purpose: `mermaid` is an optional peer dependency.
  const lib = (await import("mermaid")).default as unknown as MermaidLib;
  lib.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: mermaidTheme(),
    themeVariables: {
      fontFamily: "var(--font-ui)",
      background: "transparent",
    },
  });
  return lib;
}

export function MermaidBlock({ source }: { source: string }) {
  const frame = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    void loadMermaid()
      .then((lib) => lib.render(`mermaid-${++mermaidId}`, source))
      .then(({ svg }) => {
        if (cancelled || !frame.current) return;
        frame.current.innerHTML = svg;
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [source]);

  if (error) {
    // The source, not a blank box. A diagram that does not parse is
    // usually a diagram somebody is halfway through writing, and
    // hiding what they wrote is the least helpful response to that.
    return (
      <pre className="mermaid-error" title={`Mermaid render failed: ${error}`}>
        {source}
      </pre>
    );
  }
  return (
    <div className="mermaid-diagram">
      <CopySource source={source} />
      <div ref={frame} />
    </div>
  );
}

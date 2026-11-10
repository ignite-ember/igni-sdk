/**
 * The language on a fenced block, or null.
 *
 * ReactMarkdown hands a ``<pre>`` a single ``<code>`` child carrying
 * ``className="language-mermaid"``; this reads that without
 * assuming any particular child shape survives a plugin.
 */
import type { ReactNode } from "react";
import { isValidElement } from "react";

export interface Fence {
  lang: string;
  source: string;
}

export function fenceInfo(children: ReactNode): Fence | null {
  const only = Array.isArray(children) ? children[0] : children;
  if (!isValidElement(only)) return null;
  const props = only.props as { className?: string; children?: ReactNode };
  const match = /\blanguage-([\w-]+)\b/.exec(props.className ?? "");
  if (!match) return null;
  const source = typeof props.children === "string" ? props.children : "";
  return { lang: match[1].toLowerCase(), source: source.replace(/\n$/, "") };
}

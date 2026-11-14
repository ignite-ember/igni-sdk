/**
 * Text: a rule, a heading, a paragraph and inline code.
 *
 * Part of the primitives; see `primitives.tsx`. **Under the
 * compatibility floor.**
 */

import type { HTMLAttributes } from "react";

import { cx } from "./cx.js";

/**
 * A horizontal rule.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the rule.
 */
export function Divider({ className, ...rest }: HTMLAttributes<HTMLHRElement>) {
  return <hr {...rest} className={cx("ui-divider", className)} />;
}

/** What a {@link Heading} takes. */
export interface HeadingProps extends HTMLAttributes<HTMLHeadingElement> {
  /** The outline level. Also picks the size, so they cannot disagree. */
  level?: 1 | 2 | 3 | 4;
}

const HEADING_SIZE = {
  1: "var(--text-2xl)",
  2: "var(--text-xl)",
  3: "var(--text-lg)",
  4: "var(--text-sm)",
} as const;

/**
 * A heading, at the level you say.
 *
 * The size follows the level, so the outline and the type cannot
 * disagree — which is the whole reason there is no `Title`.
 *
 * @param level — the outline level; it also picks the size, so the two
 *   cannot disagree.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param style — the element's inline style, merged over the size the
 *   level picks.
 * @param rest — the remaining props, spread onto the heading.
 */
export function Heading({
  level = 2,
  className,
  style,
  ...rest
}: HeadingProps) {
  const Tag = `h${level}` as "h1" | "h2" | "h3" | "h4";
  return (
    <Tag
      {...rest}
      className={cx("ui-heading", className)}
      style={{ fontSize: HEADING_SIZE[level], ...style }}
    />
  );
}

/** How loud. Not {@link Tone}: this is emphasis, not status. */
export type TextTone = "default" | "muted" | "faint";

/** What a {@link Text} takes. */
export interface TextProps extends HTMLAttributes<HTMLParagraphElement> {
  /** How loud it is. */
  tone?: TextTone;
}

/**
 * A paragraph.
 *
 * {@link TextTone} says how loud it is — emphasis, not status. A
 * status is a {@link Badge}.
 *
 * @param tone — how loud it is: emphasis rather than status.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the paragraph.
 */
export function Text({ tone = "default", className, ...rest }: TextProps) {
  return <p {...rest} data-tone={tone} className={cx("ui-text", className)} />;
}

/**
 * Inline code: a name, a path, a flag.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the element.
 */
export function Code({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return <code {...rest} className={cx("ui-code", className)} />;
}

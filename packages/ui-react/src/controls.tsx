/**
 * The controls a reader acts on or scans past: a button, a text field,
 * a chip and a badge, and the tone the last two share.
 *
 * Part of the primitives; see `primitives.tsx`. **Under the
 * compatibility floor.**
 */

import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
} from "react";

import { cx } from "./cx.js";

/**
 * How a button reads.
 *
 * `default` is a plain button, `primary` is the one action on the
 * panel, `danger` is the one that destroys something, `warn` says the
 * action is not what it sounds like, and `quiet` is a button that
 * should not be the first thing the eye lands on.
 */
export type ButtonVariant = "default" | "primary" | "danger" | "warn" | "quiet";

/** `md` unless the row is dense, in which case `sm` or `xs`. */
export type ButtonSize = "md" | "sm" | "xs";

/** What a {@link Button} takes. */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** How it reads. */
  variant?: ButtonVariant;
  /** Its size. */
  size?: ButtonSize;
}

/**
 * A button.
 *
 * The variant is a prop rather than a class name you spell:
 * `btn-primery` is a typo that renders as a plain button and looks
 * like nothing at all, which is exactly why the name is one the
 * compiler checks.
 *
 * @param variant — how it reads: plain, the one action on the panel,
 *   the one that destroys something, a warning, or one that should not
 *   be the first thing the eye lands on.
 * @param size — its size: `md` unless the row is dense, in which case
 *   `sm` or `xs`.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the button.
 */
export function Button({
  variant = "default",
  size = "md",
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      className={cx(
        "btn",
        variant !== "default" && `btn-${variant}`,
        size !== "md" && `btn-${size}`,
        className,
      )}
    />
  );
}

/** What an {@link Input} takes. */
export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

/**
 * A single-line text field.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the input.
 */
export function Input({ className, ...rest }: InputProps) {
  return <input {...rest} className={cx("panel-input", className)} />;
}

/**
 * How loud a status is.
 *
 * `neutral` for a state nothing is wrong with, and the three that
 * mean something.
 */
export type Tone = "neutral" | "success" | "warning" | "danger";

/**
 * A tag the reader can scan past.
 *
 * Bordered, pill-shaped, muted, `--text-sm`. Use it for a filter, a
 * label, a piece of metadata — something that describes the row it
 * sits on.
 *
 * `Chip` and `Badge` take the same props and are not
 * interchangeable. If the thing you are showing is a *state* that
 * changes — ready, failed, three unread — it is a {@link Badge},
 * which is filled by tone and bold so it is noticed. If it is a fact
 * about the thing, it is a `Chip`.
 */
export interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  /** How loud it is. */
  tone?: Tone;
}

/**
 * A tag the reader can scan past. See {@link ChipProps} for when to
 * reach for a chip and when for a badge.
 *
 * @param tone — how loud it is: `neutral` for a state nothing is wrong
 *   with, and the three that mean something.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the span.
 */
export function Chip({ tone = "neutral", className, ...rest }: ChipProps) {
  return <span {...rest} data-tone={tone} className={cx("chip", className)} />;
}

/**
 * A state the reader is meant to notice.
 *
 * Filled by tone, bold, `--text-xs`, no border. See {@link ChipProps}
 * for which of the two to reach for.
 *
 * The tone is colour, and colour alone is not a message: put the
 * state in the text too. "Failed" in a danger badge survives being
 * read aloud and being looked at by somebody who cannot tell it from
 * the success one; an empty red badge does not.
 */
export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  /** How loud it is. */
  tone?: Tone;
}

/**
 * A state the reader is meant to notice. See {@link BadgeProps} for
 * what the tone does and does not say.
 *
 * @param tone — how loud it is: `neutral` for a state nothing is wrong
 *   with, and the three that mean something.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the span.
 */
export function Badge({ tone = "neutral", className, ...rest }: BadgeProps) {
  return (
    <span {...rest} data-tone={tone} className={cx("ui-badge", className)} />
  );
}

/**
 * Work in progress: a spinner for work of unknown length, and a bar
 * for work that can say how far along it is.
 *
 * Part of the primitives; see `primitives.tsx`. **Under the
 * compatibility floor.**
 */

import type { HTMLAttributes } from "react";

import { cx } from "./cx.js";

/**
 * Work whose duration is unknown. `Skeleton` is for known shapes.
 *
 * `label` is required for the same reason `Progress.label` is: a
 * `role="status"` with nothing in it gives a screen reader silence
 * while a sighted user watches something spin.
 */
export interface SpinnerProps extends HTMLAttributes<HTMLSpanElement> {
  /** Required: a spinner with no name is a live region with nothing in it. */
  label: string;
}

/**
 * Work whose duration is unknown.
 *
 * See {@link SpinnerProps} for why `label` is required.
 *
 * @param label — required: a spinner with no name is a live region with
 *   nothing in it.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the span.
 */
export function Spinner({ label, className, ...rest }: SpinnerProps) {
  return (
    <span
      {...rest}
      role="status"
      aria-live="polite"
      className={cx("ui-spinner", className)}
    >
      <span className="ui-visually-hidden">{label}</span>
    </span>
  );
}

/** What a {@link Progress} takes. */
export interface ProgressProps extends HTMLAttributes<HTMLDivElement> {
  /**
   * How far along, against `max`. Omit for indeterminate, which
   * slides rather than sits.
   *
   * A value against a max, as `<progress>` and the ARIA attributes
   * take it, so `value={50}` means half way.
   */
  value?: number;
  /** Defaults to 100. */
  max?: number;
  /** Its name, for a screen reader. */
  label: string;
}

/** Where a determinate bar stands: its clamped value and how full it is. */
interface Reading {
  /** `value`, clamped to `0..max`. */
  now: number;
  /** How full the bar is, as a percentage. */
  pct: number;
}

/**
 * `value` measured against `max`, or `null` when there is nothing to
 * measure and the bar is indeterminate.
 */
function measure(value: number | undefined, max: number): Reading | null {
  // NaN is not a measurement: it reads as unknown, like no value.
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  const now = Math.max(0, Math.min(max, value));
  // A `max` of zero or less has nothing to measure against; an empty
  // bar is honest where `0 / 0` would write "NaN%".
  const pct = max > 0 ? (now / max) * 100 : 0;
  return { now, pct };
}

/**
 * A bar that fills.
 *
 * See {@link ProgressProps}. Without a `value` it slides, because a
 * bar that sits still while unknown work is happening is a bar that
 * looks broken.
 *
 * @param value — how far along, against `max`; omit it for
 *   indeterminate, which slides rather than sits.
 * @param max — the value that counts as complete, against which `value`
 *   is measured; it defaults to 100.
 * @param label — its name, for a screen reader.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the element.
 */
export function Progress({
  value,
  max = 100,
  label,
  className,
  ...rest
}: ProgressProps) {
  const reading = measure(value, max);
  return (
    <div
      {...rest}
      className={cx("ui-progress", className)}
      role="progressbar"
      aria-label={label}
      aria-valuenow={reading?.now}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuetext={reading ? `${Math.round(reading.pct)}%` : undefined}
      data-indeterminate={reading === null}
    >
      <div
        className="ui-progress-fill"
        style={reading ? { width: `${reading.pct}%` } : undefined}
      />
    </div>
  );
}

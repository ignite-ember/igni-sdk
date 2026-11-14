/**
 * The form controls: a drop-down, a multi-line field, a checkbox, a
 * radio, a switch, and the field that labels any of them.
 *
 * Part of the primitives; see `primitives.tsx`. **Under the
 * compatibility floor.**
 */

import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactElement,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { cloneElement, isValidElement, useId } from "react";

import { cx } from "./cx.js";

/** What a {@link Select} takes. */
export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {}

/**
 * A drop-down.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the select.
 */
export function Select({ className, ...rest }: SelectProps) {
  return <select {...rest} className={cx("ui-select", className)} />;
}

/** What a {@link Textarea} takes. */
export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {}

/**
 * A multi-line text field.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the textarea.
 */
export function Textarea({ className, ...rest }: TextareaProps) {
  return <textarea {...rest} className={cx("ui-textarea", className)} />;
}

/** What a {@link Checkbox} takes. */
export interface CheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  /** The text beside the box. It is the accessible name too. */
  label: ReactNode;
}

/**
 * A native checkbox, wrapped in its own label.
 *
 * Wrapped rather than associated by `id`, because an `id` an
 * extension forgets to make unique is a label that checks somebody
 * else's box — and nothing about the page looks wrong when it does.
 *
 * @param label — the text beside the box, and the accessible name too.
 * @param className — added to the label's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the input inside the
 *   label.
 */
export function Checkbox({ label, className, ...rest }: CheckboxProps) {
  return (
    <label className={cx("ui-check", className)}>
      <input {...rest} type="checkbox" />
      <span>{label}</span>
    </label>
  );
}

/** What a {@link Radio} takes. */
export interface RadioProps extends InputHTMLAttributes<HTMLInputElement> {
  /** The text beside the box. It is the accessible name too. */
  label: ReactNode;
}

/**
 * A native radio, wrapped in its own label.
 *
 * Wrapped for the same reason a {@link Checkbox} is: an `id` an
 * extension forgets to make unique is a label that picks somebody
 * else's radio.
 *
 * @param label — the text beside the box, and the accessible name too.
 * @param className — added to the label's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the input inside the
 *   label.
 */
export function Radio({ label, className, ...rest }: RadioProps) {
  return (
    <label className={cx("ui-check", className)}>
      <input {...rest} type="radio" />
      <span>{label}</span>
    </label>
  );
}

/** What a {@link Switch} takes. */
export interface SwitchProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "onChange"
> {
  /** Whether it is on. */
  checked: boolean;
  /** Called with the next value. It takes effect at once. */
  onChange: (next: boolean) => void;
  /**
   * Shown beside the switch, and used as its accessible name.
   *
   * Visible, like `Checkbox.label` and `Radio.label`, so the one prop
   * name means the same thing on all three and a sighted user reads
   * what the toggle is for.
   */
  label: ReactNode;
}

/**
 * A switch, which is a button rather than a checkbox.
 *
 * The difference is not cosmetic. A checkbox is a value you submit; a
 * switch takes effect the moment it moves. `role="switch"` is what
 * tells a screen reader which of those it is looking at.
 *
 * @param checked — whether it is on.
 * @param onChange — called with the next value; it takes effect at
 *   once.
 * @param label — shown beside the switch, and used as its accessible
 *   name.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the button.
 */
export function Switch({
  checked,
  onChange,
  label,
  className,
  ...rest
}: SwitchProps) {
  const id = useId();
  return (
    <span className="ui-check">
      <button
        // `rest` goes first so a caller cannot clobber the parts that
        // make this a switch: a caller's own onClick would otherwise
        // replace the toggle, and the control would look fine and do
        // nothing.
        {...rest}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={id}
        onClick={() => onChange(!checked)}
        className={cx("ui-switch", className)}
      />
      <span id={id}>{label}</span>
    </span>
  );
}

/**
 * A label, a control, and room for the reason it is wrong.
 *
 * The error slot is the part that gets left out, and a form that
 * rejects input without saying why is the one people abandon. When
 * `htmlFor` is set and the control is a single element, `error` (or
 * `hint`) is wired to it through `aria-describedby`, and an `error`
 * also sets `aria-invalid`, so it is announced rather than merely
 * shown. Without `htmlFor` the note is shown and nothing points at it.
 */
export interface FieldProps extends HTMLAttributes<HTMLDivElement> {
  /** The label. It is visible, not a placeholder. */
  label: ReactNode;
  /** A sentence under the control, for when nothing is wrong. */
  hint?: ReactNode;
  /** Why the control is wrong. It replaces the hint while it is set. */
  error?: ReactNode;
  /**
   * The id of the control, so the label points at it. Also what wires
   * `error` and `hint` to the control: without it, nothing does.
   */
  htmlFor?: string;
}

/**
 * A label, a control, and room for the reason it is wrong.
 *
 * See {@link FieldProps}. The error slot is the part that gets left
 * out, and a form that rejects input without saying why is the one
 * people abandon.
 *
 * @param label — the label, which is visible rather than a placeholder.
 * @param hint — a sentence under the control, for when nothing is
 *   wrong.
 * @param error — why the control is wrong; it replaces the hint while
 *   it is set.
 * @param htmlFor — the id of the control, so the label points at it.
 * @param children — the control the label is for.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the element.
 */
export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  className,
  ...rest
}: FieldProps) {
  const describedBy = htmlFor ? `${htmlFor}-note` : undefined;
  // Cloned, not merely rendered beside: the control has to point at
  // the note through `aria-describedby` for the note to be announced,
  // and a Field cannot set an attribute on an opaque child any other
  // way.
  const control =
    isValidElement(children) && describedBy && (error || hint)
      ? cloneElement(children as ReactElement<Record<string, unknown>>, {
          "aria-describedby": describedBy,
          ...(error ? { "aria-invalid": true } : {}),
        })
      : children;
  return (
    <div {...rest} className={cx("ui-field", className)}>
      <label className="ui-label" htmlFor={htmlFor}>
        {label}
      </label>
      {control}
      {error ? (
        <span className="ui-error" id={describedBy} role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="ui-hint" id={describedBy}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}

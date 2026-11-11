/**
 * Typed wrappers over the CSS primitives.
 *
 * The classes already existed — `btn`, `ui-card`, `ui-row`,
 * `ui-badge` — and an extension could write them by hand. These
 * exist because writing them by hand is not an API: there is no
 * autocomplete, no way to learn the variant names short of reading
 * `theme.css`, and nothing stops `class="btn btn-primery"` from
 * shipping as an invisible bug.
 *
 * Every one of these is a thin mapping from props to class names.
 * They hold no state and make no decisions. That is deliberate: the
 * appearance lives in CSS where the app and the extension share it,
 * and a wrapper that started making layout choices would be a second
 * place for the design to live.
 *
 * `Dialog` is the exception and says so at its own definition — a
 * dialog is behaviour, not just a box.
 *
 * **Under the compatibility floor.** A prop here is a promise; see
 * EXTENSIBILITY.md §8.
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
import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useRef,
} from "react";

/** Joins class names, skipping anything falsy. */
function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// ── Controls ────────────────────────────────────────────────────────

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

// ── Layout ──────────────────────────────────────────────────────────

/**
 * A horizontal run of things, vertically centred.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the row.
 */
export function Row({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("ui-row", className)} />;
}

/** A horizontal run of buttons. Separate from `Row` because it is
 *  what a reader looks for at the foot of a panel.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the row of actions.
 */
export function Actions({
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("ui-actions", className)} />;
}

/**
 * A vertical stack.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the list.
 */
export function List({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("ui-list", className)} />;
}

/**
 * A row of controls at the top of a panel: what the panel is, and what
 * you can do to it.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the toolbar.
 */
export function Toolbar({
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("ui-toolbar", className)} />;
}

// ── Containers ──────────────────────────────────────────────────────

/**
 * A surface: background, border, radius, padding.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the card.
 */
export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("ui-card", className)} />;
}

/** One selectable row inside a list. Renders a button, because
 *  something clickable that is not a button is a keyboard trap.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the button.
 */
export function Item({
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type="button" {...rest} className={cx("ui-item", className)} />
  );
}

/**
 * A table.
 *
 * The class only; the head, the rows and the cells are yours, because
 * a table that decides its own columns is a table you cannot use for
 * anything the app has not already seen.
 *
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the table.
 */
export function Table({
  className,
  ...rest
}: HTMLAttributes<HTMLTableElement>) {
  return <table {...rest} className={cx("ui-table", className)} />;
}

/**
 * What to show where there is nothing.
 *
 * Its own component rather than a paragraph with a class, because an
 * empty state that says only "nothing here" is the commonest way a
 * panel wastes the one moment it had the reader's attention. The
 * `action` slot is a nudge to say what to do next.
 */
export interface EmptyProps extends HTMLAttributes<HTMLDivElement> {
  /** A button, usually: the one thing to do about being empty. */
  action?: ReactNode;
}

/**
 * What to show where there is nothing.
 *
 * See {@link EmptyProps} for why the `action` slot exists.
 *
 * @param children — what to show where there is nothing.
 * @param action — a button, usually: the one thing to do about being
 *   empty.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the element.
 */
export function Empty({ children, action, className, ...rest }: EmptyProps) {
  return (
    <div {...rest} className={cx("ui-empty", className)}>
      {children}
      {action}
    </div>
  );
}

// ── Dialog ──────────────────────────────────────────────────────────

/** What a {@link Dialog} takes. */
export interface DialogProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  "title"
> {
  /** Its title. Also the accessible name of the dialog. */
  title: ReactNode;
  /** Shown under the title. A sentence, not a paragraph. */
  sub?: ReactNode;
  /** The body. */
  children?: ReactNode;
  /** The buttons. Rendered in an `Actions` row at the foot. */
  actions?: ReactNode;
  /** Escape, or a click on the backdrop. */
  onClose: () => void;
}

/**
 * The one primitive here that is behaviour rather than a box.
 *
 * A dialog has to trap focus, close on Escape, restore focus to
 * whatever opened it, and not let a click inside the panel count as a
 * click on the backdrop. Every extension that built its own would get
 * some of that wrong, and the ones they get wrong are the ones only
 * keyboard and screen-reader users notice.
 *
 * @param title — its title, also the accessible name of the dialog.
 * @param sub — shown under the title: a sentence, not a paragraph.
 * @param children — the body.
 * @param actions — the buttons, rendered in an `Actions` row at the
 *   foot.
 * @param onClose — escape, or a click on the backdrop.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the dialog panel.
 */
export function Dialog({
  title,
  sub,
  children,
  actions,
  onClose,
  className,
  ...rest
}: DialogProps) {
  const panel = useRef<HTMLDivElement | null>(null);
  const opener = useRef<Element | null>(null);
  const titleId = useId();

  useEffect(() => {
    opener.current = document.activeElement;
    // Focus the panel itself rather than the first control: reading
    // the title before the buttons is the point of having one.
    panel.current?.focus();
    return () => {
      // Only if it is still in the document: an opener that has
      // unmounted drops focus to <body> silently, which is worse than
      // leaving it where the closing action put it.
      const back = opener.current;
      if (back instanceof HTMLElement && back.isConnected) back.focus();
    };
  }, []);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      // `:not([disabled])` matters more than it looks: a modal whose
      // confirm button is disabled until a field is typed is the
      // commonest pattern there is, and without this the wrap targets
      // a disabled element, preventDefault fires, focus() is a no-op
      // and Tab appears dead. Dead Tab is worse than escaping Tab.
      // `iframe` is here because an extension *is* one.
      const focusable = panel.current?.querySelectorAll<HTMLElement>(
        [
          "button:not([disabled])",
          "a[href]",
          "input:not([disabled]):not([type=hidden])",
          "select:not([disabled])",
          "textarea:not([disabled])",
          "iframe",
          "summary",
          "[contenteditable]",
          '[tabindex]:not([tabindex="-1"])',
        ].join(", "),
      );
      if (!focusable || focusable.length === 0) {
        // Nothing to move to, so hold the focus here rather than let
        // Tab walk into the page behind a modal with no way back.
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        // Primary button only, and only on the backdrop itself. A
        // right-click raising a context menu used to dismiss the
        // modal underneath it.
        if (e.button === 0 && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        {...rest}
        ref={panel}
        className={cx("dialog", className)}
        role="dialog"
        aria-modal="true"
        // Without this a screen reader announces "dialog" and nothing
        // else. The app's own hand-rolled dialogs got this right while
        // the published one did not.
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        // Without this a drag that starts inside and ends outside
        // closes the dialog, which eats a selection.
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 className="dialog-title" id={titleId}>
          {title}
        </h2>
        {sub ? <p className="dialog-sub">{sub}</p> : null}
        {children}
        {actions ? (
          <Actions className="dialog-actions">{actions}</Actions>
        ) : null}
      </div>
    </div>
  );
}

// ── Form controls ───────────────────────────────────────────────────

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
      <input type="checkbox" {...rest} />
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
      <input type="radio" {...rest} />
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
   * Visible, like `Checkbox.label` and `Radio.label`. It was an
   * `aria-label` and nothing else, so one prop name meant opposite
   * things on two components in the same package and a sighted user
   * got a bare toggle.
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
        // make this a switch. It used to spread last, and a caller's
        // own onClick silently replaced the toggle — the control
        // looked fine and did nothing.
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
 * `error` is set it is wired to the control through
 * `aria-describedby`, so it is announced rather than merely shown.
 */
export interface FieldProps extends HTMLAttributes<HTMLDivElement> {
  /** The label. It is visible, not a placeholder. */
  label: ReactNode;
  /** A sentence under the control, for when nothing is wrong. */
  hint?: ReactNode;
  /** Why the control is wrong. It replaces the hint while it is set. */
  error?: ReactNode;
  /** The id of the control, so the label points at it. */
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
  // Cloned, not merely rendered beside. The first version put the id
  // on the note and stopped, while the docstring claimed the control
  // was wired to it — a claim its own test did not check, because the
  // test asserted the id existed and never that anything referenced
  // it. Nothing was announced. A Field cannot set an attribute on an
  // opaque child without doing this.
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

// ── Feedback ────────────────────────────────────────────────────────

/**
 * Work whose duration is unknown. `Skeleton` is for known shapes.
 *
 * `label` is required for the same reason `Progress.label` is. This
 * was `role="status"` on an empty span: a live region with nothing
 * to say, so a screen reader got silence while a sighted user
 * watched something spin.
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
   * This was 0–1 while the ARIA attributes beside it were 0–100, so
   * `value={50}` meant 5000% and was silently clamped — the clamp hid
   * the mistake instead of surfacing it. Every other progress API,
   * `<progress>` included, takes a value against a max.
   */
  value?: number;
  /** Defaults to 100. */
  max?: number;
  /** Its name, for a screen reader. */
  label: string;
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
  const determinate = typeof value === "number";
  const clamped = determinate
    ? Math.max(0, Math.min(max, value as number))
    : undefined;
  const pct = determinate ? ((clamped as number) / max) * 100 : undefined;
  return (
    <div
      {...rest}
      className={cx("ui-progress", className)}
      role="progressbar"
      aria-label={label}
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuetext={determinate ? `${Math.round(pct as number)}%` : undefined}
      data-indeterminate={!determinate}
    >
      <div
        className="ui-progress-fill"
        style={determinate ? { width: `${pct}%` } : undefined}
      />
    </div>
  );
}

// ── Tabs ────────────────────────────────────────────────────────────

/** What a {@link Tabs} takes. */
export interface TabsProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  "onChange"
> {
  /** The tabs. The `id` is what {@link TabPanel}s match on. */
  tabs: { id: string; label: ReactNode }[];
  /** Which tab is showing. */
  active: string;
  /** Called with the id of the tab the reader chose. */
  onChange: (id: string) => void;
  /** The strip's name, for a screen reader. */
  label: string;
  /**
   * The id prefix shared with this strip's {@link TabPanel}s.
   *
   * Optional, and generated when it is absent — but a `TabPanel`
   * *requires* one, and for as long as this did not accept it there
   * was no way for a caller to learn what was generated. The two were
   * published as a pair that could not be used as a pair, and nothing
   * noticed because each is unit-tested on its own and neither had a
   * consumer. Found by building a second extension against them.
   */
  base?: string;
}

/**
 * Tabs with the arrow keys wired, because a tab strip that only
 * responds to clicks is a tab strip half the people cannot use.
 *
 * @param tabs — the tabs; the `id` is what the panels match on.
 * @param active — which tab is showing.
 * @param onChange — called with the id of the tab the reader chose.
 * @param label — the strip's name, for a screen reader.
 * @param base — the id prefix shared with this strip's panels; one is
 *   generated when it is left out, and the panels need the same one.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the element.
 */
export function Tabs({
  tabs,
  active,
  onChange,
  label,
  base: givenBase,
  className,
  ...rest
}: TabsProps) {
  // Hooks run unconditionally; the generated id is simply unused
  // when a caller supplied one.
  const generated = useId();
  const base = givenBase ?? generated;
  const strip = useRef<HTMLDivElement | null>(null);

  // Focus follows selection, which the ARIA practices require and
  // this did not do. Without it the focus ring sits on a tab that is
  // now tabIndex={-1} while a different one is selected, and the next
  // Tab leaves the strip from somewhere the reader cannot see.
  useEffect(() => {
    const el = strip.current?.querySelector<HTMLElement>(
      '[aria-selected="true"]',
    );
    if (el && strip.current?.contains(document.activeElement)) el.focus();
  }, [active]);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (tabs.length === 0) return;
    const i = tabs.findIndex((t) => t.id === active);
    let next: number | null = null;
    if (event.key === "ArrowRight") next = (Math.max(i, 0) + 1) % tabs.length;
    else if (event.key === "ArrowLeft")
      next = (Math.max(i, 0) - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next].id);
  };

  return (
    <div
      {...rest}
      ref={strip}
      role="tablist"
      aria-label={label}
      aria-orientation="horizontal"
      className={cx("ui-tabs", className)}
      onKeyDown={onKeyDown}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          // Real DOM ids, so a panel can point back with
          // aria-labelledby and this one can point at it. Without
          // them a screen reader announces "tab, 1 of 2" controlling
          // nothing.
          id={`${base}-${tab.id}`}
          aria-controls={`${base}-${tab.id}-panel`}
          type="button"
          role="tab"
          aria-selected={tab.id === active}
          tabIndex={tab.id === active ? 0 : -1}
          className="ui-tab"
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

/**
 * The panel a tab controls. Needs the same `base` the strip used.
 *
 * Published because `Tabs` without it is half the ARIA pattern: the
 * strip announced that it controlled something and there was nothing
 * for it to control.
 */
export interface TabPanelProps extends HTMLAttributes<HTMLDivElement> {
  /** The id prefix shared with its {@link Tabs}, so the two agree. */
  base: string;
  /** Which tab this panel belongs to. */
  id: string;
  /** Which tab is showing. The panel renders only when they match. */
  active: string;
}

/**
 * The panel a tab controls.
 *
 * See {@link TabPanelProps}. It renders nothing at all when its tab is
 * not the active one, so the content of a panel that is not showing
 * is not in the page.
 *
 * @param base — the id prefix shared with its tabs, so the two agree.
 * @param id — which tab this panel belongs to.
 * @param active — which tab is showing; the panel renders only when
 *   they match.
 * @param children — the content of the panel, shown while its tab is
 *   the active one.
 * @param className — added to the element's classes, beside the one the
 *   theme gives it.
 * @param rest — the remaining props, spread onto the element.
 */
export function TabPanel({
  base,
  id,
  active,
  children,
  className,
  ...rest
}: TabPanelProps) {
  if (id !== active) return null;
  return (
    <div
      {...rest}
      id={`${base}-${id}-panel`}
      role="tabpanel"
      aria-labelledby={`${base}-${id}`}
      tabIndex={0}
      className={className}
    >
      {children}
    </div>
  );
}

// ── Text ────────────────────────────────────────────────────────────

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

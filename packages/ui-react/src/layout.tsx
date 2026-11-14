/**
 * The boxes a panel is laid out in: rows, stacks, a toolbar, a card,
 * a selectable item, a table and an empty state.
 *
 * Part of the primitives; see `primitives.tsx`. **Under the
 * compatibility floor.**
 */

import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

import { cx } from "./cx.js";

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

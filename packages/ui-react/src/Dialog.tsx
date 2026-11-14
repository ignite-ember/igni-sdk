/**
 * The dialog: the one primitive that is behaviour rather than a box.
 *
 * Part of the primitives; see `primitives.tsx`. **Under the
 * compatibility floor.**
 */

import type { HTMLAttributes, KeyboardEvent, ReactNode } from "react";
import { useCallback, useEffect, useId, useRef } from "react";

import { cx } from "./cx.js";
import { Actions } from "./layout.js";

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
    (event: KeyboardEvent) => {
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
        // Primary button only, and only on the backdrop itself, so a
        // right-click raising a context menu leaves the modal open.
        if (e.button === 0 && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        {...rest}
        ref={panel}
        className={cx("dialog", className)}
        role="dialog"
        aria-modal="true"
        // The title is the dialog's accessible name; without it a
        // screen reader announces "dialog" and nothing else.
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

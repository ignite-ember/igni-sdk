/**
 * A tab strip and the panels it controls.
 *
 * Part of the primitives; see `primitives.tsx`. **Under the
 * compatibility floor.**
 */

import type { HTMLAttributes, KeyboardEvent, ReactNode } from "react";
import { useEffect, useId, useRef } from "react";

import { cx } from "./cx.js";

/**
 * The index a navigation key moves the selection to, from tab `i` of
 * `count`, or `null` for a key the strip does not handle. The arrows
 * wrap at either end.
 */
function tabAfterKey(key: string, i: number, count: number): number | null {
  switch (key) {
    case "ArrowRight":
      return (i + 1) % count;
    case "ArrowLeft":
      return (i - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

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
   * *requires* one, so a caller that renders panels passes the same
   * `base` to both: a generated one is never visible to the panels.
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

  // Focus follows selection, as the ARIA practices require: otherwise
  // the focus ring sits on a tab that is now tabIndex={-1} while a
  // different one is selected, and the next Tab leaves the strip from
  // somewhere the reader cannot see.
  useEffect(() => {
    const el = strip.current?.querySelector<HTMLElement>(
      '[aria-selected="true"]',
    );
    if (el && strip.current?.contains(document.activeElement)) el.focus();
  }, [active]);

  const onKeyDown = (event: KeyboardEvent) => {
    if (tabs.length === 0) return;
    const i = Math.max(
      tabs.findIndex((t) => t.id === active),
      0,
    );
    const next = tabAfterKey(event.key, i, tabs.length);
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
 * `Tabs` without it is half the ARIA pattern: a strip that announces
 * it controls something needs something for it to control.
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
 * @param className — the panel's own class; the theme gives it
 *   none.
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

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
 * This module is the one name the primitives are imported by. Each
 * group lives in its own file, re-exported here in reading order.
 *
 * **Under the compatibility floor.** A prop here is a promise; see
 * EXTENSIBILITY.md §8.
 */

export * from "./controls.js";
export * from "./layout.js";
export * from "./Dialog.js";
export * from "./formControls.js";
export * from "./progress.js";
export * from "./Tabs.js";
export * from "./text.js";

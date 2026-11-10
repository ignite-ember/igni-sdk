# `@ignite-ember/ui-react`

The React components an igni extension is allowed to build on.
Everything exported here is under the compatibility floor: removing
one, renaming it, or changing a prop's meaning is a breaking change
under `docs/EXTENSIBILITY.md` §8.

From npm, with the stylesheet it is drawn with:

```bash
npm install @ignite-ember/ui-react @ignite-ember/ui-css
```

```tsx
import { AppShell, Scroll, Table, Toolbar } from "@ignite-ember/ui-react";
import "@ignite-ember/ui-css";
```

## Peer dependencies

You already have `react` and `react-dom`. `react-markdown` and
`remark-gfm` come with `MarkdownInline`.

`mermaid` is **optional** and loaded on demand — a page with no
diagram in it never downloads the 700KB, and an extension that never
renders one does not need the dependency at all. Install it only if
you use `MermaidBlock`.

## Changed since 0.1.0, on purpose

- `loadMermaid()` configures mermaid on every call, with the theme in
  force at that moment, so a diagram drawn after a light/dark switch is
  drawn in the new theme. Each call returns a new promise, a failed load
  is tried again on the next call rather than kept, and an
  `initialize(...)` of your own is overwritten by the next
  `MermaidBlock` render. The returned `initialize` takes igni's fixed
  config (`startOnLoad`, `securityLevel: "strict"`, `theme`,
  `themeVariables`) rather than any record.
- A diagram's copy button draws the `copy` and `check` icons instead of
  the `⧉` and `✓` glyphs, so it has no text. It carries `data-state`
  (`idle`, `copied` or `failed`). A blocked or missing clipboard is no
  longer silent: the button goes to `failed`, says "Copy failed — the
  clipboard is blocked" in its title and label, and resets after 1.3s,
  as "Copied" does.
- `MenuIconName` has two more names, `copy` and `check`.

## The stylesheet is not optional

`@ignite-ember/ui-css` must be bundled into your extension, not linked from
igni's origin. Your page runs under its own origin with
`default-src 'self'`, so a cross-origin stylesheet is refused — and
that refusal is deliberate.

Inside igni the bridge pushes live token values before your first
paint, so the same markup follows dark mode, light mode and whatever
a deployment has branded. Standalone, the fallbacks in the stylesheet
are igni's own values, checked against them by a test.

## Source, not a build

This package ships TypeScript source. An extension bundles its own
React and runs its own build, so shipping a pre-compiled artifact
would mean pinning a JSX runtime and a target you may not share —
and it would put a second copy of these components in your bundle
next to the one your bundler already tree-shook.

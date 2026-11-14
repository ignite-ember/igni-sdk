# `@ignite-ember/ui-react`

**Full documentation:** [ignite-ember.sh/docs/sdk/ui-react](https://ignite-ember.sh/docs/sdk/ui-react) — guides and the complete API reference, a page per topic.

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

## Quick start

A page that fills its frame, with a toolbar, a scrolling list and a
footer:

```tsx
import { AppShell, Scroll, Toolbar, Button, Text, Empty } from "@ignite-ember/ui-react";
import { connect } from "@ignite-ember/extension-bridge";
import "@ignite-ember/ui-css";

async function main() {
  const bridge = await connect();
  const notes = await bridge.rpc<Note[]>("ext.example.teamnotes.list");

  return (
    <AppShell
      header={<Toolbar>Notes</Toolbar>}
      footer={<Button variant="primary">New note</Button>}
    >
      <Scroll>
        {notes.length === 0 ? (
          <Empty>Nothing here yet.</Empty>
        ) : (
          notes.map((note) => (
            <Text key={note.id}>{note.title}</Text>
          ))
        )}
      </Scroll>
    </AppShell>
  );
}
```

Three things to know before you write more:

- **Every component here is a thin wrapper over a class.** `Button` with
  `variant="primary"` renders `<button class="btn btn-primary">`. The
  appearance is in the stylesheet, shared with igni's own app; the
  component adds the prop names, the types and the defaults.
- **You need the stylesheet too.** `@ignite-ember/ui-css` is not optional
  and not a suggestion — see below.
- **You bring your own React.** These are React components, not web
  components, and your extension bundles its own React.

## The floor

"Everything exported here is under the compatibility floor" is a promise
about *this* list, not about igni's app. Two rules follow from it, and
they point in opposite directions:

- **You may build against anything exported here.** A component's name,
  its props and the meaning of those props will not change without a
  major version. If you need to know what a prop means, the reference
  page says so — every prop of every component is listed with its type
  and what it is for.
- **You may not build against anything else.** A class in igni's app
  that is not exported here is ours to change: it may be renamed, or
  restyled, or removed, and nothing an extension depends on will break
  in a way we would have to warn you about.

The list is deliberately short. It is not "everything an extension might
want" — it is what the first two extensions actually import, measured
rather than estimated. `CodeIndex` needs none of it; its only app
dependency is the client type. `Artifacts` is 7,737 lines and imports
exactly seven of the app's components.

Two rules decide whether something joins the floor, and both are checked
by tests:

1. **It must render outside this repository.** A component whose CSS
   lives only in igni's `theme.css` is unstyled in the one place it is
   promised for, because an extension runs on its own origin under
   `default-src 'self'` and cannot link ours. `styled.test.ts` checks
   every class named here against `clients/ui/igni-ui.css` and fails on
   the first one that is missing. This was not hypothetical: seven
   components shipped under the floor naming thirty-two classes that no
   published stylesheet defined, and the reference extension did not
   catch it because it happens to import only from `primitives`, which
   was the half that was covered.
2. **It must not drag the app behind it.** `boundary.test.ts` fails on
   an import — static or dynamic — that leaves this directory for
   anywhere but `react` and the published dependencies. `SpecBlock`
   left the floor for this reason: it loaded
   `../components/JsonRenderView`, a path that does not exist in a
   published package, through a dynamic import that no compiler would
   flag.

## Choosing a component

There are two kinds of thing in this package, and they answer different
questions.

**The primitives** are the vocabulary: `Button`, `Input`, `Select`,
`Textarea`, `Checkbox`, `Radio`, `Switch`, `Field`, `Row`, `Actions`,
`List`, `Toolbar`, `Card`, `Item`, `Table`, `Chip`, `Badge`, `Empty`,
`Dialog`, `Tabs`, `TabPanel`, `Heading`, `Text`, `Code`, `Divider`,
`Spinner`, `Progress`. They are thin, they hold no state, and they make
no decisions. Reach for one of these first — it is the thing that will
still be here next release.

**The composites** are the parts of a page that have to be a page:
`AppShell` and `Scroll` (the frame), `DataTable`'s `SortableTh` and
`Status` (a table with a sortable header and a status cell), `ToastHost`
and `useToast` (saying something) and `Banner` (a condition that is still
true), `LiveRegion` and
`useAnnounce` (announcing it), `ErrorBoundary` (catching what falls
over), `Markdown` and `MarkdownInline` and `MermaidBlock` (reading what
igni said), with `fenceInfo` and `loadMermaid` for the pieces beneath them.

**The utilities** are the small pieces: `Split`, `MenuIcon`,
`Monogram`, `OverflowMenu`, `Skeleton`, `Tooltip`.

One thing is deliberately absent: there is no `Title` component, because
the app's titles varied across four type steps and that variation is the
design — a heading level, not drift. Use `Heading`, or the type scale
and a weight.

`Dialog` is the one primitive that is not thin. A dialog is behaviour,
not just a box: it traps focus, closes on escape, and restores focus
when it closes. That is why it is a component and not a class.

## Styling

The components do not carry styles. They carry **class names**, and the
stylesheet carries the styles — so the same CSS decides what your
extension looks like and what igni's app looks like.

That is why `@ignite-ember/ui-css` is required: without it, every
component renders unstyled, and an unstyled button is not a subtle
difference.

Two things follow from sharing the stylesheet:

- **The theme is live.** The bridge pushes the computed token values
  before your first paint, so your page follows dark mode, light mode,
  and whatever a group's policy pack has branded, without a line of your
  own. Your layout is written against tokens (`var(--space-4)`), never
  against colours.
- **Your own class names still work.** `className` is passed through on
  every component, so you can add your own classes alongside. Write them
  in your own stylesheet; do not edit the published one.

## Peer dependencies

You already have `react` and `react-dom`. `react-markdown` and
`remark-gfm` come with `Markdown` and `MarkdownInline`.

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

## The source, and a build beside it

This package ships TypeScript source, and a compiled build beside it.

An extension bundles its own React and runs its own build, so a
bundler takes the source: it tree-shakes with the rest of your
extension, and it does not pin a JSX runtime or a target you may not
share. A consumer that does not compile `node_modules` — Node itself, a
test runner that is not told to transform it — takes the build instead:
plain JavaScript, and the declarations that go with it.

The build is ES2022 modules with source maps back to the TypeScript.
React stays a peer dependency, and so does the JSX runtime the build
imports. `exports` points at the build for `node`, and the `types`
condition at its declarations for everyone, so `import { Button } from
"@ignite-ember/ui-react"` names the same thing in a bundler and in
Node, and `tsc` finds it under `moduleResolution: node16`.

# igni-ui

**Full documentation:** [ignite-ember.sh/docs/sdk/ui-css](https://ignite-ember.sh/docs/sdk/ui-css) — guides and the complete API reference, a page per topic.

The controls an extension draws with, so a surface built outside igni looks like one built inside it.

This is the CSS-only package, `@ignite-ember/ui-css`. The React
components that draw with it are `@ignite-ember/ui-react`; the bridge
that themes it is `@ignite-ember/extension-bridge`. You need this
stylesheet whichever of the other two you use — a component without it
renders unstyled, and an unstyled button is not a subtle difference.

## Using it

Bundle `igni-ui.css` into your extension. Do not link it from igni's origin — your page runs under its own origin with `default-src 'self'`, so a cross-origin stylesheet is refused, and that refusal is deliberate.

```html
<link rel="stylesheet" href="./igni-ui.css" />
<body class="igni-root">
  <button class="btn btn-primary">Index this repository</button>
</body>
```

Then connect. The bridge applies the live theme before your first paint:

```ts
import { connect } from "@ignite-ember/extension-bridge";

const igni = await connect();          // tokens are on :root by now
const status = await igni.rpc("ext.acme.scanner.status");
```

That is the whole setup. No build step is required beyond whatever bundles your own code.

## How theming works

Every value in the stylesheet is a token with a fallback.

The fallback is igni's dark palette. It is what you see if you open your page on its own, outside igni — so development does not require the app running.

Inside igni, the bridge pushes the **live computed values** at handshake and again whenever they change. Your page follows dark mode, light mode, and whatever a group's policy pack has branded, without you writing a line for any of it.

Values are pushed rather than baked in, on purpose. `theme.css` defines these across many blocks — a `:root`, a light override, and a `prefers-color-scheme` block per feature. Any second copy of that is wrong within a release.

The published token list is in `packages/extension-bridge/src/tokens.ts`, and it is **under the compatibility floor**: removing or repurposing one of those is a breaking change. Tokens not on that list — `--rail-width`, `--sidebar-w`, `--crumb-row-h` — describe igni's own chrome and are ours to change. An extension positioning itself against those would break the first time we moved something.

## The floor

Some of this file is promised, and the rest is not. Knowing which is
which is the difference between a stylesheet you can build on and one
you have to read every release.

**The promised part is the token list.** The tokens published in
`packages/extension-bridge/src/tokens.ts` are under igni's compatibility
floor: removing one, renaming it, or giving it a different meaning is
a breaking change under [`docs/EXTENSIBILITY.md`](https://github.com/ignite-ember/igni-core/blob/main/docs/EXTENSIBILITY.md) §8. `npm install
@ignite-ember/extension-bridge` and read that list — it is the
authoritative one, and the fallbacks in this file are checked against it
and against `theme.css` by a test.

**The promised part is also the class names** the published React
components render. `btn`, `btn-primary`, `ui-row`, `ui-card` and the
rest are what a component's `className` is, so a page built out of the
components and a page built out of the classes by hand look the same.

**Everything else is ours to change.** A token that is not on the list
— `--rail-width`, `--sidebar-w`, `--crumb-row-h` — describes igni's
own chrome and describes the app's layout, not a control. A class that
no published component renders is a candidate for removal. An
extension that positioned itself against either would break the first
time we moved something, and we would not have warned you, because we
did not promise it.

So: build against the published tokens and the published classes. For
anything else, the stylesheet is a starting point, not a contract.

## What is here

Buttons (`btn`, with `-primary`, `-danger`, `-sm`, `-xs`, `-quiet`), chips, panels, fields, dialogs and the overlay behind them.

These are the same class names igni itself uses, so a surface built here reads as part of the app rather than beside it.

**They are copies, not one file**, and two tests now hold them to each other.

`ui-react/styled.test.ts` reads every `className=` expression in the published package and fails on the first name this file does not define. It also checks every fallback value here, `:root` and inline, against `theme.css`. Generating this file from `theme.css` is still the better fix and is still not done; until it is, these are what stop a difference being invisible.

They were written after finding two, neither of which was drift in the sense of a value slowly diverging:

- **Some components were never covered at all.** `OverflowMenu`, `Tooltip`, `Skeleton`, `Monogram`, `MarkdownInline`, `MenuIcon` and the mermaid block named classes that only `theme.css` defined. Inside the app they looked right — the one environment they are promised for is the one nobody rendered them in. The reference extension did not catch it either, because it happens to import only from `primitives`, which was the covered half.
- **Many token fallbacks were a different value from the theme they claim to copy.** Radii at 6/10/14 against the app's 8/12/18, every semantic colour a different hue, a different UI font stack. Standalone is how an extension author develops before they ever mount the thing, so that is what they were tuning against.

`btn-warn` — a typed `variant="warn"` rendering as a plain button because the class existed in the app and not here — is the case the scanner cannot see by reading source, since no line contains the string `btn-warn`; it only exists as `btn-${variant}` at runtime. Those names are enumerated explicitly in the test for that reason.

Treat a difference as a bug and report it.

## The spacing scale

`--space-1` through `--space-16` — 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 32.

Use them for `gap`, `margin` and `padding` and your layout sits on the same rhythm as the app around it, rather than next to it.

They are not an invention. They are the steps igni already used, written out as literals. Almost every gap and margin landed on them exactly, which is why adopting them changed nothing on screen — and why the few that stayed literal (`5px`, `3px`, `7px`, `18px`) are now visible as deviations rather than hidden among the rest.

## The type scale

`--text-2xs` through `--text-4xl` — 10, 11, 12, 13, 14, 17, 20, 30, 42.

Nine steps, down from many hardcoded sizes that included every half-step from 9px to 15px. `11.5px`, `12px` and `12.5px` were one size written three ways, not three sizes.

Collapsed by role rather than by ratio, because the clusters were already there. No value moved by more than 1px, and nearly every font size now names a step.

One deliberate exception survives, labelled where it lives: a digit inside a 12px circle stays at 7px, because 10px overflows it. A constrained space is a real exception. The half-pixel sizes were not.

## Shape

`--radius-sm` 8, `--radius` 12, `--radius-lg` 18, plus `--radius-pill` and `--radius-circle` for the two shapes that are not sizes.

`9999px` and `999px` were both in use for pills — identical to a renderer, two things to a reader. Now one.

**Most padding is on the scale, and the rest is probably right.** The values that stayed literal are overwhelmingly *odd* — 1, 3, 5, 7, 9, 11, 13px — which is the signature of optical correction against a 1px border rather than drift. Forcing them onto even steps would move things by a pixel for no reason. They are visible as literals now, which is the right state for a deliberate exception.

## Primitives

`ui-row`, `ui-actions`, `ui-list`, `ui-toolbar`, `ui-card`, `ui-item`, `ui-badge`, `ui-empty`, `ui-table`.

These were decided, not extracted. There was very little duplication to extract: the classes named `-row`, `-card`, `-actions` share almost nothing — `*-row` agreed only on `display: flex`. They did not repeat, they diverged, each feature choosing its own gaps and paddings because there was no scale to choose from.

So where the existing uses agreed, the agreement became the value. Where they split, the split is resolved once with a reason rather than per feature. `ui-empty` is the clearest: its colour was split evenly between `--fg-faint` and `--fg-muted`. Both clear WCAG AA, so the tie breaks on meaning — an empty state is text you must read to know what to do next, which makes it content rather than de-emphasised chrome.

There is deliberately **no `ui-title`**. Titles varied across four type steps, and that variation is the design — a heading level, not drift. Use the type scale and a weight.

**Remaining:** igni's own feature classes still carry their own copies. The primitives exist and are what an extension builds against; migrating the app onto them moves pixels, and is worth doing behind the visual suite rather than blind.

## Writing your own CSS

The stylesheet is the vocabulary, not your layout. It has three layout
shapes — `ui-shell` (a column that fills the frame), `ui-split` (two
panes with a handle) and `ui-scroll` (a scroll container that scrolls
inside a flex column) — and nothing for the page beyond them; the rest
is shaped by your own content, and a shape is cheap to write and
expensive to promise.

Write your own on top, in your own file, against the tokens:

```css
.notes {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-6);
  background: var(--bg-surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
}
```

Three rules that follow from the way this file is built:

- **Write against tokens, never against colours.** `var(--fg-muted)`,
  not `#b8b5ad`. A literal colour is a value that does not follow dark
  mode, light mode, or a group's branding — and it is a value the
  bridge cannot push over.
- **Do not edit the published stylesheet.** It is a published artifact;
  your edit is lost the next time you install. Layer yours after it.
- **Do not redefine a token to mean something else.** Overriding
  `--space-4` to `3px` changes every gap in the app's vocabulary, in
  your page, at once. If you need a different value, use your own
  variable and point the class at it.

The reference pages on the site list every token this file defines and
every class it names, with where each is used — so before you write a
rule, it is worth checking that the class you were about to invent
already exists.

## Installing

This stylesheet is `@ignite-ember/ui-css` on npm; the bridge and the React
components are `@ignite-ember/extension-bridge` and `@ignite-ember/ui-react`:

```bash
npm install @ignite-ember/ui-css @ignite-ember/extension-bridge @ignite-ember/ui-react
```

```ts
import "@ignite-ember/ui-css";
```

Each release's tarballs are also attached to igni's GitHub release
(`sdk-v<version>`), for a build that cannot reach npmjs.

## What an extension still cannot do

Worth knowing before you design around it:

- **Receive a push of anything it did not subscribe to.** The host sends `hello`, `theme`, `params`, the answers to your calls (`result`, `host-reply`), the tokens for your own service, and the signals you subscribed to with `bridge.on`. A page watches rather than polls, but a signal whose object your manifest's `permissions.host` does not grant never arrives.
- **Write the address bar or keep storage.** The frame's sandbox has no `allow-top-navigation`, and `localStorage` is wiped whenever the backend restarts, because each extension is served from an ephemeral port. `bridge.setLocation` is how a page stays addressable.
- **Reach outside its grants.** The frame's CSP admits your service's origin and the hosts in `permissions.egress`, nothing else, and `ext.<your-id>.<method>` calls are authorised against your manifest's `permissions.rpc`.

These are named here rather than left to be discovered three days into a build.

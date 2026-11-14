# `@ignite-ember/extension-bridge`

**Full documentation:** [ignite-ember.sh/docs/sdk/extension-bridge](https://ignite-ember.sh/docs/sdk/extension-bridge) — guides and the complete API reference, a page per topic.

The guest half of the bridge between an igni extension's page and igni:
`connect()`, RPC to the extension's tools, navigation, and the theme. The
host imports the same `protocol`, so there is one description of the wire.

```ts
import { connect } from "@ignite-ember/extension-bridge";

const bridge = await connect();          // igni has said hello; the theme is applied
bridge.onParams((params) => render(params));
const found = await bridge.rpc("ext.example.teamnotes.search", { query: "" });
```

Writing a page for the first time? [Your first extension](https://github.com/ignite-ember/igni-sdk/blob/main/docs/YOUR_FIRST_EXTENSION.md)
builds one end to end. A page needs no build step at all to start: it can
post the wire messages itself (`igni ext init` writes one that does);
this package is that, with types.

`connect()` resolves once igni has told the page which extension it is,
its launch params and the theme. Subpaths: `@ignite-ember/extension-bridge/protocol`
(the wire format) and `@ignite-ember/extension-bridge/tokens` (the design tokens).

## Quick start

A page is an ordinary web page that igni frames. It gets a bridge, and
the bridge is the only thing it needs from igni.

```bash
npm install @ignite-ember/extension-bridge @ignite-ember/ui-css
```

```ts
import { connect } from "@ignite-ember/extension-bridge";
import "@ignite-ember/ui-css";

async function main() {
  const bridge = await connect();

  // The theme is already applied: igni pushed its live values.
  document.body.classList.add("igni-root");

  // The launch parameters: what the link carried.
  bridge.onParams((params) => {
    document.title = String(params.title ?? "Extension");
  });

  // The extension's own backend, as the person signed in to igni.
  const notes = await bridge.rpc("ext.example.teamnotes.search", { query: "" });

  // Draw it however your page draws: plain DOM here, React with @ignite-ember/ui-react.
  const list = document.createElement("ul");
  for (const note of notes as { title: string }[]) {
    const item = document.createElement("li");
    item.textContent = note.title;
    list.append(item);
  }
  document.body.append(list);
}

main().catch((error) => {
  console.error(error);
});
```

Three things to know before you write more:

- **Every call is a round trip.** `bridge.rpc()` is a request to the host
  and back. It is fast, but it is not free, and it can time out.
- **Nothing here carries authority.** The host checks every grant. The
  bridge is a message pipe with types on it, not a key.
- **The page runs on its own origin.** It may not read igni's stylesheet,
  its storage or its scripts. What it may use is pushed over the bridge.

## The life of a page

Between the frame being created and the first paint, four things happen.
Knowing which is which saves an afternoon.

1. **The frame loads.** Your page is served from your own origin, under
   `default-src 'self'`. It may not fetch igni's stylesheet, scripts or
   fonts. The refusal is deliberate: a page that could read the app's
   origin could read the app.
2. **igni says hello.** The host posts a `hello` message carrying a
   nonce. `connect()` is waiting for exactly that message, from exactly
   that parent window; a message from anywhere else is ignored.
3. **The theme arrives.** The host computes the *live* token values and
   pushes them, and the bridge writes them onto `:root` before it
   resolves. Your stylesheet's fallbacks are what a reader sees outside
   igni; inside igni the live values apply.
4. **The params arrive.** `bridge.params` holds them, and `onParams`
   fires when they change — a link resolved after the frame was already
   mounted, say.

If the host never says hello, `connect()` rejects after thirty seconds;
`connect({ timeoutMs })` changes that. If the page is not framed at all —
opened in a browser tab — it rejects at once, saying that it is not
framed by a host.

## The host: `bridge.host`

`bridge.host` is igni as the page sees it — the **host object model**
([`docs/HOST_OBJECT_MODEL.md`](https://github.com/ignite-ember/igni-core/blob/main/docs/HOST_OBJECT_MODEL.md) in igni-core), the same model the extension's
process reaches as `ext.host`. Names are the schema's, as in Python.

```ts
const busy = await bridge.host.chat.processing.get();      // a property
await bridge.host.chat.post("Two issues in auth.py.");     // a method
await bridge.host.ui.navigate("plugins");                   // this page's window
const off = bridge.on(bridge.host.chat.run_completed, (run) => {
  if (run.changed_files.length) render(run.changed_files);
});
```

Every object needs its grant in the manifest's `permissions.host`; one
that is not granted rejects with a `HostError` whose `code` is
`not_granted`, and its signals never arrive. A page's `host.ui` is the
window it is framed in. The types (`Run`, `SessionChange`, …) are
exported from the package; `hostModel.generated.ts` is generated from
igni's host schema and `SCHEMA_VERSION` says which version.

A page observes; it cannot answer a hook. Being asked before something
happens (igni's hook events, `@ext.hook` in `igni-extension`) is the
extension's process's, because igni would otherwise wait on whatever tab
happens to be open.

## Its own service: `bridge.service`

The page talks to the service that shipped the extension directly, as
the signed-in person. igni fetches a ten-minute token for it — the same
exchange as the process's `ext.service`, audience that service and no
other — keeps it and renews it before it expires.

```ts
bridge.service.url;                                    // null when it has none (below)
const res = await bridge.service.fetch("/v1/notes");   // Authorization: Bearer …
const socket = await bridge.service.websocket("/v1/rooms/a");
socket.addEventListener("message", (e) => render(JSON.parse(e.data)));
```

`url` is `null` when the extension has no service a page may reach, and
then `fetch` and `websocket` reject with `no_service`. An extension igni
distributed always has a service: the one that shipped it. A development
install has one only when its manifest declares a `serviceUrl` setting
(`contributes.settings`) and it is set. A page is given the service only
over `https`: a plain-`http` URL counts only for this machine (`localhost`,
any name under `.localhost`, or a loopback address such as `127.0.0.1` or
`::1`) and only with `IGNI_DEV_EXTENSIONS=1`. A service on another host,
or on this machine outside development, leaves `url` `null`; a service on
another host must be `https`.

`websocket` resolves once the socket is open and has sent
`{"type": "auth", "token": …}` as its first frame (a browser socket
cannot set a header); pass `{ authFrame: (token) => … }` for a service
that reads something else. `fetch` retries once with a new token after
a `401`. Both refuse a path on any other origin with a `ServiceError`
(`other_origin`): the token goes to the service only. No
`permissions.host` grant is needed. The frame's CSP admits the
service's origin over `https`/`wss` and the hosts declared in
`permissions.egress`, nothing else. `fetch` sends the token and never
cookies (`credentials: "omit"`); a service on igni-service answers it
cross-origin with nothing to configure (`igni.install(app)`).

## Calling your extension's tools

`bridge.rpc(method, args?, timeoutMs?)` calls a method of the
extension's own service — the same namespace the agent calls.

```ts
const found = await bridge.rpc("ext.example.teamnotes.search", { query: "auth" });
const one = await bridge.rpc<Note>("ext.example.teamnotes.get", { id: "n1" });
```

- **The name** is `ext.<your-extension-id>.<your-method>`. The namespace
  is authorised against your manifest's `permissions.rpc`, and the call
  reaches your service as an MCP tool call.
- **The arguments** are a plain record of strings and JSON values, sent
  as they are.
- **The answer** is whatever the service returned, parsed as JSON. Give
  the call its type — `rpc<Note>(...)` — and the compiler will hold you
  to it; nothing checks it at runtime.
- **The deadline** is thirty seconds. `timeoutMs` overrides it. The host
  has a timeout of its own, and the shorter of the two is the one that
  fires.

A refusal is an error, not a value: the promise rejects with the host's
own sentence, or with "the host refused the call without saying why" if
it gave none. A method the service does not have, one the manifest does
not permit, and one the service answered with an error all reject the
same way.

## Following the host

A page watches; it does not poll. Three subscriptions, each returning an
unsubscribe:

```ts
const offParams = bridge.onParams((params) => render(params));
const offTheme = bridge.onTheme((theme) => setMode(theme));
const offRun = bridge.on(bridge.host.chat.run_completed, (run) => render(run));

offParams();
```

`onParams` fires only on a *change*; read `bridge.params` for the value
you were given to start with. `onTheme` fires when the person's theme
changes — the same change that moves the live token values. `on` follows
one of the host's signals.

`bridge.on(signal, fn, onRefused?)` takes a third argument, and it
matters: a signal whose object is **not granted** never arrives, and
without `onRefused` your handler simply never runs, with only a console
warning (`igni bridge: subscribing to <signal> failed: …`) to say why.
With it, the refusal arrives as a `HostError` you can show.

The first handler of a signal subscribes to it; removing the last one
unsubscribes.

## Where the page is

`bridge.setLocation(state)` says where inside your extension the person
now is. It is not a navigation — `bridge.navigate(to)` is that — and it
is how an extension can be linked to or restored: the frame cannot write
the address bar, and its `localStorage` dies with the ephemeral port it
was served from. The host folds the state into its own URL and replays
it in the next `hello`.

Keep the state small and keep it strings: it ends up in the host's URL.
Call it when the person lands somewhere worth returning to, not on every
keystroke.

`bridge.close()` tells the host this surface is finished. `bridge.navigate(to)`
asks the host app to navigate; it decides whether to.

## Putting a built page in the extension

An extension's page is the `ui/` directory of its package, and its entry is
`ui/index.html`. A page built with a bundler goes there as files: build to
`ui/` (or copy the output into it), keep the script and stylesheet as files
(the page's CSP is `script-src 'self'`, so nothing may be inline), and make
the asset URLs relative. With Vite that is `base: "./"` in `vite.config`.
`igni ext init` writes a no-build page in `ui/`; replace it with the build.

A development install (`IGNI_DEV_EXTENSIONS=1 igni ext install <dir>`) is a
copy of the directory in igni's extension store, so a rebuilt page reaches
igni only by installing again: `igni ext install --replace <dir>`, which
re-asks for the extension's permissions. A second install without
`--replace` is refused ("already installed").

With TypeScript 6 or later, `import "@ignite-ember/ui-css"` type-checks
because the stylesheet package ships a declaration for it (0.2.0 and later).

## The floor

Everything this package exports is under igni's **compatibility floor**:
removing a name, renaming it, or changing the meaning of one of its
members is a breaking change under [`docs/EXTENSIBILITY.md`](https://github.com/ignite-ember/igni-core/blob/main/docs/EXTENSIBILITY.md) §8.

Two versions of that floor are worth knowing about:

- **`BRIDGE_VERSION`** (on the `protocol` subpath) is the version of the
  wire this package speaks. Every message carries it, and a message
  whose version is not the one this package speaks is not read at all —
  it is bumped only for a change the other side cannot ignore.
- **`SCHEMA_VERSION`** (exported from the package) is the version of
  igni's host schema the generated host model was made from. It moves
  when igni's host model moves.

The host model itself is generated from igni's own schema, so a new igni
can carry objects this package has never heard of. That is not a
version skew to worry about: an object the package does not know is not
reachable from `bridge.host`, and the page simply does not use it.

## Changed since 0.1.0, on purpose

- `connect<P, S>()` and `Bridge<P, S>` take the extension's own launch
  params and settings as type arguments. Without them, `params` and
  `settings` are readonly records (`LaunchParams`, `ExtensionSettings`),
  so writing into one no longer compiles; `rpc`'s args (`RpcArgs`) and
  `setLocation`'s state (`LocationState`) are readonly too. The four
  types are new on the `protocol` subpath, and the wire messages use them.
- `bridge.on(signal, fn, onRefused?)`: a refused or unanswered
  subscription goes to `onRefused` (a `HostError`), or to the console
  (`igni bridge: subscribing to <signal> failed: …`) when there is none.
  In 0.1.0 it was dropped without a word. A refused unsubscribe is said
  on the console only (`igni bridge: unsubscribing from <signal> failed: …`).

## Installing

From npm, with the stylesheet a page is drawn with:

```bash
npm install @ignite-ember/extension-bridge @ignite-ember/ui-css
```

Each release's tarballs are also attached to igni-sdk's GitHub release
(`sdk-v<version>`), for a build that cannot reach npmjs. Versions are in
igni-sdk's `docs/PUBLISHING_THE_SDKS.md`.

## The source, and a build beside it

This package ships its TypeScript source, and a compiled build beside it.

A bundler that compiles TypeScript (Vite, esbuild, Rollup with a TS
plugin) takes the source and compiles it as it compiles the rest of
your extension. A consumer that does not compile `node_modules` — Node
itself, a test runner that is not told to transform it, a tool that
reads the types — takes the build: plain JavaScript, and the
declarations that go with it.

The build is ES2022 modules, with source maps back to the TypeScript.
`exports` points at it for `node`, and the `types` condition points at
its declarations for everyone, so `import { connect } from
"@ignite-ember/extension-bridge"` names the same things in a bundler
and in Node, and `tsc` finds them under `moduleResolution: node16`.

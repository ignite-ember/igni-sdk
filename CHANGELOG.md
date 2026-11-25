# Changelog

igni's SDKs are released in lockstep under one version
(`docs/PUBLISHING_THE_SDKS.md`). This file records the notable changes per
release; the automated release also writes a one-paragraph GitHub Release and a
run summary. Releases before 0.2.2 predate this file.

## 0.2.3

0.2.3 adds one push and one extension signal: Laya's read of whether the
person is pleased or displeased with igni. Nothing is removed or changed.
`contracts/` is igni-core's again, after its sentiment work.

### `igni-client` (PyPI) and `@ignite-ember/igni-client` (npm)

- The typed `user_sentiment` push (`UserSentimentPush`, payload
  `UserSentimentPayload`): `sentiment` (`positive` or `negative`; neutral is
  never sent), `confidence`, `session_id`, and `message_run_id` /
  `reply_run_id` — the run the judged message started and the run whose reply
  it reacts to. `aspects` (`SentimentAspects`) carries every question Laya
  answered about the message — feeling, gesture, intensity, the positive and
  negative reason, repeat, redo requested, task done — each as the chosen label
  and every label's probability (`SentimentAspect`, `LabelProbability`).

### `igni-extension` (PyPI) and `@ignite-ember/extension-bridge` (npm)

- The host model gains the `chat.sentiment` signal (`host.chat.sentiment`,
  typed `Sentiment`), with the same fields and aspects as the push.

### Unchanged

- `igni-service`, `@ignite-ember/ui-react` and `@ignite-ember/ui-css`: their
  versions move for lockstep only.

## 0.2.2

Besides fixes, 0.2.2 adds a package, new calls and new host-model members, and
changes one behaviour of `igni-client`'s `ask()` — marked **Behaviour change**
below. `contracts/` is igni-core's again, after its approval-cancel change and
its session-state work.

### `igni-client` (PyPI)

- **Behaviour change:** when igni answers a prompt with an error and starts no
  run, `ask()` raises `RunFailed` with igni's own words, where it used to return
  an empty `Reply`. A prompt blocked by a hook or the group policy now raises
  too: igni's error carries no code, so it looks the same as a refused one.
- `igni.sessions.states()` lists the chats that are running, waiting on the
  person, or unread. Each `SessionState` carries `state` (`running`, `waiting`
  or `idle`), `waiting_approvals`, `unread` and `last_message_at`; session list
  rows carry `unread` and `last_message_at` too. `igni.sessions.mark_seen()`
  marks a chat seen. It is a followed call that yields the typed
  `session_states_changed` push (`SessionStatesChangedPush`).
- `session.files.read_bytes()` reads a file's raw bytes (base64, up to 10 MiB)
  to preview an image or a PDF. `session.history.search_all()` finds text across
  every session in the project.
- Fleet discovery and signing in, the client's part of the desktop's Local /
  Cloud switch. `discover()` asks igni server for a person's cloud igni, and
  falls back to `igni_gateway` when the server is older. `Fleet.from_server()`
  connects to it, and refuses a plain-http gateway unless `allow_http` is set.
  The release also adds `set_events_owner()`, `sign_in()`, `Me.vm` (the VM's
  state, read without waking it) and `GroupIsLocalOnly`, raised on the
  gateway's 1008 `group_local_only` and on igni server's 403s. On 1008
  `token_expired` the client reconnects with a fresh token.
- A refused Fleet VM credential says how to recover. `ask()` raises
  `SignInRequired` (a person) or `ReissueRequired` (an app) when a run fails
  while igni's `vm_credential` push stands, naming the gateway and the recovery.
  Both are `CredentialRefused`, an `AuthError` and a `RunFailed` at once, so
  code catching `RunFailed` still catches them. The last push is kept as
  `igni.vm_credential`. The client never signs in by itself.
- Fixed: `async with session.cancel()` straight after `sessions.open()` on a
  session paused on an approval took the attach's leftover `stream_end` as its
  own, and ended before the cancel's frames arrived. A cancel now ends only on
  the `stream_end` of the stream its `info` arrived on.
- `igni_client.testing`: `FakeServer`; `FakeIgni.set_mode` and the matching
  `FakeGateway` additions. The fake keeps and replays the `vm_credential` push,
  and drops a paused turn's approvals on cancel, as igni does.
- The docs say who may end a run paused on an approval: igni's window or an
  approver. A program without an approver token gets `AccessRefused` from
  `cancel()`.

### `@ignite-ember/igni-client` (npm) — new

- The TypeScript twin of the PyPI `igni-client` joins the published SDK: a
  Node 20+ backend driving an igni locally or a producer's in Fleet through the
  gateway. Its calls are generated from the same RPC contract as the Python
  client's, and a parity test holds the two to the same methods. It was `0.1.0`
  in this repository and never published; it is built, version-checked and
  published with the other npm packages from this version on, and carries the
  session-state calls above.
- It is a new package on npmjs. Its first publish needs a token or a publish by
  hand; only after that can npmjs trust the release workflow for it (see
  `docs/PUBLISHING_THE_SDKS.md`).
- igni-client's README and reference show TypeScript beside Python everywhere:
  a TypeScript twin of every example, each type-checked and most run against
  the TypeScript `FakeIgni`, plus each method's TypeScript signature and each
  error's TypeScript declaration. Where TypeScript's single parent class drops
  one of Python's, the reference says so: `CredentialRefused` is not an
  `AuthError`, and `AccessRefused` is not a `NotAllowed`.

### `igni-extension` (PyPI) and `@ignite-ember/extension-bridge` (npm)

- The host model gains `host.sessions.states`, `host.sessions.mark_seen()` and
  the `sessions.states_changed` signal; `host.workspace.read_bytes()` (typed
  `FileBytes`); and `host.chat.search_all()`.
- The host model's docs say an extension needs `chat.approvals` to cancel or
  post into a session that is waiting on an approval.

### `@ignite-ember/ui-react`

- Fixed: a `Monogram`'s white letters read on every hue. The background is
  `hsl(hue 42% 32%)`, not 42% lightness; the worst hue is now 4.9:1 against
  white, over the 4.5:1 WCAG AA asks of text that small. At 42%, yellows and
  greens were 3.0–3.6:1.

### Unchanged

- `igni-service` and `@ignite-ember/ui-css`: their versions move for lockstep
  only.

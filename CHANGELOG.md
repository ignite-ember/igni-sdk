# Changelog

igni's SDKs are released in lockstep under one version
(`docs/PUBLISHING_THE_SDKS.md`). This file records the notable changes per
release; the automated release also writes a one-paragraph GitHub Release and a
run summary. Releases before 0.2.2 predate this file.

## 0.2.2

- The TypeScript **`@ignite-ember/igni-client`** joins the published SDK. It is
  the Node/TypeScript twin of the PyPI `igni-client` — a backend driving an igni
  and reaching Fleet — and is now built, version-checked and published with the
  other npm packages under the one SDK version. (It is a new npm package and
  needs its own trusted-publisher configuration on npmjs before its first
  publish; see `docs/PUBLISHING_THE_SDKS.md`.)
- The PyPI `igni-client` is unchanged in behaviour at this version; its version
  is bumped only to stay in lockstep.
- No changes to `igni-service`, `igni-extension`, `@ignite-ember/extension-bridge`,
  `@ignite-ember/ui-react` or `@ignite-ember/ui-css`; their versions move for
  lockstep.

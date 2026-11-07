# igni SDKs

What you build on igni with: a service, an extension, or a program that
drives an igni. Six packages, one version, released together
([docs/PUBLISHING_THE_SDKS.md](docs/PUBLISHING_THE_SDKS.md)).

| Package | Registry | Source | For |
|---|---|---|---|
| `igni-service` | PyPI | [`packages/igni-service`](packages/igni-service) | a service: its key, registration, people's tokens, notifications, erasure and export, its extension bundle |
| `igni-extension` | PyPI | [`packages/igni-extension`](packages/igni-extension) | an extension's process: tools over MCP, its service as the person, the host |
| `igni-client` | PyPI | [`packages/igni-client`](packages/igni-client) | a program driving an igni from outside: a producer's in Fleet through the gateway, or a local one |
| `@ignite-ember/extension-bridge` | npmjs | [`packages/extension-bridge`](packages/extension-bridge) | an extension's page: `connect()`, RPC, navigation, theme |
| `@ignite-ember/ui-react` | npmjs | [`packages/ui-react`](packages/ui-react) | the React components under the compatibility floor |
| `@ignite-ember/ui-css` | npmjs | [`clients/ui`](clients/ui) | the stylesheet `@ignite-ember/ui-react` is drawn with |

Start with [Your first extension](docs/YOUR_FIRST_EXTENSION.md); the
examples it builds are in [`examples/`](examples).

## How this repository relates to igni

igni's backend is [igni-core](https://github.com/ignite-ember/igni-core) and
its desktop app and web UI are [igni-app](https://github.com/ignite-ember/igni-app).
The SDKs build against what igni-core publishes, kept here as copies in
[`contracts/`](contracts): the host object model both SDKs' `host` objects
are generated from (`tools/host_codegen.py`), and the manifest and theme
schemas. `make contracts` refreshes them from a checkout of igni-core beside
this one (`../igni-core`, or `IGNI_CORE_DIR`), and a test fails when a copy
differs from igni-core's.

## Working here

```bash
make install         # the root environment and the npm workspaces
make check           # everything CI runs
make help            # the rest
```

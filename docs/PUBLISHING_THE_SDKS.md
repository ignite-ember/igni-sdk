# Publishing the SDKs

igni's SDKs are what services, extensions and the programs that drive an igni
build on. Six packages,
released together to the public registries — PyPI and npmjs — from this
repository, which is public under Apache-2.0:

| Package | Registry | Source | For |
|---|---|---|---|
| `igni-service` | PyPI | `packages/igni-service` | a service: its key, registration, people's tokens, the directory, notifications, erasure and export, its extension bundle |
| `igni-extension` | PyPI | `packages/igni-extension` | an extension's process: tools over MCP, its service as the person, the host |
| `igni-client` | PyPI | `packages/igni-client` | a program driving an igni from outside: a producer's in Fleet through the gateway, or a local one — sessions, runs, approvals, commands in the VM |
| `@ignite-ember/extension-bridge` | npmjs | `packages/extension-bridge` | an extension's page: `connect()`, RPC, navigation, theme |
| `@ignite-ember/ui-react` | npmjs | `packages/ui-react` | the React components under the compatibility floor |
| `@ignite-ember/ui-css` | npmjs | `clients/ui` | the stylesheet `@ignite-ember/ui-react` is drawn with |

`@ignite-ember/ui-css` is the fifth because `@ignite-ember/ui-react`'s README
tells every extension to install it beside it, and a component package whose
stylesheet cannot be installed is not installable either.

The npm scope is `@ignite-ember`, the organisation's name on npmjs; `@igni`
there is not ours. The Python names are the import names' (`igni_service`,
`igni_extension`, `igni_client`).

Every release is also a GitHub Release of this repository, `sdk-v<version>`,
carrying the same wheels, sdists and npm tarballs and their `SHA256SUMS`: what
the offline bundle and an air-gapped build take instead of a registry.

## Versions

**One version for all six (lockstep), semver.** §8 of
[EXTENSIBILITY.md](EXTENSIBILITY.md) versions the floor independently of the
product, as semver, declared as a range — and the six packages *are* the
floor's code: the bridge's protocol is the host's, `@ignite-ember/ui-react` is drawn
with `@ignite-ember/ui-css`, `igni-service` builds the bundles `igni-extension` runs
in. Independent versions would ask every extension author to find a
combination that works together; one version is that combination, and "built
on SDK 0.3" means one thing. The cost is that a release bumps a package that
did not change — cheap, since a version is a few kilobytes and nobody has to
read a changelog for it.

- **Patch** (`0.3.1`): fixes; nothing an extension relies on changes.
- **Minor** (`0.4.0`): additions. While the major version is 0 a minor
  release may also break — semver's rule for 0.x — and says so in its notes.
- **From 1.0**, §8's rules: breaking only in a major, after the deprecation
  window.
- **Pre-releases**: `0.4.0-rc.1` (also `-alpha.N`, `-beta.N`). npm reads it as
  written; Python normalises it to `0.4.0rc1`, which is the same version.
  npm publishes a pre-release under the dist-tag `next`, so `npm install
  @ignite-ember/ui-react` never picks one; uv and pip skip pre-releases unless asked.

The versions live in the six manifests (`pyproject.toml`, `package.json`) and
nowhere else. `make sdk-version VERSION=0.4.0` sets all six (and the Python
packages' `uv.lock`); `make sdk-version-check` lists them and fails when they
disagree, or disagree with `VERSION=` when it is given.

**The tag is `sdk-v<version>`**: `sdk-v0.4.0`, `sdk-v0.4.0-rc.1`. One tag,
because there is one version; `sdk-` because `v*` tags already release igni
itself (`release.yml`), and the two must never trigger each other.

## TypeScript ships as source, and as a build

`@ignite-ember/extension-bridge` and `@ignite-ember/ui-react` ship their
TypeScript source — and a compiled build beside it.

The source is what a bundler takes. An extension bundles its own React
and runs its own build, so a compiled copy would pin a JSX runtime and a
target the extension may not share, and it would put a second copy of
these components in the bundle next to the one the extension's own
bundler already tree-shook. It was checked against the consumer that
exists, the extension starter, with the packages installed into
`node_modules` the way a registry install puts them there and every
alias and `paths` entry removed: `tsc --noEmit`, `vite build` and
`vitest run` all pass unchanged. Vite compiles TypeScript in
`node_modules` like the page's own, and the packages' peers (`react`,
`react-markdown`, …) resolve from the consumer's `node_modules` without
the alias table the source checkout needed.

The build is what everybody else takes. A second kind of consumer did
turn up — one that does not compile `node_modules` at all: Node itself,
a test runner that is not told to transform it, a tool that reads the
types. Under `moduleResolution: node16` the packages' extensionless
imports could not be resolved, `connect` was not exported, and the
consumer's own type-check failed with `TS2305`.

So each package now has a `dist/`: ES2022 modules, with declarations and
source maps, built by `npm run build` (`tsconfig.build.json` beside the
package's source). `exports` points at it under the `node` condition, and
the `types` condition points at its declarations for everyone:

```json
"exports": {
  ".": {
    "types": "./dist/index.d.ts",
    "node": "./dist/index.js",
    "default": "./src/index.ts"
  }
}
```

A bundler takes the `default` — the source. Node takes the `node` — the
build. `tsc` takes the `types` — the declarations. The relative imports
in the packages' own source carry their `.js` extension, so the emitted
JavaScript finds its neighbours by name, and the declarations do too.

`scripts/check_npm_consumers.py` holds this to it: it packs the packages
the way npm publishes them, installs the tarballs into a scratch
consumer that resolves the way Node does, and type-checks and runs a
program against them. A consumer that cannot use the packages fails
there, before anything is published.

What it asks of a consumer:

- A bundler that compiles TypeScript — Vite, esbuild, Rollup with a TS
  plugin. Next.js needs `transpilePackages: ["@ignite-ember/ui-react",
  "@ignite-ember/extension-bridge"]`; Jest a `transformIgnorePatterns` exception.
- `tsc` type-checks the packages' declarations under the consumer's own
  `compilerOptions`. The declarations are written to `strict`; a consumer
  with stricter flags than that (`exactOptionalPropertyTypes`, say) may
  see errors in them.

## Building locally

```bash
make sdk-build
```

Checks the versions agree, compiles the npm packages' `dist/`, then writes
to `dist/sdk/`:

```
dist/sdk/python/igni_service-<v>-py3-none-any.whl  igni_service-<v>.tar.gz
dist/sdk/python/igni_extension-<v>-py3-none-any.whl  igni_extension-<v>.tar.gz
dist/sdk/python/igni_client-<v>-py3-none-any.whl  igni_client-<v>.tar.gz
dist/sdk/npm/ignite-ember-extension-bridge-<v>.tgz  ignite-ember-ui-react-<v>.tgz  ignite-ember-ui-css-<v>.tgz
```

Python with `uv build --no-sources` (proving the packages build with no
checkout around them), npm with `npm pack` (each package's `files` list
leaves its tests out). Every package carries `LICENSE` and `NOTICE`; the
two with TypeScript carry their `dist/` too, which is what a consumer
outside a bundler runs. To check what the registries would see:

```bash
uvx twine check --strict dist/sdk/python/*                 # PyPI's metadata and README checks
for t in dist/sdk/npm/*.tgz; do tar -tzf "$t"; done          # what each tarball carries
for t in dist/sdk/npm/*.tgz; do npm publish "$t" --dry-run --access public; done
```

Install a built one somewhere to try it: `uv pip install
dist/sdk/python/igni_service-*.whl`, `npm install
dist/sdk/npm/ignite-ember-ui-react-*.tgz`.

## The workflow

`.github/workflows/sdk-release.yml` does the publishing; a person only
versions, rehearses and tags. No publishing credential is stored anywhere:
PyPI, TestPyPI and npmjs trust the workflow itself, through OIDC (*trusted
publishing*), and only from the GitHub environment named for each.

| Job | Runs on | |
|---|---|---|
| Authorize | both | stops unless the actor is a repository admin (as `release.yml` does) |
| Resolve | both | a tag is a **release**, a manual run a **rehearsal**; checks a tag names the manifests' version (`make sdk-version-check VERSION=…`) and the six agree; picks the npm dist-tag (`next` for a pre-release, `latest` otherwise) |
| Verify Python / Verify npm | both | `make packages-check`; `clients/web`'s typecheck and vitest, which cover `packages/` — what ci.yml's `packages` and `web` jobs run, on the released commit |
| Build | both | `make sdk-build`, `twine check --strict`, `SHA256SUMS`, and each tarball's file list in the run summary; kept as a workflow artifact for 30 days |
| Rehearse on TestPyPI | rehearsal | environment `testpypi`: uploads the wheels and sdists to test.pypi.org (`pypa/gh-action-pypi-publish`, trusted publishing) |
| Rehearse npm (dry run) | rehearsal | `npm publish --dry-run --provenance --access public` for each tarball, under the dist-tag a release would use, and the tarballs as an artifact (`npm-tarballs-<v>`) |
| Publish to PyPI | release | environment `pypi`: uploads to pypi.org (trusted publishing; PEP 740 attestations) |
| Publish to npmjs | release | environment `npm`: `npm publish --provenance --access public --tag <dist-tag>` for each tarball (trusted publishing; `NPM_TOKEN` only until it is configured — below) |
| Attach to the GitHub Release | release | creates the `sdk-v<v>` release (a pre-release for `-rc.N` and the like; never marked *latest*, which the desktop app's updater reads) and uploads every file plus `SHA256SUMS` |

**Re-running is safe.** PyPI files already there are skipped
(`skip-existing`), an npm version already in the registry is skipped, and the
GitHub Release's files are replaced with the same bytes. A release that failed
half-way is finished by re-running the workflow. A published version is never
replaced — PyPI and npm refuse it — so fix forward with the next patch.

**Provenance.** npm records which workflow run built each version, and checks
the tarball's `repository.url` (`git+https://github.com/ignite-ember/igni-sdk.git`)
against the repository that ran it; the three `package.json`s carry it. PyPI
attaches the equivalent attestations on its own.

## One-time setup (founder)

Done once, by an owner of the `ignite-ember` GitHub organisation, before the
first rehearsal. Enable two-factor authentication on every account below;
PyPI and npm require it to publish.

### 1. PyPI and TestPyPI

TestPyPI is a separate service with separate accounts.

1. Create an account on [pypi.org](https://pypi.org/account/register/) and one
   on [test.pypi.org](https://test.pypi.org/account/register/), both with 2FA.
2. Optionally, request an organisation `ignite-ember` on PyPI (Your
   organisations → Create; a company organisation is reviewed by PyPI, which
   takes a while). Not needed to publish: the projects can be moved into it
   later.
3. On **pypi.org**, Your account → Publishing → *Add a new pending publisher*
   (GitHub) for one of them:

   | PyPI project name | Owner | Repository name | Workflow name | Environment name |
   |---|---|---|---|---|
   | `igni-service` | `ignite-ember` | `igni-sdk` | `sdk-release.yml` | `pypi` |
   | `igni-extension` | `ignite-ember` | `igni-sdk` | `sdk-release.yml` | `pypi` |
   | `igni-client` | `ignite-ember` | `igni-sdk` | `sdk-release.yml` | `pypi` |

4. On **test.pypi.org**, the same, with environment name `testpypi`.

PyPI takes **one** pending publisher per repository, workflow and
environment: adding the second project with the same four answers is
refused ("already been registered for a different project name"). A
publisher can be added to any number of projects once they exist, so the
first release, which creates all three, publishes with a token instead:

5. On pypi.org, Account settings → API tokens → *Add API token*, scope
   *Entire account* (no project exists to scope it to). Store it as the
   secret **`PYPI_TOKEN`** of the GitHub environment `pypi` — of the
   environment, not of the repository. For a rehearsal, the same on
   test.pypi.org as **`TEST_PYPI_TOKEN`** of `testpypi`.
6. After the first release, on each project's page → Manage → Publishing,
   add the trusted publisher of the table above (and on TestPyPI with
   `testpypi`). Then delete the secrets and the tokens: with them gone the
   workflow publishes with its OIDC token alone.

### 2. npmjs

npm's trusted publishing is configured on a package's settings page, so a
package must exist before it can trust anything. The first publish therefore
uses a token, and the token is removed straight after.

1. Create an account on [npmjs.com](https://www.npmjs.com/signup), with 2FA.
2. Create the organisation **`ignite-ember`** (Add organization → the free
   plan, which is for public packages). The scope `@ignite-ember` is then
   yours.
3. For the first release, create a **granular access token** (Access Tokens
   → Generate New Token → Granular): permission *Read and write*, packages
   and scopes *`@ignite-ember`*, organisation *`ignite-ember`*, a short
   expiry (7 days), and *Bypass two-factor authentication* ticked so CI can
   use it. Store it as the secret **`NPM_TOKEN`** of the GitHub environment
   `npm` (below) — of the environment, not of the repository.
4. After the first release has published the three packages, on each
   package's page → Settings → *Trusted Publisher* → GitHub Actions:

   | Field | Value |
   |---|---|
   | Organization or user | `ignite-ember` |
   | Repository | `igni-sdk` |
   | Workflow filename | `sdk-release.yml` |
   | Environment name | `npm` |

   for `@ignite-ember/extension-bridge`, `@ignite-ember/ui-react` and
   `@ignite-ember/ui-css`. Then delete the `NPM_TOKEN` secret and revoke the
   token, and on each package → Settings → Publishing access choose *Require
   two-factor authentication and disallow tokens*. From then on the workflow
   publishes with its OIDC token alone, and nothing else can.

(The alternative to step 3 is to publish `0.1.0` of each package by hand,
from a laptop signed in with `npm login`, from the tarballs a rehearsal
uploads — then configure step 4 before the first tagged release. The
workflow skips a version that is already published.)

### 3. GitHub environments

In `ignite-ember/igni-sdk` → Settings → Environments, create three:

| Environment | Required reviewers | Deployment branches and tags | Secrets |
|---|---|---|---|
| `testpypi` | the admin | all (a rehearsal runs from any branch) | `TEST_PYPI_TOKEN`, until the projects trust the workflow |
| `pypi` | the admin | selected: tag pattern `sdk-v*` | `PYPI_TOKEN`, until the projects trust the workflow |
| `npm` | the admin | selected: tag pattern `sdk-v*` | `NPM_TOKEN`, until npm trusted publishing is configured |

The names must match the trusted publishers above exactly. A release's
`pypi` and `npm` jobs wait together, so one review approves both. Leave
*Prevent self-review* off while there is one admin.

## Rehearsing

From any branch whose manifests carry the version to rehearse:

1. Actions → **SDK release** → *Run workflow* on that branch.
2. Approve the `testpypi` deployment when the run asks.
3. Check the result:
   - <https://test.pypi.org/project/igni-service/> and
     `…/igni-extension/` and `…/igni-client/` show the version, with the README and project links
     rendered.
   - Install from TestPyPI, taking the dependencies from PyPI (TestPyPI does
     not have them):

     ```bash
     uv venv /tmp/sdk-try && uv pip install --python /tmp/sdk-try \
       --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ \
       --index-strategy unsafe-best-match igni-service==<v> igni-extension==<v> igni-client==<v>
     ```

   - The run's summary lists each npm tarball's files, and the
     `npm-tarballs-<v>` artifact holds them: `npm install ./ignite-ember-ui-react-<v>.tgz`
     in a scratch project.

TestPyPI, like PyPI, never takes the same file twice: a second rehearsal of
one version uploads nothing. Rehearse changed code under a new pre-release
(`make sdk-version VERSION=0.4.0-rc.2`).

## Releasing

1. On a branch: `make sdk-version VERSION=0.4.0`, commit, open a PR, merge.
2. Rehearse (above) on `main`.
3. Tag the merge commit and push the tag:

   ```bash
   git tag sdk-v0.4.0 && git push origin sdk-v0.4.0
   ```

4. Approve the `pypi` and `npm` deployments when the run asks.
5. Check <https://pypi.org/project/igni-service/>,
   <https://pypi.org/project/igni-extension/>,
   <https://pypi.org/project/igni-client/>,
   <https://www.npmjs.com/package/@ignite-ember/ui-react> (and the other two;
   the version page shows *Provenance*), and the `sdk-v0.4.0` GitHub Release.

A pre-release (`sdk-v0.4.0-rc.1`) goes the same way: npm's dist-tag `next`,
a GitHub pre-release, and PyPI, where installers skip it unless asked.

## The first release

In order — the consumers cannot resolve the SDKs before they are published.

1. **One-time setup**, above.
2. **Rehearse** `0.1.0`, the version all six carry today.
3. **Release** it: `git tag sdk-v0.1.0 && git push origin sdk-v0.1.0`.
4. **Trusted publishing**: on PyPI and TestPyPI add the publisher to the
   three projects and delete `PYPI_TOKEN` and `TEST_PYPI_TOKEN` (one-time
   setup, step 1.6); on npm configure the three packages and delete
   `NPM_TOKEN` (step 2.4).
5. **Consumers' lockfiles**, which do not hold the SDKs from PyPI yet:

   ```bash
   # the CodeIndex and Artifacts checkouts
   make lock && make test && git add uv.lock && git commit
   # optionally, their pages' npm locks
   make extension-ui-lock && git add extension/page/package-lock.json
   ```

   Until then their `IGNI_SDK=local` targets are what run, and their image
   builds stop at the first stage with a message saying exactly this.

## Installing them

**Python.** From PyPI, like anything else:

```bash
uv add igni-service        # a service
uv add igni-extension      # an extension's process
uv add igni-client         # a program driving an igni
```

**npm.** From npmjs:

```bash
npm install @ignite-ember/extension-bridge @ignite-ember/ui-react @ignite-ember/ui-css
```

Nothing to configure, no token. A consumer's lockfile (`uv.lock`,
`package-lock.json`) records each file's hash, so a same-named package from
anywhere else cannot match it.

### Working against an igni-sdk checkout

The consumers keep a local override, `IGNI_SDK=local`, for changing an SDK
and its consumer together:

```bash
make test IGNI_SDK=local                       # the Artifacts and CodeIndex checkouts (IGNI=<checkout>, default the sibling)
make install IGNI_SDK=local IGNI_REPO=<path>   # the extension-starter checkout, then IGNI_SDK=local on every make
```

It installs everything else from the committed lockfiles (`uv sync --frozen
--no-install-package igni-…`), puts the checkout's SDKs over them —
editable for Python; copies for npm (`npm install --no-save
--install-links`) — and sets `UV_NO_SYNC` so `uv run` does not undo it. No
manifest or lockfile changes, and no registry is contacted for the SDKs, so it
works before a release and offline. Extension bundles built this way take
igni-extension from wheels of the checkout. Images always install from a
registry.

### Air-gapped and mirrored builds

Nothing here is needed to *run* igni's services or extensions: an image
carries its installed SDK and a bundle its wheelhouse. To *build* without
reaching PyPI or npmjs, use a mirror the build can reach (devpi, Nexus,
Artifactory, Verdaccio) holding the versions the lockfiles pin — the SDKs'
files are on PyPI and npmjs like the rest, and also attached to each
`sdk-v<version>` GitHub Release, checksummed, for a mirror that is filled by
hand:

```bash
gh release download sdk-v0.4.0 --repo ignite-ember/igni-sdk --dir sdk-0.4.0
(cd sdk-0.4.0 && sha256sum -c SHA256SUMS)
```

Point the image at the mirror:

```bash
docker build --build-arg PIP_INDEX_URL=https://mirror.example/pypi/simple/ …
```

The images install from `uv export` requirements, which carry hashes but no
URLs, so the mirror only has to serve the same files. For npm, `npm config
set registry <mirror>`; `package-lock.json`'s integrity hashes still hold.

## Not done

- **A changelog.** The release writes a run summary and a one-paragraph
  GitHub Release, not release notes.
- **A PyPI organisation.** The projects belong to the account that first
  publishes them until they are moved into one.

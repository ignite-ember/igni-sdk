# Your first extension

From an empty directory to an extension and its service running in igni:
two tools the agent calls, a hook, a page in igni's sidebar, a request
for what it needs in a cloud VM, and the export and erasure every
service owes the people it knows about — tested on the SDKs' fakes.
About thirty minutes, most of it starting things.

What you build is in this repository as
[`examples/ticket-lookup/`](../examples/ticket-lookup/), and every file
this page shows is that file — a test holds them to each other, and CI
runs the example's tests. Copy it rather than retyping it (from this
repository's checkout):

```bash
cp -R examples/ticket-lookup ~/ticket-lookup
```

> **Shortcut.** `igni ext init --service --id acme.tickets ~/ticket-lookup`
> writes the same pieces with your own id — `extension/`, `service/`,
> `tests/`, and a `pyproject.toml` for one dev environment — and its README
> says what to run. This page follows the copy.

How the pieces fit — [EXTENSIBILITY.md](https://github.com/ignite-ember/igni-core/blob/main/docs/EXTENSIBILITY.md) (in igni-core) is the
contract, and the two SDK READMEs are the reference:

```
your machine                          igni server                     your service
──────────────                        ───────────                     ────────────
igni ── installs ──▶ extension  ◀─── bundle, signed ◀─── uploads ──── service.py
          │            (MCP over stdio)     │                           │
          └── its page ── ext.acme.tickets.* ┘   approves, enables  ── portal
                                              export, erasure ───────▶  │
```

## Before you start

- **igni**, from the igni-core checkout: `uv sync`, then put it on your
  `PATH` for this shell — every command below says `igni`, and most run in
  another directory:

  ```bash
  alias igni="$PWD/.venv/bin/igni"
  igni --version
  ```

- **igni server**, from its checkout, running natively (not in Docker,
  so it can reach a service on your machine): its README's *Quick start*
  — `make dev-env`, Postgres and Redis, `make migrate`, `make run` (the
  API, on `http://localhost:7777`) and `make portal-dev` (the portal, on
  `http://localhost:3000`) — and then its *The first sign-in*: sign up in
  the portal (the first account is the super admin; the code is in the
  API's log), create an organisation with your email's domain, and add a
  model. You are then the super admin *and* that organisation's admin,
  which is both people this walk-through needs. Do not set
  `PORTAL_AUTH_BYPASS`: its demo identity cannot sign igni in, and once
  it has made its account, yours is no longer the first.
- **`uv`** and Python 3.12.

### Step 0: one environment for the walk-through

Make it in `~/ticket-lookup`. Every
command from here on runs there, in it:

```bash
cd ~/ticket-lookup
uv venv --python 3.12
source .venv/bin/activate
uv pip install igni-extension igni-service uvicorn aiosqlite pytest anyio
```

If `igni-extension` and `igni-service` are not on your package index yet
(the index may hold an older `igni-extension`), build the wheels from this
repository's checkout and install them by path. Keep the directory: step 2
reads it too.

```bash
mkdir -p ~/ticket-lookup/wheels
(cd packages/igni-extension && uv build --wheel -o ~/ticket-lookup/wheels)
(cd packages/igni-service && uv build --wheel -o ~/ticket-lookup/wheels)
uv pip install ~/ticket-lookup/wheels/*.whl uvicorn aiosqlite pytest anyio
```

(Run those from the checkout; the `cd ~/ticket-lookup` above is for the
commands after them. A project made by `igni ext init` needs the same
wheels: its `pyproject.toml` names no wheel directory, and says to run
`uv sync --find-links <the directory holding them>` instead of a plain
`uv sync`, which would look on the index.)

## 1. Write the extension

An extension is a Python package that speaks MCP over stdio, and a
manifest saying what it is and what it may do.

The package, with an entry point igni starts:

<!-- file: examples/ticket-lookup/extension/pyproject.toml -->
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "acme-tickets-extension"
version = "0.2.0"
requires-python = ">=3.12"
dependencies = ["igni-extension"]

[project.scripts]
acme-tickets-extension = "acme_tickets_extension:main"

[tool.hatch.build.targets.wheel]
packages = ["src/acme_tickets_extension"]
```

Its code: two tools and a hook. `IgniExtension("acme.tickets")` is the
manifest's `id`. Every tool states MCP's four hints (`ToolHints`) — igni's
permission modes decide on them, so `lookup_ticket`, which reads only its
own data, runs without asking. `ticket_from_service` calls the service as
the signed-in person (`ext.service` fetches and renews the token). The
hook is told about every tool the agent ran.

<!-- file: examples/ticket-lookup/extension/src/acme_tickets_extension/__init__.py -->
```python
"""Ticket lookup: two tools, a hook, and a page that calls one of them."""

import json
from pathlib import Path
from urllib.parse import quote

from igni_extension import Hooks, IgniExtension, NotConfigured, NotSignedIn, ToolHints
from igni_extension.hooks import PostToolUse

ext = IgniExtension("acme.tickets")

TICKETS = {
    "T-1001": {"id": "T-1001", "title": "VPN drops every hour", "status": "open", "owner": "ada"},
    "T-1002": {
        "id": "T-1002",
        "title": "Printer on 3rd floor offline",
        "status": "closed",
        "owner": "grace",
    },
}


@ext.tool(hints=ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False))
async def lookup_ticket(ticket_id: str) -> str:
    """Look up a support ticket by id (e.g. T-1001). Returns JSON."""
    ticket = TICKETS.get(ticket_id.upper())
    if ticket is None:
        return json.dumps({"error": f"no ticket {ticket_id}", "known": sorted(TICKETS)})
    return json.dumps(ticket)


@ext.tool(hints=ToolHints(read_only=True, destructive=False, idempotent=True, open_world=True))
async def ticket_from_service(ticket_id: str) -> str:
    """Look a ticket up on the Ticket lookup service, as the signed-in person."""
    try:
        response = await ext.service.get(f"/v1/tickets/{quote(ticket_id, safe='')}")
    except NotSignedIn:
        return "Sign in to igni to reach the ticket service."
    except NotConfigured:  # a development install has no service, so no URL for one
        return "The ticket service is not set up for this install."
    response.raise_for_status()
    return response.text


@ext.hook(Hooks.POST_TOOL_USE)
async def audit(call: PostToolUse) -> None:
    """Record every tool the agent ran in this extension's data directory."""
    data_dir: Path | None = ext.environment.data_dir  # None when igni did not start it
    if data_dir is None:
        return
    with (data_dir / "tool-audit.log").open("a") as f:
        f.write(f"{' '.join(call.tool_name.splitlines())}\n")


def main() -> None:
    ext.run()
```

The manifest. `permissions.tools` lists each tool igni lets it register,
named `<id>.<tool>` with the same hints; `permissions.rpc` is what its
own page may call; `permissions.hooks` the hook events it answers; `vm`
what it needs in a cloud VM (step 8); `contributes.pages` the page.
The `$schema` line gives you completion and checking in your editor.

<!-- file: examples/ticket-lookup/extension/manifest.json -->
```json
{
  "$schema": "https://ignite-ember.sh/schema/extension-manifest-1.json",
  "id": "acme.tickets",
  "version": "0.2.0",
  "contract": ">=1.0 <2",
  "name": "Ticket lookup",
  "description": "Look up a support ticket by its id.",
  "vendor": "Acme Corp",
  "trust": "partner",
  "python": {
    "package": "acme-tickets-extension",
    "entry": "acme-tickets-extension",
    "wheels": "wheels",
    "mcp": {
      "transport": "stdio"
    }
  },
  "permissions": {
    "workspace": "none",
    "tools": [
      {
        "name": "acme.tickets.lookup_ticket",
        "annotations": {
          "readOnlyHint": true,
          "destructiveHint": false,
          "idempotentHint": true,
          "openWorldHint": false
        }
      },
      {
        "name": "acme.tickets.ticket_from_service",
        "annotations": {
          "readOnlyHint": true,
          "destructiveHint": false,
          "idempotentHint": true,
          "openWorldHint": true
        }
      }
    ],
    "rpc": [
      "ext.acme.tickets.lookup_ticket"
    ],
    "hooks": [
      "PostToolUse"
    ]
  },
  "vm": {
    "memoryMib": 2048,
    "packages": {
      "apt": [
        "jq"
      ]
    }
  },
  "contributes": {
    "pages": [
      {
        "kind": "acme.tickets",
        "label": "Tickets",
        "sidebar": true
      }
    ]
  }
}
```

The page. Its CSP is `script-src 'self'`, so its script is a file beside
it — an inline `<script>` does not run.

<!-- file: examples/ticket-lookup/extension/ui/index.html -->
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Tickets</title>
  </head>
  <body class="igni-root">
    <form id="f"><input id="q" value="T-1001" /> <button>Look up</button></form>
    <pre id="out">Loading…</pre>
    <script type="module" src="main.js"></script>
  </body>
</html>
```

<!-- file: examples/ticket-lookup/extension/ui/main.js -->
```javascript
// The page's script. It must be a file: the page's CSP is
// `script-src 'self'`, so an inline <script> does not run.
//
// A minimal bridge, so this has no build step. For anything real, use
// @ignite-ember/extension-bridge, which is this with types.
const host = window.parent;
let nonce = null;
let next = 0;
const waiting = new Map();

window.addEventListener("message", (event) => {
  const message = event.data;
  if (event.source !== host || message?.igni !== 1) return;
  if (message.kind === "hello") {
    nonce = message.nonce;
    look();
    return;
  }
  if (message.kind === "result") {
    const waiter = waiting.get(message.id);
    if (!waiter) return;
    waiting.delete(message.id);
    message.ok ? waiter.resolve(message.value) : waiter.reject(new Error(message.error));
  }
});

function call(method, args = {}) {
  const id = String(++next);
  return new Promise((resolve, reject) => {
    waiting.set(id, { resolve, reject });
    host.postMessage({ igni: 1, kind: "call", nonce, id, method, args }, "*");
  });
}

const out = document.getElementById("out");

function look() {
  // Granted by permissions.rpc in manifest.json: ext.<extension id>.<tool>.
  call("ext.acme.tickets.lookup_ticket", { ticket_id: document.getElementById("q").value }).then(
    (value) => (out.textContent = JSON.stringify(value, null, 2)),
    (error) => (out.textContent = "error: " + error.message),
  );
}

document.getElementById("f").addEventListener("submit", (event) => {
  event.preventDefault();
  look();
});
```

Check it:

```bash
igni ext doctor extension
```

`doctor` validates the manifest, starts the extension, asks it for its
tools over MCP (with a timeout), and says what is wrong, with the fix.
Above the part shown below it prints a few `-` notes, such as `no
wheelhouse at 'wheels'` (a development install builds one), and that an
extension that runs as a process installs only on a single-user backend, and
that pages are shown only by one. They are notes, not problems: only a
line that says what to fix is a problem, and the last line says whether
there were any. The end of what it prints:

```
  process    started it and asked for its tools: 2

  each tool's names (the server's own, then where each is used):
    lookup_ticket          manifest acme.tickets.lookup_ticket
                           page     ext.acme.tickets.lookup_ticket
                           registry mcp_ext:acme.tickets_lookup_ticket
                           model    mcp_ext_acme_tickets_lookup_ticket
    ticket_from_service    manifest acme.tickets.ticket_from_service
                           page     ext.acme.tickets.ticket_from_service (not granted in permissions.rpc)
                           registry mcp_ext:acme.tickets_ticket_from_service
                           model    mcp_ext_acme_tickets_ticket_from_service

  no problems found
```

The page may call only `lookup_ticket`, because `permissions.rpc` grants
only that; the agent may call both.

### One tool, five names

| Where | Name | Who uses it |
|---|---|---|
| Your code | `lookup_ticket` | the function; `HostHarness.call("lookup_ticket", …)` in tests |
| `permissions.tools` | `acme.tickets.lookup_ticket` | the manifest: `<id>.<tool>` |
| `permissions.rpc`, the page | `ext.acme.tickets.lookup_ticket` | `call(…)` from the page |
| igni: hooks' `tool_name`, permission rules, transcripts | `mcp_ext:acme.tickets_lookup_ticket` | the registered name; an extension's hook also gets `tool_manifest_name` = `acme.tickets.lookup_ticket` |
| The model | `mcp_ext_acme_tickets_lookup_ticket` | what every provider (OpenAI-compatible, Anthropic, Gemini, a local model) is sent, since they accept only `[a-zA-Z0-9_-]`; igni maps the call back |

## 2. Bundle it

What the service uploads: the manifest, the page, and a wheelhouse with
the extension's wheel and every dependency's, for each platform igni runs
on — a machine installs from it with no index.

```bash
igni-service-bundle --extension extension --out extension-bundle.tar.gz
```

It needs network access: it downloads the wheels for each platform from the
package index (about 50 wheels and 30 MB for this example, a few seconds
to a minute). The SDK wheels in the bundle are the ones the index serves,
so an `igni-extension` newer than the index's is left out of the bundle
unless you name where it is — add `--find-links ~/ticket-lookup/wheels` (from
step 0). A wheel found there is taken as it is, not fetched again.

## 3. Run the service

The service registers with igni server, uploads the bundle, and answers
igni's export and erasure calls. `create_app(igni=None)` is a factory so
the tests can hand it a fake.

<!-- file: examples/ticket-lookup/service/service.py -->
```python
"""Ticket lookup's service.

Registers with igni server, ships the extension bundle, answers erasure and
export, and reports what became of the extension's VM profile request.

    uvicorn --factory service:create_app --app-dir service --port 8201
"""

from fastapi import Depends, FastAPI

from igni_service import ExportSection, IgniService, IgniSettings, Person, Subject


def create_app(igni: IgniService | None = None) -> FastAPI:
    """The app; `igni` is a FakeIgni's service in tests, the real one otherwise."""
    igni = igni or IgniService.from_settings(IgniSettings())
    app = FastAPI(lifespan=igni.lifespan)
    igni.install(app)

    # What this service keeps about people: who looked which ticket up.
    lookups: dict[tuple[str, str], list[str]] = {}

    @igni.on_erase
    async def erase(subject: Subject) -> None:
        lookups.pop((subject.org_id, subject.user_id), None)

    @igni.on_export
    async def export(subject: Subject) -> list[ExportSection]:
        rows = [{"ticket": t} for t in lookups.get((subject.org_id, subject.user_id), [])]
        return [ExportSection(name="Ticket lookups", rows=rows)]

    @app.get("/v1/tickets/{ticket_id}")
    async def ticket(ticket_id: str, person: Person = Depends(igni.person)) -> dict:
        lookups.setdefault((person.org_id, person.user_id), []).append(ticket_id)
        return {"id": ticket_id, "looked_up_by": person.email}

    @app.get("/v1/vm-profile")
    async def vm_profile(person: Person = Depends(igni.org_admin)) -> dict:
        """What became of the extension's `vm` request in the caller's organisation."""
        status = await igni.host(person.org_id).extension_vm_profile()
        return status.model_dump(mode="json")

    return app
```

A service has a hostname of its own — its URL is its identity, the
audience of the tokens people get for it. `*.localhost` is your machine
(on Linux, add `127.0.0.1 tickets.localhost` to `/etc/hosts` if it does
not resolve).

```bash
export IGNI_SERVER_URL=http://localhost:7777
export PUBLIC_BASE_URL=http://tickets.localhost:8201
export SERVICE_NAME="Ticket lookup"
export IGNI_KEY_DATABASE_URL=sqlite+aiosqlite:///keys.db
export IGNI_EXTENSION_BUNDLE=extension-bundle.tar.gz
# Once, and keep it: a new key is a new identity, approved again.
test -f .kek || python -c "from igni_service import KeyCipher; print(KeyCipher.generate())" > .kek
export IGNI_KEY_ENCRYPTION_KEY=$(cat .kek)
uvicorn --factory service:create_app --app-dir service --port 8201
```

It prints its identity — client id, state and the key's thumbprint — and
the next step for that state:

```
  ============================================================
  igni service identity
    client id:   09075090-00ee-446b-bc17-67ddb2b30023
    state:       pending
    URL:         http://tickets.localhost:8201
    thumbprint:  mYhl4fFoNkMKUZLRePT1ppX00Eq7Q12RGPPak-4_OAo
  A super admin approves this service in igni's portal under
  Services, after checking the thumbprint there is this one.
  ============================================================
```

The identity is printed once the service has registered with igni server.
If the server is not reachable it logs `registration failed … retrying`
with a growing delay and prints no banner, so start igni server first.

Restart it once approved and the last lines say an org admin switches it
on for a group. A new version that asks for more than the approved one is
**held**, and the service logs a warning saying so.

## 4. A super admin approves the service

In the portal (`http://localhost:3000`), **Services** → *Ticket lookup*.
Check that the thumbprint is the one the service printed, read what the
extension would put on machines — its tools and their hints, its page,
its hooks — and **Approve**.

Approval is trust. It gives the extension to nobody yet.

## 5. An org admin switches it on for a group

**Groups** → the group you are in (*Default*) → **Extensions** → switch
*Ticket lookup* on. People in that group get it; nobody else in the
organisation does.

## 6. Sign in, and install it

Point igni at the server, in `~/.igni/config.yaml`:

```yaml
api_url: http://localhost:7777
portal_url: http://localhost:3000
```

Sign in, and install what igni server gives you:

```bash
igni login        # opens the portal's sign-in page; it prints the address too
igni ext sync
igni ext list
```

(A script that already holds an access token signs in with
`printf %s "$TOKEN" | igni login --token-stdin`.)

`igni ext sync` prints what it did:

```
synced with http://localhost:7777 (group Default)
  installed  acme.tickets 0.2.0 from http://tickets.localhost:8201
```

and `igni ext list` shows `acme.tickets  0.2.0  from http://tickets.localhost:8201`
(for a development install it shows `development install` instead of the URL).
If it says *nothing is switched on for you*, step 4 or 5 is not done yet.

You need `ext sync` only the first time: every `igni -m` / `igni -p` run
syncs before it starts (best-effort, 30 seconds at most, carrying on
without it when igni server cannot be reached), and so does the igni app
when it starts and when you sign in. Under `air_gapped` it reaches only
your igni server.

## 7. Use it

Your service is plain `http` on your machine. An extension's process is
sandboxed, and outside development its sandbox lets it reach its service
only over `https`, so for this walk-through run igni in development:

```bash
export IGNI_DEV_EXTENSIONS=1
```

(Without it `lookup_ticket` still works — it reads only its own data —
and igni logs once that the service is plain http and what to do.)

A development install (see *Faster loops*) has no service, so there
`ticket_from_service` answers "The ticket service is not set up for this
install." — the example catches `NotConfigured` for that; the service
path below needs the synced install.

In chat — `--read-only`, because a headless `igni -m` cannot ask you
anything: the extension's tools say they are read-only, so they run, and
anything else the model reaches for that would need a yes is refused
rather than left waiting. Without it, a model that also tries, say, a
shell command stops the run with "Run paused for confirmation … the tool
did not run" and exit 1:

```bash
igni --read-only -m "What is the status of ticket T-1001?"
```

The first igni run in a folder sets it up as an igni project: it writes
`igni.md` and a `.igni/` directory (built-in agents, skills, hooks,
`config.yaml`, `settings.json`) into `~/ticket-lookup`, trusted or not —
igni's [First Run](https://github.com/ignite-ember/igni-core/blob/main/QUICKSTART.md#first-run).
They are igni's files, not the extension's: `igni-service-bundle` reads only
`extension/`, so they never reach the bundle, but a `git add .` picks them
up. Delete them, or keep them out of git, if you do not want them.

The agent calls `lookup_ticket` and answers "open". (The model is shown the
tool's answer wrapped in `<untrusted_tool_output>` tags, so a tool's text
is never taken for an instruction; a development install also prints a
line saying it is one.) Then once through the
service, so it has something to export:

```bash
igni --read-only -m "Look ticket T-1002 up on the ticket service."
```

Open igni's app: **Tickets** is in the sidebar, and its page shows
T-1001, fetched through `ext.acme.tickets.lookup_ticket`. The page lives on
a loopback origin igni picks (a new port each start), and only igni's app
frames it; a program reads the origin with `igni.extensions.list()` in
`igni-client`, but cannot call `ext.*` methods as a page.

The service's log shows `GET /v1/tickets/T-1002 … 200`: the extension
called it as you, with a token igni server issued for the service.

The hook wrote a line per tool call to `tool-audit.log` in the
extension's data directory (`~/.igni/extensions/.data/acme.tickets/`):
`mcp_ext:acme.tickets_lookup_ticket`, the name igni registered the tool
under.

## 8. Its VM profile

In igni's cloud each producer runs in a microVM. The manifest's `vm`
asks for 2 GiB and `jq`. It is a request, pending in every organisation:
in the portal, **VM profiles** shows exactly what would be installed;
approving it makes a profile, which the org admin gives to the groups
and apps that use the extension. A desktop install ignores `vm`.

The service reads what became of it — `GET /v1/vm-profile` in
`service.py`, as an org admin, which calls
`igni.host(org_id).extension_vm_profile()`: the request, and the
profile approved from it, if any.

## 9. Export and erasure

igni server calls every approved service for a person's data:
`GET /v1/igni/subjects/{user_id}/export` and
`DELETE /v1/igni/subjects/{user_id}` — routes `igni.install(app)` adds,
answered by your `@igni.on_export` and `@igni.on_erase`.

- **Export:** portal → **Compliance** → **Subject access**, your email.
  The report has a *Ticket lookups* section with T-1002.
- **Erasure:** portal → **Erasures**. After it runs, the service holds
  nothing about you, and a new subject-access report says so.

## 10. Test it on the fakes

`HostHarness` runs the extension's MCP server in-process and calls a tool
as igni does; `ConcurrencyHarness` calls it as many people at once;
`FakeIgni` is igni server in-process, signing the tokens a person and
igni would send.

<!-- file: examples/ticket-lookup/pytest.ini -->
```ini
[pytest]
testpaths = tests
```

<!-- file: examples/ticket-lookup/tests/test_example.py -->
```python
"""The example's tests, written only against what the SDK READMEs document."""

import json
import sys
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "service"))
sys.path.insert(0, str(HERE.parent / "extension" / "src"))

from igni_extension import Caller, CallerKind  # noqa: E402
from igni_extension.testing import ConcurrencyHarness, ConcurrentCall, HostHarness  # noqa: E402
from igni_service import Member  # noqa: E402
from igni_service.testing import FakeIgni, IgniAddresses  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


ADA = Caller(kind=CallerKind.PERSON, id="u-ada", org="org-1", group="g-1")
GRACE = Caller(kind=CallerKind.PERSON, id="u-grace", org="org-1", group="g-1")


async def test_the_tool_answers_as_igni_calls_it() -> None:
    from acme_tickets_extension import ext

    async with HostHarness(ext) as host:
        result = await host.call("lookup_ticket", {"ticket_id": "T-1001"}, caller=ADA)
    assert json.loads(result.content[0].text)["title"] == "VPN drops every hour"


async def test_many_callers_at_once() -> None:
    from acme_tickets_extension import ext

    report = await ConcurrencyHarness(ext).run(
        [
            ConcurrentCall(tool="lookup_ticket", arguments={"ticket_id": "T-1001"}, caller=ADA),
            ConcurrentCall(tool="lookup_ticket", arguments={"ticket_id": "T-1002"}, caller=GRACE),
        ]
    )
    assert report.results[0].result != report.results[1].result


async def test_the_service_takes_a_person_and_answers_export_and_erasure() -> None:
    from service import create_app

    fake = FakeIgni(addresses=IgniAddresses(service_url="http://tickets.test"))
    fake.directory.add_member("org-1", Member(user_id="u-ada", email="ada@acme.test", name="Ada"))
    app = create_app(fake.service())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tickets.test") as http:
        person = {"Authorization": f"Bearer {fake.signer.person_token('u-ada', org_id='org-1')}"}
        r = await http.get("/v1/tickets/T-1001", headers=person)
        assert r.status_code == 200, r.text
        assert r.json()["looked_up_by"] == "ada@acme.test"

        igni = {"Authorization": f"Bearer {fake.signer.igni_token('org-1')}"}
        r = await http.get("/v1/igni/subjects/u-ada/export", headers=igni)
        assert r.status_code == 200, r.text
        assert "T-1001" in r.text
        r = await http.delete("/v1/igni/subjects/u-ada", headers=igni)
        assert r.status_code in (200, 204), r.text
        r = await http.get("/v1/igni/subjects/u-ada/export", headers=igni)
        assert "T-1001" not in r.text
```

```bash
pytest
```

The test file this page prints, `tests/test_example.py`, is three tests. A
copy of the whole example also holds `test_extension.py` and
`test_service.py` (the extension's tools, hook and identity, and the
service's routes), and `pytest` runs all three files. None of them needs
igni or an igni server.

## Changing it

- **A new version** — bump `version` in `manifest.json` and
  `pyproject.toml`, bundle again, restart the service. It uploads the new
  bundle; igni installs it at the next sync. A version that asks for more
  (a new tool, a wider grant) is held until a super admin approves the
  update on the service's page.
- **Faster loops** — a development install runs a directory with no
  service: `IGNI_DEV_EXTENSIONS=1 igni ext install extension`, and start
  igni with `IGNI_DEV_EXTENSIONS=1` too. It installs a copy, so after a
  change (a rebuilt page too) install it again with
  `igni ext install --replace extension`, which re-asks for its
  permissions; without `--replace` a second install is refused
  ([EXTENSIBILITY.md §9](https://github.com/ignite-ember/igni-core/blob/main/docs/EXTENSIBILITY.md#9-developing-one)).

## Where next

- [`packages/igni-extension/README.md`](../packages/igni-extension/README.md) — the extension SDK: the host object model, notifications, signals, prompt contributions.
- [`packages/igni-service/README.md`](../packages/igni-service/README.md) — the service SDK: people, apps, the directory, notifications, reaching a producer's agent.
- [`packages/extension-bridge/README.md`](../packages/extension-bridge/README.md) — the page's bridge, typed.
- [EXTENSIBILITY.md](https://github.com/ignite-ember/igni-core/blob/main/docs/EXTENSIBILITY.md) (in igni-core) — the contract, and what igni promises not to break.

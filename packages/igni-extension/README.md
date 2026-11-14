# igni-extension

**Full documentation:** [ignite-ember.sh/docs/sdk/igni-extension](https://ignite-ember.sh/docs/sdk/igni-extension) — guides and the complete API reference, a page per topic.

**The Python SDK for an igni extension's process.**

An igni extension usually comes in two parts:

- **The extension itself** runs inside igni, on each person's device or in
  their Fleet VM. It has a *page*, shown in the igni app (a sandboxed
  frame, built with the npm package `@ignite-ember/extension-bridge`), and
  a *process*, which the igni backend on the device starts in an OS
  sandbox. The process gives the agent tools, has a say in what the agent
  does through hooks, and can drive the igni app. **The process is built
  with this package.**
- **Its backend service** is your web service. It runs once, in the
  organisation's cloud or data centre, and keeps what is shared between
  people. It is built with `igni-service`.

The process and the page call the backend service **as the person signed
in to igni**. This package fetches that person's token from the igni
backend, attaches it to every request and renews it. Your code never
holds an address, a token or a protocol message.

| Package | What it is for | Where it runs |
|---|---|---|
| `igni-service` | an extension's backend service: joins it to igni, ships the extension bundle, talks to igni server for an organisation | the organisation's cloud or data centre, once |
| `igni-extension` | the extension's process: tools, hooks, reactions, its service as the person (this package) | inside igni, on each person's device or Fleet VM |
| `igni-client` | your own program driving an igni from outside: sessions, prompts, commands | wherever your program runs |

Everything runs in the organisation's own infrastructure: igni server,
Fleet and every service. Ignite Ember hosts nothing.

Building an extension for the first time? Follow
[Your first extension](https://github.com/ignite-ember/igni-sdk/blob/main/docs/YOUR_FIRST_EXTENSION.md)
from an empty directory to a tool the agent calls, a page, a hook and a
service. This README is the reference.

## Install

```bash
pip install igni-extension        # or: uv add igni-extension
```

Python 3.12 or later. The package depends on `mcp` 2, `httpx`,
`pydantic`, `pydantic-settings`, `anyio` and `websockets`.

Each release's wheels and sdists are also attached to igni-sdk's GitHub
release (`sdk-v<version>`), for a build machine that cannot reach PyPI.
See [Publishing the SDKs](https://github.com/ignite-ember/igni-sdk/blob/main/docs/PUBLISHING_THE_SDKS.md).

## Quick start

An extension is one module with one `IgniExtension` object. Each tool is a
decorated function:

```python
from igni_extension import IgniExtension, LocalNotification, Target, ToolHints

ext = IgniExtension("acme.example")   # the id in your manifest

READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)
WRITES = ToolHints(read_only=False, destructive=False, idempotent=False, open_world=False)


@ext.tool(hints=READS)
def word_count(text: str) -> int:
    """Count the words in a piece of text."""
    return len(text.split())


@ext.tool(hints=WRITES)
async def remind_me(text: str) -> str:
    """Leave the person a reminder in igni's notifications."""
    await ext.host.notifications.notify(
        LocalNotification(
            kind="reminder",
            title="Reminder",
            body=text,
            target=Target(page="acme.example"),
            event_key=f"reminder:{text}",
        )
    )
    return "Reminder left."


def main() -> None:   # the console script your manifest's `python.entry` names
    ext.run()
```

igni starts the process and calls `main()`. `ext.run()` serves igni over
stdio until igni closes the pipe.

You do not need igni to try it. `HostHarness` plays igni's side of the
connection in your own process:

<!-- continues -->
```python
from igni_extension.testing import HostHarness

async with HostHarness(ext) as host:
    counted = await host.call("word_count", {"text": "three short words"})
    reminded = await host.call("remind_me", {"text": "Ship the release"})
    [reminder] = await host.received(1)     # what the extension told igni

assert counted.content[0].text == "3"
assert reminded.content[0].text == "Reminder left."
assert reminder.body == "Ship the release"
```

To ship it, you describe the extension in its `manifest.json`, build a
bundle with `igni-service-bundle` (from `igni-service`), which writes the
tools and their hints into the manifest from your code when the manifest
leaves `permissions.tools` out (and checks them against your code when it
declares them), and let the backend service upload it. See
[Shipping the extension](#shipping-the-extension).

## Contents

- [Concepts](#concepts)
  - [How an extension reaches people](#how-an-extension-reaches-people)
  - [The process and its lifecycle](#the-process-and-its-lifecycle)
  - [Tools and their four hints](#tools-and-their-four-hints)
  - [One tool, five names](#one-tool-five-names)
  - [Callers: whom a call is for](#callers-whom-a-call-is-for)
  - [The host: igni as the extension sees it](#the-host-igni-as-the-extension-sees-it)
  - [Hooks: having a say](#hooks-having-a-say)
  - [Calling the backend service](#calling-the-backend-service)
  - [What the service sends: events and messages](#what-the-service-sends-events-and-messages)
  - [The sandbox and its network rules](#the-sandbox-and-its-network-rules)
- [Guides](#guides)
  - [Calling the service as the person](#calling-the-service-as-the-person)
  - [Driving and watching igni](#driving-and-watching-igni)
  - [Answering hooks](#answering-hooks)
  - [Handling service events](#handling-service-events)
  - [Background work, data and assets](#background-work-data-and-assets)
  - [Prompt conditions](#prompt-conditions)
  - [Staying awake in the cloud](#staying-awake-in-the-cloud)
  - [Plain functions run off the loop](#plain-functions-run-off-the-loop)
  - [Testing an extension](#testing-an-extension)
  - [Shipping the extension](#shipping-the-extension)
- [API reference](#api-reference)
  - [`IgniExtension`](#igniextension)
  - [`ToolHints`, `ToolHintsMissing`](#toolhints-toolhintsmissing)
  - [`ToolNames`, `ManifestTool`](#toolnames-manifesttool)
  - [`Caller`, `CallerKind`, `NoCaller`](#caller-callerkind-nocaller)
  - [`ServiceClient`, `SignedIn`](#serviceclient-signedin)
  - [`Host`, `Notifications`, `Property`, `Signal`, `SCHEMA_VERSION`](#host-notifications-property-signal-schema_version)
  - [`LocalNotification`, `Target`](#localnotification-target)
  - [`Hooks`, `HookEvent`, `Allow`, `Reject`, `Modify`](#hooks-hookevent-allow-reject-modify)
  - [`ServiceEvent`](#serviceevent)
  - [`PromptConditions`](#promptconditions)
  - [`ExtensionEnvironment`, `Workspace`, `WorkspaceMode`, `Secrets`, `Assets`, `HostEndpoint`](#extensionenvironment-workspace-workspacemode-secrets-assets-hostendpoint)
  - [Errors](#errors)
  - [`igni_extension.testing`](#igni_extensiontesting)
  - [`python -m igni_extension.manifest`](#python--m-igni_extensionmanifest)
  - [Environment variables](#environment-variables)
  - [Names kept from 0.1.0](#names-kept-from-010)
- [Troubleshooting and FAQ](#troubleshooting-and-faq)
- [Changes since 0.1.0](#changes-since-010)

## Concepts

### How an extension reaches people

The backend service uploads the signed extension bundle to igni server
when it starts. Two decisions then put the extension on a person's
device, and both are needed:

1. A **super admin approves the service** (igni's portal, *Services*).
2. An **org admin switches the extension on for a group** (portal,
   *Extensions*). Each person is in exactly one group.

Every signed-in igni of a person in that group then installs the
extension the next time it syncs with igni server. Approval alone installs
it nowhere.

The approval covers what the manifest declares: the tools and their
hints, the host objects the extension may use, the hooks it answers, the
hosts it may reach, what its service may send. A new version that asks
for more is held until a super admin approves it again.

### The process and its lifecycle

The igni backend on the device starts the extension's process from the
console script the manifest names. The process is an MCP server: igni
talks to it over the process's stdin and stdout. Alongside, the process
opens a WebSocket to the igni backend, on the loopback interface, for
everything else: the host's object model, signals, hooks and service
events.

`ext.run()` does all of this:

1. It checks that every tool states all four hints, and refuses to start
   (`ToolHintsMissing`) if one does not.
2. It connects to the host's socket and stays connected, so signals keep
   arriving. If the host is not answering yet, it tries again every two
   seconds.
3. It starts every `@ext.on_start` function in the background.
4. It serves MCP over stdio until igni closes the pipe.
5. It then cancels the background work, closes the socket and closes its
   HTTP clients.

Started from a terminal rather than by igni, `ext.run()` says so on
stderr — how to run it inside igni, and how to try a tool without it —
and then waits for MCP messages as usual.

Three silences in a row (a hook or a
tool call that raised or was too slow) make the extension *faulty*: igni
restarts it and stops waiting on its hooks until it answers again.

### Tools and their four hints

A tool is a function the agent (or the extension's own page) can call.
Every tool states MCP's four hints, because igni's permission modes
decide on them:

| Hint | Means |
|---|---|
| `read_only` | It changes nothing anywhere. |
| `destructive` | A change it makes can delete or overwrite something. `False` for a read. |
| `idempotent` | Calling it again with the same arguments changes nothing more. |
| `open_world` | It reaches beyond its own system: the web, another service, somebody else's data. |

Plan mode runs a read-only tool and refuses one that changes things.
Accept Edits runs a write that destroys nothing and stays inside its own
system. The default mode asks before any write. Bypass runs everything.
(igni-core's [`docs/EXTENSIBILITY.md`](https://github.com/ignite-ember/igni-core/blob/main/docs/EXTENSIBILITY.md) has the whole table.)

MCP makes each hint optional; igni does not. `ext.tool(hints=...)`
requires all four, and `ext.run()` refuses to start while any tool on
`ext.mcp` leaves one out. A tool you add with `ext.mcp.add_tool` passes
`annotations=hints.annotations()`.

A tool the agent calls is also listed in the manifest's
`permissions.tools`, with the same four:

```json
{ "name": "acme.example.summarise",
  "annotations": { "readOnlyHint": true, "destructiveHint": false,
                   "idempotentHint": true, "openWorldHint": false } }
```

The manifest's hints are the ones that count, because an administrator
approved them. igni compares them with what the process reports and
shows a difference in its extensions panel.

**Write them once.** Leave `permissions.tools` out of `manifest.json` and
`igni-service-bundle` writes it into the bundle from the code. List them
and it checks them against the code, refusing a difference. A tool the
code registers but the manifest does not list is never offered to the
agent — what you want for a tool only your page calls. To see what the
code implies, run `python -m igni_extension.manifest acme_example` (your
module), or call `ext.tools.manifest()`.

A tool that raises reaches the model as an error result whose text is
`Error executing tool <name>: ` and the exception's message. igni's `PostToolUse` hooks are not asked
about it, and `PostToolUseFailure` is told.

### One tool, five names

| Where | The name | Example (`acme.tickets`, `def lookup_ticket`) |
|---|---|---|
| Your code, `HostHarness.call`, `ConcurrentCall` | the function's name, or `name=` | `lookup_ticket` |
| The manifest's `permissions.tools`, the Services page | the extension's id, a dot, the tool | `acme.tickets.lookup_ticket` |
| A page's `bridge.rpc(...)`, and the `permissions.rpc` that grants it | `ext.`, then the manifest's name | `ext.acme.tickets.lookup_ticket` |
| igni: its permission rules, settings-file hooks, transcripts; a hook's `tool_name` | `mcp_ext:` + id + `_` + tool | `mcp_ext:acme.tickets_lookup_ticket` |
| What the model is sent | igni's name with every character a provider refuses made `_` | `mcp_ext_acme_tickets_lookup_ticket` |

The model's name is made at the provider boundary, because OpenAI's and
Anthropic's tool names allow only letters, digits, `_` and `-`. igni maps
the model's call back to its own name, so nothing you write ever sees it.

A hook is handed both of the names it may want: `tool_name`, igni's
(`read_file` for one of igni's own tools), and `tool_manifest_name`, the
manifest's (empty for igni's own). `ext.tools.names("lookup_ticket")`
answers the first four, and a decorated tool carries its manifest name as
`lookup_ticket.manifest_name`:

```python
from igni_extension import IgniExtension, ToolHints

ext = IgniExtension("acme.tickets")


@ext.tool(hints=ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False))
async def lookup_ticket(ticket_id: str) -> str:
    """Look up a support ticket."""
    return f"Ticket {ticket_id}: open"


names = ext.tools.names("lookup_ticket")
assert names.manifest == lookup_ticket.manifest_name == "acme.tickets.lookup_ticket"
assert names.rpc == "ext.acme.tickets.lookup_ticket"
assert names.registered == "mcp_ext:acme.tickets_lookup_ticket"
assert ext.tools.manifest()[0].wire()["annotations"]["readOnlyHint"] is True
```

### Callers: whom a call is for

Every call igni makes — a tool call, a page's call, a hook, a service
event — names whom it is for: a person (`kind="person"`, their `id`, their
`org` and the one `group` they belong to), an app (no group) or an app's
space (one end user of an app). The SDK reads it from the request.

A tool or hook handler that wants it declares a parameter typed `Caller`.
The SDK fills it in, and it is never part of the tool's input schema.
`Caller.current()` answers the same anywhere inside the call — in a
helper, or in a plain `def` running in a worker thread.

The extension never decides who may call it: igni forwards only calls the
caller may make, to extensions an org admin enabled for them. The
extension's job is to serve calls in parallel and keep callers apart. A
caller kept in a module global is the bug to avoid. `ConcurrencyHarness`
checks both (see [Testing an extension](#testing-an-extension)).

Work no caller started — `@ext.on_start` work, a reaction to a signal —
has no caller, and `ext.service` there is the person signed in to igni.

### The host: igni as the extension sees it

`ext.host` is the igni app as the extension sees it: the **host object
model** ([`docs/HOST_OBJECT_MODEL.md`](https://github.com/ignite-ember/igni-core/blob/main/docs/HOST_OBJECT_MODEL.md) in igni-core). There is one object per part
of the app — `ext.host.chat`, `ext.host.sessions`, `ext.host.ui`,
`ext.host.workspace` and so on — each with:

- **properties**, read with `await prop` and, when writable, written with
  `await prop.set(value)`;
- **signals**, handled with `@ext.on(signal)`, carrying a typed value;
- **methods**, which are `async` and return typed results.

An extension can do anything igni's own UI can do, and see everything
that happens in it, within its grants. **Every object needs its grant** in
the manifest's `permissions.host` (`"host": ["sessions", "chat.read",
"chat.post"]`); `host.workspace` is granted by `permissions.workspace`.
An object not granted raises `HostError` with `code == "not_granted"`, and
its signals never arrive.

`ext.host` travels on a loopback WebSocket igni gives the process
(`IGNI_HOST_URL`, `IGNI_HOST_SECRET`). Run outside igni, `ext.host`
raises `NotConfigured` — except `notifications.notify`, which then
travels as an MCP notification on the process's stdio connection, which
igni has always understood.

### Hooks: having a say

igni's hook events (`docs/HOOKS.md` in igni) are where an extension gets a
say before something happens, in one pipeline with igni's own
settings-file hooks.

Five events **decide** something. The handler answers `Allow()` (or
`None`), `Reject(reason)`, or `Modify(value)`:

| Event | When | A `Modify` may change |
|---|---|---|
| `Hooks.PRE_TOOL_USE` | a tool is about to run, before igni's own checks | `tool_args` |
| `Hooks.POST_TOOL_USE` | a tool succeeded, before the model reads its result | `result` |
| `Hooks.USER_PROMPT_SUBMIT` | a message is about to start a run | `message` |
| `Hooks.STOP` | the agent wants to end its turn | nothing (allow or reject) |
| `Hooks.PLAN_SUBMIT` | the agent is about to put a plan to the person | `plan` |

Every other event (`SESSION_START`, `SUBAGENT_STOP`, `PRE_COMPACT`,
`POST_TOOL_USE_FAILURE`, …) is only **told**: the handler hears it, and
what it returns is not read.

igni asks only about the events in the manifest's `permissions.hooks`
(`["PreToolUse", "PlanSubmit"]`). It asks extensions in the super admin's
priority order, each handed what the one before left, before igni's own
configured hooks. igni sets the deadline (two seconds) and decides what a
silence means: a handler that raises, or is too slow, has not answered.
A tool call or a message then does not go ahead; everything else does.
One handler per event.

### Calling the backend service

`ext.service` is an `httpx.AsyncClient` for the extension's own backend
service, as the person signed in to igni. Paths are relative to the
service.

The extension never holds the person's igni session. The igni backend
trades it for a short-lived token (about ten minutes) that is good for
this extension's service only, and hands it over on a loopback URL behind
a secret made for this process. The SDK keeps the token until 30 seconds
before it expires, attaches it to every request, and on a `401` from the
service fetches a fresh one and sends the request once more. On the
service side, `Depends(igni.person)` from `igni-service` checks it.

When nobody is signed in to igni, a request raises `NotSignedIn`. When
igni started the process without a service URL, `ext.service` raises
`NotConfigured` (and a page's `bridge.service.url` is `null` for the same
reason). An extension igni distributed always has one: the service that
shipped it. A development install has one only when it declares a
`serviceUrl` setting in `contributes.settings` and it is set; a
plain-`http` URL is given only for this machine (`localhost`), and only
with `IGNI_DEV_EXTENSIONS=1`.

### What the service sends: events and messages

The backend service reaches a producer's igni — on their desktop, or in
their Fleet VM, woken for it — two ways (igni server's
service-identity §15, igni-core's `docs/CLOUD.md` §6). A *producer* is a
person, an app or an app's space: whoever an igni runs for.

- **An event is the extension's** (`agent.send_event` in `igni-service`).
  igni hands it to the extension's `@ext.on_service_event(type)` handler
  and posts nothing. The handler does what it wants through its host
  calls, and the agent runs only if it posts.
- **A message is the agent's** (`agent.send_message`, `new_chat`,
  `chat(thread)` in `igni-service`). igni posts it exactly as sent,
  labelled as this extension's, in the chat its thread names or in this
  extension's own chat. No handler is asked, and the extension cannot
  rewrite, redirect or drop it. It sees it, as any post, on
  `chat.message_added`, with `from_extension` set to this extension's id
  and `from_service` to the service's client id. A post the extension made
  itself has `from_service` set to `None`.

The service sends a message when it knows what the agent should read, and
an event when the extension should decide.

What the service may send beyond a plain event, the extension declares in
its manifest:

```json
"permissions": {"service": ["messages", "attachments", "chats"]}
```

`messages` lets it post text, `attachments` send files, `chats` name
threads (each opens a chat), open chats and act on them. The super admin
approves them with the service, and igni server refuses the rest.

### The sandbox and its network rules

**The process is sandboxed to its grants.** igni starts it in an OS
sandbox written from its manifest — Seatbelt on macOS, bubblewrap on
Linux.

- **Network.** It reaches its own service and its `permissions.egress`
  hosts through igni's egress proxy, and nothing else. When the
  installation is air-gapped, only hosts inside the network. On macOS,
  services on this machine stay reachable.
- **Reading.** Its bundle, its runtime, its data directory and the
  workspace when granted — not the rest of the person's home.
- **Writing.** Its data directory, its temp directory, and the workspace
  when the grant is `write`.

On Windows it is not sandboxed yet. Where no sandbox is available it runs
unconfined with a warning — unless managed settings set
`extensions.require_sandbox`, which refuses it. `extensions.sandbox:
false` (managed or user settings) turns the sandbox off while you
develop.

The sandbox confines; it does not vouch. Approving the service is still
the decision to run its code, and an org admin switching the extension on
for a group is the decision to run it for those people.

Because the process cannot open files with other applications itself,
`ext.host.workspace.open(path)` asks igni to (documents only, within the
workspace grant), and `ext.host.app.open_external(url)` opens an
`https://` link in the person's browser.

## Guides

### Calling the service as the person

`ext.service` behaves like any `httpx.AsyncClient`. Catch `NotSignedIn`
where you can tell the person what to do. Here the service is played by
an `httpx.MockTransport`, and the igni backend's token endpoint by
`FakeHostTokenEndpoint`:

```python
import httpx

from igni_extension import IgniExtension, NotSignedIn, ToolHints
from igni_extension.testing import FakeHostTokenEndpoint, HostHarness


def documents_service(request: httpx.Request) -> httpx.Response:
    """The extension's backend service, as this example wants it to answer."""
    assert request.headers["authorization"].startswith("Bearer ")
    slug = request.url.path.split("/")[2]
    return httpx.Response(200, json={"summary": f"{slug}, in one line"})


host_tokens = FakeHostTokenEndpoint(user_id="u-ada", org_id="org-1", name="Ada")
ext = IgniExtension(
    "acme.example",
    environ=host_tokens.environment(),          # what igni would start the process with
    token_transport=host_tokens.transport,
    service_transport=httpx.MockTransport(documents_service),
)


@ext.tool(hints=ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False))
async def summarise(slug: str) -> str:
    """Summarise one of the organisation's documents."""
    try:
        response = await ext.service.get(f"/documents/{slug}/summary")
    except NotSignedIn:
        return "Sign in to igni to read documents."
    response.raise_for_status()
    return response.json()["summary"]


async with HostHarness(ext) as host:
    first = await host.call("summarise", {"slug": "runbook"})
    host_tokens.sign_out()                       # the person signs out of igni
    ext.tokens.invalidate()                      # (as if the kept token had expired)
    second = await host.call("summarise", {"slug": "runbook"})

assert first.content[0].text == "runbook, in one line"
assert second.content[0].text == "Sign in to igni to read documents."
assert ext.tokens.signed_in is None              # nobody, once igni says so
```

Three more ways to reach the same service:

- **`ext.service.anonymous`** — the same service with no token, for what
  anyone may read (a public link, a health check). It never asks the
  igni backend for a token, so it works when nobody is signed in:
  `await ext.service.anonymous.get(f"/v1/public/{slug}")`.
- **`ext.service.websocket(path)`** — a WebSocket to the service, opened
  with the person's token in its `Authorization` header:

  <!-- continues -->
  ```python
  import json

  @ext.on_start
  async def follow_room() -> None:
      async with ext.service.websocket("/v1/rooms/runbook") as room:
          await room.send(json.dumps({"hello": "room"}))
          async for frame in room:
              print(frame)
  ```

- **`ext.service.for_(caller)`** — the service as a specific caller. The
  token is fetched for them and kept apart from every other caller's. On
  a device serving one person, the igni backend gives that person's token
  and refuses anybody else's (`HostError`, code `refused`):

  <!-- continues -->
  ```python
  from igni_extension import Caller

  @ext.tool(hints=ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False))
  async def my_summary(slug: str, caller: Caller) -> str:
      response = await ext.service.for_(caller).get(f"/documents/{slug}/summary")
      return response.json()["summary"]
  ```

For a client none of these covers, `await ext.tokens.token()` is the token
itself. `ext.tokens.signed_in` says who the last token was for
(`user_id`, `org_id`, `email`, `name`), read from it *without checking
it*; it is `None` before the first token or once nobody is signed in. Use
it to show who is signed in and to notice that it changed; the service
checks the token, and this never decides anything. Whether anyone is
signed in to igni at all is `await ext.host.account.status` (with the
`account` grant).

### Driving and watching igni

<!-- continues -->
```python
from igni_extension.host_model import Run, SessionChange

@ext.on(ext.host.sessions.current_changed)
async def follow(change: SessionChange) -> None:
    busy = await ext.host.chat.processing            # read a property
    print(change, busy)

@ext.on(ext.host.chat.run_completed)                 # handle a signal
async def review(run: Run) -> None:
    if run.changed_files:
        await ext.host.chat.post("Two issues in the files you just changed.")

@ext.tool(hints=ToolHints(read_only=False, destructive=False, idempotent=True, open_world=False))
async def show_session(session_id: str, window_id: str) -> str:
    await ext.host.sessions.current.set(session_id)            # write a property
    await ext.host.windows.ui(window_id).navigate("plugins")   # any window
    return "shown"
```

- Registering the first handler of a signal subscribes to it on the
  host's socket. Handlers of one signal run in the order they were
  registered; one that raises is logged and does not stop the others. A
  handler may read and write the model while it runs.
- `ext.host.chat.post(text)` posts in the chat **labelled as the
  extension**; the agent is told who sent it and answers as usual.
  `ext.host.chat.append(view)` shows a json-render block that is never
  sent to the model, and returns its id for `chat.replace`.
- `ext.host.sessions.chat(session_id)` is the same chat for any session of
  the project, without switching what the person is looking at. A post
  there starts a run, or waits for the run already going, and never
  answers an approval. It needs `sessions.post` as well as `chat.post`
  (or `chat.append`):

  <!-- continues -->
  ```python
  @ext.on(ext.host.chat.run_completed)
  async def review_where_it_ran(run: Run) -> None:
      if run.changed_files:
          # The session the run was in, even if the person has moved on.
          chat = ext.host.sessions.chat(run.session_id)
          await chat.post("Two issues in the files you just changed.")
  ```

- `ext.host.agents.promote_ephemeral(name, target)` keeps an agent the
  orchestrator made for one task, as `/agents promote` does. `target` is
  `"project"` (the default — `.igni/agents/`, committed and the team's,
  `--project`) or `"personal"` (`.igni/agents.local/`, kept out of git,
  `--personal`). It needs the `agents` grant:

  <!-- continues -->
  ```python
  async def keep_for_me(name: str) -> None:
      await ext.host.agents.promote_ephemeral(name, target="personal")
  ```

- `await ext.host.notifications.notify(LocalNotification(...))` tells the
  person at this device something. It never leaves the device. igni opens
  `target` when it is clicked and shows a repeated `event_key` once. To
  tell *other* people, the backend service uses `host.notify` in
  `igni-service`.

`ext.host.ui` is the window the person last used: its page, panel,
sidebar, preview, selection, composer, toasts, dialog and scroll — the
same model igni's own views bind to. A write shows in the window, and
whatever the person does there is a signal. A dialog waits for the
person, with no timeout:

<!-- continues -->
```python
@ext.tool(hints=ToolHints(read_only=False, destructive=False, idempotent=False, open_world=False))
async def ship() -> str:
    answer = await ext.host.ui.show_dialog(
        {"title": "Ship it?", "buttons": [{"id": "yes", "label": "Ship", "primary": True}]}
    )
    if answer and answer["button"] == "yes":
        await ext.host.ui.toast("Shipping.", "success")
        return "shipped"
    return "not shipped"
```

`ext.host.decide(context, questions)` asks igni's local decision model
typed questions about a piece of text, on the device. Its accuracy is
modest: measure it on your own data before acting on an answer.

The [host object reference](#the-host-objects) lists every object.

### Answering hooks

<!-- continues -->
```python
from igni_extension import Hooks, Modify, Reject
from igni_extension.hooks import PlanSubmit, PreToolUse

@ext.hook(Hooks.PLAN_SUBMIT)
async def grounded(plan: PlanSubmit) -> Reject | None:
    if plan.attempt < 2 and plan.plan.count("src/") < 2:
        return Reject("Cite the files the plan changes.")   # back to the agent
    return None                                             # allowed

@ext.hook(Hooks.PRE_TOOL_USE)
async def quieter(call: PreToolUse) -> Modify | None:
    if call.tool_name == "run_shell_command":
        command = call.tool_args.get("command", "") + " --quiet"
        return Modify(call.model_copy(update={"tool_args": {**call.tool_args, "command": command}}))
    return None
```

- `Reject(reason)`: the reason reaches the agent or the person, so write
  it for them.
- `Modify(value)`: the whole value, with only the fields the event lets
  it change changed (`model_copy(update=...)` is the easy way).
- A handler may take a second parameter typed `Caller` to be handed whom
  the event is for.
- A handler that raises is reported to igni as *failed*, with the
  exception's message, and counts as a silence.
- Asked about an event nothing here hooks, the SDK allows it and logs a
  warning: add a handler, or take it out of `permissions.hooks`.

Test a hook with `FakeHost.hook` (see [Testing an extension](#testing-an-extension)).

### Handling service events

<!-- continues -->
```python
from igni_extension import ServiceEvent

@ext.on_service_event("index.ready")
async def index_ready(event: ServiceEvent) -> None:
    repo = event.payload["repo"]
    created = await ext.host.sessions.create(title=f"Index: {repo}")
    await ext.host.sessions.chat(created.session_id).post(
        f"The index for {repo} is ready; review the open changes."
    )
```

`sessions.create` returns the new session (`created.session_id`) and moves
no window, so the person stays where they are. The title shows in their
session list at once, and no auto-name replaces it. Pass `focus=True` to
show it in the caller's window instead. Creating needs the `sessions`
grant; posting into a session that is not on screen needs `sessions.post`
as well as `chat.post`:

```json
"permissions": {"host": ["sessions", "chat.post", "sessions.post"]}
```

- `@ext.on_service_event()` with no type takes every type no other
  handler names. One handler per type.
- An event with no handler for its type, one that reaches no running
  extension, or one whose handler raises is *not handled*: the service
  reads `not_handled`, with the reason, when it polls.
- igni waits up to 10 seconds, so keep the handler quick. Delivery is at
  least once, and igni drops a repeat by `event_id`.
- A handler returns nothing. What it wants posted, it posts through
  `ext.host.sessions`.

To see the messages the service sends (rather than events), watch the
chat:

<!-- continues -->
```python
from igni_extension.host_model import ChatMessage

@ext.on(ext.host.chat.message_added)
async def seen(message: ChatMessage) -> None:
    if message.from_service is not None:
        print("the service sent it, as a message item:", message)
```

### Background work, data and assets

Work the extension does for as long as it runs — a sync loop, a process
it starts — goes in `@ext.on_start`. It starts with `ext.run()` and is
cancelled when igni closes the extension, so it cleans up in its own
`finally`. An exception it raises does not stop the extension; it is
logged when the process stops. A plain `def` runs in a worker thread and
cannot be cancelled: it ends with the process.

<!-- continues -->
```python
import asyncio

class Index:  # your own work
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

index = Index()


@ext.on_start
async def follow_head() -> None:
    try:
        await index.start()
        await asyncio.Event().wait()
    finally:
        await index.stop()
```

igni provides no database, vector store or model to extensions. What one
keeps on this device goes in `ext.environment.data_dir`
(`IGNI_EXTENSION_DATA`): a directory that is this extension's alone and
survives reinstalls and updates of its bundle. It is `None` outside igni.

What it *runs* that is not Python — a database, a JVM, a model — it ships
as `assets` in its manifest, so it installs with no network. igni checks
each against the digest the signed manifest pins and lays it out
read-only, one directory per asset, under `IGNI_EXTENSION_ASSETS`:

<!-- continues -->
```python
@ext.on_start
def where_things_are() -> None:
    neo4j_home = ext.assets.path("neo4j")                 # an unpacked archive
    model = ext.assets.file("minilm", "model.onnx")       # one file, as shipped
    print(neo4j_home, model)
```

Both raise `NotConfigured` for a name igni did not lay out — one the
manifest does not declare, or a process running outside igni:

<!-- continues -->
```python
from pathlib import Path

from igni_extension import Assets, NotConfigured

Path("assets/minilm").mkdir(parents=True)
Path("assets/minilm/model.onnx").write_bytes(b"onnx")
assets = Assets(root=Path("assets"))           # what igni lays out

assert assets.file("minilm", "model.onnx").read_bytes() == b"onnx"
try:
    assets.path("neo4j")
except NotConfigured as error:
    print(error)                               # no asset named 'neo4j' was laid out at assets
```

Each secret the manifest declares and the deployment supplies arrives as
`IGNI_SECRET_<NAME>`; read it with `ext.environment.secrets.get("ledger-token")`.

### Prompt conditions

A manifest's `contributes.prompt` overrides a prompt — the main prompt,
plan mode, any agent — with a whole one of its own, or edits it: appends
a section, inserts one before or after a named section, replaces a named
section (an agent's header is the section `frontmatter`). Each may hold
only while a condition holds (`"when": "index-covers-head"`). The rules —
what stacks, what collides, what an override leaves out — are in igni's
[`docs/EXTENSIBILITY.md`](https://github.com/ignite-ember/igni-core/blob/main/docs/EXTENSIBILITY.md). Only the extension can judge the condition, so it
says when it changes:

<!-- continues -->
```python
await ext.prompt.hold("index-covers-head", True)
await ext.prompt.set({"index-covers-head": False, "signed-in": True})
assert ext.prompt.holding == {"index-covers-head": False, "signed-in": True}
```

igni rebuilds the agent with the prompt as it now is. The message travels
on the process's own MCP connection (`notifications/igni/conditions`), so
an extension only ever speaks for its own conditions. It works before
igni has finished connecting (up to 100 messages are held until then), and
only what changed is sent. Nothing holds until it is said, and nothing
survives a restart: say it again when the process starts. A condition
name is lower case letters, digits and `-`, starting with a letter; at
most 64 go in one message.

Text a contribution takes from a tool (`"source": "tool"`) is fetched when
the extension starts, and so is a `promptFragments` anchor's. When what it
says changes — CodeIndex's project map, when HEAD moves to another indexed
commit — have igni fetch it again:

<!-- continues -->
```python
await ext.prompt.refresh()
```

### Staying awake in the cloud

In the cloud, igni's VM sleeps when nothing is busy. Work your process
does on its own — indexing, a sync — says so:

<!-- continues -->
```python
async def index_everything() -> None: ...   # your own work


@ext.on_start
async def keep_indexing() -> None:
    async with ext.busy.during("indexing"):
        await index_everything()
```

`ext.busy.take(reason, ttl)` takes a lease (at most 600 s) and renews it
when called again; `ext.busy.release(reason)` lets it go; `during` does
both and renews every half `ttl` in between. A lease nobody renews
expires, so a stuck process cannot keep the VM up. A failed renewal or
release inside `during` is logged rather than raised, so it never hides
what the block itself raised. Leases show in `ext.host.app.activity`.

### Plain functions run off the loop

The process serves igni on one event loop. A plain `def` you hand the SDK
— a tool, a hook handler, a reaction (`@ext.on`), a service event handler,
background work (`@ext.on_start`) — runs in a worker thread, so a slow one
never holds the calls that arrive meanwhile. An `async def` is called as
it is. A tool's schema is `mcp`'s, from the function as you wrote it.

Two things this does not do: blocking inside an `async def` still holds
the loop, and threads share the GIL — CPU-heavy work belongs in a process
pool you run (`concurrent.futures.ProcessPoolExecutor`). The thread pool
is anyio's default (40 threads). It is your process, so change it if you
need to:

<!-- continues -->
```python
import anyio.to_thread

anyio.to_thread.current_default_thread_limiter().total_tokens = 8
```

### Testing an extension

`igni_extension.testing` plays igni's side in your own process. No igni,
no network.

**One tool, as igni calls it.** `HostHarness(ext)` is igni's side of the
MCP session `ext.run()` serves. `host.call(tool, args, caller=...)` calls
one tool for one caller. Build a `Caller` per person the test plays:

```python
import json

from igni_extension import Caller, CallerKind, IgniExtension, ToolHints
from igni_extension.testing import ConcurrencyHarness, ConcurrentCall, HostHarness

ext = IgniExtension("acme.example")
READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)


@ext.tool(hints=READS)
async def mine(caller: Caller) -> str:
    return json.dumps({"for": caller.id})


ada = Caller(kind=CallerKind.PERSON, id="u-ada", org="org-1", group="g-engineering")
grace = Caller(kind=CallerKind.PERSON, id="u-grace", org="org-1", group="g-engineering")

async with HostHarness(ext) as host:
    result = await host.call("mine", {}, caller=ada)
    no_caller = await host.call("mine", {})
assert json.loads(result.content[0].text) == {"for": "u-ada"}
assert no_caller.is_error                     # `caller: Caller` needs one; `Caller | None` would not
```

**Many callers at once.** `ConcurrencyHarness(ext).run([...])` makes every
call concurrently, each as its own caller, and raises `ConcurrencyProblem`
if the event loop was held longer than `stall_limit` (0.1 s), or if a
tool saw a caller other than the one its call was sent with:

<!-- continues -->
```python
report = await ConcurrencyHarness(ext).run([
    ConcurrentCall(tool="mine", caller=ada),
    ConcurrentCall(tool="mine", caller=grace),
])
assert report.results[0].result != report.results[1].result
assert report.leaks == []
```

**Its service, and what it tells igni.** `FakeHostTokenEndpoint` hands out
tokens the way the igni backend does, and answers as igni does when nobody
is signed in (`sign_out()`). Give the extension your service as an
`httpx.MockTransport` (as in
[Calling the service as the person](#calling-the-service-as-the-person)).
`HostHarness` records every notification the extension sends
(`host.notifications`, `await host.received(n)`) and every prompt
condition it says (`host.conditions`, `await host.conditions_said(n)`).

Its tokens are unsigned JWTs of the person's claims. To test against a
service that checks signatures — one built on `igni-service`, with its
`FakeIgni` — pass `minter`. It is given the person's `TokenClaims` and
returns the token to hand out. This needs `igni-service` installed beside
`igni-extension`, so the block below is only compiled here:

<!-- illustrative -->
```python
from igni_extension.testing import FakeHostTokenEndpoint
from igni_service.testing import FakeIgni

igni = FakeIgni()
host_tokens = FakeHostTokenEndpoint(
    minter=lambda claims: igni.signer.person_token(claims.sub, org_id=claims.org)
)
```

**Token renewal.** Pass a `ManualClock` to move time by hand:

```python
from igni_extension import IgniExtension
from igni_extension.testing import FakeHostTokenEndpoint, ManualClock

clock = ManualClock()
host_tokens = FakeHostTokenEndpoint(expires_in=600)
ext = IgniExtension(
    "acme.example",
    environ=host_tokens.environment(),
    token_transport=host_tokens.transport,
    clock=clock,
)

first = await ext.tokens.token()
clock.advance(500)
assert await ext.tokens.token() == first      # still fresh
clock.advance(80)                              # within 30 s of expiry
assert await ext.tokens.token() != first      # renewed
assert len(host_tokens.issued) == 2
await ext.aclose()
```

**The host.** `FakeHost` is igni's host object model on a loopback socket,
speaking the protocol igni speaks. You decide what it answers:

```python
import asyncio

from igni_extension import HostError, IgniExtension
from igni_extension.host_model import Run
from igni_extension.testing import FakeHost, HostCall

async with FakeHost(
    values={"chat.processing": False},
    answers={"chat.post": None},
    refusals={"mcp.servers": ("not_granted", "acme.example is not granted 'mcp'")},
) as host:
    ext = IgniExtension("acme.example", environ=host.environment())

    @ext.on(ext.host.chat.run_completed)
    async def review(run: Run) -> None:
        if run.changed_files:
            await ext.host.chat.post(f"I read {', '.join(run.changed_files)}.")

    assert await ext.host.chat.processing is False
    try:
        await ext.host.mcp.servers
    except HostError as error:
        assert error.code == "not_granted"

    await ext.connect()
    await host.wait_subscribed("chat.run_completed")
    await host.emit(
        "chat.run_completed",
        {"session_id": "s-1", "run_id": "r-1", "parent_run_id": "", "input_tokens": 10,
         "output_tokens": 5, "reasoning_tokens": 0, "duration": 1.5,
         "changed_files": ["auth.py"]},
    )                                               # your handler runs
    posted = HostCall(op="call", path="chat.post", params={"text": "I read auth.py."})
    for _ in range(100):
        if posted in host.calls:
            break
        await asyncio.sleep(0.01)
    await ext.aclose()

assert posted in host.calls                        # everything the extension asked
```

**Hooks and service events.** `FakeHost.hook(event, value, caller=...)`
asks the connected extension about a deciding event as igni does, and
returns its answer as it crossed the wire. A service event is asked the
same way, under the event name `"ServiceEvent"`. `FakeHost.tell(event,
value)` tells it an event that decides nothing.

```python
from igni_extension import Hooks, IgniExtension, Reject, ServiceEvent
from igni_extension.hooks import PlanSubmit
from igni_extension.testing import FakeHost

async with FakeHost() as host:
    ext = IgniExtension("acme.example", environ=host.environment())
    seen: list[ServiceEvent] = []

    @ext.hook(Hooks.PLAN_SUBMIT)
    async def grounded(plan: PlanSubmit) -> Reject | None:
        return None if "src/" in plan.plan else Reject("Name the files the plan changes.")

    @ext.on_service_event("index.ready")
    async def ready(event: ServiceEvent) -> None:
        seen.append(event)

    await ext.connect()
    answer = await host.hook("PlanSubmit", {"session_id": "s-1", "plan": "Refactor it."})
    handled = await host.hook(
        "ServiceEvent", {"event_id": "evt-1", "type": "index.ready", "payload": {"repo": "acme/api"}}
    )
    unknown = await host.hook("ServiceEvent", {"event_id": "evt-2", "type": "build.failed"})
    await ext.aclose()

assert answer["outcome"] == "reject" and answer["reason"] == "Name the files the plan changes."
assert handled["outcome"] == "allow" and seen[0].payload == {"repo": "acme/api"}
assert unknown["outcome"] == "reject"                      # not handled: no handler for its type
```

### Shipping the extension

The extension is a Python package with a console script, a `manifest.json`
and, usually, a page. Its `pyproject.toml` names the script that calls
`ext.run()`:

```toml
[project.scripts]
acme-tickets-extension = "acme_tickets_extension:main"
```

and the manifest's `python` section names the package and that script:

```json
"python": {
  "package": "acme-tickets-extension",
  "entry": "acme-tickets-extension",
  "wheels": "wheels",
  "mcp": {"transport": "stdio"}
}
```

Then, from `igni-service`:

```bash
igni-service-bundle --extension extension --out extension-bundle.tar.gz
```

builds the bundle: the manifest (with `permissions.tools` written from the
code when you left it out, or checked against the code when you did not),
the extension's wheel and a wheelhouse of every dependency for each
platform. The backend service uploads it at start-up. The full manifest,
the page and the service are in
[Your first extension](https://github.com/ignite-ember/igni-sdk/blob/main/docs/YOUR_FIRST_EXTENSION.md);
the bundle's options are in
[igni-service's README](https://github.com/ignite-ember/igni-sdk/blob/main/packages/igni-service/README.md).

During development, `IGNI_DEV_EXTENSIONS=1 igni ext install <dir>`
installs it into your own igni as a development install.

## API reference

Everything below is importable from `igni_extension` unless another
module is named.

### `IgniExtension`

```text
IgniExtension(
    extension_id: str,
    *,
    instructions: str | None = None,
    environ: Mapping[str, str] | None = None,
    token_transport: httpx.AsyncBaseTransport | None = None,
    service_transport: httpx.AsyncBaseTransport | None = None,
    clock: Clock | None = None,
)
```

One extension's process: its tools, its service and the host. Make one per
process, at module level, so `python -m igni_extension.manifest` and
`igni-service-bundle` can find it.

| Parameter | Meaning |
|---|---|
| `extension_id` | The manifest's `id` (`"acme.tickets"`). Tool names are derived from it. An empty id raises `ValueError`. |
| `instructions` | Text for the MCP server's `instructions`, sent to igni when it connects. |
| `environ` | Where to read igni's variables from. `None` reads `os.environ`. Tests pass `FakeHost.environment()` or `FakeHostTokenEndpoint.environment()`. |
| `token_transport` | The `httpx` transport for requests to the igni backend's token endpoint. Tests pass `FakeHostTokenEndpoint.transport`. |
| `service_transport` | The `httpx` transport for requests to the backend service. Tests pass an `httpx.MockTransport`. |
| `clock` | Measures a token's age. Tests pass `testing.ManualClock`. |

The environment is read once, in the constructor.

**Attributes**

| Attribute | What it is |
|---|---|
| `ext.id` | The extension id. |
| `ext.environment` | The `ExtensionEnvironment` igni started the process with. |
| `ext.assets` | `ext.environment.assets`: what the extension ships for this platform. |
| `ext.host` | The `Host`: igni as the extension sees it. |
| `ext.service` | The `ServiceClient` for the backend service, as the signed-in person. Raises `NotConfigured` without `IGNI_SERVICE_URL`. |
| `ext.tokens` | The person's tokens for the service: `await ext.tokens.token()`, `ext.tokens.signed_in`, `ext.tokens.invalidate()`, `ext.tokens.for_(caller)`. |
| `ext.tools` | The tool registry: `names(tool)`, `manifest()`, `await check()`, `observing(observer)`. |
| `ext.prompt` | `PromptConditions`: which of its prompt conditions hold. |
| `ext.busy` | Busy leases: `take(reason, ttl)`, `release(reason)`, `during(reason, ttl)`. |
| `ext.mcp` | The underlying `mcp` `MCPServer`, for what the decorators do not cover (`ext.mcp.add_tool`, resources, prompts). |
| `ext.signals` | The `SignalHandlers` `@ext.on` registered into: list them, or run them in a test. See [`ext.signals`](#extsignals). |
| `ext.process` | The `ExtensionProcess` `run()` serves; `await ext.process.serve(read, write)` serves one MCP session over streams you hold. See [`ext.process`](#extprocess). |
| `ext.connection` | The `HostConnection`, the socket to the host: whether there is one, what it granted. You rarely need it. See [`ext.connection`](#extconnection). |

**`@ext.tool(*, hints, name=None, description=None)`**

Registers a function as a tool igni can call. Returns the function
unchanged, with `manifest_name` set on it.

- `hints` (`ToolHints`, required) — what the tool is.
- `name` — the tool's name; defaults to the function's name.
- `description` — defaults to the function's docstring.

The input schema comes from the function's parameters. A parameter typed
`Caller` (or `Caller | None`) is filled from the call and left out of the
schema. A plain `def` runs in a worker thread. An exception the tool
raises reaches igni, and the model, as an error result whose text is
`Error executing tool <name>: ` and the exception's message.

**`@ext.on(signal)`**

Handles a host signal, such as `ext.host.chat.run_completed`. The handler
receives the signal's typed value and returns nothing. igni never waits on
it. Several handlers per signal are allowed.

**`@ext.hook(event)`**

Answers one of igni's hook events, `event` being a member of `Hooks`. On
a deciding event the handler returns `Allow()`, `Reject(reason)`,
`Modify(value)` or `None` (allow); on any other it is only told. Raises
`ValueError` if the event already has a handler.

**`@ext.on_service_event(event_type=None)`**

Handles events the backend service sends, of one `type`, or of every type
no other handler names when `event_type` is `None`. The handler receives a
`ServiceEvent` and returns nothing. Raises `ValueError` if the type
already has a handler.

**`@ext.on_start`**

Runs the function (taking no arguments) in the background for as long as
`run()` serves igni. Returns the function unchanged.

**`ext.run() -> None`**

Serves igni over stdio until it closes the pipe. Blocks. Raises
`ToolHintsMissing` before serving if a tool leaves a hint unstated.

**`await ext.connect() -> None`**

Connects to the igni backend's socket now rather than on the first
`ext.host` call, and subscribes to the signals that have handlers. `run()`
does this itself; a test or script that drives the extension without
`run()` calls it so that signals, hooks and service events arrive.
Idempotent. Raises `HostUnavailable` if the host does not answer.

**`await ext.aclose() -> None`**

Closes the socket and the HTTP clients. `run()` calls it on the way out;
call it yourself after `connect()` in a test.

#### `ext.signals`

```text
ext.signals -> SignalHandlers
```

The handlers `@ext.on` registered, by signal. The host's socket
subscribes to the signals it holds and delivers into it. A test can run
the handlers itself, with no host at all.

| Member | What it does |
|---|---|
| `wires() -> list[str]` | Every handled signal, by wire name (`"session.switched"`), sorted. This is what the socket subscribes to. |
| `handlers(signal) -> list` | One signal's handlers, in registration order. Empty when it has none. |
| `await emit(signal, value)` | Runs the signal's handlers with a typed `value`, in registration order, as a delivery from the host does. A handler that raises is logged, and the others still run. |
| `await deliver(wire, raw)` | The same from the wire name and the JSON value the host sends, parsed into the signal's type first. A signal nobody handles is ignored. A value that does not parse is logged and skipped. |
| `on(signal)` | What `@ext.on(signal)` does. |

```python
from igni_extension import IgniExtension
from igni_extension.host_model import SessionChange

ext = IgniExtension("acme.example")
followed: list[str] = []


@ext.on(ext.host.sessions.current_changed)
async def follow(change: SessionChange) -> None:
    followed.append(change.session_id)


assert ext.signals.wires() == ["session.switched"]
await ext.signals.emit(ext.host.sessions.current_changed, SessionChange(session_id="s-2"))
await ext.signals.deliver("session.switched", {"session_id": "s-3"})
assert followed == ["s-2", "s-3"]
```

#### `ext.connection`

```text
ext.connection -> HostConnection
```

The WebSocket to the igni backend that `ext.host`, signals, hooks and
service events travel on. igni starts the process with `IGNI_HOST_URL`
and `IGNI_HOST_SECRET`, which say where it is. `run()` keeps it open,
and the first `ext.host` call opens it, so an extension rarely needs it.

| Member | What it is |
|---|---|
| `configured` | Whether igni gave the process the host's address. `False` outside igni: then `ext.host` reaches igni only through `notifications.notify`. |
| `connected` | Whether the socket is open now. |
| `granted` | Once connected, the `permissions.host` grants the host says this extension holds. Empty before. |
| `schema_version` | Once connected, the version of the host's object model. Empty before. |
| `await connect()` | What `ext.connect()` does: connects and subscribes to every handled signal. Idempotent. Raises `HostUnavailable`. |
| `await serve_forever()` | Stays connected, connecting again every two seconds after the host goes away, until cancelled. Returns at once when not `configured`. `run()` runs it; run it as a task in a test that needs signals, hooks and service events to keep arriving. |
| `await close()` | Closes the socket. `ext.aclose()` calls it. |

Its other methods are the SDK's own wire to the host. Use `ext.host`.

```python
from igni_extension import IgniExtension
from igni_extension.testing import FakeHost

assert not IgniExtension("acme.example", environ={}).connection.configured

async with FakeHost(granted=("chat.read", "sessions")) as host:
    ext = IgniExtension("acme.example", environ=host.environment())
    assert ext.connection.configured and not ext.connection.connected
    await ext.connect()
    assert ext.connection.connected
    assert ext.connection.granted == ["chat.read", "sessions"]
    await ext.aclose()
```

#### `ext.process`

```text
ext.process -> ExtensionProcess
```

What `ext.run()` serves: the MCP server, the host's socket beside it, and
the `@ext.on_start` work.

| Member | What it does |
|---|---|
| `run()` | What `ext.run()` does: checks the tools' hints, then serves MCP over stdio until igni closes the pipe, with the host's socket open and every `on_start` function running; on the way out, cancels them and calls `ext.aclose()`. |
| `await serve(read_stream, write_stream)` | Checks every tool's hints (raising `ToolHintsMissing`), then serves one MCP session over the streams until they close. It does not connect to the host or start the `on_start` work. |
| `on_start(fn)` | What `@ext.on_start` does. |

`HostHarness` serves this way, and is the usual way to call a tool in a
test. `serve` is for an MCP client of your own, or a program that embeds
the extension:

```python
import anyio
from mcp import ClientSession

from igni_extension import IgniExtension, ToolHints

ext = IgniExtension("acme.example", environ={})


@ext.tool(hints=ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False))
def ping() -> str:
    """Answer pong."""
    return "pong"


to_server, server_reads = anyio.create_memory_object_stream(16)
server_writes, to_client = anyio.create_memory_object_stream(16)
async with anyio.create_task_group() as tasks:
    tasks.start_soon(ext.process.serve, server_reads, server_writes)
    async with ClientSession(to_client, to_server) as session:
        await session.initialize()
        assert [tool.name for tool in (await session.list_tools()).tools] == ["ping"]
    tasks.cancel_scope.cancel()
```

### `ToolHints`, `ToolHintsMissing`

```text
ToolHints(*, read_only: bool, destructive: bool, idempotent: bool, open_world: bool)
```

A frozen pydantic model. All four are required. `read_only=True` with
`destructive=True` raises `pydantic.ValidationError` ("a read-only tool
cannot also be destructive").

- `hints.annotations() -> mcp.types.ToolAnnotations` — the hints as MCP
  lists them; pass it to `ext.mcp.add_tool(..., annotations=...)`.
- `hints.wire() -> dict[str, bool]` — as a manifest spells them:
  `{"readOnlyHint": ..., "destructiveHint": ..., "idempotentHint": ..., "openWorldHint": ...}`.

`ToolHintsMissing(tools: list[str])` is raised by `ext.run()` and
`await ext.tools.check()` when a tool on `ext.mcp` leaves a hint unstated.
`error.tools` names them, and the message says how to fix it.

```python
from igni_extension import IgniExtension, ToolHints, ToolHintsMissing

ext = IgniExtension("acme.example")


def legacy(query: str) -> str:
    return query


ext.mcp.add_tool(legacy)                     # no annotations: refused
try:
    await ext.tools.check()
except ToolHintsMissing as error:
    assert error.tools == ["legacy"]

hints = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)
ext.mcp.remove_tool("legacy")
ext.mcp.add_tool(legacy, annotations=hints.annotations())
await ext.tools.check()                      # all four stated
```

### `ToolNames`, `ManifestTool`

`ext.tools.names(tool) -> ToolNames` gives every name a registered tool
goes by. Raises `KeyError` for a tool the extension does not register
(the message lists the ones it does). `ToolNames.of(extension_id, tool)`
builds the same without an extension.

| Field | Example |
|---|---|
| `tool` | `lookup_ticket` |
| `manifest` | `acme.tickets.lookup_ticket` |
| `rpc` | `ext.acme.tickets.lookup_ticket` |
| `registered` | `mcp_ext:acme.tickets_lookup_ticket` |

`ext.tools.manifest() -> list[ManifestTool]` is `permissions.tools` as the
code states it, sorted by tool name: each a `ManifestTool` with `name`
(the manifest name) and `annotations`. `line.wire()` is the line as JSON
spells it. It lists only tools registered with `ext.tool`; a tool added
on `ext.mcp` directly is declared in the manifest by hand.

### `Caller`, `CallerKind`, `NoCaller`

```text
Caller(*, kind: CallerKind, id: str, org: str | None = None, group: str | None = None,
       session: str | None = None, app: str | None = None, external_id: str | None = None)
```

A frozen pydantic model: the producer one call is for.

| Field | Meaning |
|---|---|
| `kind` | `CallerKind.PERSON`, `CallerKind.APP` or `CallerKind.SPACE` (one end user of an app). |
| `id` | The person's or the app's id on igni server. |
| `org` | Their organisation. |
| `group` | The one group a person belongs to in `org`; an app has none. |
| `session` | The igni session the call comes from, when there is one. |
| `app` | A space's app id; `None` for a person or an app. |
| `external_id` | The app's own name for a space's end user. |

- `caller.ref -> str` — `"person:u-ada"`: how the token endpoint is told
  whom a token is for.
- `Caller.current() -> Caller | None` — the caller of the call being
  served now; `None` outside one.
- `Caller.required() -> Caller` — the same, or raises `NoCaller`.
- `Caller.of(raw) -> Caller | None` — a caller from a wire dict; `None`
  when missing or malformed.

`CallerKind` is a `StrEnum` (`"person"`, `"app"`, `"space"`).

`NoCaller` (a `LookupError`) is raised by `Caller.required()`, and so by a
tool declaring `caller: Caller` that igni called without one — in
`on_start` work, say, or from a test that passed no `caller=`. Declare
`caller: Caller | None` to run with `None` instead.

### `ServiceClient`, `SignedIn`

`ServiceClient` is the type of `ext.service`: an `httpx.AsyncClient` with
`base_url` set to the service, a 30-second timeout, and an auth flow that
attaches the person's token and retries once on a `401`. Use every
`httpx.AsyncClient` method (`get`, `post`, `request`, `stream`, …).

| Member | What it does |
|---|---|
| `for_(caller) -> ServiceClient` | The same service as `caller`, with tokens fetched for that caller and kept apart. One client per caller, reused. |
| `anonymous -> httpx.AsyncClient` | The same service with no token. Never asks for one. |
| `websocket(path, **options)` | An async context manager that opens a WebSocket to `path` (`https` becomes `wss`) with the person's token, and yields a `websockets` `ClientConnection`. `options` go to `websockets.asyncio.client.connect`. |

A request raises:

- `NotSignedIn` — nobody is signed in to igni (the token endpoint answered `503`);
- `HostError` with code `refused` — the igni backend will not give a token for that caller (`403`);
- `HostUnavailable` — the token endpoint did not answer, or answered something else;
- `NotConfigured` — igni gave the process no token endpoint (`IGNI_SERVICE_TOKEN_URL`, `IGNI_SERVICE_TOKEN_SECRET`);
- any `httpx` error for the request itself. A non-2xx answer from your
  service is returned, not raised; call `response.raise_for_status()`.

`SignedIn` (from `ext.tokens.signed_in`) is a frozen model with `user_id`,
`org_id`, `email` and `name`, read from the last token's claims without
checking its signature. `SignedIn.of(token)` reads any token; an
unreadable one gives empty fields.

### `Host`, `Notifications`, `Property`, `Signal`, `SCHEMA_VERSION`

`Host` is the type of `ext.host`. `Notifications` is the type of
`ext.host.notifications` (`HostNotifications`, under the name it had
before the model was generated).

`Property[T]` is one value of a host object:

- `await prop` or `await prop.get() -> T` — read it, typed.
- `await prop.set(value)` — write it, as the person's UI would; refused
  where theirs would be. Raises `TypeError` for a read-only property.
- `prop.path`, `prop.writable`.

`Signal[T]` is one signal of a host object. Pass it to `@ext.on`.
`signal.name` is its wire name (`chat.run_completed`; for four older
events the topic strings `session.switched`, `workspace.head-changed`,
`workspace.files-changed`, `extension.state-changed`).

`SCHEMA_VERSION` is the host schema version `igni_extension.host_model`
was generated from (currently `"1.13.0"`). `igni_extension.host_model`
also holds every value type the model uses (`Run`, `SessionChange`,
`ChatMessage`, `Approval`, …), as pydantic models that accept extra
fields.

Every host call can raise `HostError` (igni refused or failed it),
`HostUnavailable` (the socket is down or a request got no answer in 120
seconds; dialogs wait indefinitely), or `NotConfigured` (no socket).

#### The host objects

Each object needs the matching grant in `permissions.host`. igni's
[`docs/HOST_OBJECT_MODEL.md`](https://github.com/ignite-ember/igni-core/blob/main/docs/HOST_OBJECT_MODEL.md) describes every member in full.

| Object | What it is | Some members |
|---|---|---|
| `host.app` | The igni app | `display`, `version`, `connection`, `activity`, `update_available`; `set_verbose`, `set_output_style`, `check_for_update`, `open_external(url)` |
| `host.app.state` | Key–value state of the extension's own, kept across restarts | `values`; `get`, `set`, `delete`; `changed` |
| `host.windows` | Every open igni window | `list`, `focused`; `ui(window_id)`; `opened`, `closed`, `focus_changed` |
| `host.ui` | The window the person last used | `route`, `panel`, `sidebar`, `preview`, `selection`, `composer` (writable), `toasts`, `dialog`, `scroll`; `navigate`, `back`, `open_panel`, `open_preview`, `select`, `set_composer`, `toast`, `show_dialog`, `scroll_to`; a signal per change |
| `host.sessions` | The project's sessions | `list`, `current` (writable); `open`, `create`, `attach`, `chat(session_id)`; `current_changed`, `listed`, `cleared`, `named` |
| `host.chat` | The conversation in the current session | `session_id`, `messages`, `pending`, `processing`, `status`, `context`; `post`, `queue`, `append`, `replace`, `search`, `cancel`, `cancel_agent`, `truncate`, `compact`, `upload`; `message_added`, `run_started`, `run_completed`, `run_error`, `tool_started`, `tool_completed`, `file_edited`, … |
| `host.chat.approvals` | The agent asking to act | `waiting`; `answer`, `answer_all`; `requested`, `resolved`, `changed` |
| `host.chat.views` | json-render views in the chat | `list`; `dispatch`; `shown`, `action` |
| `host.plan` | Plan mode | `latest`; `approve`, `dismiss`; `changed` |
| `host.tasks` | The todo list and sub-agent tasks | `todos`; `created`, `updated`, `snapshot`, `todos_changed` |
| `host.loop` | A task loop | `status`; `pause`, `resume`, `cancel_pending`, `pop_pending` |
| `host.commands` | Slash commands and skills | `list`, `skills`; `run(command)` |
| `host.agents` | Agent definitions | `details`; `promote_ephemeral`, `discard_ephemeral` |
| `host.workflows` | Scripted runs | `list`; `run`, `cancel` |
| `host.scheduler` | Scheduled tasks | `tasks`; `start`, `run_now`, `cancel` |
| `host.processes` | Background shells | `list`; `tail`, `stop`, `run` |
| `host.workspace` | The project, as far as the workspace grant reaches | `root`, `head`; `read`, `list`, `complete`, `search`, `pick_dir`, `open(path)`; `head_changed`, `files_changed` |
| `host.models` | Models | `registry`, `current` (writable) |
| `host.mcp` | MCP servers | `servers`, `status`; `connect`, `disconnect`, `set_tool_enabled` |
| `host.plugins` | Plugins and marketplaces | `installed`; `install`, `update`, `remove`, `set_enabled`, … |
| `host.extensions` | Installed extensions (read-only, but for this one's settings) | `installed`; `set_settings`; `state_changed` |
| `host.hooks` | Hooks | `details`; `reload`, `fire_session_start` |
| `host.permissions` | What the agent may do without asking | `mode`; `check`, `save_rule`; `mode_changed` |
| `host.policy` | The group policy in force | `pack` |
| `host.account` | Whether the person is signed in (never a credential) | `status`; `sign_in`, `sign_out`; `changed` |
| `host.notifications` | Notifications on this device | `list`, `unread`; `notify`, `mark_read`; `changed` |
| `host.self` | This extension, as igni sees it | `id`, `settings` (writable), `state`, `web_url`; `busy`, `done`; `settings_changed`, `state_changed` |
| `host` (the root) | Everything | `changed` (any change anywhere); `decide`, `decide_batch` |

### `LocalNotification`, `Target`

```text
LocalNotification(*, kind: str, title: str, body: str = "", target: Target, event_key: str)
Target(*, page: str, params: dict[str, str] = {})
```

Something to tell the person using this igni; there are no recipients.
Send it with `await ext.host.notifications.notify(notification)`. Both
models are frozen and refuse unknown fields.

| Field | Rules |
|---|---|
| `kind` | The extension's own word for what happened (`export_ready`); 1–64 characters. |
| `title` | What it is about; 1–200 characters. |
| `body` | One line; whitespace is collapsed; at most 1,000 characters. |
| `target` | Where opening it goes: one of this extension's pages. Required; igni shows nothing it cannot open. |
| `event_key` | The same event is shown once, however often it is sent; 1–200 characters. Required. |
| `Target.page` | The page's id, as the manifest declares it; 1–200 characters. igni checks it is one of this extension's pages. |
| `Target.params` | Strings only (a page reads them from its location); at most 32, at most 2,048 bytes as JSON. |

A value outside these rules raises `pydantic.ValidationError` where you
build it. igni keeps the notification and its read state on the device,
never sending it to igni server.

### `Hooks`, `HookEvent`, `Allow`, `Reject`, `Modify`

`Hooks` holds every event as a `HookEvent`:

| Decides | Told only |
|---|---|
| `PRE_TOOL_USE`, `POST_TOOL_USE`, `USER_PROMPT_SUBMIT`, `STOP`, `PLAN_SUBMIT` | `POST_TOOL_USE_FAILURE`, `SESSION_START`, `SESSION_END`, `SUBAGENT_START`, `SUBAGENT_STOP`, `NOTIFICATION`, `PRE_COMPACT`, `POST_COMPACT`, `INSTRUCTIONS_LOADED`, `TASK_CREATED`, `TASK_COMPLETED`, `STOP_FAILURE`, `PERMISSION_REQUEST`, `PERMISSION_DENIED` |

`Hooks.all()` lists them. A `HookEvent` has `name` (igni's name,
`"PreToolUse"`), `value` (the model a handler is handed), `decides` and
`modify` (the fields a `Modify` may change).

What a handler is handed, from `igni_extension.hooks` (every value has
`session_id`, and keeps any extra field igni sends):

| Model | Fields |
|---|---|
| `PreToolUse` | `tool_name`, `tool_manifest_name`, `tool_args` |
| `PostToolUse` | `tool_name`, `tool_manifest_name`, `tool_args`, `result` |
| `UserPromptSubmit` | `message` |
| `Stop` | `response` |
| `PlanSubmit` | `plan` (markdown), `tasks` (a list of JSON values), `attempt` (plans rejected since plan mode began; 0 for the first) |
| `Told` | for events that decide nothing |

The answers:

- `Allow()` — let it happen as it is. Returning `None` is the same.
- `Reject(reason: str)` — stop it; `reason` reaches the agent or the person.
- `Modify(value)` — let it happen, changed: the whole value.

### `ServiceEvent`

A pydantic model of one event from the backend service. Extra fields are
kept.

| Field | Meaning |
|---|---|
| `event_id` | igni's id for it; a repeat has the same one. |
| `type` | The service's word for it (`"index.ready"`). |
| `payload` | A dict, as the service sent it. |
| `extension_id` | This extension's id. |
| `client_id` | The service that sent it. |
| `event_key` | The service's own key for it, if it gave one. |
| `created_at`, `expires_at` | Timestamps, as strings, when given. |

### `PromptConditions`

The type of `ext.prompt`.

- `await hold(condition: str, holds: bool = True)` — say whether one
  condition holds. Saying the same again sends nothing.
- `await set(conditions: dict[str, bool])` — say several at once; only
  the ones that changed are sent.
- `await refresh()` — have igni fetch the extension's tool-sourced prompt
  text again and rebuild the agent.
- `holding -> dict[str, bool]` — what was last said, by condition.

A name that is not lower case letters, digits and `-` (starting with a
letter), or more than 64 at once, raises `pydantic.ValidationError`.

### `ExtensionEnvironment`, `Workspace`, `WorkspaceMode`, `Secrets`, `Assets`, `HostEndpoint`

`ExtensionEnvironment.read(environ=None)` reads what igni granted the
process from its environment (`os.environ` by default). `ext.environment`
is the one read at start. Nothing here is a setting you choose; it is
what the process was granted.

```python
from igni_extension import ExtensionEnvironment, WorkspaceMode

env = ExtensionEnvironment.read({
    "IGNI_WORKSPACE": "/home/ada/project",
    "IGNI_WORKSPACE_MODE": "write",
    "IGNI_WORKSPACE_PATHS": "src/**:docs/**",
    "IGNI_SECRET_LEDGER_TOKEN": "s3cret",
    "IGNI_EXTENSION_DATA": "/home/ada/.igni/extensions/acme.example/data",
})
assert env.workspace.writable and env.workspace.mode is WorkspaceMode.WRITE
assert env.workspace.paths == ("src/**", "docs/**")
assert env.secrets.get("ledger-token") == "s3cret"
assert env.data_dir is not None and env.data_dir.name == "data"
assert not env.host.configured                     # no IGNI_HOST_URL: not inside igni
```

| Field | Type | From |
|---|---|---|
| `workspace` | `Workspace` | `IGNI_WORKSPACE`, `IGNI_WORKSPACE_MODE`, `IGNI_WORKSPACE_PATHS` |
| `data_dir` | `Path \| None` | `IGNI_EXTENSION_DATA` |
| `assets` | `Assets` | `IGNI_EXTENSION_ASSETS` |
| `secrets` | `Secrets` | every `IGNI_SECRET_<NAME>` |
| `service` | the service endpoint (`url`, `token_url`, `token_secret`, `configured`) | `IGNI_SERVICE_URL`, `IGNI_SERVICE_TOKEN_URL`, `IGNI_SERVICE_TOKEN_SECRET` |
| `host` | `HostEndpoint` (`url`, `secret`, `configured`) | `IGNI_HOST_URL`, `IGNI_HOST_SECRET` |

- `Workspace` — `root: Path | None`, `mode: WorkspaceMode`, `paths:
  tuple[str, ...]` (globs the grant is limited to; empty means all of
  it), `granted`, `writable`. An unknown mode reads as `read`.
- `WorkspaceMode` — `NONE`, `READ`, `WRITE`.
- `Secrets.get(name) -> str | None` — a declared secret by its manifest
  name; `Secrets.env_name("ledger-token")` is `"LEDGER_TOKEN"`.
- `Assets.path(name) -> Path` — `<assets>/<name>/`, the unpacked archive
  or the directory its one file is in. `Assets.file(name, file) -> Path`
  — one file of an asset. Both raise `NotConfigured` when it was not laid
  out.

### Errors

```text
IgniExtensionError            anything this SDK raises on purpose
├── NotSignedIn               nobody is signed in to igni
├── NotConfigured             igni did not start the process with what the call needs
├── HostUnavailable           the igni backend did not answer as expected
└── HostError                 the igni backend refused or failed a host request
ToolHintsMissing              a tool leaves one of its four hints unstated
NoCaller (LookupError)        the caller was asked for outside a call igni made
```

`HostError(code, message)` has `code` and `message`. `code` is a
`HostErrorCode` — a `StrEnum`, so `error.code == "not_granted"` and
`error.code is HostErrorCode.NOT_GRANTED` both hold — or, for a code a
newer igni sends that this SDK does not know yet, the plain string.

| `HostErrorCode` | Means |
|---|---|
| `NOT_GRANTED` | The manifest's `permissions.host` (or `permissions.workspace`) lacks the object. |
| `NOT_FOUND` | No such member, session, window or item. |
| `INVALID` | The parameters are wrong. |
| `READ_ONLY` | The property cannot be written. |
| `STAGE_2` | Defined in the schema, not yet built in igni. |
| `REFUSED` | The person could not have done it either; or a token for another caller was refused. |
| `UNAVAILABLE` | What answers it (igni's decision model, say) could not be started. |
| `FAILED` | Anything else. |

### `igni_extension.testing`

| Name | What it is |
|---|---|
| `HostHarness(ext, *, timeout=5.0)` | igni's MCP client, connected to the extension over memory streams. `async with` it. `await call(tool, arguments=None, *, caller=None) -> CallToolResult`; `session` (the `mcp` `ClientSession`); `notifications` (`LocalNotification`s received), `raw` (igni's notifications as they crossed the wire), `conditions`; `await received(count)`, `await conditions_said(count)` wait for them, failing after `timeout`. |
| `ConcurrencyHarness(ext, *, stall_limit=0.1, timeout=10.0)` | `await run(calls, *, check=True) -> ConcurrencyReport` makes every call at once; raises `ConcurrencyProblem` on a stall or a leak unless `check=False`. `check(report)` raises for a report. |
| `ConcurrentCall(tool, arguments={}, caller)` | One call the harness makes. |
| `ConcurrentResult` | `call`, `result` (structured content, else content), `is_error`, `took` (seconds). |
| `ConcurrencyReport` | `results`, `longest_stall` (seconds), `leaks` (descriptions). |
| `ConcurrencyProblem` | An `AssertionError`: the loop was blocked, or a call saw another's caller. |
| `FakeHost(*, extension_id="acme.example", granted=(), values=None, answers=None, refusals=None)` | igni's host object model on a loopback WebSocket. `async with` it (or `start()`/`stop()`). `values`: `path -> value` for a `get`, and a `set` stores into it (an unknown path is `not_found`). `answers`: `path -> value`, or a callable of the params, for a `call`. `refusals`: `path -> (code, message)`. `environment(**extra)`; `calls` (every `HostCall`); `subscribed`; `await emit(signal, value)`; `await hook(event, value, timeout=5.0, *, caller=None) -> dict`; `await tell(event, value, timeout=5.0, *, caller=None)`; `await wait_subscribed(signal, timeout=5.0)`. |
| `HostCall` | One `get`, `set` or `call` the extension made: `op`, `path`, `window`, `session`, `params`, `value`. Compare with one you write down. |
| `FakeHostTokenEndpoint(*, service_url="http://service.test", expires_in=600, user_id="u-ada", org_id="org-acme", email="ada@acme.test", name="Ada", minter=None)` | The igni backend's token endpoint for one process. `environment(**extra)`; `transport` (an `httpx.MockTransport`); `sign_in(*, user_id, org_id, email="", name="")`; `sign_out()`; `issued` (every token handed out); `requests`. It refuses (`403`) a token for any caller other than the signed-in person, as igni does. |
| `TokenClaims` | What its tokens say: `sub`, `org`, `email`, `name`, `aud` (the service URL), `token_use`, `jti`. |
| `Minter` | `Callable[[TokenClaims], str]`: makes the token for one person. |
| `ManualClock(start=1000.0)` | A clock that moves only on `advance(seconds)`. Pass it as `IgniExtension(clock=...)`. |

### `python -m igni_extension.manifest`

```bash
python -m igni_extension.manifest acme_tickets_extension
python -m igni_extension.manifest acme_tickets_extension:ext    # when the module holds more than one
```

Imports the module (never runs its `main()`), finds its `IgniExtension`
and prints, as JSON, the extension's `id` and `tools` — `permissions.tools`
as the code states it:

```json
{
  "id": "acme.tickets",
  "tools": [
    {"name": "acme.tickets.lookup_ticket",
     "annotations": {"readOnlyHint": true, "destructiveHint": false,
                     "idempotentHint": true, "openWorldHint": false}}
  ]
}
```

Exit status `0` on success; `1` when the module cannot be imported, holds
no `IgniExtension` or more than one (name it as `module:attribute`), or a
tool leaves a hint unstated; `2` for wrong usage. `igni-service-bundle`
runs it on the extension it bundles.

### Environment variables

igni alone sets these when it starts the process; a manifest cannot
shadow them. You never set them yourself, except in tests through
`environ=`.

| Variable | What |
|---|---|
| `IGNI_SERVICE_URL` | The extension's backend service. Without it, `ext.service` raises `NotConfigured`. |
| `IGNI_SERVICE_TOKEN_URL`, `IGNI_SERVICE_TOKEN_SECRET` | The igni backend's loopback token endpoint, and this process's secret for it. |
| `IGNI_HOST_URL`, `IGNI_HOST_SECRET` | The host object model's loopback socket, and the same secret. Without them, `ext.host` raises `NotConfigured` (but for `notifications.notify`). |
| `IGNI_WORKSPACE`, `IGNI_WORKSPACE_MODE`, `IGNI_WORKSPACE_PATHS` | The project, when the workspace was granted: its root, `read` or `write`, and `:`-separated globs. |
| `IGNI_SECRET_<NAME>` | Each declared secret (`ledger-token` arrives as `IGNI_SECRET_LEDGER_TOKEN`). |
| `IGNI_EXTENSION_DATA` | This extension's own directory on the device, kept across reinstalls and updates. |
| `IGNI_EXTENSION_ASSETS` | Where its assets for this platform are laid out, read-only. |

`IGNI_DEV_EXTENSIONS=1` is a setting of igni itself, not of the process:
it allows development installs.

### Names kept from 0.1.0

`IgniExtension` still answers to igni-extension 0.1.0's spellings. Each
delegates to where the work now lives:

| 0.1.0 | Now |
|---|---|
| `ext.tool_names(tool)` | `ext.tools.names(tool)` |
| `ext.manifest_tools()` | `[line.wire() for line in ext.tools.manifest()]` |
| `await ext.check_tools()` | `await ext.tools.check()` |
| `ext.observing(observer)` | `ext.tools.observing(observer)` |
| `await ext.busy(reason, ttl)` | `await ext.busy.take(reason, ttl)` |
| `await ext.done(reason)` | `await ext.busy.release(reason)` |
| `ext.busy_while(reason, ttl)` | `ext.busy.during(reason, ttl)` |
| `await ext.serve(read, write)` | `await ext.process.serve(read, write)` |

## Troubleshooting and FAQ

**`NotConfigured: … was not started with its service's URL (IGNI_SERVICE_URL)`.**
igni gave the process no service. A bundle igni distributed always has
one. A development install needs a `serviceUrl` setting in
`contributes.settings`, set; a plain-`http` URL only for `localhost` and
only with `IGNI_DEV_EXTENSIONS=1`. In a test, pass
`environ=FakeHostTokenEndpoint().environment()`.

**`NotConfigured: host.…: igni did not give this process the host's address`.**
The process is not running inside igni (or a test did not pass
`environ=FakeHost(...).environment()`). Only `notifications.notify` works
without the socket. `HostHarness` speaks MCP only, so under it `ext.host`
is the same.

**`NotConfigured` from `ext.assets.path(...)` or `ext.assets.file(...)`.**
The manifest does not declare that asset, the name is spelled
differently, or the process runs outside igni.

**`NotSignedIn`.** Nobody is signed in to igni on this device. Catch it in
the tool and tell the person to sign in; it is theirs to fix.
`ext.service.anonymous` still works.

**`HostError` with code `not_granted`.** Add the object to the manifest's
`permissions.host` (or `permissions.workspace` for `host.workspace`). Its
signals do not arrive either until it is granted. A new grant is a new
version, which a super admin approves.

**`HostError` with code `refused` from `ext.service.for_(caller)`.** On a
device serving one person, the igni backend gives a token for that person
only.

**`HostError` with code `stage_2`.** The member is in the host schema but
igni does not implement it yet. Nothing to fix on your side.

**`HostUnavailable`.** The igni backend did not answer: the socket could
not be opened, closed, or a request got no answer within 120 seconds; or
the token endpoint failed. `ext.run()` reconnects on its own.

**`ToolHintsMissing` at start-up.** A tool added on `ext.mcp` directly has
no annotations, or not all four. Use `ext.tool(hints=...)`, or pass
`annotations=ToolHints(...).annotations()`.

**`NoCaller`, or a tool that fails with "no caller".** The tool declares
`caller: Caller` and the call had none — in a test, pass `caller=` to
`HostHarness.call`. Declare `caller: Caller | None` for a tool that also
runs without one.

**`ValueError: … is hooked twice` / `… has a handler already`.** One
handler per hook event, and one per service event type.

**My tool is not offered to the agent.** It must be in the manifest's
`permissions.tools`, or left for `igni-service-bundle` to write. A tool
the manifest omits is reachable only from the page (`permissions.rpc`).

**My hook is never called.** igni asks only about the events listed in
`permissions.hooks`, and only once the process is connected to the host
(`ext.run()` does this; in a test, `await ext.connect()`).

**My signal handler never runs.** The object must be granted, and the
process connected. In a test, `await host.wait_subscribed(signal_name)`
before `emit`.

**The extension is installed for nobody.** A super admin must approve the
service *and* an org admin must switch the extension on for the person's
group. A new version asking for more is held for a super admin.

**The service says my event was `not_handled`.** No handler for its type,
the extension was not running, or the handler raised (the reason says
which).

**Started from a terminal, the process seems to hang.** It is an MCP
server waiting on stdin, and says so on stderr. Test tools with
`HostHarness` instead.

**Is there a database or model I can use?** No. Keep data in
`ext.environment.data_dir`, and ship what you run as `assets`.

## Changes since 0.1.0

On purpose:

- `HookHandlers.tell(name, raw, caller=None)` and
  `HookHandlers.answer(hook_id, name, raw, caller=None)` in
  `igni_extension.hooks`, and `ServiceEventHandlers.answer(hook_id, raw,
  caller=None)` in `igni_extension.service_events`, take the `Caller`
  already read off the wire, or `None`, and hand it to the handler as
  given. In 0.1.0 they took the raw `principal=` dict and read it
  themselves; `principal=` now raises `TypeError`. Handlers reached
  through `ext.hook`, `ext.on_service_event` and `FakeHost` see the same
  caller as before.
- `PlanSubmit.tasks` is a list of JSON values. A task built in Python
  that is not JSON (a date, a set, a dict with an int key) is refused
  with `ValidationError`; what the agent sends is read as before.
- New: `HookMessage.caller` in `igni_extension.wire`, the hook's
  `principal` read as a `Caller`, or `None` when it is missing or
  malformed.
- The work `IgniExtension` did itself moved to `ext.tools`, `ext.busy` and
  `ext.process`. The 0.1.0 spellings still work (see
  [Names kept from 0.1.0](#names-kept-from-010)).
- `ext.connection` is a read-only property, as `ext.process` and
  `ext.signals` are. In 0.1.0 it was a plain attribute, but one assigned
  over left `ext.host` on the old socket: assigning it now raises
  `AttributeError`.

## License

Apache-2.0. See
[LICENSE](https://github.com/ignite-ember/igni-sdk/blob/main/packages/igni-extension/LICENSE).

# igni-client

Drive an igni from your own code. Connect headlessly to a person's, an
app's or a space's igni — in Fleet, through its gateway, or on this
machine — and run work there: open sessions, send prompts, follow the
answer as it streams, answer approvals, run shell commands in the VM.

It speaks the same protocol igni's own app does, so anything the app can
do in a session, your code can do.

<!-- illustrative -->
```python
from igni_client import Fleet, IgniClient, Person

async with IgniClient(Fleet("https://gw.acme.internal", auth=Person.from_cli())) as igni:
    session = await igni.sessions.create()
    reply = await session.ask("Summarise the open pull requests", approve=False)
    print(reply)
```

| | igni-client | igni-extension | igni-service |
|---|---|---|---|
| Runs | anywhere: a script, a backend, CI | on each machine, started by igni | as your service's backend |
| Reaches | one producer's igni, from outside | the igni that started it, from inside | igni server, for an organisation |
| For | running the agent from code | adding tools, hooks and pages to igni | a service people's agents use |

## Installing

**Until the SDKs are on PyPI**, build the wheel from a checkout of igni:

```bash
git clone https://github.com/ignite-ember/igni-sdk.git
uv build --wheel --out-dir ./sdk-wheels igni-sdk/packages/igni-client
uv add igni-client --find-links ./sdk-wheels
```

Once published: `uv add igni-client` (or `pip install igni-client`).
Python 3.12 or later. Every release is also a GitHub Release of igni,
`sdk-v<version>`, carrying the wheel for a machine with no route to PyPI.

## Where the igni is

`Fleet` is a producer's igni in Fleet, reached through the gateway, which
wakes its VM if it is asleep. `Local` is an igni on this machine — the
desktop app's, found from the project it has open.

<!-- illustrative -->
```python
from igni_client import Fleet, IgniClient, Local, Person

fleet = Fleet("https://gw.acme.internal", auth=Person.from_cli())
here = Local(project_dir="~/code/payments")         # the desktop app's igni for that project
by_hand = Local(url="ws://127.0.0.1:8765")           # `python -m igni_core.backend --ws-port 8765`
```

Through the gateway the first connection to a sleeping VM waits while it
resumes — tens of milliseconds paused, a fraction of a second suspended.
Your code sees a pause, not an error.

## Who you connect as

The gateway decides whose igni you reach from the token: a person's, an
app's, or a space's.

**A person** gives a program an **API key**: made on the portal (*API keys*),
it expires after 30, 90 or 365 days, and stops when they revoke it, sign out
everywhere or leave the organisation. The client exchanges it with igni
server for a 15-minute session as them, renewed as needed. That session
can do what the person can, except make more keys.

<!-- illustrative -->
```python
from igni_client import Fleet, IgniClient, Person

key = Person.from_api_key("igpak1.…", server="https://igni.acme.internal")
# or Person.from_api_key() with IGNI_API_KEY and IGNI_SERVER_URL set
async with IgniClient(Fleet("https://gw.acme.internal", auth=key)) as igni:
    ...
```

On their own machine, a person can also use the session `igni login`
keeps (`Person.from_cli()`, 30 days), or an organisation-pinned session
token (`Person("eyJ…")`).

**An app** — a review bot, an integration — signs in as itself with its
own key. Make the key once, give its public half to an org admin to
register the app on igni server, and keep the private half:

```python
from igni_client import App

App.generate_key("app-key.pem")
app = App("app-review-bot", server="https://igni.acme.internal", key_file="app-key.pem")
print(app.public_jwks().model_dump_json())  # what the org admin registers
```

<!-- continues -->
```python
await app.aclose()
```

Its tokens last ten minutes and are renewed for you.

**A space** is one end user of an app, with an igni of its own. The app
declares it by your own id for the user, then connects as it:

<!-- illustrative -->
```python
space = await app.spaces.declare("customer-42")      # the same space every time for that id
async with IgniClient(Fleet("https://gw.acme.internal", auth=space)) as igni:
    ...
```

`app.spaces.get(id)`, `.list()` and `.delete(id)` manage them; deleting a
space erases its VM.

Changed since igni-client 0.1.0, on purpose:

- `App.public_jwks()` returns a `JwkSet` (`igni_client.auth.keys`), not a
  dict: read `jwks.keys[0].kid` where you read `jwks["keys"][0]["kid"]`,
  and write `jwks.model_dump_json()` where you wrote
  `json.dumps(jwks)`. The JSON is the same, members in the same order.
- Each auth name lives in the module that owns it (`igni_client.auth.app`,
  `.person`, `.spaces`, `.tokens`, `.keys`, `.grants`); `from
  igni_client.auth import App` and the other 0.1.0 names still work.
- New on `App`: `exchange(space_id)` (its token exchanged for a space's),
  `request(method, path, what=...)` (a call to igni server as the app,
  retried once on a 401) and the `clock` it was made with, which the app
  and its spaces read at each renewal.
- A space renews its token by its app's `RENEW_BEFORE`, a subclass's or
  one set on the app included; 0.1.0 always used `App.RENEW_BEFORE`.
- `spaces.delete(id)` is done on any 2xx answer, whatever its body; 0.1.0
  raised `Unavailable` on a 200 or 202 that was not a JSON object.
- A space record igni server sent malformed (no `space_id`, say) raises
  `Unavailable("igni server answered … with something else")` from
  `declare`, `get` and `list`, where 0.1.0 raised pydantic's
  `ValidationError`.
- A discovery document that is not a JSON object raises
  `Unavailable("igni server published no issuer")`, and an API key refused
  with a JSON body that is not an object raises `AuthError` with that
  body; 0.1.0 raised `JSONDecodeError` or `AttributeError`.

## Sessions

<!-- illustrative -->
```python
session = await igni.sessions.create(project_dir="/workspace/payments")
again = await igni.sessions.open(session.id)         # an existing one, approvals it waits on included
for entry in await igni.sessions.list():
    print(entry.session_id, entry.name, entry.run_count)
```

`sessions.default()` is the session igni opened at start. A session has
`history()` (its turns, as `HistoryTurn`s), `status()` (its model, context
used and permission mode) and `use_model(name)`; `igni.models.list()` says
which models there are, as a `ModelCatalogue`.

## A run, event by event

`session.send()` starts a run and yields what happens as it happens: the
answer in pieces, each tool call, sub-agents starting, the end.

```python
from igni_client import ContentDelta, IgniClient, RunCompleted, ToolStarted
from igni_client.testing import FakeIgni

async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
    session = await igni.sessions.create()
    async for event in session.send("What does the payments service do?"):
        match event:
            case ContentDelta(text=text, is_thinking=False):
                print(text, end="")
            case ToolStarted(friendly_name=name):
                print(f"\n[{name}]")
            case RunCompleted(output_tokens=tokens):
                print(f"\n{tokens} tokens")
```

Every event is a typed model of igni's message. A message this version
does not know arrives as `Unknown`, with everything it carried, so a newer
igni does not break an older client.

## Approvals

When the agent wants to use a tool that needs a yes — a shell command, an
edit, depending on the permission mode — igni pauses the run and the loop
yields an `ApprovalRequested`. Answer it in the loop and the same loop
carries on with the resumed run:

```python
from igni_client import ApprovalRequested, IgniClient
from igni_client.testing import FakeIgni, Steps

async with FakeIgni() as fake:
    fake.runs.script = lambda text: [
        Steps.approval("run_shell_command", command="rm -rf build"),
        *Steps.answer("Cleaned the build directory."),
    ]
    async with IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        async for event in session.send("Clean the build directory"):
            if isinstance(event, ApprovalRequested):
                for requirement in event.requirements:
                    print("asks for", requirement.tool_name, requirement.tool_args)
                await event.approve()
```

`approve(choice)` lets every call run (`"once"`, or `"always"` / `"similar"`
to save a permission rule); `reject()` refuses them. `decide({...})`
answers each call separately with a `Decision.allow()` or
`Decision.deny()`. igni asks about the calls of one pause together and
counts a call left out as refused, so every answer covers all of them.

A loop that ends without answering leaves the run waiting on igni's side;
`sessions.open()` offers it again.

**Approving on this machine.** Found from the lockfile, `Local` runs
sessions but cannot answer approvals: the agent can read that file too, and
must not approve its own calls. igni refuses the answer and `approve()`
raises `NotAllowed`. To let your program approve, type `/programs` in igni's
window, make an approver token and give it to the program:

<!-- illustrative -->
```python
here = Local(project_dir="~/code/payments", approver_token="…")
# or set IGNI_APPROVER_TOKEN
```

igni forgets approver tokens when it quits, and revoking them in
`/programs` disconnects the programs using one. An approver answers each
pause once: `approve("always")`, `Decision.deny(remember=True)` and
switching the permission mode stay igni's window's. Through Fleet's gateway
none of this applies: the token you connect with is already the person's.

## The whole answer at once

`session.ask()` runs the prompt to the end and returns the answer.
`approve=` decides approvals: `True` allows everything, `False` refuses
everything, or a function of each `Requirement` — sync or async —
returns a `bool` or a `Decision`:

```python
from igni_client import Decision, IgniClient
from igni_client.testing import FakeIgni


def only_reads(requirement):
    return Decision.allow() if requirement.tool_name == "read_file" else Decision.deny()


async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
    session = await igni.sessions.create()
    reply = await session.ask("Explain src/auth.py", approve=only_reads)
    print(reply.text, reply.completed.output_tokens if reply.completed else 0)
```

Without `approve=`, a pause raises `ApprovalRequired`; a failed run raises
`RunFailed`. `session.queue(text)` adds a prompt for after the run going;
`session.cancel()` stops it.

Changed since igni-client 0.1.0, on purpose:

- `Decision`, `Policy`, `Choice` and `Answer` live in
  `igni_client.approvals`, and `Reply` in `igni_client.replies`; they are
  no longer importable from `igni_client.runs`. `from igni_client import
  Decision, Reply` works as before.
- The free function `igni_client.runs.collect(events, approve)` is now
  `Reply.collect(events, Approver(approve))`. `Approver(policy).answer(request)`
  and `Decision.frame(requirement_id)` are new.
- A decision's choice is one of igni's scopes, `"once"`, `"always"`,
  `"similar"` or `"deny"` (`igni_client.frames.Scope`). Any other string,
  as in `Decision(action="confirm", choice="sometimes")` or
  `approve("sometimes")`, raises pydantic's `ValidationError` before
  anything is sent, and the approval stays unanswered. In 0.1.0 it was sent
  to igni as given. `FakeIgni` passes over an answer with an unknown scope:
  it is not recorded in `fake.runs.decisions` or `fake.socket.received`.
- An `ApprovalRequested(paused, answer)` built by hand hands its `answer`
  callback a list of `igni_client.frames.HitlDecision` models (read
  `decision.action`), not dicts. igni gets the same message as before.

## Commands in the VM

Through Fleet, run a shell command in the producer's VM — as root, in a
shell — and stream its output as it is written. igni server decides who
may run what, and audits every command.

```python
from igni_client import IgniClient, Person
from igni_client.testing import FakeGateway, FakeIgni, PlayedCommand

gateway = FakeGateway({"t-ada": "person:u-ada"})
gateway.commands["pytest -q"] = PlayedCommand(stdout="12 passed\n")
async with FakeIgni(gateway=gateway) as fake:
    async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
        run = await igni.commands.run("pytest -q", timeout_s=300)
        async for output in run:
            print(output.text, end="")
        print("exit", run.finished.exit_code)
```

`await run.wait()` collects it instead (into `run.stdout` and
`run.stderr`). A producer runs commands in its own VM; an org admin may
name another with `producer="person:<id>"`. `igni.me()` says who the
gateway takes you for. A local igni has no gateway, so neither is
available there.

A line of the gateway's stream that is not a JSON object — garbled, or
JSON such as `[1]`, `5` or `null` — is passed over with a warning on the
`igni_client.commands.run` logger, and the run goes on. (igni-client
0.1.0 raised `AttributeError` or `TypeError` out of the iteration on a
line that was JSON but not an object.)

Changed since igni-client 0.1.0, on purpose:

- `run.record` and `run.woken` are `None` until their lines arrive, then a
  `CommandRecord` (`command_id`, `command`, `state`) and a `Wake` (`how`,
  `node`, `ms`), both keeping any other field the gateway sends. In 0.1.0
  they were plain dicts, `{}` until then: read `run.record.command` where
  you read `run.record["command"]`, and test `run.record is None` where
  you tested `not run.record`.
- `Wake.ms` is a float, as the gateway sends it (`30` is read as `30.0`).
  `FakeIgni`'s gateway now wakes a VM in `12.345` ms, not `30`.
- `CommandRun(fleet, request, token)` takes a
  `igni_client.commands.wire.CommandRequest`, not a dict;
  `igni.commands.run(...)` builds it for you.
- A line that is not JSON at all is still passed over, now with the same
  warning.
- New names: `CommandRecord` and `Wake` in `igni_client.commands`, and the
  gateway's wire models in `igni_client.commands.wire`.

## Anything else igni can do

Every one of igni's methods — the ones its own app uses for plugins, MCP
servers, scheduled tasks, workflows and the rest — is a typed method on
`IgniClient` or `Session`, generated from igni-core's contract. The API
reference below lists them all:

```python
from igni_client import IgniClient
from igni_client.models import ScheduledTask
from igni_client.testing import FakeIgni

async with FakeIgni() as fake:
    fake.methods.answers["get_scheduled_tasks"] = []
    async with IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        tasks: list[ScheduledTask] = await session.scheduler.list(include_done=False)
        print(tasks)
```

## Watching

igni sends every message to every client attached — a person's open
window, and you. `igni.events()` yields them all, from every session, to
watch what an igni is doing; `session.send()` is for following your own
run. A person with igni open on their VM sees your runs as they happen.

## When the connection changes under you

- **Fleet moved the VM.** When a node drains or fails, the gateway wakes
  the VM on another node and reconnects behind you. The client re-attaches
  its sessions on its own; a run going at that moment ends with
  `RunInterrupted` — it may or may not have finished, so read the
  session's history.
- **Busy.** With no room for the VM right away, the gateway answers "busy,
  retry"; the client tries again, backing off, and raises `Unavailable`
  if it stays busy.
- **Refused.** `AuthError` for a credential igni does not accept,
  `NotAllowed` for a producer that is no longer active, a lapsed licence,
  or a command in somebody else's VM. Neither is retried.

```python
from igni_client import IgniClient, Person
from igni_client.testing import FakeGateway, FakeIgni

async with FakeIgni(gateway=FakeGateway({"t-ada": "person:u-ada"})) as fake:
    fake.socket.busy_next(1)                # the first connection is told "busy, retry"
    async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
        print("connected on attempt", fake.socket.connections)
```

A local igni is not retried: one that closed has stopped, and the client
raises `Unavailable`.

Changed since igni-client 0.1.0, on purpose:

- `IgniClient(target, backoff=Backoff(attempts=5, first=0.5, most=8.0))`
  paces opening the socket again; `reconnect_attempts=` is gone and raises
  `TypeError`. The default waits are 0.1.0's. A negative `attempts` tries
  once and raises; 0.1.0 tried no times and returned as if connected.
  `Backoff` is new in `igni_client`.
- A client closed and connected again opens its socket again when it drops,
  like a new client. In 0.1.0 it never did.
- `igni_client.connection` keeps only `Connection` and `REFUSED_METHODS`:
  `Interruption` is in `igni_client.routing`, and the connection's
  `new_id`, `open_stream`, `close_stream`, `listen` and `unlisten` are its
  `router`'s. `Connection(target, backoff, router)` takes all three, and
  its `send` takes a frame from `igni_client.frames`, not a dict.
  `Run.stream` takes a `UserMessage`.
- Closing passes over only a socket error, logged at INFO on the
  `igni_client.connection` logger; any other error closing the socket is
  raised. That logger also warns of a message from igni that is not a JSON
  object (still passed over), and says at INFO when reading stops.

## Testing your code

`igni_client.testing.FakeIgni` is igni on a loopback socket, scripted.
Each part is a collaborator a test talks to: `fake.runs.script` decides
what each prompt runs (`Steps.answer(text)`, `Steps.approval(tool,
**args)`, `Delay(seconds=...)`, or any typed message), and `fake.methods`
answers the rest (`answers`, `models`, `history`). Given
`gateway=FakeGateway(tokens)` it plays Fleet's gateway too: bearer tokens
on `/v1/connect`, `/v1/me` and `/v1/commands` through `fake.fleet(auth)`,
with `gateway.commands` deciding what each command prints.

It records what your code did — `fake.socket.received` (the typed frames
it sent), `fake.runs.decisions`, `gateway.commands_run`,
`fake.methods.sessions` — and plays what Fleet does under you:
`fake.socket.move()`, `drop(code)`, `busy_next(n)` and
`fake.methods.unbound_for(n)`.

## API reference

<!-- api-reference:start -->

<!-- Generated by tools/client_codegen.py from contracts/rpc-contract.json. Do not edit by hand: run `make client-api`. -->

#### Who may call what

Who may make a call, as the backend enforces it
(`backend/standing_policy.py`, `backend/message_admission.py`).

* `client` — any connection igni admitted.
* `approver` — igni's window, or a connection standing as an approver.
* `window` — a connection standing as igni's window only.
* `page` — an extension's page, through a window that sets the
  request's `caller`, where the deployment lets a connection speak
  for an extension.
* `platform` — the platform. Where the deployment requires it (the
  cloud), only on the gateway's control connection; elsewhere any
  connection.

A connection's standing is decided once, at the WebSocket handshake,
by the token it offers (`transport/ws_auth.py`):

* **Local client, on the desktop.** igni's desktop app launches igni
  with a per-launch secret that only the app holds, so only the app's
  own window stands as the window. A client attaching with the token
  igni publishes in its owner-only lockfile stands as a *program*: it
  reaches every `client` call and the `platform` calls (the
  desktop does not require a control connection for them), and is
  refused every `window` and `approver` call, every approval
  answer (`hitl_response`), any `caller`, and the window-only
  slash commands. A client given an approver token (minted in igni's
  window with `mint_approver_token`) stands as an *approver*: it
  also answers approval requests and calls `approve_plan`, each
  time once — no saved rule, no permission-mode change. It still
  reaches no `window` call.
* **Local client, igni started without a secret** (by hand, or with
  the development switch): every connection stands as the window, so
  it reaches `client`, `approver` and `window` calls.
* **Through Fleet's gateway** (a cloud VM): the gateway authenticates
  the client — with a person's key or an app's — and igni on the VM
  takes no token, so every connection stands as the window and
  reaches `client`, `approver` and `window` calls alike; igni
  cannot tell a person's key from an app's. No connection there may
  speak for an extension, so `page` calls are refused, and the
  `platform` calls are taken only from the gateway's control
  connection, which a client never has.

| Namespace | Methods |
|---|---|
| [`igni`](#igni) | `check_for_update`, `group_policy` |
| [`igni.agents`](#igniagents) | `cancel_run` |
| [`igni.approvers`](#igniapprovers) | `mint_token`, `revoke_tokens` |
| [`igni.auth`](#igniauth) | `cancel_login`, `discover_server`, `login`, `set_server` |
| [`igni.extensions`](#igniextensions) | `list`, `set_settings` |
| [`igni.files`](#ignifiles) | `list_dirs` |
| [`igni.marketplaces`](#ignimarketplaces) | `add`, `list`, `refresh`, `remove` |
| [`igni.notifications`](#igninotifications) | `counts`, `list`, `mark_read` |
| [`igni.processes`](#igniprocesses) | `list`, `stop`, `tail` |
| [`igni.sessions`](#ignisessions) | `attach` |
| [`igni.window`](#igniwindow) | `model` |
| [`session`](#session) | `cancel`, `command`, `current_id`, `display_config`, `extract_learnings`, `fire_session_start_hook`, `get_project_dir`, `is_processing`, `list_sessions`, `output_styles`, `run_shell`, `run_timeout`, `shutdown`, `slash_commands`, `status`, `switch`, `todos`, `toggle_verbose`, `typing`, `upload_attachment`, `visualization_action` |
| [`session.agents`](#sessionagents) | `discard`, `list`, `promote` |
| [`session.auth`](#sessionauth) | `reload_credentials`, `sign_out` |
| [`session.context`](#sessioncontext) | `breakdown`, `compact`, `tokens` |
| [`session.files`](#sessionfiles) | `complete`, `pick_dir`, `read`, `search` |
| [`session.history`](#sessionhistory) | `get`, `search`, `truncate` |
| [`session.hooks`](#sessionhooks) | `list`, `reload` |
| [`session.loop`](#sessionloop) | `cancel`, `next_iteration`, `pause`, `resume`, `status` |
| [`session.mcp`](#sessionmcp) | `connect`, `disconnect`, `ensure`, `server_details`, `servers`, `set_tool_enabled`, `status` |
| [`session.models`](#sessionmodels) | `list`, `switch` |
| [`session.permissions`](#sessionpermissions) | `check`, `save_rule` |
| [`session.plan`](#sessionplan) | `approve`, `dismiss`, `latest` |
| [`session.plugins`](#sessionplugins) | `contents`, `install`, `list`, `preview`, `remove`, `set_enabled`, `update` |
| [`session.runs`](#sessionruns) | `discard_interrupted`, `interrupted`, `pending_messages` |
| [`session.scheduler`](#sessionscheduler) | `cancel`, `execute`, `list`, `start` |
| [`session.skills`](#sessionskills) | `definitions`, `list`, `names` |
| [`session.workflows`](#sessionworkflows) | `cancel`, `list`, `run` |
| [`session.workspace`](#sessionworkspace) | `set_trust`, `trust` |

#### igni

The methods igni answers for igni as a whole; `IgniClient` is one.

<details>
<summary><code>await igni.check_for_update()</code> → <code>UpdateAvailable | None</code></summary>

Wire method `check_for_update` · access `client`

Ask whether a newer igni release is available.

Takes no arguments. Returns the newer release — its version, the
version installed, where to get it — or `null` when there is none
(or update checks are switched off). Fails when the check could not
reach an answer (network, HTTP status, an unreadable reply), so a
caller can tell that from "no update".

</details>

<details>
<summary><code>await igni.group_policy()</code> → <code>GroupPolicyPackResult</code></summary>

Wire method `get_group_policy` · access `client`

Read which organisation group's policy igni follows.

Takes no arguments. Returns the group's id and name, when its
policy pack was fetched, how many entries it has and the default
model it sets; nulls and zero when igni follows no group.

</details>

#### igni.agents

Sub-agents' runs, wherever they are going.

<details>
<summary><code>await igni.agents.cancel_run(*, run_id: str = '')</code> → <code>CancelAgentRunResult</code></summary>

Wire method `cancel_agent_run` · access `client`

Stop one sub-agent's run, leaving the rest of the turn going.

`run_id` is the sub-agent run's id, as its events carry it.
Returns `ok: true` once the cancellation is asked for — an unknown
id is not detected — or `ok: false` with `error` when
`run_id` is empty or the cancellation failed.

</details>

#### igni.approvers

Approver tokens: what lets a program answer approval requests.

<details>
<summary><code>await igni.approvers.mint_token()</code> → <code>ApproverTokenMinted</code></summary>

Wire method `mint_approver_token` · access `window`

Make a token that lets a program answer the agent's approval requests.

Takes no arguments. Returns `token`: a program that connects with it
stands as an approver — it may answer approval requests and approve a
plan, once each time, but saves no rule and changes no permission mode.
The token lives in memory until igni exits or the tokens are revoked,
and is sent only to the connection that asked.

Fails when this igni's transport takes no token at all, so every
connection may already answer approval requests.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

<details>
<summary><code>await igni.approvers.revoke_tokens()</code> → <code>ApproverTokensRevoked</code></summary>

Wire method `revoke_approver_tokens` · access `window`

Forget every approver token, so no program answers approval requests any more.

Takes no arguments. Returns `revoked`: how many tokens were
forgotten (`0` when there were none, or when this igni takes no
token). Connections that attached with a revoked token lose their
approver standing.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### igni.auth

Signing igni in to igni server, and choosing which server.

<details>
<summary><code>await igni.auth.cancel_login()</code> → <code>None</code></summary>

Message `cancel_login`

Cancel the sign-in to igni server that `igni.auth.login()` started.

igni answers nothing; the sign-in's `login_result` push says it ended.

</details>

<details>
<summary><code>await igni.auth.discover_server(email: str)</code> → <code>ServerFound</code></summary>

Wire method `discover_server` · access `client`

Find the igni server an email address's organisation runs.

`email` is the person's work address. igni reads the record the
organisation publishes on the address's domain (a well-known URL,
then DNS) and changes nothing. Returns `api_url` and `portal_url`,
with `source` saying where they were found; when nothing usable
was found both are empty and `reason` says why.

</details>

<details>
<summary><code>igni.auth.login()</code> → <code>Call[LoginStarted, LoginEvent]</code></summary>

Wire method `login` · access `window` · streams `login_result`, `login_status`, `notifications_changed`

Start signing in to igni server through the person's browser.

Takes no arguments, and answers at once with `started: true`; a
sign-in already in progress is cancelled first. The sign-in itself
goes on in the background: `login_status` pushes say what it is
doing (the local callback server starting, the URL to open, the
account being read), and one `login_result` push ends it, with
`success` and, in `result`, the signed-in email or the reason it
failed. On success the person's notifications are read and
`notifications_changed` follows.

Followed: `async with` the call to follow it: it yields the `login_status` pushes and ends with the `login_result` one. igni signs in one way at a time — a new `login` cancels the one going — so these are the sign-in igni is doing.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

<details>
<summary><code>await igni.auth.set_server(api_url: str, *, portal_url: str = '')</code> → <code>ServerChoice</code></summary>

Wire method `set_server` · access `window`

Choose the igni server to sign in to, and remember it for the next launch.

`api_url` is the server's API address (`https` only);
`portal_url` its portal, empty to derive it from `api_url`.
Returns the server as stored, or, when the choice is refused (an
empty or non-`https` address), `error` saying why and nothing
stored. Fails when the user configuration file cannot be read or
written.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### igni.extensions

The extensions installed into this igni, and their settings.

<details>
<summary><code>await igni.extensions.list()</code> → <code>ExtensionListResult</code></summary>

Wire method `list_extensions` · access `client`

List the installed extensions, including the ones that failed to start.

Takes no arguments. Returns each extension's id, name, version and
`state` — a failed one with its `reason`, rather than left out —
with what it adds to igni's window (pages, menu items, indicators),
its settings and their values, and the addresses of its UI, its web
home and its service.

</details>

<details>
<summary><code>await igni.extensions.set_settings(*, extension_id: str, values: dict[str, JsonValue])</code> → <code>ExtensionListResult</code></summary>

Wire method `set_extension_settings` · access `window`

Change an installed extension's settings.

`extension_id` is the extension; `values` the settings to
change, by key, merged over what is stored. The extension reads them
the next time it starts. Returns the whole list, as
`list_extensions` does. Fails when the extension is not
installed, a key is not one of its settings, a value is not one of
a setting's options, or igni has no extension support.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### igni.files

Folders on the machine igni runs on.

<details>
<summary><code>await igni.files.list_dirs(*, path: str | None = None, show_hidden: bool = False)</code> → <code>DirListResult</code></summary>

Wire method `list_dirs` · access `client`

List the folders inside a folder on igni's machine, for picking a project.

`path` is the folder to list (the home folder when absent or
empty); `show_hidden` includes folders whose names start with a
dot. Returns the resolved `path`, its `parent` (empty at the
root), the folder names in it (`dirs`, sorted), the home folder,
and `error` when it could not be read.

</details>

#### igni.marketplaces

Plugin marketplaces: where plugins are installed from.

<details>
<summary><code>await igni.marketplaces.add(url: str)</code> → <code>InfoMessage</code></summary>

Wire method `add_marketplace` · access `window`

Add a plugin marketplace and read its catalogue.

`url` is the marketplace's git URL. Returns an `info` message,
sent in place of an `rpc_response`, whose text says how many
plugins it catalogues — or why it was not added: the
organisation's policy, a git error, an unreadable catalogue.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

<details>
<summary><code>await igni.marketplaces.list()</code> → <code>list[MarketplaceInfo]</code></summary>

Wire method `get_marketplaces` · access `client`

List the plugin marketplaces igni knows, with their catalogues.

Takes no arguments. Returns each marketplace's name, URL, when it
was last fetched, and the plugins it offers.

</details>

<details>
<summary><code>await igni.marketplaces.refresh(*, name: str | None = None)</code> → <code>InfoMessage</code></summary>

Wire method `refresh_marketplaces` · access `client`

Fetch marketplaces' catalogues again.

`name` is one marketplace; absent or empty refreshes every one.
Returns an `info` message, sent in place of an `rpc_response`,
whose text says what was refreshed, or why not.

</details>

<details>
<summary><code>await igni.marketplaces.remove(name: str)</code> → <code>InfoMessage</code></summary>

Wire method `remove_marketplace` · access `window`

Forget a plugin marketplace.

`name` is the marketplace. Returns an `info` message, sent in
place of an `rpc_response`, whose text says it was removed, or
that there is no such marketplace.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### igni.notifications

The signed-in person's notifications, and what extensions posted.

<details>
<summary><code>await igni.notifications.counts()</code> → <code>NotificationCounts</code></summary>

Wire method `notifications_counts` · access `client`

Count the person's unread notifications, in all and per extension.

Takes no arguments. Answers from what was last read, asking nobody;
`notifications_changed` pushes the counts whenever they move.

</details>

<details>
<summary><code>await igni.notifications.list()</code> → <code>NotificationsListResult</code></summary>

Wire method `notifications_list` · access `client` · streams `notifications_changed`

List the signed-in person's notifications, newest first.

Takes no arguments. Reads igni server again and merges in what
extensions on this machine posted. Returns at most 100
`notifications` (each with its source, title, body, target and
whether it is read), the unread `counts` in all and per
extension, and `server_error` when igni server could not be
read. The fresh counts are also pushed as `notifications_changed`.

Not followed: the `notifications_changed` push repeats the counts the answer carries, to every client, and does not say what caused it.

</details>

<details>
<summary><code>await igni.notifications.mark_read(*, ids: list[str] | None = None, source: str | None = None)</code> → <code>NotificationsReadResult</code></summary>

Wire method `notifications_mark_read` · access `client` · streams `notifications_changed`

Mark notifications read.

`ids` names the notifications; `source` (an extension id) marks
all of that extension's; neither marks every notification. Returns
the unread `counts` afterwards, also pushed as
`notifications_changed`, and `server_error` when igni server
could not be told.

Not followed: the `notifications_changed` push repeats the counts the answer carries, to every client, and does not say what caused it.

</details>

#### igni.processes

Background processes igni tracks, in every session.

<details>
<summary><code>await igni.processes.list()</code> → <code>list[ProcessRow]</code></summary>

Wire method `list_background_processes` · access `client`

List the background processes igni is tracking, in every session.

Takes no arguments. Returns each process's `pid`, command, how
long it has run, whether it is still running, and its exit code
once it has ended.

</details>

<details>
<summary><code>igni.processes.stop(pid: int)</code> → <code>Call[StopProcessResult, StopBackgroundProcessEvent]</code></summary>

Wire method `stop_background_process` · access `client` · streams `background_process_done`, `process_exited`, `process_line`

Stop a background process.

`pid` is the process. Returns `killed: true` once it was told to
stop — its last lines, `process_exited` and
`background_process_done` follow — or `killed: false` with a
`message` when igni is not tracking it or it had already ended.

Followed: `async with` the call to follow it: it yields the `process_line`, `process_exited` and `background_process_done` pushes of `pid` and ends with `background_process_done`, or with the answer when `killed` is false.

</details>

<details>
<summary><code>await igni.processes.tail(pid: int, *, tail: int = 200)</code> → <code>ProcessTailResult</code></summary>

Wire method `read_process_tail` · access `client`

Read the last lines a background process printed.

`pid` is the process; `tail` how many lines (default 200).
Returns its `output`, whether it `is_running`, and its
`exit_code` once it has ended. An unknown `pid` answers empty
output, not running.

</details>

#### igni.sessions

igni's sessions: attach one, or make a new one in a project folder.

<details>
<summary><code>await igni.sessions.attach(*, project_dir: str = '', session_id: str = '')</code> → <code>AttachSessionResult</code></summary>

Wire method `attach_session` · access `client` · streams `content_delta`, `error`, `info`, `model_completed`, `background_process_done`, `file_edited`, `http_retry_attempt`, `http_retry_succeeded`, `orchestrate_event`, `permission_mode_changed`, `plan_submitted`, `process_exited`, `process_line`, `process_started`, `todos_updated`, `reasoning_started`, `requirement_details`, `run_completed`, `run_error`, `run_paused`, `run_started`, `stream_end`, `streaming_done`, `task_created`, `task_iteration`, `task_state_updated`, `task_updated`, `tool_completed`, `tool_error`, `tool_started`

Bind to a session — an existing one, or a new one in a project folder.

`session_id` names the session to resume; `project_dir` the folder
it works in. Neither: the default session. Only `project_dir`: a new
session locked to that folder. Both: that session, which must belong
to that folder. The session is made live if it is not.

Returns the `session_id` and `project_dir` actually bound; send
later requests for that session with this `session_id` on the
envelope. Right after the answer, every approval the session is
waiting on is shown again (a `run_paused` carrying its
`hitl_request` items), since a client that reloaded lost its
dialog; a run igni was continuing when it stopped is reported with
an `info`, and a sub-agent's interrupted run is continued, which
streams as any run does.

Fails when `project_dir` is not a directory, or the session belongs
to another project.

Not followed: the approvals and runs it shows again carry no request id and no end, and every client attaching the session shows them again; watch them with `session.events()`, which offers each waiting approval as an `ApprovalRequested`.

</details>

#### igni.window

igni's own window's model — its fields, toasts and dialog.

<details>
<summary><code>await igni.window.model(*, op: Literal['hydrate', 'write', 'toast', 'dismiss_toast', 'open_dialog', 'answer_dialog'], window: str, connection_id: str = '', dialog_id: str = '', field: str = '', kind: str = '', token: str = '', value: JsonValue = None)</code> → <code>WindowModelResult</code></summary>

Wire method `window_model` · access `window` · streams `window_model_changed`

Read or change the calling window's own model: its fields, toasts and dialog.

A window spans sessions, so this is not tied to one. `op` says what
to do (see the arguments); `window` is the window's own stable id.
The window is the one on the connection the request came on.

Returns, by `op`: `hydrate` the whole model (`state`), its
revision (`rev`) and the fields nobody set (`unset`); `write`,
`dismiss_toast` the new `rev`; `toast` the toast as shown, with
its id; `open_dialog` the dialog as shown; `answer_dialog`
whether that dialog was still the open one (`answered`). Every
change is pushed to every window as `window_model_changed`.

Fails when the model refuses the write (an unknown field, a field
that is not writable, a value that does not fit its type), or when
the window's saved state could not be read or written.

Not followed: a `window_model_changed` push says which window changed and its new revision, but not which request changed it, and a request that changes nothing pushes nothing.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### session

The methods igni answers for one session; `Session` is one.

<details>
<summary><code>await session.cancel()</code> → <code>None</code></summary>

Wire method `cancel_run` · access `client` · streams `info`, `stream_end`

Stop the turn this session is running.

Takes no arguments and returns nothing; with no turn running it does
nothing. The turn's stream ends with an `info` saying it was
cancelled and its `stream_end`, and the run is recorded as
interrupted. A foreground shell command the turn started is killed.

Not followed: the `info` and `stream_end` it causes belong to the turn it stops, whose own stream (`session.send()`) ends with them; with no turn going nothing follows, and the answer does not say which it was.

</details>

<details>
<summary><code>await session.command(text)</code> → <code>CommandResult</code></summary>

Message `command`, answered by `command_result`

Run a slash command in this session, as typed in igni's composer: `/help`, `/compact`, `/model`.

`text` is the command line, its leading `/` optional. Returns igni's `command_result`: its `kind` (`markdown`, `info`, `error` or `action`), the `content` to show and the `action` the command asks a client to take. The commands that switch approvals off, change what igni loads or whom it signs in to (`/bypass`, `/accept`, `/plugin`, `/eject`, `/login`, `/logout`) answer an `error` to anything but igni's window.

</details>

<details>
<summary><code>await session.current_id()</code> → <code>str</code></summary>

Wire method `get_session_id` · access `client`

Read the id of the session this request reached.

Takes no arguments. Returns the session's current id, which can
differ from the one the request was routed by after `/clear` or
`switch_session`.

</details>

<details>
<summary><code>await session.display_config()</code> → <code>DisplayConfig</code></summary>

Wire method `get_display_config` · access `client`

Read this session's display settings.

Takes no arguments. Returns how output is shown: markdown rendering,
tool calls, routing, reasoning, the colour theme, and how many lines
of a tool result and a message are shown before truncating.

</details>

<details>
<summary><code>await session.extract_learnings(*, assistant_msg: str, user_msg: str)</code> → <code>None</code></summary>

Wire method `extract_learnings` · access `client`

Let igni learn from one finished turn, in the background.

`user_msg` and `assistant_msg` are the turn's message and
answer. Returns at once with nothing; what is learnt is kept for
later sessions, and a failure is only logged.

</details>

<details>
<summary><code>await session.fire_session_start_hook()</code> → <code>None</code></summary>

Wire method `fire_session_start_hook` · access `client`

Run this session's `SessionStart` hooks.

Takes no arguments and returns nothing. The organisation's group
policy is checked again first. Every call runs the hooks again;
their failures are logged, not raised.

</details>

<details>
<summary><code>await session.get_project_dir()</code> → <code>str</code></summary>

Wire method `get_project_dir` · access `client`

Read the folder this session is locked to.

Takes no arguments. Returns the absolute path the agent's tools and
shell commands work in.

</details>

<details>
<summary><code>await session.is_processing()</code> → <code>bool</code></summary>

Wire method `get_processing` · access `client`

Say whether this session is running a turn right now.

Takes no arguments. Returns `true` while a turn the person (or a
client) started is starting, streaming or finishing.

</details>

<details>
<summary><code>await session.list_sessions()</code> → <code>SessionListResult</code></summary>

Wire method `list_sessions` · access `client`

List the sessions kept in this session's project.

Takes no arguments. Returns a `session_list_result` message, sent
in place of an `rpc_response`: each session's id, name, when it
was created and last updated, how many runs it has, a summary and
the agent it runs. A storage failure answers an empty list.

</details>

<details>
<summary><code>await session.output_styles()</code> → <code>OutputStylesResult</code></summary>

Wire method `get_output_styles` · access `client`

List the output styles this session can answer in, and the active one.

Takes no arguments. Returns the `active` style's name (empty for
none) and every style's `name` and `description`.

</details>

<details>
<summary><code>await session.run_shell(*, command: str = '')</code> → <code>RunShellResult</code></summary>

Wire method `run_shell` · access `window` · streams `background_process_done`, `process_exited`, `process_line`, `process_started`

Run a shell command in this session's project folder and return its output.

`command` is the command line (what follows `$` in the
composer); blank runs nothing. Output is captured, not interactive.
Returns `output` (the tail, at most 100 KB) and `exit_code`
(`-1` when it could not start). A command still running after two
minutes moves to the background: the answer then comes at once with
`exit_code` 0 and a note, and the process goes on as a background
process — `process_started`, a `process_line` per line,
`process_exited` and `background_process_done`.

Not followed: a command that moves to the background is reported by `process_*` pushes carrying its `pid`, but the answer does not say the `pid`; watch `igni.processes.list()` or `igni.events()`.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

<details>
<summary><code>await session.run_timeout()</code> → <code>int</code></summary>

Wire method `get_run_timeout` · access `client`

Read how long, in seconds, a client should wait for one run.

Takes no arguments. Returns the configured maximum run time; igni
does not stop a run at it, the client decides what to do.

</details>

<details>
<summary><code>session.shutdown()</code> → <code>Call[None, ShutdownEvent]</code></summary>

Wire method `shutdown` · access `client` · streams `background_process_done`, `process_exited`

Wind this session down: end its hooks, MCP servers, scheduler and background processes.

Takes no arguments and returns nothing once done. Runs the session's
`SessionEnd` hooks, disconnects its MCP servers, stops its
scheduler, and kills every background process igni is tracking —
which ends them with `process_exited` and
`background_process_done`. It does not stop igni or close the
connection. Each step's failure is logged, not raised.

Followed: `async with` the call to follow it: it yields the `process_exited` and `background_process_done` pushes that arrive while igni winds the session down — the processes this call kills — and ends with the answer.

</details>

<details>
<summary><code>await session.slash_commands()</code> → <code>list[SlashCommand]</code></summary>

Wire method `get_slash_commands` · access `client`

List every slash command this session takes.

Takes no arguments. Returns igni's built-in commands, commands
written as markdown files, skills a person can invoke, and
extensions' commands, told apart by `source`; each with its
`name`, `description` and `argument_hint`.

</details>

<details>
<summary><code>await session.status()</code> → <code>StatusUpdate</code></summary>

Wire method `get_status` · access `client`

Read this session's status: model, account, context size and permission mode.

Takes no arguments. Returns a `status_update` message, sent in
place of an `rpc_response`: the model and whether it is
configured, the igni server connection and account, the context
used and its window, the permission mode and the theme.

</details>

<details>
<summary><code>await session.switch(session_id: str)</code> → <code>InfoMessage</code></summary>

Wire method `switch_session` · access `client`

Make the session this request is routed to continue another stored session.

`session_id` is the stored session to continue; the conversation,
its history and its runs are read from it from now on. Returns an
`info` message, sent in place of an `rpc_response`, naming the
session switched to. The id is not checked: an unknown one starts
an empty session under that id.

</details>

<details>
<summary><code>await session.todos()</code> → <code>list[TodoItem]</code></summary>

Wire method `get_todos` · access `client`

Read the agent's to-do list in this session.

Takes no arguments. Returns each item's `content`, `status`
(`pending`, `in_progress`, `completed`) and `activeForm`
(how it reads while in progress). `todos_updated` pushes the list
whenever the agent changes it.

</details>

<details>
<summary><code>await session.toggle_verbose()</code> → <code>bool</code></summary>

Wire method `toggle_verbose` · access `client`

Turn showing the agent's routing decisions on or off for this session.

Takes no arguments. Returns the new setting: `true` when routing is
now shown. Not saved; the session's next settings reload resets it.

</details>

<details>
<summary><code>await session.typing(text)</code> → <code>None</code></summary>

Message `typing`

Show what this client is typing to every other client of this session.

`text` is the whole draft, not a change to it; empty clears it. igni relays it to every client attached, this one included, as a `Typing` event.

</details>

<details>
<summary><code>await session.upload_attachment(*, content_base64: str, filename: str)</code> → <code>UploadAttachmentResult</code></summary>

Wire method `upload_attachment` · access `client`

Store a file for this session, so a message can refer to it.

`filename` is the file's name (made safe for the disk; a clash gets
a `-N` suffix); `content_base64` its bytes, base64-encoded.
Returns `path` — the stored file's path, or an `attachment:<id>`
reference when attachments are kept in shared storage — and its
`size` in bytes; or `error` when the content is not valid base64.
Fails when the file cannot be stored.

</details>

<details>
<summary><code>session.visualization_action(*, action: str = '', params: dict[str, JsonValue] | None = None)</code> → <code>Call[VisualizationActionResult, DispatchVisualizationActionEvent]</code></summary>

Wire method `dispatch_visualization_action` · access `client` · streams `visualization_action_dispatched`

Tell this session the person used a control in a view the agent drew.

`action` is the control's action name; `params` the values the
view attached to it (JSON). The action is kept for the agent and
pushed to every window as `visualization_action_dispatched`.
Returns the action and params as recorded, with `ok`.

Followed: `async with` the call to follow it: it yields the `visualization_action_dispatched` push of this session carrying this `action` and `params`, and ends with it.

</details>

#### session.agents

The agents this session can hand work to.

<details>
<summary><code>await session.agents.discard(name: str)</code> → <code>DiscardEphemeralResult</code></summary>

Wire method `discard_ephemeral_agent` · access `client`

Delete an agent made during this session.

`name` is the ephemeral agent. Returns `ok` with its `name`;
or `ok: false` with `reason` when it is unknown or not
ephemeral.

</details>

<details>
<summary><code>await session.agents.list()</code> → <code>list[AgentInfo]</code></summary>

Wire method `get_agent_details` · access `client`

List the agents this session can hand work to.

Takes no arguments. Returns each agent's name, description, tools,
model, MCP servers, tags, system prompt, where it was defined, and
whether it is ephemeral (made during this session, not yet saved).

</details>

<details>
<summary><code>await session.agents.promote(name: str, *, target: str | None = None)</code> → <code>PromoteEphemeralResult</code></summary>

Wire method `promote_ephemeral_agent` · access `window`

Keep an agent made during this session, as a project or personal agent.

`name` is the ephemeral agent; `target` is `project` (the
default: the project's agents) or `personal` (the person's own).
Returns `ok` with the agent's `name` and where it was saved
(`dest`); or `ok: false` with `reason` when the agent is
unknown, not ephemeral, or the destination exists.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### session.auth

This session's sign-in to igni server.

<details>
<summary><code>await session.auth.reload_credentials()</code> → <code>StatusUpdate</code></summary>

Wire method `reload_cloud_credentials` · access `window`

Read the saved sign-in again, so this session acts as whoever is signed in now.

Takes no arguments. Use it after a sign-in made elsewhere (another
session, another window). Returns the session's status afterwards —
model, cloud connection, account, context size, permission mode — as
a `status_update` message, sent in place of an `rpc_response`.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

<details>
<summary><code>await session.auth.sign_out()</code> → <code>StatusUpdate</code></summary>

Wire method `clear_cloud_credentials` · access `window` · streams `notifications_changed`

Sign this session out of igni server.

Takes no arguments. The session forgets its cloud credentials, and
the signed-in person's notifications stop arriving and leave the
badges (`notifications_changed`). Returns the session's status
afterwards as a `status_update` message, sent in place of an
`rpc_response`.

Not followed: `notifications_changed` carries the new counts, not what changed them; read `igni.notifications.counts()`.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### session.context

This session's context window: how full it is, and compacting it.

<details>
<summary><code>await session.context.breakdown()</code> → <code>ContextBreakdown</code></summary>

Wire method `get_context_breakdown` · access `client`

Split this session's context into what compaction can shrink and what it cannot.

Takes no arguments. Returns the `total` tokens, the part taken by
the conversation's runs (`runs`, which `/compact` can shrink),
and the `floor` — instructions, tools and the rest that stays.
Zeros when it cannot be measured.

</details>

<details>
<summary><code>await session.context.compact(*, ctx_tokens: int, max_ctx: int)</code> → <code>SessionCleared | None</code></summary>

Wire method `compact_if_needed` · access `client`

Compact this session's conversation when its context is nearly full.

`ctx_tokens` is the context the last turn used and `max_ctx`
the model's window; at 80% or more the conversation is summarised
and replaced by the summary (the `PreCompact` hooks may refuse).
Returns a `session_cleared` message, sent in place of an
`rpc_response`, carrying the `summary`; or `null` (in an
`rpc_response`) when nothing was compacted.

</details>

<details>
<summary><code>await session.context.tokens()</code> → <code>int</code></summary>

Wire method `count_context_tokens` · access `client`

Estimate how many tokens this session's conversation takes up.

Takes no arguments. Returns the estimate (`0` when it cannot be
read); a positive estimate also becomes the context size
`get_status` reports.

</details>

#### session.files

Files in this session's project folder.

<details>
<summary><code>await session.files.complete(*, limit: int = 50, query: str = '')</code> → <code>FileCompletion</code></summary>

Wire method `complete_files` · access `client`

Complete a file path typed after `@`, from this session's project.

`query` is what was typed so far (empty matches everything);
`limit` caps the matches returned (default 50). Returns the
matching project-relative paths, best first, and `total`: how
many matched before the cap. The project's file list is read once
per session.

</details>

<details>
<summary><code>await session.files.pick_dir(*, start: str | None = None)</code> → <code>PickDirResult</code></summary>

Wire method `pick_dir_native` · access `client`

Open the operating system's folder picker on igni's machine and return the choice.

`start` is the folder the picker opens in (this session's project
when absent or empty). igni runs on the person's machine, so the
dialog appears on their desktop; it waits as long as they take, so
give the call a long timeout. Returns the chosen `path`, or
`cancelled`, or `error` when no native dialog is available.

</details>

<details>
<summary><code>await session.files.read(path: str)</code> → <code>ReadFileResult</code></summary>

Wire method `read_file` · access `client`

Read a file for preview: one of this session's project, igni's data, or an attachment.

`path` is relative to the project, absolute, or an
`attachment:<id>` reference. Returns the resolved `path`, its
`contents` and `size`, and a `language` hint for highlighting;
or `error` when the file is missing, a directory, too large to
preview (256 KiB), unreadable, or outside the folders igni lets a
client read.

</details>

<details>
<summary><code>await session.files.search(query: str)</code> → <code>SearchCodeResult</code></summary>

Wire method `search_code` · access `client`

Find where a snippet of code appears in this session's project.

`query` is the snippet, matched exactly; one shorter than five
characters finds nothing. Returns up to 20 `matches` (path, first
and last line, a preview), `truncated` when there may be more or
the search timed out, and `error` when it failed.

</details>

#### session.history

This session's conversation as stored: read, search, cut back.

<details>
<summary><code>await session.history.get()</code> → <code>list[ChatTurn]</code></summary>

Wire method `get_chat_history` · access `client`

Read a session's conversation, turn by turn, as a client draws it.

`session_id` names the session. Returns the conversation in
order, one entry per item, told apart by `role`: the person's
message (`user`), the agent's answer (`assistant`), its
reasoning (`thinking`), a tool call and its result (`tool`), a
submitted plan (`plan`), a run's token counts (`stats`), and a
view the agent drew (`visualization`). Sub-agents' runs are left
out.

</details>

<details>
<summary><code>await session.history.search(query: str, *, limit: int = 50)</code> → <code>list[ChatSearchHit]</code></summary>

Wire method `search_chat` · access `client`

Find text in a session's conversation.

`session_id` names the session; `query` is the text to find
(case-insensitive; blank finds nothing); `limit` caps the hits
(default 50). Returns one hit per match, in conversation order:
its index in `get_chat_history`, its role and run, a snippet
around it, and where the match sits in the snippet.

</details>

<details>
<summary><code>await session.history.truncate(run_id: str)</code> → <code>TruncateHistoryResult</code></summary>

Wire method `truncate_history` · access `client`

Drop a run from a session's history, with every run after it.

`session_id` names the session; `run_id` the first run to drop
(a top-level run, as `get_chat_history` carries it). Use it to
edit and resend a message. Returns how many runs were `removed`,
or `error` when the session or the run is not found or the
history could not be saved.

</details>

#### session.hooks

The hooks that run on this session's events.

<details>
<summary><code>await session.hooks.list()</code> → <code>list[HookEntryView]</code></summary>

Wire method `get_hooks_details` · access `client`

List the hooks this session runs.

Takes no arguments. Returns one row per hook: the `event` it runs
on, its `type` (a shell `command` or an HTTP `url`), the
`matcher` that narrows it, its timeout, whether it runs in the
background, and the HTTP headers it sends.

</details>

<details>
<summary><code>await session.hooks.reload()</code> → <code>InfoMessage</code></summary>

Wire method `reload_hooks` · access `client`

Read this session's hook configuration again.

Takes no arguments. Returns an `info` message, sent in place of an
`rpc_response`, saying how many hooks are now active.

</details>

#### session.loop

This session's loop: a task the agent repeats until it is done.

<details>
<summary><code>await session.loop.cancel()</code> → <code>bool</code></summary>

Wire method `cancel_pending_loop` · access `client`

End this session's running `/loop`.

Takes no arguments. Returns `true` when a loop was ended;
`false` when there was none or it is paused (a paused loop is
resumed or left alone, not cancelled).

</details>

<details>
<summary><code>await session.loop.next_iteration()</code> → <code>LoopAdvance | None</code></summary>

Wire method `pop_pending_loop_iteration` · access `client`

Take the next step of this session's `/loop`, for the client to send.

Takes no arguments. Returns `null` when there is no loop or it is
paused. Otherwise `kind` says what happened: `step` carries the
`prompt` to send as the next message (and `display_prompt` to
show), the iteration number and how many remain; `completed`
says the loop reached its cap and ended; `safety_paused` says it
reached the hard cap and paused.

</details>

<details>
<summary><code>await session.loop.pause()</code> → <code>bool</code></summary>

Wire method `loop_pause` · access `client`

Pause this session's `/loop` after the current iteration.

Takes no arguments. Returns `true` when the loop is now paused
(or already was), `false` when there is no loop.

</details>

<details>
<summary><code>await session.loop.resume()</code> → <code>str</code></summary>

Wire method `loop_resume` · access `client`

Resume this session's paused `/loop`.

Takes no arguments. Returns the prompt of the iteration to run next,
for the client to send as a message — nothing runs on its own — or
`""` when there is no paused loop.

</details>

<details>
<summary><code>await session.loop.status()</code> → <code>LoopStatusSnapshot</code></summary>

Wire method `loop_status` · access `client`

Read the state of this session's `/loop`.

Takes no arguments. Returns whether a loop is `active` and
`paused`, its prompt, which iteration it is on and how many
remain, whether its cap was set explicitly, and the total the agent
announced, if any.

</details>

#### session.mcp

MCP servers this session connects to, and their tools.

<details>
<summary><code>await session.mcp.connect(server_name: str)</code> → <code>InfoMessage</code></summary>

Wire method `mcp_connect` · access `client`

Connect one configured MCP server to this session.

`server_name` is the server's name in the MCP configuration.
Returns an `info` message, sent in place of an `rpc_response`.
A server that could not connect is not an error: read
`get_mcp_server_details` for its `error`.

</details>

<details>
<summary><code>await session.mcp.disconnect(server_name: str)</code> → <code>InfoMessage</code></summary>

Wire method `mcp_disconnect` · access `client`

Disconnect one MCP server from this session.

`server_name` is the server's name in the MCP configuration.
Returns an `info` message, sent in place of an `rpc_response`,
whether or not the server was connected.

</details>

<details>
<summary><code>await session.mcp.ensure()</code> → <code>McpInitResult</code></summary>

Wire method `ensure_mcp` · access `client`

Connect this session's configured MCP servers, once.

Takes no arguments. The first call connects every configured server
and rebuilds the agent with their tools; later calls do nothing.
Returns the servers `connected`, the ones that `failed` with
their errors, whether the agent was `rebuilt`, and, when nothing
was done, `skipped_reason` (`already_initialized`,
`no_configured_servers`, `no_clients_connected`).

</details>

<details>
<summary><code>await session.mcp.server_details()</code> → <code>list[McpServerSnapshot]</code></summary>

Wire method `get_mcp_server_details` · access `client`

Describe each of this session's MCP servers in full.

Takes no arguments. Returns one row per server: whether it is
connected, its transport, its tools (names, descriptions, the ones
switched off), its resources and prompts, the last error connecting
it, and whether policy blocks it. Each server is asked in turn, so
a slow one slows the answer.

</details>

<details>
<summary><code>await session.mcp.servers()</code> → <code>list[McpServerSummary]</code></summary>

Wire method `get_mcp_servers` · access `client`

List this session's configured MCP servers, in configuration order.

Takes no arguments. Returns one `{name, connected}` row per
server.

</details>

<details>
<summary><code>await session.mcp.set_tool_enabled(*, enabled: bool, server: str, tool: str)</code> → <code>McpToolToggleResult</code></summary>

Wire method `set_mcp_tool_enabled` · access `client`

Switch one MCP server's tool on or off for this project.

`server` and `tool` name the tool; `enabled` is its new state.
The choice is saved in the project's `.igni/mcp-tool-state.json`.
Returns the `server`, `tool` and `enabled` as recorded; the
server and tool are not checked to exist. Fails when the state file
cannot be written.

</details>

<details>
<summary><code>await session.mcp.status()</code> → <code>list[McpServerStatus]</code></summary>

Wire method `get_mcp_status` · access `client`

List this session's MCP servers and whether each is connected.

Takes no arguments. Returns one `{name, connected}` row per
server, in no particular order.

</details>

#### session.models

The models this session can use, and switching between them.

<details>
<summary><code>await session.models.list()</code> → <code>ModelRegistryResult</code></summary>

Wire method `get_model_registry` · access `client`

List the models this session can run on.

Takes no arguments. Returns the `default` model's name, the
largest context window configured, and `registry`: every model by
name, with its provider and settings.

</details>

<details>
<summary><code>await session.models.switch(model_name: str)</code> → <code>InfoMessage</code></summary>

Wire method `switch_model` · access `client`

Make another model the one this session's agent runs on.

`model_name` is a name from the model registry
(`get_model_registry`). The choice is also saved as the default
for new sessions. Returns an `info` message, sent in place of an
`rpc_response`, saying the model switched, with a note for any
part of the choice that could not be saved. Fails when the model is
not in the registry.

</details>

#### session.permissions

Saved permission rules for tool calls.

<details>
<summary><code>await session.permissions.check(*, func_name: str, tool_args: ToolCallArgs, tool_name: str)</code> → <code>Literal['allow', 'ask', 'deny']</code></summary>

Wire method `check_permission` · access `client`

Look up the saved permission level for one tool call.

`tool_name` and `func_name` name the tool and its function;
`tool_args` are the call's arguments, which argument rules match
against. The rules are read from this session's project and the
person's settings files. Returns `allow`, `ask` or `deny`:
the last matching argument rule, else the tool's own level, else
`ask`. The session's permission mode is not applied.

</details>

<details>
<summary><code>await session.permissions.save_rule(*, level: Literal['allow', 'ask', 'deny'], rule: str)</code> → <code>None</code></summary>

Wire method `save_permission_rule` · access `window`

Save a permission rule for this session's project.

`rule` is a permission rule (`Bash(git status)`, a tool name);
`level` is `allow`, `ask` or `deny`. The rule is written to
the project's `.igni/settings.local.json` (the person's own when
there is no project). Returns nothing. Fails when the settings file
cannot be written.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### session.plan

Plan mode: the plan the agent submitted, and the person's decision.

<details>
<summary><code>session.plan.approve(*, run_id: str = '')</code> → <code>Call[PlanDecisionResult, ApprovePlanEvent]</code></summary>

Wire method `approve_plan` · access `approver` · streams `permission_mode_changed`, `plan_decided`

Approve the plan the agent submitted, so it leaves plan mode and carries it out.

`run_id` is the run that submitted the plan (`plan_submitted`
carries it). The decision is recorded, the session's permission
mode returns to the one it started in (`permission_mode_changed`
when it changes), and `plan_decided` tells every window. Returns
the `run_id`, the `decision`, `mode_status` describing the
mode change, and `ok`; `ok: false` with `error` when
`run_id` is empty or the decision could not be recorded.

Followed: `async with` the call to follow it: it yields the `plan_decided` push whose `run_id` is this call's, and ends with it, or with the answer when `ok` is false. A change of permission mode is in the answer's `mode_status`.

Access: `approver`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop, a program needs an approver token the window minted (`Local(approver_token=...)`); with the lockfile's token it gets `AccessRefused`.

</details>

<details>
<summary><code>session.plan.dismiss(*, run_id: str = '')</code> → <code>Call[PlanDecisionResult, DismissPlanEvent]</code></summary>

Wire method `dismiss_plan` · access `client` · streams `plan_decided`

Send the submitted plan back for refining, staying in plan mode.

`run_id` is the run that submitted the plan. The decision is
recorded and `plan_decided` tells every window. Returns the same
shape as `approve_plan`, with an empty `mode_status`; `ok:
false` with `error` when `run_id` is empty.

Followed: `async with` the call to follow it: it yields the `plan_decided` push whose `run_id` is this call's, and ends with it, or with the answer when `ok` is false.

</details>

<details>
<summary><code>await session.plan.latest()</code> → <code>LatestPlanResult</code></summary>

Wire method `get_latest_plan` · access `client`

Read the plan the agent last submitted in this session, with its task list.

Takes no arguments. Returns the `latest` plan's text, every plan
submitted before it (`history`), the to-do list (`tasks`), and
`state`: `pending` while a plan is waiting for a decision, empty
when none was submitted.

</details>

#### session.plugins

Plugins installed into this session's project.

<details>
<summary><code>await session.plugins.contents(name: str)</code> → <code>PluginContents</code></summary>

Wire method `get_plugin_contents` · access `client`

Show what an installed plugin contains.

`name` is the installed plugin. Returns its folder and its
skills, agents, hooks, MCP servers and tools, with its README; or
`error` when no such plugin is installed.

</details>

<details>
<summary><code>await session.plugins.install(ref: str, *, install_ref: str | None = None)</code> → <code>InfoMessage</code></summary>

Wire method `install_plugin` · access `window`

Install a plugin from a git repository or a marketplace.

`ref` is a git URL or `@<marketplace>/<plugin>`; `install_ref`
the branch, tag or commit to check out (the marketplace's, or the
default branch, when absent). The plugin is active in this session
at once. Returns an `info` message, sent in place of an
`rpc_response`, whose text says what was installed — or why not:
git missing, an unknown marketplace entry, the organisation's
policy, a git error.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

<details>
<summary><code>await session.plugins.list()</code> → <code>list[PluginInfo]</code></summary>

Wire method `get_plugin_details` · access `client`

List the installed plugins.

Takes no arguments. Returns each plugin's name, version,
description, where it came from, whether it is enabled (a plugin
the organisation manages always is), the commit it is pinned to,
and what it brings: skills, agents, hooks, MCP servers.

</details>

<details>
<summary><code>await session.plugins.preview(source: str, *, branch: str | None = None, subdir: str | None = None)</code> → <code>PluginContents</code></summary>

Wire method `preview_plugin` · access `client`

Show what a plugin contains without installing it.

`source` is the plugin's git URL (optionally followed by a
subfolder); `branch` the branch, tag or commit to read (the
default branch when absent); `subdir` the plugin's folder inside
the repository, which wins over one in `source`. The repository
is cloned to a temporary place. Returns the same shape as
`get_plugin_contents`, with `preview_source` naming what was
read; or `error` when the organisation's policy refuses the
source, git is missing, or the clone failed.

</details>

<details>
<summary><code>await session.plugins.remove(name: str)</code> → <code>InfoMessage</code></summary>

Wire method `remove_plugin` · access `window`

Uninstall a plugin.

`name` is the installed plugin. Returns an `info` message, sent
in place of an `rpc_response`, whose text says it was removed, or
why not.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

<details>
<summary><code>await session.plugins.set_enabled(*, enabled: bool, name: str)</code> → <code>InfoMessage</code></summary>

Wire method `set_plugin_enabled` · access `window`

Switch an installed plugin on or off.

`name` is the installed plugin; `enabled` its new state. The
choice is saved and this session reloads its plugins. Returns an
`info` message, sent in place of an `rpc_response`, whose text
says what happened — including a refusal: no such plugin, or one
the organisation manages.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

<details>
<summary><code>await session.plugins.update(name: str, *, install_ref: str | None = None)</code> → <code>InfoMessage</code></summary>

Wire method `update_plugin` · access `window`

Move an installed plugin to another commit.

`name` is the installed plugin; `install_ref` the branch, tag
or commit to move to (the remote's default branch when absent).
Returns an `info` message, sent in place of an `rpc_response`,
whose text names the commit now installed, or why not.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### session.runs

This session's runs that were received but not finished.

<details>
<summary><code>await session.runs.discard_interrupted(message_id: str)</code> → <code>DiscardInterruptedRunResult</code></summary>

Wire method `discard_interrupted_run` · access `client`

Forget one interrupted run, so it is not offered again.

`message_id` names the run (from `get_interrupted_runs`);
`session_id` the session it belongs to. Returns `ok: true` —
also when no such run exists, so a retry is harmless — or `ok:
false` with `error` when `message_id` is empty.

</details>

<details>
<summary><code>await session.runs.interrupted()</code> → <code>list[InterruptedRun]</code></summary>

Wire method `get_interrupted_runs` · access `client`

List a session's runs that stopped before they finished.

`session_id` names the session. Returns one row per run that was
cancelled or failed: the `message_id` and text of the message that
started it, when it arrived and when it stopped, why (`cancelled`
or `errored`) and the last error. A client offers to retry,
discard or edit each. A storage failure answers an empty list.

</details>

<details>
<summary><code>await session.runs.pending_messages()</code> → <code>list[PendingMessage]</code></summary>

Wire method `get_pending_messages` · access `client`

List a session's messages that were received but never answered.

`session_id` names the session. Returns the user messages still
pending at least a minute after they arrived — typically left by a
crash — oldest first, each with its text, when it arrived and its
`message_id`. A storage failure answers an empty list.

</details>

#### session.scheduler

Scheduled tasks of this session's project.

<details>
<summary><code>await session.scheduler.cancel(task_id: str)</code> → <code>InfoMessage</code></summary>

Wire method `cancel_scheduled_task` · access `client`

Cancel a scheduled task of this session's project.

`task_id` is the task's `id` (from `get_scheduled_tasks`). The
task is marked cancelled, so it does not run again; a run already
going is not stopped, but its outcome is not recorded. Returns an
`info` message, sent in place of an `rpc_response`. An unknown
id is not detected.

</details>

<details>
<summary><code>await session.scheduler.execute(description: str)</code> → <code>str</code></summary>

Wire method `execute_scheduled_task` · access `client` · streams `background_process_done`, `file_edited`, `http_retry_attempt`, `http_retry_succeeded`, `orchestrate_event`, `permission_mode_changed`, `process_exited`, `process_line`, `process_started`, `todos_updated`

Run a scheduled task's work now, in this session, and wait for the answer.

`description` is what the task asks the agent to do (a scheduled
task's `description`). The agent runs it as a stored task firing,
not as a live message: its run is not streamed to the windows, and
the task's own record is not touched. What its tools push while
they work still goes out. Returns the agent's answer as text.
Fails when the organisation's group policy refuses the run, or the
run fails.

Not followed: what the task's tools push carries nothing that says which run it came from, so it cannot be told from another run's in the same session; watch `igni.events()`.

</details>

<details>
<summary><code>await session.scheduler.list(*, include_done: bool = True)</code> → <code>list[ScheduledTask]</code></summary>

Wire method `get_scheduled_tasks` · access `client`

List the scheduled tasks of this session's project.

`include_done` (default `true`) lists finished, failed and
cancelled tasks too. Returns the tasks, latest scheduled first:
each one's `id`, `description`, when it is scheduled and was
created, its `status`, its `result` or `error`, and its
`recurrence` (empty for a one-shot task).

</details>

<details>
<summary><code>session.scheduler.start()</code> → <code>Call[None, StartSchedulerEvent]</code></summary>

Wire method `start_scheduler` · access `client` · streams `background_process_done`, `file_edited`, `http_retry_attempt`, `http_retry_succeeded`, `orchestrate_event`, `permission_mode_changed`, `process_exited`, `process_line`, `process_started`, `scheduler_completed`, `scheduler_started`, `todos_updated`

Start running this project's scheduled tasks as they fall due.

Takes no arguments and returns nothing; a scheduler already running
is left as it is. From then on each due task runs through the
agent: `scheduler_started` when it starts, `scheduler_completed`
with its result when it ends, and whatever its tools push between.

Followed: `async with` the call to follow it: it yields this session's `scheduler_started` and `scheduler_completed` pushes for as long as the block runs. What a task's tools push meanwhile carries nothing that says which run it came from, so it is not yielded; read it from `igni.events()`.

</details>

#### session.skills

The skills this session's agent can use.

<details>
<summary><code>await session.skills.definitions()</code> → <code>list[SkillDefinition]</code></summary>

Wire method `get_skill_definitions` · access `client`

List this session's skills with what each tells the agent.

Takes no arguments. Returns each skill's `name`, `description`
and `prompt` (the skill's body).

</details>

<details>
<summary><code>await session.skills.list()</code> → <code>list[SkillInfo]</code></summary>

Wire method `get_skill_details` · access `client`

Describe each of this session's skills in full.

Takes no arguments. Returns each skill's name, description,
version, category, argument hint, the context and agent it runs
in, whether a person can invoke it, its body and its folder.

</details>

<details>
<summary><code>await session.skills.names()</code> → <code>list[str]</code></summary>

Wire method `get_skill_names` · access `client`

List the names of the skills this session has loaded.

Takes no arguments. Returns the names, each usable as `/<name>`.

</details>

#### session.workflows

Workflows: scripted runs this session starts and follows.

<details>
<summary><code>session.workflows.cancel(workflow_run_id: str)</code> → <code>Call[WorkflowCancelResponse, CancelWorkflowEvent]</code></summary>

Wire method `cancel_workflow` · access `client` · streams `workflow_event`

Stop a running workflow of this session.

`workflow_run_id` is the run (from `run_workflow`). The
workflow is asked to stop, then terminated after a grace period;
its last `workflow_event` says it was cancelled. Returns
`cancelled: true` when a live run was stopped, `false` when
there was no such run or it had already ended, with the
`workflow_run_id` asked about.

Followed: `async with` the call to follow it: it yields the `workflow_event` pushes of `workflow_run_id` and ends with the run's last, or with the answer when `cancelled` is false.

</details>

<details>
<summary><code>await session.workflows.list()</code> → <code>list[WorkflowListItem]</code></summary>

Wire method `list_workflows` · access `client`

List the workflows this session's project can run.

Takes no arguments (any it is sent are ignored). Returns each workflow in
`.igni/workflows/*.mjs` (a project's shadowing the person's own
of the same name), sorted by name: its `name`, `description`,
`whenToUse`, `phases` and `path`. A file whose metadata cannot
be read is left out.

</details>

<details>
<summary><code>session.workflows.run(name: str, *, args: dict[str, JsonValue] | None = None)</code> → <code>Call[WorkflowRunResponse, RunWorkflowEvent]</code></summary>

Wire method `run_workflow` · access `client` · streams `workflow_event`

Start a workflow in this session and return its run id at once.

`name` is the workflow (from `list_workflows`); `args` its
input, a JSON object the workflow reads as it defines. Returns the
`workflow_run_id` and `name`. The run goes on in the
background: each step it takes is pushed as `workflow_event`
carrying that id, ending with `workflow_completed` or
`workflow_failed`. Fails when there is no such workflow or the
workflow runtime is missing.

Followed: `async with` the call to follow it: it yields every `workflow_event` push carrying the `workflow_run_id` igni answered with — those that came before the answer too — and ends with the run's `workflow_completed` or `workflow_failed`.

</details>

#### session.workspace

Whether this session's project folder is trusted.

<details>
<summary><code>await session.workspace.set_trust(decision: Literal['trust', 'distrust', 'once'])</code> → <code>WorkspaceTrustStatus</code></summary>

Wire method `set_workspace_trust` · access `window` · streams `workspace_trust_required`

Answer "Trust this folder?" for this session's project folder.

`decision` is `trust` (remembered), `once` (until igni exits)
or `distrust`. When trust changed, the session is rebuilt so the
folder's tools, hooks, plugins, language servers and configuration
come in or go. Every window showing the dialog for that folder is
told the new status (`workspace_trust_required`). Returns the new
status. Fails when the organisation's policy does not let the folder
be trusted.

Not followed: igni pushes `workspace_trust_required` only to the windows showing the trust dialog; the answer is the new status.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

<details>
<summary><code>await session.workspace.trust()</code> → <code>WorkspaceTrustStatus</code></summary>

Wire method `get_workspace_trust` · access `client`

Read whether this session's project folder is trusted.

Takes no arguments. Returns the folder's trust `state`
(`trusted`, `untrusted`, or `ask` when the person has not
decided), whether it `can_trust` it under the organisation's
policy and, if not, the `reason`, plus where the decision came
from. Until a folder is trusted its own tools, hooks, plugins and
configuration are not loaded.

</details>

#### Not for clients

| Wire method | Why |
|---|---|
| `deliver_service_events` | the platform's call: Fleet delivers an extension service's events on its own control connection |
| `extension_service_token` | an extension page's call: it hands the page its service's token, and only igni's window speaks for a page |
| `host_model` | an extension page's call: igni's window makes it for the page it hosts, setting `caller`, which igni honours from no other connection |
| `vm_sign_in` | the platform's call: Fleet signs a VM's igni in on its control connection |

| Message | Why a client does not send it |
|---|---|
| `cancel` | `cancel_run` does the same and answers, so `session.cancel()` calls it |
| `hitl_response` | answers one call of a pause and leaves the rest refused; `hitl_response_batch` answers every call of it, which is what `ApprovalRequested` sends |
| `mcp_toggle` | the methods `mcp_connect` and `mcp_disconnect` do the same, so `session.mcp.connect()` and `.disconnect()` call them |
| `model_switch` | the method `switch_model` does the same, so `session.models.switch()` calls it |
| `session_list` | the method `list_sessions` answers the same, so `session.list_sessions()` calls it |
| `session_switch` | the method `switch_session` does the same, so `session.switch()` calls it |
| `shutdown` | stops igni itself, for every window and program attached; no client of a person's igni should, and `session.shutdown()` winds one session down instead |

<!-- api-reference:end -->

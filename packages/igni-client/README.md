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

## Sessions

<!-- illustrative -->
```python
session = await igni.sessions.create(project_dir="/workspace/payments")
again = await igni.sessions.open(session.id)         # an existing one, approvals it waits on included
for entry in await igni.sessions.list():
    print(entry.session_id, entry.name, entry.run_count)
```

`sessions.default()` is the session igni opened at start. A session has
`history()`, `status()` (its model, context used and permission mode) and
`use_model(name)`; `igni.models.list()` says which models there are.

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
from igni_client.testing import FakeIgni

async with FakeIgni() as fake:
    fake.script = lambda text: [
        FakeIgni.approval("run_shell_command", command="rm -rf build"),
        *FakeIgni.answer("Cleaned the build directory."),
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

## Commands in the VM

Through Fleet, run a shell command in the producer's VM — as root, in a
shell — and stream its output as it is written. igni server decides who
may run what, and audits every command.

```python
from igni_client import IgniClient, Person
from igni_client.testing import CommandResult, FakeIgni

async with FakeIgni(gateway=True, tokens={"t-ada": "person:u-ada"}) as fake:
    fake.commands["pytest -q"] = CommandResult(stdout="12 passed\n")
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

## Anything else igni can do

`igni.rpc(method, **args)` calls any of igni's methods by name — the ones
its own app uses for plugins, MCP servers, scheduled tasks, workflows and
the rest — and `session.rpc(...)` does the same in one session:

```python
from igni_client import IgniClient
from igni_client.testing import FakeIgni

async with FakeIgni() as fake:
    fake.rpc_answers["get_scheduled_tasks"] = [{"task_id": "t-1", "description": "nightly review"}]
    async with IgniClient(fake.local()) as igni:
        print(await igni.rpc("get_scheduled_tasks", include_done=False))
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
from igni_client.testing import FakeIgni

async with FakeIgni(gateway=True, tokens={"t-ada": "person:u-ada"}) as fake:
    fake.busy_next(1)                       # the first connection is told "busy, retry"
    async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
        print("connected on attempt", fake.connections)
```

A local igni is not retried: one that closed has stopped, and the client
raises `Unavailable`.

## Testing your code

`igni_client.testing.FakeIgni` is igni on a loopback socket, scripted:
`script` decides what each prompt runs (`FakeIgni.answer(text)`,
`FakeIgni.approval(tool, **args)`, `Delay(seconds)`, or any message), and
`rpc_answers`, `models`, `history` and `commands` answer the rest. With
`gateway=True` it plays Fleet's gateway too: bearer tokens on
`/v1/connect`, `/v1/me` and `/v1/commands` through `fake.fleet(auth)`.

It records what your code did — `received`, `decisions`, `commands_run`,
`sessions` — and plays what Fleet does under you: `move()`,
`drop(code)`, `busy_next(n)` and `unbound_for(n)`.

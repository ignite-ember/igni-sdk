# igni-client

**Full documentation:** [ignite-ember.sh/docs/sdk/igni-client](https://ignite-ember.sh/docs/sdk/igni-client) — guides and the complete API reference, a page per topic.

**The Python SDK for driving an igni from your own program.**

igni is an AI agent that works on a person's projects. It runs on the
person's own machine, inside the igni desktop app, or in a VM of their
own in Fleet, the organisation's cloud. igni-client connects to one igni
from outside — a script, a backend, a CI job, a bot — and does there what
a person does in igni's window:

- **Run the agent.** Open a session, send a prompt and follow the answer
  token by token, tool call by tool call, or wait for the whole of it.
- **Answer it.** When the agent wants to run a tool that needs a yes,
  approve or refuse it, from your code or by a policy.
- **Use everything else igni has.** Every one of igni's methods — plans,
  history, MCP servers, plugins, scheduled tasks, workflows, background
  processes, notifications, sign-in — is a typed Python method, its
  arguments and result generated from igni's own contract. A call that
  makes igni stream events follows them, and only its own.
- **Run commands in a Fleet VM**, streaming their output.

It speaks the protocol igni's own app speaks, so anything the app can do,
your program can.

| Package | For |
|---|---|
| `igni-client` | your own program driving an igni from outside: sessions, prompts, approvals, every method igni has (this one) |
| `igni-extension` | an extension's process, inside igni: tools, hooks, host calls |
| `igni-service` | an extension's backend service: the organisation's shared data, igni server's calls |

Everything here runs in the organisation's own cloud or data centre, or on
the person's machine: igni server, Fleet, the igni you connect to, and
your program. Ignite Ember hosts none of it.

## Contents

- [Installing](#installing)
- [Quick start](#quick-start)
- [Concepts](#concepts)
  - [Where the igni is: Fleet or this machine](#where-the-igni-is-fleet-or-this-machine)
  - [Who you connect as: a person, an app, a space](#who-you-connect-as-a-person-an-app-a-space)
  - [Sessions, and igni as a whole](#sessions-and-igni-as-a-whole)
  - [Who may call what](#who-may-call-what)
  - [igni tells everyone everything](#igni-tells-everyone-everything)
  - [Typed from igni's contract](#typed-from-ignis-contract)
- [Guides](#guides)
  - [A run, token by token](#a-run-token-by-token)
  - [Approvals](#approvals)
  - [The whole answer at once](#the-whole-answer-at-once)
  - [Calls that stream](#calls-that-stream)
  - [Watching an igni](#watching-an-igni)
  - [Slash commands](#slash-commands)
  - [Commands in a Fleet VM](#commands-in-a-fleet-vm)
  - [When the connection changes under you](#when-the-connection-changes-under-you)
  - [Testing your program](#testing-your-program)
- [API reference](#api-reference)
  - [IgniClient](#igniclient)
  - [Session and Sessions](#session-and-sessions)
  - [Call](#call)
  - [Targets: Fleet and Local](#targets-fleet-and-local)
  - [Credentials: Person, App, Space](#credentials-person-app-space)
  - [Approvals and replies](#approvals-and-replies)
  - [Models, events and frames](#models-events-and-frames)
  - [Errors](#errors)
  - [igni_client.testing](#igni_clienttesting)
  - [igni's methods, by namespace](#ignis-methods-by-namespace)
- [Errors and troubleshooting](#errors-and-troubleshooting)
- [Changes since 0.1.0](#changes-since-010)

## Installing

```bash
pip install igni-client        # or: uv add igni-client
```

It needs Python 3.12 or later, and brings httpx, websockets, Pydantic and
PyJWT with `cryptography`.

Each release's wheels and sdists are also attached to igni-sdk's GitHub
release (`sdk-v<version>`), for a machine that cannot reach PyPI. The
versions, and working from an igni-sdk checkout, are in
[PUBLISHING_THE_SDKS.md](https://github.com/ignite-ember/igni-sdk/blob/main/docs/PUBLISHING_THE_SDKS.md).

## Quick start

Against a person's igni in Fleet, with an API key they made on igni's
portal:

<!-- illustrative -->
```python
from igni_client import Fleet, IgniClient, Person

key = Person.from_api_key("igpak1.…", server="https://igni.acme.internal")
async with IgniClient(Fleet("https://gw.acme.internal", auth=key)) as igni:
    session = await igni.sessions.create(project_dir="/workspace/payments")
    reply = await session.ask("Summarise the open pull requests", approve=False)
    print(reply)
```

Every example below runs as it is pasted. Instead of a real igni they use
`FakeIgni`, from `igni_client.testing`, which plays igni on a loopback
socket — so this one runs anywhere:

```python
from igni_client import IgniClient
from igni_client.testing import FakeIgni, Steps

async with FakeIgni() as fake:
    fake.runs.script = lambda text: Steps.answer("Two pull requests are open.")
    fake.methods.answers["get_todos"] = []           # what the fake answers igni's get_todos
    async with IgniClient(fake.local()) as igni:
        session = await igni.sessions.create(project_dir="/workspace/payments")
        reply = await session.ask("Summarise the open pull requests", approve=False)
        print(reply)                                 # Two pull requests are open.

        status = await session.status()              # a StatusUpdate
        print(status.model, status.permission_mode)
        todos = await session.todos()                # list[TodoItem]
        print(todos)
```

## Concepts

### Where the igni is: Fleet or this machine

A **target** says where the igni is and how to reach it.

- **`Fleet(url, auth=...)`** — a producer's igni in Fleet, reached
  through Fleet's gateway at `url`. The gateway authenticates you, wakes
  the producer's VM if it is asleep, and relays igni's socket. The first
  connection to a sleeping VM waits while it resumes — tens of
  milliseconds paused, a fraction of a second suspended; your program
  sees a pause, not an error.
- **`Local(project_dir)`** — the igni the desktop app runs for that
  project on this machine, found from the lockfile it writes there
  (`<project>/.igni/backend.lock`), which carries the token a
  program attaches with. A backend started by hand publishes the same
  lockfile, so `Local(project_dir=...)` attaches to it too, as a program
  (`standing` is `"program"` once the client is open — it is
  `"unknown"` until the lockfile is read, at open; it approves nothing).
- **`Local(url=..., token=...)`** — an igni you name directly, such as
  one started by hand with `--ws-port`. A hand-started backend mints its
  own window token, prints it once to stderr and requires it:
  `Local(url=..., token="<the printed token>")` connects as igni's window.
  The development opt-out `IGNI_DEV_NO_WS_TOKEN=1` (igni warns) starts one
  that takes no token, where every connection is the window. It prints
  `{"status": "ready", "ws_url": ...}` on stdout once it listens: read that
  line to know it is ready, and pass `--project-dir` so sessions have a
  folder.

<!-- illustrative -->
```python
from igni_client import Fleet, Local, Person

fleet = Fleet("https://gw.acme.internal", auth=Person.from_cli())
here = Local(project_dir="~/code/payments")          # the desktop app's igni for that project
by_hand = Local(url="ws://127.0.0.1:8765", token="<the printed token>")  # `python -m igni_core.backend --ws-port 8765`
```

Both speak the same protocol once open, so everything above the target is
the same code. Two things differ: only Fleet has `igni.commands` and
`igni.me()` (they are the gateway's), and only Fleet reconnects on its own
when the line drops — a local igni that closed has stopped.

### Who you connect as: a person, an app, a space

Through Fleet, the token you connect with decides whose igni you reach.

**A person** gives a program an **API key**. They make it on igni's
portal (*API keys*); it expires after 30, 90 or 365 days, and stops when
they revoke it, sign out everywhere or leave the organisation. The client
exchanges it with igni server for a 15-minute session as them, renewed as
needed. That session can do what the person can, except make more keys.

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

### Sessions, and igni as a whole

A **session** is one of igni's conversations: its own history, model,
permission mode and project folder. Most of igni's methods act on one
session, and are methods of its `Session`:

```python
from igni_client import IgniClient
from igni_client.testing import FakeIgni

async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
    session = await igni.sessions.create(project_dir="/workspace/payments")
    again = await igni.sessions.open(session.id)     # the same Session object; an id igni does not know is opened new, not an error
    default = await igni.sessions.default()          # the one igni opened at start
    for entry in await igni.sessions.list():
        print(entry.session_id, entry.name, entry.run_count)

    registry = await session.models.list()           # a ModelRegistryResult
    print(registry.default, list(registry.registry))
    notice = await session.models.switch("igni-1")   # a ModelSwitched
    print(notice.text)
```

The rest act on igni as a whole — the machine, the account, every
session — and are methods of `IgniClient`: `igni.processes`,
`igni.notifications`, `igni.auth`, `igni.marketplaces` and the others.
igni's contract says which is which (each method's *scope*), and the
SDK follows it.

### Who may call what

igni decides what a connection may do by the token it attached with — its
*standing* — and each method needs one of three access levels:

| Access | Who reaches it |
|---|---|
| `client` | any connection |
| `approver` | igni's window, or a program holding an approver token the window minted |
| `window` | igni's own window only |

- **Through Fleet**, igni on the VM takes no token: every connection —
  yours included — stands as igni's window and reaches every method.
- **On the desktop**, the app launches igni with a secret only its window
  holds. A program attached through the lockfile (`Local(project_dir)`)
  is a *program*: it runs sessions and calls every `client` method, but
  decides nothing for the person. Given an **approver token**, it also
  answers approvals — each time once: no saved rule, no change of
  permission mode.

A program's limits are what keeps the agent, which can read the lockfile
too, from approving its own tool calls. To let a program approve, the
person types `/programs` in igni's window, makes an approver token and
hands it over:

<!-- illustrative -->
```python
here = Local(project_dir="~/code/payments", approver_token="…")
# or set IGNI_APPROVER_TOKEN
```

igni forgets approver tokens when it quits, and revoking them in
`/programs` disconnects the programs using one.

Where igni-client knows the standing — a program, an approver, Fleet —
it refuses a call the connection cannot make before sending it, with
`AccessRefused`, the error igni would answer. Where it does not (a
`Local(url=..., token=...)` given a token by hand, which may be the
window's own secret), it sends the call and igni decides. Each method in
the [reference](#ignis-methods-by-namespace) says its access level.

### igni tells everyone everything

igni sends every message to every client attached to it — a person's
open window, an extension's page, your program. A person with igni open
sees your runs as they happen, and you see theirs. So nothing in
igni-client assumes a message is for it:

- a method's answer is matched by the id of the request it answers;
- `session.send()` follows its own run by the run's request id, and the
  approvals it answers;
- a [call that streams](#calls-that-stream) picks out its own events by
  what they carry — a workflow run's id, a process's pid;
- `igni.events()` and `session.events()` are for watching everything.

### Typed from igni's contract

igni publishes its whole protocol as a contract: every method's
arguments and result, every message on its socket, every push
notification's payload, as JSON Schema. igni-client is generated from it:

- `igni_client.models` — a Pydantic model for every type a client sends
  or reads, with igni's descriptions as docstrings;
- `igni_client.api` — every method a client calls, typed, grouped by
  namespace, igni's documentation as its docstring;
- the [method reference](#ignis-methods-by-namespace) at the end of this
  page.

A model of something igni sends keeps a field a newer igni adds, so an
older igni-client keeps working against a newer igni; a message type
newer than the SDK arrives as `Unknown`, with everything it carried.

## Guides

### A run, token by token

`session.send()` sends a prompt and yields the run it starts as it
happens: the answer a few tokens at a time, the model's reasoning, each
tool call and its result, sub-agents starting and finishing, the end.

```python
from igni_client import ContentDelta, IgniClient, RunCompleted, ToolCompleted, ToolStarted
from igni_client.testing import FakeIgni, Steps

async with FakeIgni() as fake:
    fake.runs.script = lambda text: [
        *Steps.answer("The payments service charges cards")[:2],
        ToolStarted(run_id="r-1", tool_name="read_file", friendly_name="Read file"),
        ToolCompleted(run_id="r-1", summary="src/charge.py"),
        ContentDelta(text=" and refunds them."),
        RunCompleted(run_id="r-1", input_tokens=900, output_tokens=12),
    ]
    async with IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        async for event in session.send("What does the payments service do?"):
            match event:
                case ContentDelta(text=text, is_thinking=False):
                    print(text, end="", flush=True)
                case ToolStarted(friendly_name=name):
                    print(f"\n[{name}]", end=" ")
                case RunCompleted(parent_run_id="", output_tokens=tokens):
                    print(f"\n{tokens} tokens")
```

Each event is a typed model of igni's message — `ContentDelta`,
`ReasoningStarted`, `ToolStarted`, `ToolCompleted`, `ToolError`,
`RunStarted`, `ModelCompleted`, `StreamingDone`, `RunCompleted`,
`RunError`, `TaskCreated`, a push notification and the rest; see
[Models, events and frames](#models-events-and-frames). A sub-agent's
events carry its `parent_run_id`.

`files={path: content}` attaches files to the prompt as the app attaches
them; `force=True` discards a run left interrupted in the session first.
The loop ends when the run does. Breaking out of it stops following the
run; the run goes on in igni. `await session.cancel()` stops it.

### Approvals

When the agent wants to run a tool that needs a yes — a shell command, an
edit, depending on the session's permission mode — igni pauses the run,
and the loop yields an `ApprovalRequested`. Answer it in the loop and the
same loop carries on with the resumed run:

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

- `approve(choice)` lets every call of the pause run: `"once"`, or
  `"always"` / `"similar"` to save a permission rule (igni's window only).
- `reject(remember=False)` refuses them; `remember=True` saves a rule
  refusing such calls from now on (igni's window only).
- From an approver, an answer that saves a rule raises `AccessRefused`
  before it is sent, and the pause stays open for an answer of `"once"`.
- `decide({requirement_id: Decision, ...})` answers each call on its own,
  with `Decision.allow(choice)` or `Decision.deny(remember=...)`.

A refused call never starts, so the resumed run sends no `ToolStarted`,
`ToolCompleted` or `ToolError` for it: the model reads the refusal as the
call's result, and the run goes on to its answer. A program counting
tool events counts only the calls that ran. (`FakeIgni` plays it so.)

igni asks about every call of one pause together and counts a call left
out as refused, so every answer covers them all: `decide()` raises
`ValueError` for a call it leaves out, and `RuntimeError` when the pause
was already answered. A loop that ends without
answering leaves the run waiting on igni's side; the next time the
session is attached igni shows the approval again, and
[`session.events()`](#watching-an-igni) offers it as an
`ApprovalRequested`.

A program without an approver token cannot answer: `approve()`,
`reject()` and `decide()` raise `AccessRefused` (a `NotAllowed`) before
anything is sent, and the run keeps waiting (see
[Who may call what](#who-may-call-what)). Where igni-client does not know
the standing (`Local(url=..., token=...)`), the answer is sent, and igni's
refusal comes as `NotAllowed` from the `send()` loop.

### The whole answer at once

`session.ask()` runs the prompt to the end and returns a `Reply`: the
answer's `text`, the model's `thinking`, every `ToolCompleted` in
`tools`, and the main run's `RunCompleted` with its token counts.
`approve=` answers approvals as they come: `True` allows every call,
`False` refuses every call, or a function of each `Requirement` — sync or
async — returns a `bool` or a `Decision`:

```python
from igni_client import Decision, IgniClient
from igni_client.testing import FakeIgni, Steps


def only_reads(requirement):
    return Decision.allow() if requirement.tool_name == "read_file" else Decision.deny()


async with FakeIgni() as fake:
    fake.runs.script = lambda text: [Steps.approval("read_file", path="src/auth.py"), *Steps.answer("It checks tokens.")]
    async with IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        reply = await session.ask("Explain src/auth.py", approve=only_reads)
        print(reply.text, reply.completed.output_tokens if reply.completed else 0)
        await session.queue("Then write tests for it")   # starts after the run going
```

Without `approve=`, a pause raises `ApprovalRequired` (its
`requirements` say what was asked); a failed run raises `RunFailed`.
`session.queue(text)` adds a prompt for after the run that is going.

### Calls that stream

Some of igni's methods make igni send events while it does the work, or
after: a workflow reports each step, a stopped process prints its last
lines, a sign-in says what it is doing. Each of those returns a **`Call`**.

**Await it** for the result, as any other method:

```python
from igni_client import IgniClient
from igni_client.models import WorkflowRunResponse
from igni_client.testing import FakeIgni

async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
    fake.methods.answers["run_workflow"] = WorkflowRunResponse(workflow_run_id="wf-1", name="nightly")
    session = await igni.sessions.create()
    started = await session.workflows.run("nightly", args={"branch": "main"})
    print(started.workflow_run_id)
```

**Enter it** with `async with` to follow the events this call causes,
too. `async with` starts listening before the call is sent, so nothing is
missed; `async for` yields only this call's events, typed, and ends when
igni has no more to send for it; `await call.result()` is the result:

```python
import asyncio

from igni_client import IgniClient
from igni_client.models import WorkflowRunResponse
from igni_client.testing import FakeIgni


def step(run_id, kind, seq):
    return {"workflow_run_id": run_id, "name": "nightly", "ts": seq, "seq": seq, "type": kind, "payload": {}}


async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
    session = await igni.sessions.create()

    async def run_workflow(args):
        async def report():
            await asyncio.sleep(0.05)
            await fake.socket.push("workflow_event", step("wf-someone-else", "step", 1), session_id=session.id)
            await fake.socket.push("workflow_event", step("wf-1", "step", 1), session_id=session.id)
            await fake.socket.push("workflow_event", step("wf-1", "workflow_completed", 2), session_id=session.id)

        asyncio.ensure_future(report())
        return WorkflowRunResponse(workflow_run_id="wf-1", name=args["name"])

    fake.methods.answers["run_workflow"] = run_workflow

    async with session.workflows.run("nightly") as run:
        async for event in run:                       # WorkflowEventPush, this run's only
            print(event.payload.seq, event.payload.type)
        print("run", (await run.result()).workflow_run_id)
```

Leaving the block stops listening; the work itself is igni's and goes on.
A call whose answer is an error raises it from `async for` as from
`await`; a connection that moves or drops while you follow raises
`RunInterrupted`.

These calls are followed, each by what igni's events carry:

| Method | Yields | Ends |
|---|---|---|
| `session.workflows.run(name)` | `workflow_event` of the run id igni answers with | the run's `workflow_completed` or `workflow_failed` |
| `session.workflows.cancel(id)` | `workflow_event` of that run | its last event, or the answer when nothing was cancelled |
| `igni.processes.stop(pid)` | `process_line`, `process_exited`, `background_process_done` of that pid | `background_process_done`, or the answer when it was not running |
| `session.plan.approve(run_id)`, `.dismiss(run_id)` | `plan_decided` of that run | that push, or the answer when `ok` is false |
| `session.visualization_action(...)` | `visualization_action_dispatched` of this session, action and params | that push |
| `session.scheduler.start()` | this session's `scheduler_started` and `scheduler_completed` | when you leave the block |
| `igni.auth.login()` | `login_status`, `login_result` | `login_result` |
| `igni.sessions.attach()` | the approvals it shows again and the runs it continues (`run_paused`, `requirement_details`, `stream_end`) | the `stream_end` |
| `session.cancel()` | the `info` and `stream_end` of the turn it stops | that `stream_end`, or the answer when no turn was running |
| `session.run_shell(command)` | `process_started`, `process_line`, `process_exited`, `background_process_done` of the command's pid, when it outlives the wait | `background_process_done`, or the answer when the command finished inside the wait |
| `session.scheduler.execute(...)` | what the task's tools push: `orchestrate_event`, `file_edited`, `todos_updated`, `process_started`, `permission_mode_changed`, `plan_submitted` | the answer |
| `session.auth.sign_out()`, `igni.notifications.list()`, `.mark_read()` | `notifications_changed` of that cause | the answer |
| `session.workspace.set_trust(...)` | `workspace_trust_required` of that path | the answer |
| `igni.window.model(...)` | `window_model_changed` carrying this call's token | the answer |

### Watching an igni

`igni.events()` yields every message igni sends from now on, from every
session and every client — runs, approvals, push notifications. A push on
a channel igni's contract types is that channel's class, its payload a
model: `ProcessLinePush`, `SessionNamedPush`, `TodosUpdatedPush`,
`NotificationsChangedPush` and the rest.

```python
import asyncio

from igni_client import IgniClient
from igni_client.models import SessionNamedPush
from igni_client.testing import FakeIgni

async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
    async def watch():
        async for event in igni.events():
            if isinstance(event, SessionNamedPush):
                return event.payload.name

    watching = asyncio.ensure_future(watch())
    await asyncio.sleep(0.05)
    await fake.socket.push("session_named", {"session_id": "s-1", "name": "Payments refactor"})
    print(await asyncio.wait_for(watching, 5))
```

`session.events()` is the same for one session, and offers each pause it
sees as an `ApprovalRequested` — among them the approvals a session was
waiting on, which igni shows again when it is attached. Answering one
resumes that run, whose events follow in the same loop.

### Slash commands

`session.command(text)` runs one of igni's slash commands, as typed in its
composer, and returns igni's `CommandResult`: what to show (`kind`,
`content`) and what it asks a client to do (`action`).

```python
from igni_client import IgniClient
from igni_client.testing import FakeIgni

async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
    session = await igni.sessions.create()
    result = await session.command("/help")
    print(result.kind, result.content)   # against a real igni, /help is an action for the window: kind "action", content empty
    await session.typing("half a tho")              # every client sees the draft
```

The commands that switch approvals off, change what igni loads or whom it
signs in to (`/bypass`, `/accept`, `/plugin`, `/eject`, `/login`, `/logout`) answer
an `error` to anything but igni's window.

### Commands in a Fleet VM

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
        print(await igni.me())
```

`await run.wait()` collects it instead (into `run.stdout` and
`run.stderr`). A producer runs commands in its own VM; an org admin may
name another with `producer="person:<id>"`. `igni.me()` says who the
gateway takes you for. A local igni has no gateway, so neither is
available there: both raise `NotSupported`.

A line of the gateway's stream that is not a JSON object is passed over
with a warning on the `igni_client.commands.run` logger, and the run goes
on.

### When the connection changes under you

- **Fleet moved the VM.** When a node drains or fails, the gateway wakes
  the VM on another node and reconnects behind you. The client re-attaches
  its sessions on its own; a run or call going at that moment ends with
  `RunInterrupted` — it may or may not have finished, so read the
  session's history (`session.history.get()`).
- **Busy.** With no room for the VM right away, the gateway answers "busy,
  retry"; the client tries again, backing off (`Backoff`), and raises
  `Unavailable` if it stays busy.
- **Not bound yet.** A VM that has just woken answers "not bound to a
  producer yet" for a moment; calls are asked again.
- **Refused.** `AuthError` for a credential igni does not accept,
  `NotAllowed` for a producer that is no longer active, a lapsed licence,
  or a command in somebody else's VM. Neither is retried.

```python
from igni_client import Backoff, IgniClient, Person
from igni_client.testing import FakeGateway, FakeIgni

async with FakeIgni(gateway=FakeGateway({"t-ada": "person:u-ada"})) as fake:
    fake.socket.busy_next(1)                # the first connection is told "busy, retry"
    async with IgniClient(fake.fleet(Person("t-ada")), backoff=Backoff(first=0.01)) as igni:
        print("connected on attempt", fake.socket.connections)
```

A local igni is not reconnected: one that closed has stopped, and the
client raises `Unavailable`.

### Testing your program

`igni_client.testing` plays igni — and Fleet's gateway in front of it —
in your test's own process, on a real loopback socket, so your program
runs against it unchanged:

```python
from igni_client import IgniClient
from igni_client.models import ProcessTailResult
from igni_client.testing import FakeIgni, Steps, sample

async with FakeIgni() as fake:
    fake.runs.script = lambda text: Steps.answer(f"you said {text}")
    fake.methods.answers["read_process_tail"] = sample(ProcessTailResult)   # any valid answer
    fake.methods.answers["get_todos"] = lambda args: []                      # or a function of the args
    async with IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        assert str(await session.ask("hi")) == "you said hi"
        tail = await igni.processes.tail(1)
        assert tail == sample(ProcessTailResult)

    [call] = [c for c in fake.methods.calls if c.method == "read_process_tail"]
    assert call.args == {"pid": 1, "tail": 200}
```

It records what your program did — `fake.socket.received` (the typed
frames it sent), `fake.methods.calls`, `fake.runs.decisions`,
`gateway.commands_run` — and plays what igni and Fleet do under you:
`fake.socket.push(channel, payload)`, `fake.socket.move()`,
`drop(code)`, `busy_next(n)` and `fake.methods.unbound_for(n)`. See
[igni_client.testing](#igni_clienttesting).

## API reference

### IgniClient

`IgniClient(target, *, backoff=None)` — a connection to one igni. Open it
with `async with` (or `await igni.connect()` and `await igni.close()`).

| Member | What it is |
|---|---|
| `sessions` | `Sessions`: create, open, list sessions |
| `events()` | every message igni sends from now on (an async iterator of `Event`) |
| `commands` | `Commands`, shell commands in a Fleet VM (`NotSupported` locally) |
| `me()` | who the gateway takes you for: a `Me` (`NotSupported` locally) |
| `client_id` | igni's name for this connection; its own messages carry it |
| `target` | the `Fleet` or `Local` it was made with |
| `agents`, `approvers`, `auth`, `extensions`, `files`, `marketplaces`, `notifications`, `processes`, `window`, `check_for_update()`, `group_policy()` | igni's methods for igni as a whole, [by namespace](#ignis-methods-by-namespace) |

`backoff=Backoff(attempts=5, first=0.5, most=8.0)` paces opening the
socket again after Fleet said busy or the line dropped.

### Session and Sessions

`igni.sessions` (`Sessions`):

| Method | Returns |
|---|---|
| `create(project_dir=None)` | a new `Session`, working in `project_dir` (igni's own project when left out) |
| `open(session_id, project_dir=None)` | that `Session` |
| `default()` | the `Session` igni opened at start |
| `list()` | `list[SessionListEntry]`, every session of igni's own project, newest first |
| `attach(*, project_dir="", session_id="")` | igni's own call underneath: an `AttachSessionResult` |

A `Session`:

| Member | What it is |
|---|---|
| `id`, `project_dir` | the session's id and folder, as igni bound them |
| `send(text, *, files=None, force=False)` | the run, event by event: an async iterator of `Event` and `ApprovalRequested` |
| `ask(text, *, files=None, approve=None)` | the whole answer: a `Reply` |
| `queue(text)` | a prompt for after the run going |
| `events()` | every message about this session from now on, pauses as `ApprovalRequested` |
| `command(text)`, `typing(text)` | a slash command; this client's draft |
| `cancel()`, `status()`, `todos()`, … and `plan`, `history`, `context`, `loop`, `models`, `mcp`, `plugins`, `scheduler`, `workflows` and the other namespaces | igni's methods for one session, [by namespace](#ignis-methods-by-namespace) |

### Call

What a [method that streams](#calls-that-stream) returns
(`igni_client.calls.Call[R, E]`, `R` its result and `E` its events).

| Use | What it does |
|---|---|
| `await call` | sends it; its result |
| `async with call:` | sends it, listening for its events from before it is sent |
| `async for event in call` | inside the block: this call's events, then the end |
| `await call.result()` | inside the block: its result, once it came |
| `call.method` | its wire method |

Iterating a call that was not entered raises `RuntimeError`, as does
entering one twice.

### Targets: Fleet and Local

| Target | |
|---|---|
| `Fleet(url, *, auth, http=None)` | a producer's igni through Fleet's gateway at `url`; `auth` is a `Person`, `App` or `Space`; `http` an `httpx.AsyncClient` to use |
| `Local(project_dir=".", *, url=None, token=None, approver_token=None)` | an igni on this machine: from the project's lockfile, or at `url` with `token` |

Each has `standing` — what igni stands the connection as (`"window"`,
`"approver"`, `"program"` or `"unknown"`; see
[Who may call what](#who-may-call-what)) — and `describe()`. A
`Local(project_dir)` reads its lockfile when the client opens, so until
then its `standing` is `"unknown"` (or `"approver"`, with an approver
token); read it inside `async with IgniClient(...)`. `Local.approves`
says whether it has an approver token; `IGNI_APPROVER_TOKEN` gives it one.

### Credentials: Person, App, Space

| Credential | Made with |
|---|---|
| `Person(token)` | an organisation-pinned session token |
| `Person.from_api_key(key=None, *, server=None)` | a person's API key, exchanged for 15-minute sessions (`IGNI_API_KEY`, `IGNI_SERVER_URL`) |
| `Person.from_cli(path=None)` | the session `igni login` keeps |
| `App(app_id, *, server, key_file=None, key_pem=None)` | an app signing in as itself, by its private key; `App.generate_key(path)`, `app.public_jwks()`, `await app.aclose()` |
| `await app.spaces.declare(external_id)` | a `Space`, one end user of the app; also `get`, `list`, `delete` |

Each is a `TokenSource`: `await source.token()` is a fresh bearer token.

### Approvals and replies

| Name | What it is |
|---|---|
| `ApprovalRequested` | a paused run: `requirements` (each a `Requirement`), `run_id`, `approve(choice="once")`, `reject(remember=False)`, `decide({id: Decision})`, `answered` |
| `Decision` | one call's answer: `Decision.allow(choice="once")`, `Decision.deny(remember=False)` |
| `Requirement` | one tool call waiting: `requirement_id`, `tool_name`, `friendly_name`, `tool_args`, `details`, `agent_path` |
| `Reply` | `ask()`'s answer: `text`, `thinking`, `tools`, `completed`; `str(reply)` is the text |

### Models, events and frames

- **`igni_client.models`** — every type igni's contract defines that a
  client sends or reads: arguments (`ProcessTailArgs`), results
  (`ProcessTailResult`, `ModelRegistryResult`, `ChatTurn` — a union told
  apart by `role`), messages and push payloads. Generated; the
  contract's descriptions are their docstrings.
- **`igni_client.events`** — the messages igni sends, re-exported:
  `ContentDelta`, `ReasoningStarted`, `RunStarted`, `ToolStarted`,
  `ToolCompleted`, `ToolError`, `ModelCompleted`, `StreamingDone`,
  `RunCompleted`, `RunError`, `RunPaused`, `Requirement`,
  `RequirementDetails`, `RequirementResolved`, `StreamEnd`, `TaskCreated`,
  `TaskUpdated`, `TaskIteration`, `TaskStateUpdated`, `SessionCleared`,
  `SessionListResult`, `StatusUpdate`, `CommandResult`, `InfoMessage`
  (`info`), `ErrorMessage` (`error`), `SchedulerEvent`, `Welcome`,
  `Typing`, `UserMessageReceived`, `PushNotification`, `RpcResponse`; and
  `Unknown`, a message type newer than this igni-client. `Event` is their
  base (`type`, `id`, `session_id`, `event_seq`), `RunEvent` a run's
  (`run_id`, `parent_run_id`). `parse_event(dict)` reads one.
- **Push notifications** — a `PushNotification` on a channel the contract
  types is that channel's class, named for it: `BackgroundProcessDonePush`,
  `FileEditedPush`, `LoginResultPush`, `LoginStatusPush`,
  `NotificationsChangedPush`, `OrchestrateEventPush`,
  `PermissionModeChangedPush`, `PlanDecidedPush`, `PlanSubmittedPush`,
  `ProcessExitedPush`, `ProcessLinePush`, `ProcessStartedPush`,
  `SchedulerCompletedPush`, `SchedulerStartedPush`, `SessionNamedPush`,
  `TodosUpdatedPush`, `WorkflowEventPush`, `WorkspaceTrustRequiredPush` and
  the rest (`igni_client.models.PUSH_TYPES`). One on a newer channel is a
  plain `PushNotification` with its payload as JSON.
- **`igni_client.frames`** — the messages a client sends: `UserMessage`,
  `QueueMessage`, `HitlResponseBatch`, `HitlDecision`, `RpcRequest`,
  `Command`, `Typing`, `CancelLogin`, and the ones igni-client types but
  does not send (`Shutdown`, `Cancel`, `HitlResponse`, `SessionList`,
  `SessionSwitch`, `ModelSwitch`, `McpToggle`; the
  [reference](#ignis-methods-by-namespace) says why). `frame.wire()` is
  its JSON.

### Errors

Everything igni-client raises on purpose is an `IgniClientError`:

| Error | When | What to do |
|---|---|---|
| `Unavailable` | igni could not be reached, went away, is busy, or did not answer in time | try again later |
| `AuthError` | the credential was refused | fix or renew it |
| `NotAllowed` | igni said no, and asking again will not change it: an inactive producer, a lapsed licence, somebody else's VM | stop |
| `NotSupported` | the target cannot do it: commands and `me()` need Fleet | use Fleet |
| `RpcError` | a method failed; `method` and `message` say which and why | see its kinds below |
| `AccessRefused` (`RpcError`, `NotAllowed`) | the connection's standing does not reach the method | connect with the standing it needs |
| `UnknownMethod` (`RpcError`) | igni is older than this igni-client | upgrade igni |
| `InvalidArguments` (`RpcError`, `ValueError`) | an argument is not of the type the method takes; checked before sending (a keyword it does not take, or a required one left out, is Python's own `TypeError`) | fix the call |
| `UnexpectedAnswer` (`RpcError`) | igni answered with something the method does not return | igni and igni-client disagree: align their versions |
| `MethodFailed` (`RpcError`) | the method ran and failed; `message` is igni's reason | read it |
| `RunFailed` | a run ended with `run_error` | read the message |
| `RunInterrupted` | the connection moved or dropped while a run or followed call was going | read the session's history |
| `ApprovalRequired` | `ask()` reached an approval with no `approve=`; `requirements` say what | pass `approve=`, or use `send()` |

### igni_client.testing

| Name | What it is |
|---|---|
| `FakeIgni(*, gateway=None, local_token=None)` | igni on a loopback socket; `fake.local()` and `fake.fleet(auth)` are targets pointed at it |
| `fake.runs` | `script` (the run for a prompt's text, a list of steps), `decisions` (every approval answer) |
| `fake.methods` | `answers` (by method: a value, a model, a message, or a function of the args), `calls`, `history`, `models`, `sessions`, `unbound_for(n)` |
| `fake.socket` | `received`, `broadcast(event)`, `push(channel, payload, session_id="")`, `move()`, `drop(code)`, `busy_next(n)`, `connections` |
| `fake.commands` | how a slash command is answered: a function of its text |
| `FakeGateway(tokens)` | Fleet's gateway: `commands` (by command line, a `PlayedCommand`), `commands_run` |
| `Steps` | runs to script: `answer(text)`, `approval(tool, **args)`, `echo`, `rejected()`; with `Pause` and `Delay` steps |
| `sample(T)` | a valid value of any of igni-client's types |

### igni's methods, by namespace

Every method below is generated from igni's contract, its documentation
igni's own. A method that streams and is followed returns a
[`Call`](#call); its entry says what it yields. Each says its wire method
and the [access](#who-may-call-what) it needs.

<!-- api-reference:start -->

<!-- Generated by tools/client_codegen.py from contracts/rpc-contract.json. Do not edit by hand: run `make client-api`. -->

#### Who may call what

Who may make a call, as igni enforces it.

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
by the token it offers:

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
* **Local client, igni started by hand.** With no launcher to give it
  a secret, igni mints its own window token and prints it once to the
  terminal; the connection that offers it stands as the window, and
  the lockfile's program token makes a program, as on the desktop.
* **Local client, igni started with the development switch**
  (`IGNI_DEV_NO_WS_TOKEN=1`): no token at all, so every connection
  stands as the window and reaches `client`, `approver` and
  `window` calls.
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
| [`session.auth`](#sessionauth) | `plan`, `reload_credentials`, `sign_out` |
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
<summary><code>await igni.agents.cancel_run(run_id: str = '')</code> → <code>CancelAgentRunResult</code></summary>

Wire method `cancel_agent_run` · access `client`

Stop one sub-agent's run, leaving the rest of the turn going.

`run_id` is the sub-agent run's id, as its events carry it.
Returns `ok: true` when the run was cancelled, or `ok: false`
with `error` when `run_id` is empty, no such run is running, or
the cancellation failed.

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

`api_url` is the server's API address: `https`, or `http` to
`localhost`, `127.0.0.1` or `::1` for a local deployment;
`portal_url` its portal, empty to derive it from `api_url`, and
held to the same rule when given. Returns the server as stored, or,
when the choice is refused (an empty `api_url`, or an address that
breaks that rule), `error` saying why and nothing stored. Fails when the user configuration file cannot be read or
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
<summary><code>await igni.marketplaces.refresh(name: str | None = None)</code> → <code>InfoMessage</code></summary>

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
<summary><code>igni.notifications.list()</code> → <code>Call[NotificationsListResult, NotificationsListEvent]</code></summary>

Wire method `notifications_list` · access `client` · streams `notifications_changed`

List the signed-in person's notifications, newest first.

Takes no arguments. Reads igni server again and merges in what
extensions on this machine posted. Returns at most 100
`notifications` (each with its source, title, body, target and
whether it is read), the unread `counts` in all and per
extension, and `server_error` when igni server could not be
read. The fresh counts are also pushed as `notifications_changed`.

Followed: `async with` the call to follow it: it yields the `notifications_changed` push that says the list was read, and ends with the answer.

</details>

<details>
<summary><code>igni.notifications.mark_read(*, ids: list[str] | None = None, source: str | None = None)</code> → <code>Call[NotificationsReadResult, NotificationsMarkReadEvent]</code></summary>

Wire method `notifications_mark_read` · access `client` · streams `notifications_changed`

Mark notifications read.

`ids` names the notifications; `source` (an extension id) marks
all of that extension's; neither marks every notification. Returns
the unread `counts` afterwards, also pushed as
`notifications_changed`, and `server_error` when igni server
could not be told.

Followed: `async with` the call to follow it: it yields the `notifications_changed` push that says the notifications were marked read, and ends with the answer.

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
<summary><code>igni.sessions.attach(*, project_dir: str = '', session_id: str = '')</code> → <code>Call[AttachSessionResult, AttachSessionEvent]</code></summary>

Wire method `attach_session` · access `client` · streams `content_delta`, `error`, `info`, `model_completed`, `reasoning_started`, `requirement_details`, `run_completed`, `run_error`, `run_paused`, `run_started`, `stream_end`, `streaming_done`, `task_created`, `task_iteration`, `task_state_updated`, `task_updated`, `tool_completed`, `tool_error`, `tool_started`

Bind to a session — an existing one, or a new one in a project folder.

`session_id` names the session to resume; `project_dir` the folder
it works in. Neither: the default session. Only `project_dir`: a new
session locked to that folder. Both: that session, which must belong
to that folder. The session is made live if it is not. An id igni has
no session by is not an error: a new, empty session starts under that
id, so check `session_id` against the session list first when it
must already exist.

Returns the `session_id` and `project_dir` actually bound; send
later requests for that session with this `session_id` on the
envelope. Right after the answer, every approval the session is
waiting on is shown again (a `run_paused` carrying its
`hitl_request` items), since a client that reloaded lost its
dialog; a run igni was continuing when it stopped is reported with
an `info`, and a sub-agent's interrupted run is continued, which
streams as any run does. Each of those messages carries this
request's `id`, and a `stream_end` of that `id` ends them.

Fails when `project_dir` is not a directory, or the session belongs
to another project folder — an attach never moves a session.

Followed: `async with` the call to follow it: it yields the approvals the session is still waiting for and the run it continues again — every message of them carries the attach's own request id — and ends with the `stream_end` that closes them.

</details>

#### igni.window

igni's own window's model — its fields, toasts and dialog.

<details>
<summary><code>igni.window.model(*, op: Literal['hydrate', 'write', 'toast', 'dismiss_toast', 'open_dialog', 'answer_dialog'], window: str, connection_id: str = '', dialog_id: str = '', field: str = '', kind: str = '', token: str = '', value: JsonValue = None)</code> → <code>Call[WindowModelResult, WindowModelEvent]</code></summary>

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

Followed: `async with` the call to follow it: it yields the `window_model_changed` push that carries this change, and ends with the answer. The change's token is the one given; igni-client makes one when the caller does not, so the push can be told from another window's.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### session

The methods igni answers for one session; `Session` is one.

<details>
<summary><code>session.cancel()</code> → <code>Call[CancelRunResult, CancelRunEvent]</code></summary>

Wire method `cancel_run` · access `client` · streams `info`, `stream_end`

Stop the turn this session is running.

Takes no arguments. Returns `cancelled`: whether a turn was
running. Its stream then ends with an `info` saying it was
cancelled and its `stream_end`, and the run is recorded as
interrupted; a foreground shell command the turn started is killed.
With no turn running nothing happens and nothing is streamed.

Followed: `async with` the call to follow it: it yields the `info` and `stream_end` of the turn it stops, and ends with the `stream_end`. With no turn running nothing is streamed, and the answer says so.

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
<summary><code>session.run_shell(command: str = '')</code> → <code>Call[RunShellResult, RunShellEvent]</code></summary>

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

Followed: `async with` the call to follow it: a command that finishes inside the wait pushes nothing, and the answer is its output. A command that outlives the wait moves to the background: the answer names the pid, and the `process_started`, `process_line`, `process_exited` and `background_process_done` pushes of that pid follow, ending with the last of them.

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
<summary><code>await session.shutdown()</code> → <code>None</code></summary>

Wire method `shutdown` · access `window`

Wind this session down: its hooks, its agents, its MCP servers, its scheduler.

Takes no arguments and returns nothing once done. Runs the session's
`SessionEnd` hooks, cleans up its ephemeral agents, disconnects its
MCP servers and stops its scheduler — once: a session already wound
down is left as it is. Background processes are igni's, not the
session's, and are left running; they end when igni does. It does
not stop igni or close the connection. Each step's failure is
logged, not raised. Only igni's window may call it.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

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
<summary><code>await session.auth.plan()</code> → <code>CloudPlan | None</code></summary>

Wire method `get_cloud_plan` · access `client`

Read who is signed in to igni server, and their organisation's plan.

Takes no arguments. Asks igni server with this session's sign-in and
returns the person's `email` and `full_name`, the organisation's
display name (`org_name`) and plan `tier`; any of them may be
null when igni server does not say. Returns `null` when nobody is
signed in or igni server could not be asked.

</details>

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
<summary><code>session.auth.sign_out()</code> → <code>Call[StatusUpdate, ClearCloudCredentialsEvent]</code></summary>

Wire method `clear_cloud_credentials` · access `window` · streams `notifications_changed`

Sign this session out of igni server.

Takes no arguments. The session forgets its cloud credentials, and
the signed-in person's notifications stop arriving and leave the
badges (`notifications_changed`). Returns the session's status
afterwards as a `status_update` message, sent in place of an
`rpc_response`.

Followed: `async with` the call to follow it: it yields the `notifications_changed` push that says the person signed out, and ends with the answer — the session's status.

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
<summary><code>await session.context.compact(*, ctx_tokens: int, max_ctx: int)</code> → <code>CompactionOutcome</code></summary>

Wire method `compact_if_needed` · access `client`

Compact this session's conversation when its context is nearly full.

`ctx_tokens` is the context the last turn used and `max_ctx`
the model's window; at 80% or more the conversation is summarised
and replaced by the summary (the `PreCompact` hooks may refuse).
Returns `compacted` and, when it was, the `summary`.

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
<summary><code>await session.files.pick_dir(start: str | None = None)</code> → <code>PickDirResult</code></summary>

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
on, its `type` (`command`, `http`, `prompt` or `mcp_tool`)
and the `command` or `url` it runs, the `matcher` that narrows
it, its timeout, whether it runs in the background, and the HTTP
headers it sends.

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
Returns an `info` message, sent in place of an `rpc_response`,
once it is connected. Fails with the reason when it did not connect
(not configured, refused by policy, no tools, approval denied); the
reason is also `get_mcp_server_details`'s `error` for it.

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
<summary><code>await session.models.switch(model_name: str)</code> → <code>ModelSwitched</code></summary>

Wire method `switch_model` · access `client`

Make another model the one this session's agent runs on.

`model_name` is a name from the model registry
(`get_model_registry`). The choice is also saved as the default
for new sessions. Returns `text`, saying the model switched, with a
note for any part of the choice that could not be saved. Fails when
the model is not in the registry.

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
there is no project), and the session follows it from its next tool
call. Returns nothing. Fails when the settings file cannot be
written.

Access: `window`. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets `AccessRefused`.

</details>

#### session.plan

Plan mode: the plan the agent submitted, and the person's decision.

<details>
<summary><code>session.plan.approve(run_id: str = '')</code> → <code>Call[PlanDecisionResult, ApprovePlanEvent]</code></summary>

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
<summary><code>session.plan.dismiss(run_id: str = '')</code> → <code>Call[PlanDecisionResult, DismissPlanEvent]</code></summary>

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
`session_id` the session it belongs to; only that session's
interrupted run is deleted. Returns `ok: true` — also when no such
run exists, so a retry is harmless — or `ok: false` with `error`
when `message_id` is empty or the store could not be written.

</details>

<details>
<summary><code>await session.runs.interrupted()</code> → <code>list[InterruptedRun]</code></summary>

Wire method `get_interrupted_runs` · access `client`

List a session's runs that stopped before they finished.

`session_id` names the session. Returns one row per run that was
cancelled, failed or never finished: the `message_id` and text of
the message that started it, when it arrived and when it stopped, why
(`cancelled`, `errored`, or `abandoned` when igni stopped while
it ran) and the last error. A client offers to retry,
discard or edit each. A storage failure answers an empty list.

</details>

<details>
<summary><code>await session.runs.pending_messages()</code> → <code>list[PendingMessage]</code></summary>

Wire method `get_pending_messages` · access `client`

List a session's messages whose run started but never finished.

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
`info` message, sent in place of an `rpc_response`. Fails for
an id the project has no task for, and for a task that already
completed, failed or was cancelled, whose record is left as it is.

</details>

<details>
<summary><code>session.scheduler.execute(description: str, *, run_id: str = '')</code> → <code>Call[ScheduledTaskRunResult, ExecuteScheduledTaskEvent]</code></summary>

Wire method `execute_scheduled_task` · access `client`

Run a scheduled task's work now, in this session, and wait for the answer.

`description` is what the task asks the agent to do (a scheduled
task's `description`). The agent runs it as a stored task firing,
not as a live message: its run is not streamed to the windows, and
the task's own record is not touched. What its tools push while
they work still goes out. It is the session's run while it goes:
it waits for a turn already running, `get_processing` reports
it, and `cancel_run` stops it. Returns the agent's answer as
text with the run's `run_id` — the one given, or one made — which
every push the run's tools make carries too. Fails when the
organisation's group policy refuses the run, the run is cancelled,
or the run fails.

Followed: `async with` the call to follow it: it yields the pushes of the run it starts — what its tools do while it works — as they come, and ends with the answer, which is the agent's own words. The run's id is the one given; igni-client makes one when the caller does not, so the pushes can be told from another run's.

</details>

<details>
<summary><code>await session.scheduler.list(include_done: bool = True)</code> → <code>list[ScheduledTask]</code></summary>

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

Wire method `start_scheduler` · access `client` · streams `scheduler_completed`, `scheduler_started`

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
<summary><code>session.workspace.set_trust(decision: Literal['trust', 'distrust', 'once'])</code> → <code>Call[WorkspaceTrustStatus, SetWorkspaceTrustEvent]</code></summary>

Wire method `set_workspace_trust` · access `window` · streams `workspace_trust_required`

Answer "Trust this folder?" for this session's project folder.

`decision` is `trust` (remembered), `once` (until igni exits)
or `distrust`. When trust changed, the session is rebuilt so the
folder's tools, hooks, plugins, language servers and configuration
come in or go. Every window showing the dialog for that folder is
told the new status (`workspace_trust_required`). Returns the new
status. Fails when the organisation's policy does not let the folder
be trusted.

Followed: `async with` the call to follow it: it yields the `workspace_trust_required` push that tells the windows the folder's trust changed, and ends with the answer — the new status.

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
| `shutdown` | stops igni itself, for every window and program attached, and only igni's window may; `session.shutdown()` winds one session down instead |

<!-- api-reference:end -->

## Errors and troubleshooting

**`AccessRefused: … only igni's window may do this`.** The connection is
a program, attached with igni's lockfile on the desktop, and the method
is the window's: it loosens a rule the agent is held to (a saved
permission rule, a trusted folder, a plugin) or changes whom igni acts
for. Make the change in igni's window, or run the program through Fleet,
where every connection is the window.

**`AccessRefused: … approver token` from `approve()`, or `NotAllowed` from the `send()` loop (or `ask()`) after it.**
A program answers approvals only with an approver token: `/programs` in
igni's window makes one; pass it as `Local(approver_token=...)` or
`IGNI_APPROVER_TOKEN`. An approver answers once: `approve("always")`,
`Decision.deny(remember=True)` and switching the permission mode stay the
window's, and igni-client refuses them from an approver before sending
(`AccessRefused: … an approver answers once`).

**`AuthError: igni at … refused the approver token`.** igni forgets
approver tokens when it quits, and `/programs` can revoke them: make a new
one.

**`Unavailable: no igni is running for …`.** `Local(project_dir)` found no
lockfile: open the project in igni, or pass `url=`.

**`Unavailable: … got no answer`.** A call waits as long as igni's
contract allows its method: 10 seconds for an `instant` one, 30 for `io`,
60 for `network`, 600 for `long` — installing a plugin, compacting a
conversation, a shell command, a scheduled task's run. Only a method that
waits for the person (`session.files.pick_dir()`) waits without limit.
Each method's entry says its wait; `igni_client.calls.timeout_of(wire)`
gives it, and `Connection.RPC_TIMEOUT` (60 seconds) is for a call the
contract does not time.

**`UnknownMethod`.** igni is older than this igni-client and lacks the
method. igni-client is generated from one version of igni's contract,
which is in its `igni_client.models` docstring; use an igni at least as
new.

**`UnexpectedAnswer`.** igni answered with a shape the method does not
return: igni and igni-client disagree about the contract. Align their
versions; report it if they match.

**`InvalidArguments`.** An argument is not of the method's type. Nothing was
sent. A keyword the method does not take, or a required one left out, is
Python's `TypeError`, raised by the method's signature before anything else.

**`RunInterrupted`.** Fleet moved the VM, or the line dropped, while a run
or a followed call was going. It may or may not have finished: read
`session.history.get()`, or the method's own state.

**A followed call never ends.** It ends when igni has no more to send for
it, and some never do: `session.scheduler.start()` follows the scheduler
for as long as the block runs. Leave the block, or wrap the loop in
`asyncio.timeout(...)`.

**An event arrives as `Unknown`.** igni sent a message type newer than
this igni-client; upgrade it. Everything it carried is in
`event.model_extra`. A known message this version cannot read is
`Unknown` too, and logged as a warning on `igni_client.events`.

**Logging.** igni-client logs on the `igni_client.*` loggers: the
connection's reconnects at INFO, a message that is not JSON or cannot be
read at WARNING. It never logs a token.

## Changes since 0.1.0

On purpose, and not backwards compatible:

- **Every method is typed.** `igni.rpc(method, **args)` and
  `session.rpc(...)` are gone: every one of igni's methods is a Python
  method on `IgniClient` or `Session`, its arguments checked before
  sending and its result a model. `session.use_model(name)` is
  `session.models.switch(name)` (a `ModelSwitched`); `igni.models.list()`
  is `session.models.list()` (a `ModelRegistryResult`; `ModelCatalogue`
  and `ModelEntry` are gone); `session.history()` is
  `session.history.get()`, a list of `ChatTurn` — `UserTurn`,
  `AssistantTurn`, `ToolTurn` and the others, told apart by `role` —
  where it was `HistoryTurn` (gone). `session.cancel()` calls igni's
  `cancel_run`, which answers, instead of sending `cancel`.
- **Every message is generated from igni's contract**, field for field.
  A result is required where the contract requires it
  (`DiscardEphemeralResult(…)` built by hand needs `name` and `ok`); every
  field of a message has the contract's default, so `Requirement(…)`,
  `RunPaused(…)` and `PushNotification(…)` need none.
  `HitlDecision.action` and `.choice` are strings, as igni types them;
  `Decision` still holds the values igni knows.
- **A frame on the wire** is its `type` and the fields given a value; a
  field left at its default is left out, and igni applies the same
  default. In 0.1.0 every field went, as given.
- **Errors.** igni's error answers raise `AccessRefused`,
  `UnknownMethod`, `InvalidArguments`, `UnexpectedAnswer` or
  `MethodFailed`, each an `RpcError`. A page's and the platform's methods
  (`host_model`, `extension_service_token`, `deliver_service_events`,
  `vm_sign_in`) are refused with `ValueError` before they are sent, as
  before; `shutdown` is no longer among them, since igni's `shutdown`
  method winds one session down (`session.shutdown()`, igni's window's),
  while the `shutdown` message, which stops igni, is still never sent.
- **New:** `Call` (`igni_client.calls`), `session.events()`,
  `session.command()`, `session.typing()`, `igni.auth.cancel_login()`,
  typed push notifications, `Fleet.standing` and `Local.standing`,
  `igni_client.access`, `igni_client.testing.sample`, and `FakeIgni`'s
  `methods.calls`, `socket.push()`, `commands` and `logins_cancelled`.
- From earlier 0.2 changes: `IgniClient(target, backoff=Backoff(...))`
  replaces `reconnect_attempts=`; `App.public_jwks()` is a `JwkSet`;
  `Decision`, `Policy`, `Choice` and `Answer` live in
  `igni_client.approvals` and `Reply` in `igni_client.replies`;
  `run.record` and `run.woken` of a command are models, `None` until
  their lines arrive; `igni_client.connection` keeps only `Connection`
  and `REFUSED_METHODS`.

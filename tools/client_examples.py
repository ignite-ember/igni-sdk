"""A short example for each of igni-client's methods, for its page on the site.

``tools/sdk_docs.py`` writes a page per namespace of igni-client's methods
(``make sdk-docs``), and every method on it has an example. A method that
only reads — its wire name says so (``get_…``, ``list_…``, ``count_…``) and
it needs no argument — gets one generated from its result type. Every
other method's is written here, by wire name, because what to pass and
what to do with the answer is not in the contract; the generator refuses
a method that has neither, and checks that each example below calls its
method with arguments the method takes.

Each runs inside an ``async`` function with ``igni`` an open
``IgniClient`` and ``session`` one of its ``Session``\\ s.

Every example is shown in both Python and TypeScript: the site pairs the
``python`` block below with the matching ``TS_EXAMPLES`` ``typescript``
block into one language toggle. The TypeScript twin drives the same igni
through ``@ignite-ember/igni-client`` (the Node client at surface parity):
method and field names are the same ``snake_case``, so a call translates
directly, but its positional arguments are in the TypeScript signature's
order (alphabetical), a streaming call is followed with ``for await`` and
its result read from ``.result()`` rather than ``async with``, and an
``isinstance`` check becomes narrowing on the push's ``channel``. A method
that only reads gets a generated twin in both languages; every Python
example here has a TypeScript counterpart (``TS_EXAMPLES`` or generated),
and ``tools/client_example_check.py`` type-checks the TypeScript against
the real client, as it mypy-checks the Python.
"""

from __future__ import annotations

#: Examples by wire method (or, for a message sent as a method, wire message).
EXAMPLES: dict[str, str] = {
    # ── igni as a whole ──────────────────────────────────────────────
    "attach_session": """
async with igni.sessions.attach(session_id="0b7c…", project_dir="/work/api") as attached:
    async for event in attached:
        print(event.type)  # the approvals the session is still waiting on
    bound = await attached.result()
    print(bound.session_id, bound.project_dir)
""",
    "cancel_agent_run": """
answer = await igni.agents.cancel_run("run_42")
if not answer.ok:
    print("not cancelled:", answer.error)
""",
    "mint_approver_token": """
minted = await igni.approvers.mint_token()
# Hand it to the program that answers approvals: Local(approver_token=minted.token)
print(minted.token)
""",
    "revoke_approver_tokens": """
revoked = await igni.approvers.revoke_tokens()
print(f"{revoked.revoked} approver token(s) no longer work")
""",
    "discover_server": """
found = await igni.auth.discover_server("ada@acme.test")
if found.api_url:
    await igni.auth.set_server(found.api_url, portal_url=found.portal_url)
else:
    print("no server found:", found.reason)
""",
    "set_server": """
choice = await igni.auth.set_server("https://igni.acme.internal")
if choice.error:
    print(choice.error)
""",
    "login": """
from igni_client.models import LoginResultPush, LoginStatusPush

async with igni.auth.login() as sign_in:
    async for event in sign_in:
        if isinstance(event, LoginStatusPush):
            print(event.payload.text)
        elif isinstance(event, LoginResultPush):
            print("signed in" if event.payload.success else event.payload.result)
""",
    "cancel_login": """
await igni.auth.cancel_login()
""",
    "set_extension_settings": """
listed = await igni.extensions.set_settings(
    extension_id="acme.tickets",
    values={"board": "PLAT", "notify": True},
)
print([extension.id for extension in listed.extensions])
""",
    "list_dirs": """
listing = await igni.files.list_dirs(path="/work", show_hidden=False)
for folder in listing.dirs:
    print(folder)
""",
    "add_marketplace": """
info = await igni.marketplaces.add("https://github.com/acme/igni-plugins")
print(info.text)
""",
    "refresh_marketplaces": """
info = await igni.marketplaces.refresh()  # every marketplace; or refresh("acme")
print(info.text)
""",
    "remove_marketplace": """
info = await igni.marketplaces.remove("acme")
print(info.text)
""",
    "notifications_list": """
async with igni.notifications.list() as listing:
    async for event in listing:
        print(event.payload.counts.unread)
    listed = await listing.result()
    print([n.title for n in listed.notifications])
""",
    "mark_session_seen": """
async with igni.sessions.mark_seen("0b7c…") as marking:
    async for event in marking:
        print(len(event.payload.sessions), "chats still running, waiting or unread")
    states = await marking.result()
    print([s.session_id for s in states.sessions if s.unread])
""",
    "notifications_mark_read": """
async with igni.notifications.mark_read(source="acme.tickets") as marking:
    async for event in marking:
        print(event.payload.counts.unread)
    read = await marking.result()
    print(read.counts.unread, "unread left")
""",
    "stop_background_process": """
from igni_client.models import BackgroundProcessDonePush, ProcessLinePush

async with igni.processes.stop(4242) as stopping:
    async for event in stopping:
        if isinstance(event, ProcessLinePush):
            print(event.payload.line)
        elif isinstance(event, BackgroundProcessDonePush):
            print("exited with", event.payload.exit_code)
    answer = await stopping.result()
    print(answer.killed, answer.message)
""",
    "read_process_tail": """
tail = await igni.processes.tail(4242, tail=50)
print(tail.output)
if not tail.is_running:
    print("exit code", tail.exit_code)
""",
    "window_model": """
async with igni.window.model(op="toast", window="main", value={"text": "Deployed"}) as changed:
    async for event in changed:
        print(event.payload.window, event.payload.field)
    print((await changed.result()).rev)
""",
    # ── One session ──────────────────────────────────────────────────
    "cancel_run": """
async with session.cancel() as stopping:
    async for event in stopping:
        print(event.type)  # the info and the stream_end of the turn
    print((await stopping.result()).cancelled)
""",
    "shutdown": """
await session.shutdown()
""",
    "switch_session": """
info = await session.switch("0b7c…")
print(info.text)
""",
    "fire_session_start_hook": """
await session.fire_session_start_hook()
""",
    "upload_attachment": """
import base64
from pathlib import Path

data = base64.b64encode(Path("report.pdf").read_bytes()).decode()
uploaded = await session.upload_attachment(filename="report.pdf", content_base64=data)
reply = await session.ask(f"Summarise the report at {uploaded.path}")
""",
    "toggle_verbose": """
verbose = await session.toggle_verbose()
print("verbose" if verbose else "quiet")
""",
    "extract_learnings": """
await session.extract_learnings(
    user_msg="Use pnpm, never npm, in this repository.",
    assistant_msg="Understood: pnpm from now on.",
)
""",
    "run_shell": """
from igni_client.models import ProcessLinePush

async with session.run_shell("git status --short") as run:
    async for event in run:
        if isinstance(event, ProcessLinePush):
            print(event.payload.line)  # a command that outlives the wait
    result = await run.result()
    print(result.exit_code)
    print(result.output)
""",
    "dispatch_visualization_action": """
async with session.visualization_action(action="select", params={"row": 3}) as dispatched:
    async for event in dispatched:
        print(event.payload.action, event.payload.params)
""",
    "report_visualization_verdict": """
from igni_client.models import ElementFailureArgs

verdict = await session.visualization_verdict(
    "chart_42",
    revision=1,
    total=3,
    failed=[ElementFailureArgs(type="BarGraph", message="the data had no rows")],
    issues=["the axis has no label"],
)
print(verdict.drawn, "of", verdict.total, "elements drawn")
""",
    "command": """
result = await session.command("/help")
print(result.kind, result.content)
""",
    "typing": """
await session.typing("Draft: rename the")
await session.typing("")  # clears it
""",
    "discard_interrupted_run": """
for run in await session.runs.interrupted():
    await session.runs.discard_interrupted(run.message_id)
""",
    "discard_pending_message": """
for message in await session.runs.pending_messages():
    await session.runs.discard_pending(message.message_id)
""",
    "search_chat": """
for hit in await session.history.search("migration", limit=10):
    print(hit.run_id, hit.snippet)
""",
    "search_all_chats": """
for hit in await session.history.search_all("migration", limit=10):
    print(hit.session_name or hit.session_id, hit.snippet)
""",
    "truncate_history": """
cut = await session.history.truncate("run_42")
print(f"removed {cut.removed} run(s)")
""",
    "compact_if_needed": """
status = await session.status()
cleared = await session.context.compact(
    ctx_tokens=status.context_tokens, max_ctx=status.max_context
)
if cleared.compacted:
    print("compacted into", cleared.new_session_id)
""",
    "loop_pause": """
paused = await session.loop.pause()
print("paused" if paused else "no loop to pause")
""",
    "loop_resume": """
answer = await session.loop.resume()
print(answer)
""",
    "pop_pending_loop_iteration": """
advance = await session.loop.next_iteration()
if advance is not None:
    print(advance.iteration, advance.prompt)
""",
    "cancel_pending_loop": """
cancelled = await session.loop.cancel()
print("cancelled" if cancelled else "no loop waiting")
""",
    "approve_plan": """
from igni_client.models import PlanDecidedPush

async with session.plan.approve("run_42") as approving:
    async for event in approving:
        if isinstance(event, PlanDecidedPush):
            print("plan", event.payload.decision)
    decided = await approving.result()
    print(decided.ok, decided.mode_status)
""",
    "dismiss_plan": """
decided = await session.plan.dismiss("run_42")
if not decided.ok:
    print(decided.error)
""",
    "switch_model": """
info = await session.models.switch("igni-large")
print(info.text)
""",
    "check_permission": """
from igni_client.models import ToolCallArgs

verdict = await session.permissions.check(
    tool_name="bash",
    func_name="run",
    tool_args=ToolCallArgs(command="rm -rf build"),
)
print(verdict)  # "allow", "ask" or "deny"
""",
    "save_permission_rule": """
await session.permissions.save_rule(rule="Bash(git status:*)", level="allow")
""",
    "set_workspace_trust": """
async with session.workspace.set_trust("trust") as trusting:
    async for event in trusting:
        print(event.payload.state)
    print((await trusting.result()).state)
""",
    "complete_files": """
completion = await session.files.complete(query="src/app", limit=10)
print(completion.total, completion.matches)
""",
    "read_file": """
read = await session.files.read("pyproject.toml")
print(read.error or read.contents)
""",
    "read_file_bytes": """
import base64

read = await session.files.read_bytes("docs/diagram.png")
if read.error:
    print(read.error)
else:
    print(read.media_type, len(base64.b64decode(read.data)), "bytes")
""",
    "search_code": """
found = await session.files.search("def create_app")
for match in found.matches:
    print(match)
""",
    "pick_dir_native": """
picked = await session.files.pick_dir()
if not picked.cancelled:
    print(picked.path)
""",
    "promote_ephemeral_agent": """
promoted = await session.agents.promote("reviewer")
print(promoted.ok, promoted.dest or promoted.reason)
""",
    "discard_ephemeral_agent": """
discarded = await session.agents.discard("reviewer")
print(discarded.ok, discarded.reason)
""",
    "reload_hooks": """
info = await session.hooks.reload()
print(info.text)
""",
    "start_scheduler": """
from igni_client.models import SchedulerCompletedPush, SchedulerStartedPush

async with session.scheduler.start() as scheduler:
    async for event in scheduler:
        if isinstance(event, SchedulerStartedPush):
            print("started", event.payload.description)
        elif isinstance(event, SchedulerCompletedPush):
            print("done", event.payload.task_id, event.payload.result)
""",
    "execute_scheduled_task": """
async with session.scheduler.execute("Summarise yesterday's failed builds") as task:
    async for event in task:
        print(event.channel)  # what the run's tools do while it works
    print((await task.result()).result)
""",
    "cancel_scheduled_task": """
for task in await session.scheduler.list(include_done=False):
    info = await session.scheduler.cancel(task.id)
    print(info.text)
""",
    "run_workflow": """
async with session.workflows.run("nightly", args={"branch": "main"}) as run:
    async for event in run:
        print(event.payload.type, event.payload.payload)
    started = await run.result()
    print(started.workflow_run_id)
""",
    "cancel_workflow": """
cancelled = await session.workflows.cancel("wf_7")
print("cancelled" if cancelled.cancelled else "already over")
""",
    "ensure_mcp": """
ready = await session.mcp.ensure()
print("connected:", ready.connected, "failed:", ready.failed)
""",
    "mcp_connect": """
info = await session.mcp.connect("github")
print(info.text)
""",
    "mcp_disconnect": """
info = await session.mcp.disconnect("github")
print(info.text)
""",
    "set_mcp_tool_enabled": """
toggled = await session.mcp.set_tool_enabled(server="github", tool="delete_repo", enabled=False)
print(toggled.tool, toggled.enabled)
""",
    "set_mcp_approval": """
for server in await session.mcp.list_approvals():
    if not server.approved:
        await session.mcp.set_approval(server_name=server.name, approved=True)
""",
    "get_plugin_contents": """
contents = await session.plugins.contents("acme-review")
print(contents.skills, contents.agents)
""",
    "preview_plugin": """
preview = await session.plugins.preview("https://github.com/acme/review-plugin", branch="main")
print(preview.name, preview.readme[:200])
""",
    "install_plugin": """
info = await session.plugins.install("@acme/acme-review")
print(info.text)
""",
    "update_plugin": """
info = await session.plugins.update("acme-review")
print(info.text)
""",
    "remove_plugin": """
info = await session.plugins.remove("acme-review")
print(info.text)
""",
    "set_plugin_enabled": """
info = await session.plugins.set_enabled(name="acme-review", enabled=False)
print(info.text)
""",
    "reload_cloud_credentials": """
status = await session.auth.reload_credentials()
print(status.cloud_connected, status.cloud_email)
""",
    "clear_cloud_credentials": """
async with session.auth.sign_out() as signing_out:
    async for event in signing_out:
        print(event.payload.cause)  # "signed_out"
    print((await signing_out.result()).cloud_connected)
""",
}

#: The TypeScript twin of each example in ``EXAMPLES``, by the same wire name.
#: Each runs inside an ``async`` function with ``igni`` an open ``IgniClient``
#: and ``session`` one of its ``Session``\\ s, from ``@ignite-ember/igni-client``.
TS_EXAMPLES: dict[str, str] = {
    # ── igni as a whole ──────────────────────────────────────────────
    "attach_session": """
const attached = igni.sessions.attach("/work/api", "0b7c…");
for await (const event of attached) {
  console.log(event.type);  // the approvals the session is still waiting on
}
const bound = await attached.result();
console.log(bound.session_id, bound.project_dir);
""",
    "cancel_agent_run": """
const answer = await igni.agents.cancel_run("run_42");
if (!answer.ok) {
  console.log("not cancelled:", answer.error);
}
""",
    "mint_approver_token": """
const minted = await igni.approvers.mint_token();
// Hand it to the program that answers approvals: new Local({ approverToken: minted.token })
console.log(minted.token);
""",
    "revoke_approver_tokens": """
const revoked = await igni.approvers.revoke_tokens();
console.log(`${revoked.revoked} approver token(s) no longer work`);
""",
    "discover_server": """
const found = await igni.auth.discover_server("ada@acme.test");
if (found.api_url) {
  await igni.auth.set_server(found.api_url, found.portal_url);
} else {
  console.log("no server found:", found.reason);
}
""",
    "set_server": """
const choice = await igni.auth.set_server("https://igni.acme.internal");
if (choice.error) {
  console.log(choice.error);
}
""",
    "login": """
const signIn = igni.auth.login();
for await (const event of signIn) {
  if (event.channel === "login_status") {
    console.log(event.payload.text);
  } else if (event.channel === "login_result") {
    console.log(event.payload.success ? "signed in" : event.payload.result);
  }
}
""",
    "cancel_login": """
await igni.auth.cancel_login();
""",
    "set_extension_settings": """
const listed = await igni.extensions.set_settings("acme.tickets", { board: "PLAT", notify: true });
console.log((listed.extensions ?? []).map((extension) => extension.id));
""",
    "list_dirs": """
const listing = await igni.files.list_dirs("/work", false);
for (const folder of listing.dirs) {
  console.log(folder);
}
""",
    "add_marketplace": """
const info = await igni.marketplaces.add("https://github.com/acme/igni-plugins");
console.log(info.text);
""",
    "refresh_marketplaces": """
const info = await igni.marketplaces.refresh();  // every marketplace; or refresh("acme")
console.log(info.text);
""",
    "remove_marketplace": """
const info = await igni.marketplaces.remove("acme");
console.log(info.text);
""",
    "notifications_list": """
const listing = igni.notifications.list();
for await (const event of listing) {
  console.log(event.payload.counts?.unread);
}
const listed = await listing.result();
console.log((listed.notifications ?? []).map((n) => n.title));
""",
    "mark_session_seen": """
const marking = igni.sessions.mark_seen("0b7c…");
for await (const event of marking) {
  console.log(event.payload.sessions?.length, "chats still running, waiting or unread");
}
const states = await marking.result();
console.log((states.sessions ?? []).filter((s) => s.unread).map((s) => s.session_id));
""",
    "notifications_mark_read": """
const marking = igni.notifications.mark_read(undefined, "acme.tickets");
for await (const event of marking) {
  console.log(event.payload.counts?.unread);
}
const read = await marking.result();
console.log(read.counts?.unread, "unread left");
""",
    "stop_background_process": """
const stopping = igni.processes.stop(4242);
for await (const event of stopping) {
  if (event.channel === "process_line") {
    console.log(event.payload.line);
  } else if (event.channel === "background_process_done") {
    console.log("exited with", event.payload.exit_code);
  }
}
const answer = await stopping.result();
console.log(answer.killed, answer.message);
""",
    "read_process_tail": """
const tail = await igni.processes.tail(4242, 50);
console.log(tail.output);
if (!tail.is_running) {
  console.log("exit code", tail.exit_code);
}
""",
    "window_model": """
const changed = igni.window.model("toast", "main", undefined, undefined, undefined, undefined, undefined, { text: "Deployed" });
for await (const event of changed) {
  console.log(event.payload.window, event.payload.field);
}
console.log((await changed.result()).rev);
""",
    # ── One session ──────────────────────────────────────────────────
    "cancel_run": """
const stopping = session.cancel();
for await (const event of stopping) {
  console.log(event.type);  // the info and the stream_end of the turn
}
console.log((await stopping.result()).cancelled);
""",
    "shutdown": """
await session.shutdown();
""",
    "switch_session": """
const info = await session.switch("0b7c…");
console.log(info.text);
""",
    "fire_session_start_hook": """
await session.fire_session_start_hook();
""",
    "upload_attachment": """
import { readFile } from "node:fs/promises";

const data = (await readFile("report.pdf")).toString("base64");
const uploaded = await session.upload_attachment(data, "report.pdf");
const reply = await session.ask(`Summarise the report at ${uploaded.path}`);
console.log(reply.text);
""",
    "toggle_verbose": """
const verbose = await session.toggle_verbose();
console.log(verbose ? "verbose" : "quiet");
""",
    "extract_learnings": """
await session.extract_learnings(
  "Understood: pnpm from now on.",
  "Use pnpm, never npm, in this repository.",
);
""",
    "run_shell": """
const run = session.run_shell("git status --short");
for await (const event of run) {
  if (event.channel === "process_line") {
    console.log(event.payload.line);  // a command that outlives the wait
  }
}
const result = await run.result();
console.log(result.exit_code);
console.log(result.output);
""",
    "dispatch_visualization_action": """
const dispatched = session.visualization_action("select", { row: 3 });
for await (const event of dispatched) {
  console.log(event.payload.action, event.payload.params);
}
""",
    "report_visualization_verdict": """
const verdict = await session.visualization_verdict(
  "chart_42",
  [{ type: "BarGraph", message: "the data had no rows" }],
  ["the axis has no label"],
  1,
  3,
);
console.log(verdict.drawn, "of", verdict.total, "elements drawn");
""",
    "command": """
const result = await session.command("/help");
console.log(result.kind, result.content);
""",
    "typing": """
await session.typing("Draft: rename the");
await session.typing("");  // clears it
""",
    "discard_interrupted_run": """
for (const run of await session.runs.interrupted()) {
  await session.runs.discard_interrupted(run.message_id);
}
""",
    "discard_pending_message": """
for (const message of await session.runs.pending_messages()) {
  await session.runs.discard_pending(message.message_id);
}
""",
    "search_chat": """
for (const hit of await session.history.search("migration", 10)) {
  console.log(hit.run_id, hit.snippet);
}
""",
    "search_all_chats": """
for (const hit of await session.history.search_all("migration", 10)) {
  console.log(hit.session_name || hit.session_id, hit.snippet);
}
""",
    "truncate_history": """
const cut = await session.history.truncate("run_42");
console.log(`removed ${cut.removed} run(s)`);
""",
    "compact_if_needed": """
const status = await session.status();
const cleared = await session.context.compact(status.context_tokens ?? 0, status.max_context ?? 0);
if (cleared.compacted) {
  console.log("compacted into", cleared.new_session_id);
}
""",
    "loop_pause": """
const paused = await session.loop.pause();
console.log(paused ? "paused" : "no loop to pause");
""",
    "loop_resume": """
const answer = await session.loop.resume();
console.log(answer);
""",
    "pop_pending_loop_iteration": """
const advance = await session.loop.next_iteration();
if (advance !== null) {
  console.log(advance.iteration, advance.prompt);
}
""",
    "cancel_pending_loop": """
const cancelled = await session.loop.cancel();
console.log(cancelled ? "cancelled" : "no loop waiting");
""",
    "approve_plan": """
const approving = session.plan.approve("run_42");
for await (const event of approving) {
  if (event.channel === "plan_decided") {
    console.log("plan", event.payload.decision);
  }
}
const decided = await approving.result();
console.log(decided.ok, decided.mode_status);
""",
    "dismiss_plan": """
const decided = await session.plan.dismiss("run_42");
if (!decided.ok) {
  console.log(decided.error);
}
""",
    "switch_model": """
const info = await session.models.switch("igni-large");
console.log(info.text);
""",
    "check_permission": """
const verdict = await session.permissions.check("run", { command: "rm -rf build" }, "bash");
console.log(verdict);  // "allow", "ask" or "deny"
""",
    "save_permission_rule": """
await session.permissions.save_rule("allow", "Bash(git status:*)");
""",
    "set_workspace_trust": """
const trusting = session.workspace.set_trust("trust");
for await (const event of trusting) {
  console.log(event.payload.state);
}
console.log((await trusting.result()).state);
""",
    "complete_files": """
const completion = await session.files.complete(10, "src/app");
console.log(completion.total, completion.matches);
""",
    "read_file": """
const read = await session.files.read("pyproject.toml");
console.log(read.error || read.contents);
""",
    "read_file_bytes": """
const read = await session.files.read_bytes("docs/diagram.png");
if (read.error) {
  console.log(read.error);
} else {
  console.log(read.media_type, Buffer.from(read.data, "base64").length, "bytes");
}
""",
    "search_code": """
const found = await session.files.search("def create_app");
for (const match of found.matches ?? []) {
  console.log(match);
}
""",
    "pick_dir_native": """
const picked = await session.files.pick_dir();
if (!picked.cancelled) {
  console.log(picked.path);
}
""",
    "promote_ephemeral_agent": """
const promoted = await session.agents.promote("reviewer");
console.log(promoted.ok, promoted.dest || promoted.reason);
""",
    "discard_ephemeral_agent": """
const discarded = await session.agents.discard("reviewer");
console.log(discarded.ok, discarded.reason);
""",
    "reload_hooks": """
const info = await session.hooks.reload();
console.log(info.text);
""",
    "start_scheduler": """
const scheduler = session.scheduler.start();
for await (const event of scheduler) {
  if (event.channel === "scheduler_started") {
    console.log("started", event.payload.description);
  } else if (event.channel === "scheduler_completed") {
    console.log("done", event.payload.task_id, event.payload.result);
  }
}
""",
    "execute_scheduled_task": """
const task = session.scheduler.execute("Summarise yesterday's failed builds");
for await (const event of task) {
  console.log(event.channel);  // what the run's tools do while it works
}
console.log((await task.result()).result);
""",
    "cancel_scheduled_task": """
for (const task of await session.scheduler.list(false)) {
  const info = await session.scheduler.cancel(task.id);
  console.log(info.text);
}
""",
    "run_workflow": """
const run = session.workflows.run("nightly", { branch: "main" });
for await (const event of run) {
  console.log(event.payload.type, event.payload.payload);
}
const started = await run.result();
console.log(started.workflow_run_id);
""",
    "cancel_workflow": """
const cancelled = await session.workflows.cancel("wf_7");
console.log(cancelled.cancelled ? "cancelled" : "already over");
""",
    "ensure_mcp": """
const ready = await session.mcp.ensure();
console.log("connected:", ready.connected, "failed:", ready.failed);
""",
    "mcp_connect": """
const info = await session.mcp.connect("github");
console.log(info.text);
""",
    "mcp_disconnect": """
const info = await session.mcp.disconnect("github");
console.log(info.text);
""",
    "set_mcp_tool_enabled": """
const toggled = await session.mcp.set_tool_enabled(false, "github", "delete_repo");
console.log(toggled.tool, toggled.enabled);
""",
    "set_mcp_approval": """
for (const server of await session.mcp.list_approvals()) {
  if (!server.approved) {
    await session.mcp.set_approval(true, server.name);
  }
}
""",
    "get_plugin_contents": """
const contents = await session.plugins.contents("acme-review");
console.log(contents.skills, contents.agents);
""",
    "preview_plugin": """
const preview = await session.plugins.preview("https://github.com/acme/review-plugin", "main");
console.log(preview.name, (preview.readme ?? "").slice(0, 200));
""",
    "install_plugin": """
const info = await session.plugins.install("@acme/acme-review");
console.log(info.text);
""",
    "update_plugin": """
const info = await session.plugins.update("acme-review");
console.log(info.text);
""",
    "remove_plugin": """
const info = await session.plugins.remove("acme-review");
console.log(info.text);
""",
    "set_plugin_enabled": """
const info = await session.plugins.set_enabled(false, "acme-review");
console.log(info.text);
""",
    "reload_cloud_credentials": """
const status = await session.auth.reload_credentials();
console.log(status.cloud_connected, status.cloud_email);
""",
    "clear_cloud_credentials": """
const signingOut = session.auth.sign_out();
for await (const event of signingOut) {
  console.log(event.payload.cause);  // "signed_out"
}
console.log((await signingOut.result()).cloud_connected);
""",
}

__all__ = ["EXAMPLES", "TS_EXAMPLES"]

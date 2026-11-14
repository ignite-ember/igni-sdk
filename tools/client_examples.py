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
    "search_chat": """
for hit in await session.history.search("migration", limit=10):
    print(hit.run_id, hit.snippet)
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
    "get_plugin_contents": """
contents = await session.plugins.contents("acme-review")
print(contents.skills, contents.agents)
""",
    "preview_plugin": """
preview = await session.plugins.preview("https://github.com/acme/review-plugin", branch="main")
print(preview.name, preview.readme[:200])
""",
    "install_plugin": """
info = await session.plugins.install("acme-review@acme")
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

__all__ = ["EXAMPLES"]

# igni-client: coverage of igni's protocol

This file tracks one goal: **igni-client does everything igni's own app
can do, fully typed.** Every RPC method gets a real Python method with
typed arguments and a typed result. Every message igni sends gets its
own class. Anything that streams in the app streams in the SDK. And
every package's PyPI page documents all of it.

It is updated in the same change that moves a row.

**Status:** ⬜ todo · 🟨 in progress or to re-check · ✅ done (typed in
igni-core, generated into the SDK, tested, documented) · ⛔ not for
clients (the reason is in the row)

## How it is built

1. **igni-core publishes the whole contract.** `docs/rpc-contract.json`
   holds, for each method, the JSON Schema of its arguments and result,
   its scope (`session` or `igni`), who may call it (`access`), and the
   messages and push channels it streams; every message on the socket;
   every push channel's payload; and which access level a connection
   reaches. igni-sdk keeps a copy in `contracts/rpc-contract.json`
   (`make contracts`; `make contracts-check` and the contracts test hold
   it to igni-core's).
2. **igni-sdk generates the typed client from that file.**
   `tools/client_codegen.py` writes `igni_client.models` (a Pydantic model
   per type, the contract's descriptions as docstrings, unions
   discriminated where the schema discriminates), `igni_client.api`
   (every method on `IgniClient` for scope `igni` and on `Session` for
   scope `session`, grouped by namespace, the contract's `doc` as its
   docstring) and the API reference in igni-client's README.
   `tools/client_names.py` is the one hand-kept table: what each method
   is called in Python, which streaming methods are followed and why the
   rest are not, and which messages are sent as methods.
   `tests/test_the_client_api_is_generated.py` fails when what is checked
   in is stale (`make client-api`), and the generator refuses a contract
   with a method the table does not place. The by-name `rpc()` call is
   gone.
3. **Streaming.** A method that streams returns a `Call`: `await` it for
   the typed result, or `async with` it and `async for` the typed events
   this call caused, told apart from every other call's by what they
   carry (`igni_client.follow`). A method whose events igni gives nothing
   to correlate returns its result only, and its row says why.
4. **Access.** igni-core's contract says a Fleet connection stands as
   igni's window; a desktop program with the lockfile's token reaches
   `client` calls, one with an approver token `approver` calls too.
   igni-client refuses a call it knows the connection cannot make with
   `AccessRefused` before sending it (`igni_client.access`), and reads
   igni's own refusal into the same error.
5. **Documentation.** Each package's README, which is its PyPI page, is a
   complete reference. Every area and method is documented, with
   examples.

## Summary

| | Total | Done |
|---|---|---|
| RPC methods | 105 (4 not for clients) | 101 of 101 |
| Messages | 45 | 45 |
| Push channels | 26 | 26 |
| PyPI documentation | 3 packages | 3 |

## RPC methods

### Sessions

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | `attach_session` | `await igni.sessions.attach(…)` | client | ✅ AttachSessionParams | ✅ `AttachSessionResult` | yes | ✅ done | not followed: the approvals and runs it shows again carry no request id and no end; on `igni` though scoped `session`: a session is attached before there is a `Session` to call it on; `igni.sessions.create()` and `.open()` are built on it |
| 2 | `list_sessions` | `await session.list_sessions(…)` | client | ✅ NoArgs | ✅ `SessionListResult` |  | ✅ done |  |
| 3 | `switch_session` | `await session.switch(…)` | client | ✅ SessionIdArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 4 | `get_session_id` | `await session.current_id(…)` | client | ✅ NoArgs | ✅ `str` |  | ✅ done |  |
| 5 | `get_project_dir` | `await session.get_project_dir(…)` | client | ✅ NoArgs | ✅ `str` |  | ✅ done |  |
| 6 | `get_status` | `await session.status(…)` | client | ✅ NoArgs | ✅ `StatusUpdate` |  | ✅ done |  |
| 7 | `get_processing` | `await session.is_processing(…)` | client | ✅ NoArgs | ✅ `bool` |  | ✅ done |  |
| 8 | `get_run_timeout` | `await session.run_timeout(…)` | client | ✅ NoArgs | ✅ `int` |  | ✅ done |  |

### Runs

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 9 | `cancel_run` | `await session.cancel(…)` | client | ✅ NoArgs | ✅ `None` | yes | ✅ done | not followed: the `info` and `stream_end` it causes belong to the turn it stops |
| 10 | `cancel_agent_run` | `await igni.agents.cancel_run(…)` | client | ✅ AgentRunArgs | ✅ `CancelAgentRunResult` |  | ✅ done |  |
| 11 | `get_pending_messages` | `await session.runs.pending_messages(…)` | client | ✅ SessionIdArgs | ✅ `list[PendingMessage]` |  | ✅ done |  |
| 12 | `get_interrupted_runs` | `await session.runs.interrupted(…)` | client | ✅ SessionIdArgs | ✅ `list[InterruptedRun]` |  | ✅ done |  |
| 13 | `discard_interrupted_run` | `await session.runs.discard_interrupted(…)` | client | ✅ InterruptedRunArgs | ✅ `DiscardInterruptedRunResult` |  | ✅ done |  |
| 14 | `upload_attachment` | `await session.upload_attachment(…)` | client | ✅ UploadAttachmentArgs | ✅ `UploadAttachmentResult` |  | ✅ done |  |
| 15 | `fire_session_start_hook` | `await session.fire_session_start_hook(…)` | client | ✅ NoArgs | ✅ `None` |  | ✅ done |  |
| 16 | `shutdown` | `await session.shutdown(…)` | window | ✅ NoArgs | ✅ `None` |  | ✅ done |  |

### History & context

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 17 | `get_chat_history` | `await session.history.get(…)` | client | ✅ SessionIdArgs | ✅ `list[ChatTurn]` |  | ✅ done |  |
| 18 | `search_chat` | `await session.history.search(…)` | client | ✅ SearchChatArgs | ✅ `list[ChatSearchHit]` |  | ✅ done |  |
| 19 | `truncate_history` | `await session.history.truncate(…)` | client | ✅ TruncateHistoryArgs | ✅ `TruncateHistoryResult` |  | ✅ done |  |
| 20 | `count_context_tokens` | `await session.context.tokens(…)` | client | ✅ NoArgs | ✅ `int` |  | ✅ done |  |
| 21 | `get_context_breakdown` | `await session.context.breakdown(…)` | client | ✅ NoArgs | ✅ `ContextBreakdown` |  | ✅ done |  |
| 22 | `compact_if_needed` | `await session.context.compact(…)` | client | ✅ CompactIfNeededArgs | ✅ `SessionCleared \| None` |  | ✅ done |  |
| 23 | `extract_learnings` | `await session.extract_learnings(…)` | client | ✅ ExtractLearningsArgs | ✅ `None` |  | ✅ done |  |

### Loop

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 24 | `loop_status` | `await session.loop.status(…)` | client | ✅ NoArgs | ✅ `LoopStatusSnapshot` |  | ✅ done |  |
| 25 | `loop_resume` | `await session.loop.resume(…)` | client | ✅ NoArgs | ✅ `str` |  | ✅ done |  |
| 26 | `loop_pause` | `await session.loop.pause(…)` | client | ✅ NoArgs | ✅ `bool` |  | ✅ done |  |
| 27 | `pop_pending_loop_iteration` | `await session.loop.next_iteration(…)` | client | ✅ NoArgs | ✅ `LoopAdvance \| None` |  | ✅ done |  |
| 28 | `cancel_pending_loop` | `await session.loop.cancel(…)` | client | ✅ NoArgs | ✅ `bool` |  | ✅ done |  |

### Plans

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 29 | `get_latest_plan` | `await session.plan.latest(…)` | client | ✅ NoArgs | ✅ `LatestPlanResult` |  | ✅ done |  |
| 30 | `approve_plan` | `session.plan.approve(…)` → `Call` | approver | ✅ PlanRunArgs | ✅ `PlanDecisionResult` | yes | ✅ done | followed: `plan_decided` by `run_id` |
| 31 | `dismiss_plan` | `session.plan.dismiss(…)` → `Call` | client | ✅ PlanRunArgs | ✅ `PlanDecisionResult` | yes | ✅ done | followed: `plan_decided` by `run_id` |
| 32 | `get_todos` | `await session.todos(…)` | client | ✅ NoArgs | ✅ `list[TodoItem]` |  | ✅ done |  |

### Models

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 33 | `switch_model` | `await session.models.switch(…)` | client | ✅ SwitchModelArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 34 | `get_model_registry` | `await session.models.list(…)` | client | ✅ NoArgs | ✅ `ModelRegistryResult` |  | ✅ done |  |
| 35 | `get_display_config` | `await session.display_config(…)` | client | ✅ NoArgs | ✅ `DisplayConfig` |  | ✅ done |  |
| 36 | `toggle_verbose` | `await session.toggle_verbose(…)` | client | ✅ NoArgs | ✅ `bool` |  | ✅ done |  |

### Permissions

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 37 | `check_permission` | `await session.permissions.check(…)` | client | ✅ CheckPermissionArgs | ✅ `Literal['allow', 'ask', 'deny']` |  | ✅ done |  |
| 38 | `save_permission_rule` | `await session.permissions.save_rule(…)` | window | ✅ SavePermissionRuleArgs | ✅ `None` |  | ✅ done |  |
| 39 | `get_group_policy` | `await igni.group_policy(…)` | client | ✅ NoArgs | ✅ `GroupPolicyPackResult` |  | ✅ done |  |

### Workspace

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 40 | `get_workspace_trust` | `await session.workspace.trust(…)` | client | ✅ NoArgs | ✅ `WorkspaceTrustStatus` |  | ✅ done |  |
| 41 | `set_workspace_trust` | `await session.workspace.set_trust(…)` | window | ✅ TrustDecisionArgs | ✅ `WorkspaceTrustStatus` | yes | ✅ done | not followed: igni pushes `workspace_trust_required` only to the windows showing the trust dialog |

### Files

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 42 | `complete_files` | `await session.files.complete(…)` | client | ✅ CompleteFilesArgs | ✅ `FileCompletion` |  | ✅ done |  |
| 43 | `list_dirs` | `await igni.files.list_dirs(…)` | client | ✅ ListDirsArgs | ✅ `DirListResult` |  | ✅ done |  |
| 44 | `read_file` | `await session.files.read(…)` | client | ✅ ReadFileArgs | ✅ `ReadFileResult` |  | ✅ done |  |
| 45 | `search_code` | `await session.files.search(…)` | client | ✅ SearchCodeArgs | ✅ `SearchCodeResult` |  | ✅ done |  |
| 46 | `pick_dir_native` | `await session.files.pick_dir(…)` | client | ✅ PickDirArgs | ✅ `PickDirResult` |  | ✅ done |  |

### Shell & processes

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 47 | `run_shell` | `await session.run_shell(…)` | window | ✅ RunShellArgs | ✅ `RunShellResult` | yes | ✅ done | not followed: a command that moves to the background is reported by `process_*` pushes carrying its `pid` |
| 48 | `list_background_processes` | `await igni.processes.list(…)` | client | ✅ NoArgs | ✅ `list[ProcessRow]` |  | ✅ done |  |
| 49 | `read_process_tail` | `await igni.processes.tail(…)` | client | ✅ ProcessTailArgs | ✅ `ProcessTailResult` |  | ✅ done |  |
| 50 | `stop_background_process` | `igni.processes.stop(…)` → `Call` | client | ✅ ProcessArgs | ✅ `StopProcessResult` | yes | ✅ done | followed: `process_*` by `pid` |

### Agents

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 51 | `get_agent_details` | `await session.agents.list(…)` | client | ✅ NoArgs | ✅ `list[AgentInfo]` |  | ✅ done |  |
| 52 | `promote_ephemeral_agent` | `await session.agents.promote(…)` | window | ✅ PromoteAgentArgs | ✅ `PromoteEphemeralResult` |  | ✅ done |  |
| 53 | `discard_ephemeral_agent` | `await session.agents.discard(…)` | client | ✅ AgentNameArgs | ✅ `DiscardEphemeralResult` |  | ✅ done |  |

### Skills & commands

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 54 | `get_skill_names` | `await session.skills.names(…)` | client | ✅ NoArgs | ✅ `list[str]` |  | ✅ done |  |
| 55 | `get_skill_definitions` | `await session.skills.definitions(…)` | client | ✅ NoArgs | ✅ `list[SkillDefinition]` |  | ✅ done |  |
| 56 | `get_skill_details` | `await session.skills.list(…)` | client | ✅ NoArgs | ✅ `list[SkillInfo]` |  | ✅ done |  |
| 57 | `get_slash_commands` | `await session.slash_commands(…)` | client | ✅ NoArgs | ✅ `list[SlashCommand]` |  | ✅ done |  |
| 58 | `get_output_styles` | `await session.output_styles(…)` | client | ✅ NoArgs | ✅ `OutputStylesResult` |  | ✅ done |  |
| 59 | `dispatch_visualization_action` | `session.visualization_action(…)` → `Call` | client | ✅ VisualizationActionArgs | ✅ `VisualizationActionResult` | yes | ✅ done | followed: `visualization_action_dispatched` by session, action and params |

### Hooks

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 60 | `get_hooks_details` | `await session.hooks.list(…)` | client | ✅ NoArgs | ✅ `list[HookEntryView]` |  | ✅ done |  |
| 61 | `reload_hooks` | `await session.hooks.reload(…)` | client | ✅ NoArgs | ✅ `InfoMessage` |  | ✅ done |  |

### Scheduler

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 62 | `start_scheduler` | `session.scheduler.start(…)` → `Call` | client | ✅ NoArgs | ✅ `None` | yes | ✅ done | followed: `scheduler_*` by session |
| 63 | `execute_scheduled_task` | `await session.scheduler.execute(…)` | client | ✅ ExecuteScheduledTaskArgs | ✅ `str` | yes | ✅ done | not followed: what the task's tools push carries nothing that says which run it came from |
| 64 | `cancel_scheduled_task` | `await session.scheduler.cancel(…)` | client | ✅ ScheduledTaskArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 65 | `get_scheduled_tasks` | `await session.scheduler.list(…)` | client | ✅ ScheduledTasksArgs | ✅ `list[ScheduledTask]` |  | ✅ done |  |

### Workflows

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 66 | `list_workflows` | `await session.workflows.list(…)` | client | ✅ WorkflowListRequest | ✅ `list[WorkflowListItem]` |  | ✅ done |  |
| 67 | `run_workflow` | `session.workflows.run(…)` → `Call` | client | ✅ WorkflowRunRequest | ✅ `WorkflowRunResponse` | yes | ✅ done | followed: `workflow_event` by the answer's `workflow_run_id` |
| 68 | `cancel_workflow` | `session.workflows.cancel(…)` → `Call` | client | ✅ WorkflowCancelRequest | ✅ `WorkflowCancelResponse` | yes | ✅ done | followed: `workflow_event` by `workflow_run_id` |

### MCP

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 69 | `ensure_mcp` | `await session.mcp.ensure(…)` | client | ✅ NoArgs | ✅ `McpInitResult` |  | ✅ done |  |
| 70 | `get_mcp_status` | `await session.mcp.status(…)` | client | ✅ NoArgs | ✅ `list[McpServerStatus]` |  | ✅ done |  |
| 71 | `get_mcp_servers` | `await session.mcp.servers(…)` | client | ✅ NoArgs | ✅ `list[McpServerSummary]` |  | ✅ done |  |
| 72 | `get_mcp_server_details` | `await session.mcp.server_details(…)` | client | ✅ NoArgs | ✅ `list[McpServerSnapshot]` |  | ✅ done |  |
| 73 | `mcp_connect` | `await session.mcp.connect(…)` | client | ✅ McpServerArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 74 | `mcp_disconnect` | `await session.mcp.disconnect(…)` | client | ✅ McpServerArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 75 | `set_mcp_tool_enabled` | `await session.mcp.set_tool_enabled(…)` | client | ✅ McpToolEnabledArgs | ✅ `McpToolToggleResult` |  | ✅ done |  |

### Plugins

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 76 | `get_plugin_details` | `await session.plugins.list(…)` | client | ✅ NoArgs | ✅ `list[PluginInfo]` |  | ✅ done |  |
| 77 | `get_plugin_contents` | `await session.plugins.contents(…)` | client | ✅ PluginNameArgs | ✅ `PluginContents` |  | ✅ done |  |
| 78 | `preview_plugin` | `await session.plugins.preview(…)` | client | ✅ PreviewPluginArgs | ✅ `PluginContents` |  | ✅ done |  |
| 79 | `install_plugin` | `await session.plugins.install(…)` | window | ✅ InstallPluginArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 80 | `update_plugin` | `await session.plugins.update(…)` | window | ✅ UpdatePluginArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 81 | `remove_plugin` | `await session.plugins.remove(…)` | window | ✅ PluginNameArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 82 | `set_plugin_enabled` | `await session.plugins.set_enabled(…)` | window | ✅ PluginEnabledArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 83 | `get_marketplaces` | `await igni.marketplaces.list(…)` | client | ✅ NoArgs | ✅ `list[MarketplaceInfo]` |  | ✅ done |  |
| 84 | `add_marketplace` | `await igni.marketplaces.add(…)` | window | ✅ MarketplaceUrlArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 85 | `remove_marketplace` | `await igni.marketplaces.remove(…)` | window | ✅ MarketplaceNameArgs | ✅ `InfoMessage` |  | ✅ done |  |
| 86 | `refresh_marketplaces` | `await igni.marketplaces.refresh(…)` | client | ✅ RefreshMarketplacesArgs | ✅ `InfoMessage` |  | ✅ done |  |

### Extensions

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 87 | `list_extensions` | `await igni.extensions.list(…)` | client | ✅ NoArgs | ✅ `ExtensionListResult` |  | ✅ done |  |
| 88 | `set_extension_settings` | `await igni.extensions.set_settings(…)` | window | ✅ SetExtensionSettingsArgs | ✅ `ExtensionListResult` |  | ✅ done |  |

### Notifications

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 89 | `notifications_list` | `await igni.notifications.list(…)` | client | ✅ NoArgs | ✅ `NotificationsListResult` | yes | ✅ done | not followed: the `notifications_changed` push repeats the counts the answer carries |
| 90 | `notifications_counts` | `await igni.notifications.counts(…)` | client | ✅ NoArgs | ✅ `NotificationCounts` |  | ✅ done |  |
| 91 | `notifications_mark_read` | `await igni.notifications.mark_read(…)` | client | ✅ MarkReadArgs | ✅ `NotificationsReadResult` | yes | ✅ done | not followed: the `notifications_changed` push repeats the counts the answer carries |

### Sign-in & server

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 92 | `login` | `igni.auth.login(…)` → `Call` | window | ✅ NoArgs | ✅ `LoginStarted` | yes | ✅ done | followed: `login_status` to `login_result` |
| 93 | `discover_server` | `await igni.auth.discover_server(…)` | client | ✅ DiscoverServerArgs | ✅ `ServerFound` |  | ✅ done |  |
| 94 | `set_server` | `await igni.auth.set_server(…)` | window | ✅ SetServerArgs | ✅ `ServerChoice` |  | ✅ done |  |
| 95 | `reload_cloud_credentials` | `await session.auth.reload_credentials(…)` | window | ✅ NoArgs | ✅ `StatusUpdate` |  | ✅ done |  |
| 96 | `clear_cloud_credentials` | `await session.auth.sign_out(…)` | window | ✅ NoArgs | ✅ `StatusUpdate` | yes | ✅ done | not followed: `notifications_changed` carries the new counts |
| 97 | `get_cloud_plan` | `await session.auth.plan(…)` | client | ✅ NoArgs | ✅ `CloudPlan \| None` |  | ✅ done |  |
| 98 | `check_for_update` | `await igni.check_for_update(…)` | client | ✅ NoArgs | ✅ `UpdateAvailable \| None` |  | ✅ done |  |

### Approvals

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 99 | `mint_approver_token` | `await igni.approvers.mint_token(…)` | window | ✅ NoArgs | ✅ `ApproverTokenMinted` |  | ✅ done |  |
| 100 | `revoke_approver_tokens` | `await igni.approvers.revoke_tokens(…)` | window | ✅ NoArgs | ✅ `ApproverTokensRevoked` |  | ✅ done |  |

### Extension pages

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 101 | `host_model` | — | page | ✅ PageRequest | ✅ `Reply` | yes | ⛔ not for clients | an extension page's call: igni's window makes it for the page it hosts, setting `caller`, which igni honours from no other connection |
| 102 | `window_model` | `await igni.window.model(…)` | window | ✅ WindowModelArgs | ✅ `WindowModelResult` | yes | ✅ done | not followed: a `window_model_changed` push says which window changed and its new revision |
| 103 | `extension_service_token` | — | page | ✅ NoArgs | ✅ `PageTokenReply` |  | ⛔ not for clients | an extension page's call: it hands the page its service's token, and only igni's window speaks for a page |

### Platform only

| # | Wire method | SDK call | Access | Args (igni-core) | Result (igni-core) | Streams | SDK | Notes |
|---|---|---|---|---|---|---|---|---|
| 104 | `deliver_service_events` | — | platform | ✅ ServiceEventsParams | ✅ `ServiceEventsAck` | yes | ⛔ not for clients | the platform's call: Fleet delivers an extension service's events on its own control connection |
| 105 | `vm_sign_in` | — | platform | ✅ VmSignInParams | ✅ `VmCredentialState` | yes | ⛔ not for clients | the platform's call: Fleet signs a VM's igni in on its control connection |

## Messages

Every message has a generated class in `igni_client.models`; those igni
sends are re-exported from `igni_client.events`, those a client sends from
`igni_client.frames`. `Unknown` is only for a message type newer than this
igni-client.

| # | Message | Direction | SDK class | SDK | Notes |
|---|---|---|---|---|---|
| 1 | `cancel` | client → igni | `Cancel` | ✅ done | typed, not sent: `cancel_run` does the same and answers, so `session.cancel()` calls it |
| 2 | `cancel_login` | client → igni | `CancelLogin` | ✅ done | sent by `igni.auth.cancel_login()` |
| 3 | `command` | client → igni | `Command` | ✅ done | sent by `session.command()` |
| 4 | `command_result` | igni → client | `CommandResult` | ✅ done |  |
| 5 | `content_delta` | igni → client | `ContentDelta` | ✅ done |  |
| 6 | `error` | igni → client | `ErrorMessage` | ✅ done |  |
| 7 | `hitl_decision` | client → igni | `HitlDecision` | ✅ done | sent by a row of `hitl_response_batch` |
| 8 | `hitl_request` | igni → client | `Requirement` | ✅ done |  |
| 9 | `hitl_response` | client → igni | `HitlResponse` | ✅ done | typed, not sent: answers one call of a pause and leaves the rest refused; `hitl_response_batch` answers every call of it, which is what `ApprovalRequested` sends |
| 10 | `hitl_response_batch` | client → igni | `HitlResponseBatch` | ✅ done | sent by `ApprovalRequested.approve()`, `.reject()` and `.decide()` |
| 11 | `info` | igni → client | `InfoMessage` | ✅ done |  |
| 12 | `mcp_toggle` | client → igni | `McpToggle` | ✅ done | typed, not sent: the methods `mcp_connect` and `mcp_disconnect` do the same, so `session.mcp.connect()` and `.disconnect()` call them |
| 13 | `model_completed` | igni → client | `ModelCompleted` | ✅ done |  |
| 14 | `model_switch` | client → igni | `ModelSwitch` | ✅ done | typed, not sent: the method `switch_model` does the same, so `session.models.switch()` calls it |
| 15 | `push_notification` | igni → client | `PushNotification` | ✅ done |  |
| 16 | `queue_message` | client → igni | `QueueMessage` | ✅ done | sent by `session.queue()` |
| 17 | `reasoning_started` | igni → client | `ReasoningStarted` | ✅ done |  |
| 18 | `requirement_details` | igni → client | `RequirementDetails` | ✅ done |  |
| 19 | `requirement_resolved` | igni → client | `RequirementResolved` | ✅ done |  |
| 20 | `rpc_request` | client → igni | `RpcRequest` | ✅ done | sent by every generated method |
| 21 | `rpc_response` | igni → client | `RpcResponse` | ✅ done |  |
| 22 | `run_completed` | igni → client | `RunCompleted` | ✅ done |  |
| 23 | `run_error` | igni → client | `RunError` | ✅ done |  |
| 24 | `run_paused` | igni → client | `RunPaused` | ✅ done |  |
| 25 | `run_started` | igni → client | `RunStarted` | ✅ done |  |
| 26 | `scheduler_event` | igni → client | `SchedulerEvent` | ✅ done |  |
| 27 | `session_cleared` | igni → client | `SessionCleared` | ✅ done |  |
| 28 | `session_list` | client → igni | `SessionList` | ✅ done | typed, not sent: the method `list_sessions` answers the same, so `session.list_sessions()` calls it |
| 29 | `session_list_result` | igni → client | `SessionListResult` | ✅ done |  |
| 30 | `session_switch` | client → igni | `SessionSwitch` | ✅ done | typed, not sent: the method `switch_session` does the same, so `session.switch()` calls it |
| 31 | `shutdown` | client → igni | `Shutdown` | ✅ done | typed, not sent: stops igni itself, for every window and program attached, and only igni's window may; `session.shutdown()` winds one session down instead |
| 32 | `status_update` | igni → client | `StatusUpdate` | ✅ done |  |
| 33 | `stream_end` | igni → client | `StreamEnd` | ✅ done |  |
| 34 | `streaming_done` | igni → client | `StreamingDone` | ✅ done |  |
| 35 | `task_created` | igni → client | `TaskCreated` | ✅ done |  |
| 36 | `task_iteration` | igni → client | `TaskIteration` | ✅ done |  |
| 37 | `task_state_updated` | igni → client | `TaskStateUpdated` | ✅ done |  |
| 38 | `task_updated` | igni → client | `TaskUpdated` | ✅ done |  |
| 39 | `tool_completed` | igni → client | `ToolCompleted` | ✅ done |  |
| 40 | `tool_error` | igni → client | `ToolError` | ✅ done |  |
| 41 | `tool_started` | igni → client | `ToolStarted` | ✅ done |  |
| 42 | `typing` | both | `Typing` | ✅ done | sent by `session.typing()` |
| 43 | `user_message` | client → igni | `UserMessage` | ✅ done | sent by `session.send()` and `session.ask()` |
| 44 | `user_message_received` | igni → client | `UserMessageReceived` | ✅ done |  |
| 45 | `welcome` | igni → client | `Welcome` | ✅ done |  |

## Push channels

A push notification on a channel the contract types parses into that
channel's class, a `PushNotification` whose `payload` is typed.

| # | Channel | SDK class | Payload | SDK |
|---|---|---|---|---|
| 1 | `background_process_done` | `BackgroundProcessDonePush` | `BackgroundProcessDonePayload` | ✅ done |
| 2 | `file_edited` | `FileEditedPush` | `FileEditedPayload` | ✅ done |
| 3 | `host_signal` | `HostSignalPush` | `HostSignal` | ✅ done |
| 4 | `http_retry_attempt` | `HttpRetryAttemptPush` | `HttpRetryAttemptPayload` | ✅ done |
| 5 | `http_retry_succeeded` | `HttpRetrySucceededPush` | `HttpRetrySucceededPayload` | ✅ done |
| 6 | `login_result` | `LoginResultPush` | `LoginResultPayload` | ✅ done |
| 7 | `login_status` | `LoginStatusPush` | `LoginStatusPayload` | ✅ done |
| 8 | `notifications_changed` | `NotificationsChangedPush` | `NotificationsChanged` | ✅ done |
| 9 | `open_external` | `OpenExternalPush` | `ExternalOpen` | ✅ done |
| 10 | `orchestrate_event` | `OrchestrateEventPush` | `OrchestrateEvent` | ✅ done |
| 11 | `output_style_changed` | `OutputStyleChangedPush` | `OutputStyleChangedPayload` | ✅ done |
| 12 | `permission_mode_changed` | `PermissionModeChangedPush` | `PermissionModeChange` | ✅ done |
| 13 | `plan_decided` | `PlanDecidedPush` | `PlanDecidedPayload` | ✅ done |
| 14 | `plan_submitted` | `PlanSubmittedPush` | `PlanSubmittedPayload` | ✅ done |
| 15 | `process_exited` | `ProcessExitedPush` | `ProcessExitedPayload` | ✅ done |
| 16 | `process_line` | `ProcessLinePush` | `ProcessLinePayload` | ✅ done |
| 17 | `process_started` | `ProcessStartedPush` | `ProcessStartedPayload` | ✅ done |
| 18 | `scheduler_completed` | `SchedulerCompletedPush` | `SchedulerCompletedPayload` | ✅ done |
| 19 | `scheduler_started` | `SchedulerStartedPush` | `SchedulerStartedPayload` | ✅ done |
| 20 | `session_named` | `SessionNamedPush` | `SessionNamedPayload` | ✅ done |
| 21 | `todos_updated` | `TodosUpdatedPush` | `TodosUpdatedPayload` | ✅ done |
| 22 | `visualization_action_dispatched` | `VisualizationActionDispatchedPush` | `VisualizationActionDispatchedPayload` | ✅ done |
| 23 | `vm_credential` | `VmCredentialPush` | `VmCredentialState` | ✅ done |
| 24 | `window_model_changed` | `WindowModelChangedPush` | `WindowChange` | ✅ done |
| 25 | `workflow_event` | `WorkflowEventPush` | `WorkflowEventRecord` | ✅ done |
| 26 | `workspace_trust_required` | `WorkspaceTrustRequiredPush` | `WorkspaceTrustStatus` | ✅ done |

## PyPI documentation

| Package | Status | What "done" means |
|---|---|---|
| `igni-client` | ✅ written: a complete reference, its API section generated from the contract; its examples run as tests | Every area and method above: what it does, its arguments, its result, its errors, and an example. Streaming, approvals, events, reconnects, and Fleet vs local, each with a worked example. |
| `igni-service` | ✅ written (branch `docs/pypi-reference`, 2,591 lines; its examples run as tests); on PyPI from 0.1.1 | The plain opening (PR #18), then every capability documented in depth. |
| `igni-extension` | ✅ written (branch `docs/pypi-reference`, 1,739 lines; its examples run as tests); on PyPI from 0.1.1 | The same depth for an extension's process: tools, hooks, host calls, service calls, events. |

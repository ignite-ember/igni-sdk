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

1. **igni-core publishes the whole contract.** Every RPC method has an
   arguments model and a concrete result type: no raw `dict`, no `Any`.
   `docs/rpc-contract.json` holds, for each method, the JSON Schema of
   its arguments and result, who may call it, and which messages it
   streams. A test regenerates the file and fails when the committed copy
   differs.
2. **igni-sdk generates the typed client from that file.** The models
   and the methods, grouped by area, are generated. CI fails when the
   generated code no longer matches igni-core's contract. The by-name
   `rpc()` call is removed once every row is typed.
3. **Streaming.** A method whose work arrives as messages returns an
   async iterator of typed events, the way `Session.send()` follows a run.
4. **Documentation.** Each package's README, which is its PyPI page, is a
   complete reference. Every area and method is documented, with
   examples.

## Summary

| | Total | Done |
|---|---|---|
| RPC methods | 104 (2 not for clients) | 0 |
| Messages | 45 | 0 |
| PyPI documentation | 3 packages | 0 |

## RPC methods

### Sessions

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 1 | `attach_session` | `igni.sessions.create() / .open(id)` | n/a | n/a (pool-level) | 🟨 typed, to re-check | already typed |
| 2 | `list_sessions` | `igni.sessions.list()` | ❌ raw dict | ✅ msg.SessionListResult | 🟨 typed, to re-check | already typed |
| 3 | `switch_session` | `session.switch_to()` | ✅ SessionIdArgs | ✅ msg.Info | ⬜ todo |  |
| 4 | `get_session_id` | `session.id (attach answer)` | ❌ raw dict | ✅ str | ⬜ todo | already used internally |
| 5 | `get_project_dir` | `session.project_dir()` | ❌ raw dict | ✅ str | ⬜ todo |  |
| 6 | `get_status` | `session.status()` | ❌ raw dict | ✅ msg.StatusUpdate | 🟨 typed, to re-check | already typed |
| 7 | `get_processing` | `session.is_processing()` | ❌ raw dict | ✅ bool | ⬜ todo |  |
| 8 | `get_run_timeout` | `session.run_timeout()` | ❌ raw dict | ✅ int | ⬜ todo |  |

### Runs

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 9 | `cancel_run` | `session.cancel()` | ❌ raw dict | ✅ None | ⬜ todo | exists as a frame; check |
| 10 | `cancel_agent_run` | `session.cancel_agent_run(run_id)` | ✅ AgentRunArgs | ✅ CancelAgentRunResult | ⬜ todo |  |
| 11 | `get_pending_messages` | `session.pending_messages()` | ✅ SessionIdArgs | ✅ list[PendingMessage] | ⬜ todo |  |
| 12 | `get_interrupted_runs` | `session.interrupted_runs()` | ✅ SessionIdArgs | ✅ list[InterruptedRun] | ⬜ todo |  |
| 13 | `discard_interrupted_run` | `session.discard_interrupted_run(run_id)` | ✅ InterruptedRunArgs | ✅ DiscardInterruptedRunResult | ⬜ todo |  |
| 14 | `upload_attachment` | `session.upload_attachment(path|bytes)` | ✅ UploadAttachmentArgs | ✅ UploadAttachmentResult | ⬜ todo |  |
| 15 | `fire_session_start_hook` | `session.fire_start_hook()` | ❌ raw dict | ✅ None | ⬜ todo |  |
| 16 | `shutdown` | `igni.shutdown()` | ❌ raw dict | ✅ None | ⬜ todo | stops the igni; documented as such |

### History & context

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 17 | `get_chat_history` | `session.history()` | ✅ SessionIdArgs | ✅ list[ChatTurn] | 🟨 typed, to re-check | already typed |
| 18 | `search_chat` | `session.search(query)` | ✅ SearchChatArgs | ✅ list[ChatSearchHit] | ⬜ todo |  |
| 19 | `truncate_history` | `session.truncate(...)` | ✅ TruncateHistoryArgs | ✅ TruncateHistoryResult | ⬜ todo |  |
| 20 | `count_context_tokens` | `session.context.tokens()` | ❌ raw dict | ✅ int | ⬜ todo |  |
| 21 | `get_context_breakdown` | `session.context.breakdown()` | ❌ raw dict | ✅ ContextBreakdown | ⬜ todo |  |
| 22 | `compact_if_needed` | `session.context.compact()` | ✅ CompactIfNeededArgs | ✅ msg.SessionCleared \| None | ⬜ todo |  |
| 23 | `extract_learnings` | `session.extract_learnings()` | ✅ ExtractLearningsArgs | ✅ None | ⬜ todo |  |

### Loop

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 24 | `loop_status` | `session.loop.status()` | ❌ raw dict | ✅ LoopStatusSnapshot | ⬜ todo |  |
| 25 | `loop_resume` | `session.loop.resume()` | ❌ raw dict | ✅ str | ⬜ todo |  |
| 26 | `loop_pause` | `session.loop.pause()` | ❌ raw dict | ✅ bool | ⬜ todo |  |
| 27 | `pop_pending_loop_iteration` | `session.loop.next()` | ❌ raw dict | ✅ LoopAdvance \| None | ⬜ todo |  |
| 28 | `cancel_pending_loop` | `session.loop.cancel()` | ❌ raw dict | ✅ bool | ⬜ todo |  |

### Plans

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 29 | `get_latest_plan` | `session.plan.latest()` | ❌ raw dict | ❌ Any | ⬜ todo | result is Any in igni-core |
| 30 | `approve_plan` | `session.plan.approve()` | ❌ raw dict | ❌ Awaitable[Any] | ⬜ todo | result is Any in igni-core |
| 31 | `dismiss_plan` | `session.plan.dismiss()` | ❌ raw dict | ❌ Awaitable[Any] | ⬜ todo | result is Any in igni-core |
| 32 | `get_todos` | `session.todos()` | ❌ raw dict | ✅ list[TodoItemWire] | ⬜ todo |  |

### Models

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 33 | `switch_model` | `session.use_model(name)` | ✅ SwitchModelArgs | ✅ msg.Info | 🟨 typed, to re-check | already typed |
| 34 | `get_model_registry` | `igni.models.list()` | ❌ raw dict | ✅ ModelRegistryResult | 🟨 typed, to re-check | already typed (catalogue) |
| 35 | `get_display_config` | `igni.display_config()` | ❌ raw dict | ✅ DisplayConfig | ⬜ todo |  |
| 36 | `toggle_verbose` | `igni.set_verbose(on)` | ❌ raw dict | ✅ bool | ⬜ todo |  |

### Permissions

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 37 | `check_permission` | `igni.permissions.check(tool, args)` | ✅ CheckPermissionArgs | ✅ PermissionLevel | ⬜ todo |  |
| 38 | `save_permission_rule` | `igni.permissions.save_rule(rule)` | ✅ SavePermissionRuleArgs | ✅ None | ⬜ todo |  |
| 39 | `get_group_policy` | `igni.permissions.group_policy()` | ❌ raw dict | ✅ GroupPolicyPackResult | ⬜ todo |  |

### Workspace

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 40 | `get_workspace_trust` | `igni.workspace.trust(dir)` | ❌ raw dict | ✅ WorkspaceTrustStatus | ⬜ todo |  |
| 41 | `set_workspace_trust` | `igni.workspace.set_trust(dir, trusted)` | ❌ raw dict | ✅ WorkspaceTrustStatus | ⬜ todo |  |

### Files

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 42 | `complete_files` | `igni.files.complete(prefix)` | ✅ CompleteFilesArgs | ✅ FileCompletion | ⬜ todo |  |
| 43 | `list_dirs` | `igni.files.list_dirs(path)` | ✅ ListDirsArgs | ✅ DirListResult | ⬜ todo |  |
| 44 | `read_file` | `igni.files.read(path)` | ✅ ReadFileArgs | ✅ ReadFileResult | ⬜ todo |  |
| 45 | `search_code` | `igni.files.search(query)` | ✅ SearchCodeArgs | ✅ SearchCodeResult | ⬜ todo |  |
| 46 | `pick_dir_native` | `igni.files.pick_dir()` | ✅ PickDirArgs | ✅ PickDirResult | ⬜ todo | opens a dialog on the igni machine |

### Shell & processes

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 47 | `run_shell` | `igni.shell.run(cmd) → streams output` | ✅ RunShellArgs | ✅ RunShellResult | ⬜ todo | streaming |
| 48 | `list_background_processes` | `igni.processes.list()` | ❌ raw dict | ✅ list[ProcessRow] | ⬜ todo |  |
| 49 | `read_process_tail` | `igni.processes.tail(id) / .follow(id)` | ✅ ProcessTailArgs | ✅ ProcessTailResult | ⬜ todo | streaming |
| 50 | `stop_background_process` | `igni.processes.stop(id)` | ✅ ProcessArgs | ✅ StopProcessResult | ⬜ todo |  |

### Agents

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 51 | `get_agent_details` | `igni.agents.list()` | ❌ raw dict | ✅ list[AgentInfo] | ⬜ todo |  |
| 52 | `promote_ephemeral_agent` | `igni.agents.promote(name)` | ✅ PromoteAgentArgs | ✅ PromoteEphemeralResult | ⬜ todo |  |
| 53 | `discard_ephemeral_agent` | `igni.agents.discard(name)` | ✅ AgentNameArgs | ✅ DiscardEphemeralResult | ⬜ todo |  |

### Skills & commands

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 54 | `get_skill_names` | `igni.skills.names()` | ❌ raw dict | ✅ list[str] | ⬜ todo |  |
| 55 | `get_skill_definitions` | `igni.skills.definitions()` | ❌ raw dict | ✅ list[SkillDefinition] | ⬜ todo |  |
| 56 | `get_skill_details` | `igni.skills.list()` | ❌ raw dict | ✅ list[SkillInfo] | ⬜ todo |  |
| 57 | `get_slash_commands` | `igni.slash_commands.list()` | ❌ raw dict | ✅ list[SlashCommandEntry] | ⬜ todo |  |
| 58 | `get_output_styles` | `igni.output_styles.list()` | ❌ raw dict | ✅ OutputStylesResult | ⬜ todo |  |
| 59 | `dispatch_visualization_action` | `session.visualization_action(...)` | ✅ VisualizationActionArgs | ✅ VisualizationActionResult | ⬜ todo |  |

### Hooks

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 60 | `get_hooks_details` | `igni.hooks.list()` | ❌ raw dict | ✅ list[HookEntryView] | ⬜ todo |  |
| 61 | `reload_hooks` | `igni.hooks.reload()` | ❌ raw dict | ❌ Any | ⬜ todo | result is Any in igni-core |

### Scheduler

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 62 | `start_scheduler` | `igni.scheduler.start()` | ❌ raw dict | ✅ None | ⬜ todo |  |
| 63 | `execute_scheduled_task` | `igni.scheduler.schedule(description) → follows task events` | ❌ raw dict | ❌ Any | ⬜ todo | args and result untyped in igni-core; streaming |
| 64 | `cancel_scheduled_task` | `igni.scheduler.cancel(task_id)` | ❌ raw dict | ❌ Any | ⬜ todo | args and result untyped in igni-core |
| 65 | `get_scheduled_tasks` | `igni.scheduler.list(include_done=…)` | ❌ raw dict | ❌ Any | ⬜ todo | args and result untyped in igni-core |

### Workflows

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 66 | `list_workflows` | `igni.workflows.list()` | ❌ raw dict | ✅ list[WorkflowListItem] | ⬜ todo |  |
| 67 | `run_workflow` | `igni.workflows.run(name) → follows its events` | ❌ raw dict | ✅ WorkflowRunResponse | ⬜ todo | streaming |
| 68 | `cancel_workflow` | `igni.workflows.cancel(id)` | ❌ raw dict | ✅ WorkflowCancelResponse | ⬜ todo |  |

### MCP

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 69 | `ensure_mcp` | `igni.mcp.ensure()` | ❌ raw dict | ✅ McpInitResult | ⬜ todo |  |
| 70 | `get_mcp_status` | `igni.mcp.status()` | ❌ raw dict | ✅ list[McpServerStatus] | ⬜ todo |  |
| 71 | `get_mcp_servers` | `igni.mcp.servers()` | ❌ raw dict | ✅ list[MCPServerSummary] | ⬜ todo |  |
| 72 | `get_mcp_server_details` | `igni.mcp.server_details()` | ❌ raw dict | ✅ list[MCPServerSnapshot] | ⬜ todo |  |
| 73 | `mcp_connect` | `igni.mcp.connect(name)` | ✅ McpServerArgs | ✅ msg.Info | ⬜ todo |  |
| 74 | `mcp_disconnect` | `igni.mcp.disconnect(name)` | ✅ McpServerArgs | ✅ msg.Info | ⬜ todo |  |
| 75 | `set_mcp_tool_enabled` | `igni.mcp.set_tool_enabled(server, tool, on)` | ✅ McpToolEnabledArgs | ✅ MCPToolToggleResult | ⬜ todo |  |

### Plugins

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 76 | `get_plugin_details` | `igni.plugins.list()` | ❌ raw dict | ✅ list[PluginInfo] | ⬜ todo |  |
| 77 | `get_plugin_contents` | `igni.plugins.contents(name)` | ✅ PluginNameArgs | ✅ PluginContents | ⬜ todo |  |
| 78 | `preview_plugin` | `igni.plugins.preview(source)` | ✅ PreviewPluginArgs | ✅ PluginContents | ⬜ todo |  |
| 79 | `install_plugin` | `igni.plugins.install(name)` | ✅ InstallPluginArgs | ✅ msg.Info | ⬜ todo |  |
| 80 | `update_plugin` | `igni.plugins.update(name)` | ✅ UpdatePluginArgs | ✅ msg.Info | ⬜ todo |  |
| 81 | `remove_plugin` | `igni.plugins.remove(name)` | ✅ PluginNameArgs | ✅ msg.Info | ⬜ todo |  |
| 82 | `set_plugin_enabled` | `igni.plugins.set_enabled(name, on)` | ✅ PluginEnabledArgs | ✅ msg.Info | ⬜ todo |  |
| 83 | `get_marketplaces` | `igni.marketplaces.list()` | ❌ raw dict | ✅ list[MarketplaceInfo] | ⬜ todo |  |
| 84 | `add_marketplace` | `igni.marketplaces.add(source)` | ✅ MarketplaceUrlArgs | ✅ msg.Info | ⬜ todo |  |
| 85 | `remove_marketplace` | `igni.marketplaces.remove(name)` | ✅ MarketplaceNameArgs | ✅ msg.Info | ⬜ todo |  |
| 86 | `refresh_marketplaces` | `igni.marketplaces.refresh()` | ✅ RefreshMarketplacesArgs | ✅ msg.Info | ⬜ todo |  |

### Extensions

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 87 | `list_extensions` | `igni.extensions.list()` | ❌ raw dict | ✅ ExtensionListResult | ⬜ todo |  |
| 88 | `set_extension_settings` | `igni.extensions.set_settings(id, settings)` | ✅ SetExtensionSettingsArgs | ✅ ExtensionListResult | ⬜ todo |  |

### Notifications

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 89 | `notifications_list` | `igni.notifications.list()` | ❌ raw dict | ✅ NotificationsListResult | ⬜ todo |  |
| 90 | `notifications_counts` | `igni.notifications.counts()` | ❌ raw dict | ✅ NotificationCounts | ⬜ todo |  |
| 91 | `notifications_mark_read` | `igni.notifications.mark_read(ids)` | ✅ MarkReadArgs | ✅ NotificationsReadResult | ⬜ todo |  |

### Sign-in & server

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 92 | `login` | `igni.auth.login() → follows the sign-in` | ❌ raw dict | ✅ LoginStarted | ⬜ todo | streaming |
| 93 | `discover_server` | `igni.auth.discover_server(url)` | ✅ DiscoverServerArgs | ✅ ServerFound | ⬜ todo |  |
| 94 | `set_server` | `igni.auth.set_server(url)` | ✅ SetServerArgs | ✅ ServerChoice | ⬜ todo |  |
| 95 | `reload_cloud_credentials` | `igni.auth.reload_credentials()` | ❌ raw dict | ✅ msg.StatusUpdate | ⬜ todo |  |
| 96 | `clear_cloud_credentials` | `igni.auth.sign_out()` | ❌ raw dict | ✅ msg.StatusUpdate | ⬜ todo |  |
| 97 | `check_for_update` | `igni.check_for_update()` | ❌ raw dict | ✅ UpdateAvailable \| None | ⬜ todo |  |

### Approvals

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 98 | `mint_approver_token` | `igni.approvers.mint_token(...)` | n/a | n/a (pool-level) | ⬜ todo | pool-level; no handler model yet |
| 99 | `revoke_approver_tokens` | `igni.approvers.revoke_tokens(...)` | n/a | n/a (pool-level) | ⬜ todo | pool-level; no handler model yet |

### Extension pages

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 100 | `host_model` | `—` | n/a | n/a (pool-level) | ⬜ todo | decide: page-only (PAGE_RPCS) |
| 101 | `window_model` | `—` | n/a | n/a (pool-level) | ⬜ todo | decide: page-only |
| 102 | `extension_service_token` | `—` | n/a | n/a (pool-level) | ⬜ todo | decide: page-only (PAGE_RPCS) |

### Platform only

| # | Wire method | SDK call (planned) | Args typed in igni-core | Result typed in igni-core | SDK | Notes |
|---|---|---|---|---|---|---|
| 103 | `deliver_service_events` | `— not for clients` | n/a | n/a (pool-level) | ⛔ not for clients | PLATFORM_RPCS: only the platform's control connection |
| 104 | `vm_sign_in` | `— not for clients` | n/a | n/a (pool-level) | ⛔ not for clients | PLATFORM_RPCS: only the platform's control connection |

## Messages

Every message igni sends to a client has a class on the `refactor/standards`
branch. Most of the messages a client sends do not yet.

| # | Message | Direction | SDK | Notes |
|---|---|---|---|---|
| 1 | `cancel` | client → igni | 🟨 typed, to re-check |  |
| 2 | `cancel_login` | client → igni | ⬜ todo |  |
| 3 | `command` | client → igni | ⬜ todo |  |
| 4 | `command_result` | igni → client | 🟨 typed, to re-check |  |
| 5 | `content_delta` | igni → client | 🟨 typed, to re-check |  |
| 6 | `error` | igni → client | 🟨 typed, to re-check |  |
| 7 | `hitl_decision` | client → igni | 🟨 typed, to re-check |  |
| 8 | `hitl_request` | igni → client | 🟨 typed, to re-check |  |
| 9 | `hitl_response` | client → igni | ⬜ todo |  |
| 10 | `hitl_response_batch` | client → igni | 🟨 typed, to re-check |  |
| 11 | `info` | igni → client | 🟨 typed, to re-check |  |
| 12 | `mcp_toggle` | client → igni | ⬜ todo |  |
| 13 | `model_completed` | igni → client | 🟨 typed, to re-check |  |
| 14 | `model_switch` | client → igni | ⬜ todo |  |
| 15 | `push_notification` | igni → client | 🟨 typed, to re-check |  |
| 16 | `queue_message` | client → igni | 🟨 typed, to re-check |  |
| 17 | `reasoning_started` | igni → client | 🟨 typed, to re-check |  |
| 18 | `requirement_details` | igni → client | 🟨 typed, to re-check |  |
| 19 | `requirement_resolved` | igni → client | 🟨 typed, to re-check |  |
| 20 | `rpc_request` | client → igni | 🟨 typed, to re-check | replaced by the typed methods above |
| 21 | `rpc_response` | igni → client | 🟨 typed, to re-check | answer of every method above |
| 22 | `run_completed` | igni → client | 🟨 typed, to re-check |  |
| 23 | `run_error` | igni → client | 🟨 typed, to re-check |  |
| 24 | `run_paused` | igni → client | 🟨 typed, to re-check |  |
| 25 | `run_started` | igni → client | 🟨 typed, to re-check |  |
| 26 | `scheduler_event` | igni → client | 🟨 typed, to re-check |  |
| 27 | `session_cleared` | igni → client | 🟨 typed, to re-check |  |
| 28 | `session_list` | client → igni | ⬜ todo |  |
| 29 | `session_list_result` | igni → client | 🟨 typed, to re-check |  |
| 30 | `session_switch` | client → igni | ⬜ todo |  |
| 31 | `shutdown` | client → igni | ⬜ todo |  |
| 32 | `status_update` | igni → client | 🟨 typed, to re-check |  |
| 33 | `stream_end` | client → igni | 🟨 typed, to re-check |  |
| 34 | `streaming_done` | igni → client | 🟨 typed, to re-check |  |
| 35 | `task_created` | igni → client | 🟨 typed, to re-check |  |
| 36 | `task_iteration` | igni → client | 🟨 typed, to re-check |  |
| 37 | `task_state_updated` | igni → client | 🟨 typed, to re-check |  |
| 38 | `task_updated` | igni → client | 🟨 typed, to re-check |  |
| 39 | `tool_completed` | igni → client | 🟨 typed, to re-check |  |
| 40 | `tool_error` | igni → client | 🟨 typed, to re-check |  |
| 41 | `tool_started` | igni → client | 🟨 typed, to re-check |  |
| 42 | `typing` | igni → client | 🟨 typed, to re-check |  |
| 43 | `user_message` | client → igni | 🟨 typed, to re-check |  |
| 44 | `user_message_received` | igni → client | 🟨 typed, to re-check |  |
| 45 | `welcome` | igni → client | 🟨 typed, to re-check |  |

## PyPI documentation

| Package | Status | What "done" means |
|---|---|---|
| `igni-client` | ⬜ todo | Every area and method above: what it does, its arguments, its result, its errors, and an example. Streaming, approvals, events, reconnects, and Fleet vs local, each with a worked example. |
| `igni-service` | ⬜ todo | The plain opening (PR #18), then every capability documented in depth. |
| `igni-extension` | ⬜ todo | The same depth for an extension's process: tools, hooks, host calls, service calls, events. |

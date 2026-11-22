// GENERATED from igni-core's RPC contract (version 1) by igni-sdk's tools/client_ts.py — do not edit. Run `make client-api` after refreshing contracts/rpc-contract.json.
//
// Every method a client calls, typed, by namespace. `IgniApi` is what
// `IgniClient` adds for igni as a whole, and `SessionApi` what `Session`
// adds for one session. A method that streams returns a `Call`.

import type { Caller } from "./calls.js";
import { Call } from "./calls.js";
import type { Correlation, MethodSpec } from "./methodSpec.js";
import type {
  AgentInfo,
  ApproverTokenMinted,
  ApproverTokensRevoked,
  AssistantTurn,
  AttachSessionResult,
  BackgroundProcessDonePush,
  BuiltinSlashCommand,
  CancelAgentRunResult,
  CancelRunResult,
  ChatSearchHit,
  ChatTurn,
  CloudPlan,
  CommandResult,
  CompactionOutcome,
  ContentDelta,
  ContextBreakdown,
  DialogAnswered,
  DialogShown,
  DirListResult,
  DiscardEphemeralResult,
  DiscardInterruptedRunResult,
  DiscardPendingMessageResult,
  DisplayConfig,
  ElementFailureArgs,
  ErrorMessage,
  ExtensionListResult,
  ExtensionSlashCommand,
  FileCompletion,
  FileEditedPush,
  GroupPolicyPackResult,
  HookEntryView,
  HttpRetryAttemptPush,
  HttpRetrySucceededPush,
  Hydrated,
  InfoMessage,
  InterruptedRun,
  JsonValue,
  LatestPlanResult,
  LoginResultPush,
  LoginStarted,
  LoginStatusPush,
  LoopAdvance,
  LoopStatusSnapshot,
  MarkdownSlashCommand,
  MarketplaceInfo,
  McpApproval,
  McpInitResult,
  McpServerSnapshot,
  McpServerStatus,
  McpServerSummary,
  McpToolToggleResult,
  ModelCompleted,
  ModelRegistryResult,
  ModelSwitched,
  NotificationCounts,
  NotificationsChangedPush,
  NotificationsListResult,
  NotificationsReadResult,
  OrchestrateEventPush,
  OutputStylesResult,
  PendingMessage,
  PermissionModeChangedPush,
  PickDirResult,
  PlanDecidedPush,
  PlanDecisionResult,
  PlanSubmittedPush,
  PlanTurn,
  PluginContents,
  PluginInfo,
  ProcessExitedPush,
  ProcessLinePush,
  ProcessRow,
  ProcessStartedPush,
  ProcessTailResult,
  PromoteEphemeralResult,
  ReadFileResult,
  ReasoningStarted,
  RequirementDetails,
  Revised,
  RunCompleted,
  RunError,
  RunPaused,
  RunShellResult,
  RunStarted,
  ScheduledTask,
  ScheduledTaskRunResult,
  SchedulerCompletedPush,
  SchedulerStartedPush,
  SearchCodeResult,
  ServerChoice,
  ServerFound,
  SessionListResult,
  SkillDefinition,
  SkillInfo,
  SkillSlashCommand,
  SlashCommand,
  StatsTurn,
  StatusUpdate,
  StopProcessResult,
  StreamEnd,
  StreamingDone,
  TaskCreated,
  TaskIteration,
  TaskStateUpdated,
  TaskUpdated,
  TeamTurn,
  ThinkingTurn,
  ToastAdded,
  TodoItem,
  TodosUpdatedPush,
  ToolCallArgs,
  ToolCompleted,
  ToolError,
  ToolStarted,
  ToolTurn,
  TruncateHistoryResult,
  UpdateAvailable,
  UploadAttachmentResult,
  UserTurn,
  VisualizationActionDispatchedPush,
  VisualizationActionResult,
  VisualizationTurn,
  VisualizationVerdictResult,
  WindowModelChangedPush,
  WindowModelResult,
  WorkflowCancelResponse,
  WorkflowEventPush,
  WorkflowListItem,
  WorkflowRunResponse,
  WorkflowTurn,
  WorkspaceTrustRequiredPush,
  WorkspaceTrustStatus,
  Written,
} from "./models.generated.js";


// What each followed method causes.
export type ApprovePlanEvent = PermissionModeChangedPush | PlanDecidedPush;
export type AttachSessionEvent = ContentDelta | ErrorMessage | InfoMessage | ModelCompleted | ReasoningStarted | RequirementDetails | RunCompleted | RunError | RunPaused | RunStarted | StreamEnd | StreamingDone | TaskCreated | TaskIteration | TaskStateUpdated | TaskUpdated | ToolCompleted | ToolError | ToolStarted | BackgroundProcessDonePush | FileEditedPush | HttpRetryAttemptPush | HttpRetrySucceededPush | OrchestrateEventPush | PermissionModeChangedPush | PlanSubmittedPush | ProcessExitedPush | ProcessLinePush | ProcessStartedPush | TodosUpdatedPush;
export type CancelRunEvent = InfoMessage | StreamEnd;
export type CancelWorkflowEvent = WorkflowEventPush;
export type ClearCloudCredentialsEvent = NotificationsChangedPush;
export type DismissPlanEvent = PlanDecidedPush;
export type DispatchVisualizationActionEvent = VisualizationActionDispatchedPush;
export type ExecuteScheduledTaskEvent = BackgroundProcessDonePush | FileEditedPush | HttpRetryAttemptPush | HttpRetrySucceededPush | OrchestrateEventPush | PermissionModeChangedPush | PlanSubmittedPush | ProcessExitedPush | ProcessLinePush | ProcessStartedPush | TodosUpdatedPush;
export type LoginEvent = LoginResultPush | LoginStatusPush | NotificationsChangedPush;
export type NotificationsListEvent = NotificationsChangedPush;
export type NotificationsMarkReadEvent = NotificationsChangedPush;
export type RunShellEvent = BackgroundProcessDonePush | ProcessExitedPush | ProcessLinePush | ProcessStartedPush;
export type RunWorkflowEvent = WorkflowEventPush;
export type SetWorkspaceTrustEvent = WorkspaceTrustRequiredPush;
export type StartSchedulerEvent = SchedulerCompletedPush | SchedulerStartedPush | BackgroundProcessDonePush | FileEditedPush | HttpRetryAttemptPush | HttpRetrySucceededPush | OrchestrateEventPush | PermissionModeChangedPush | PlanSubmittedPush | ProcessExitedPush | ProcessLinePush | ProcessStartedPush | TodosUpdatedPush;
export type StopBackgroundProcessEvent = BackgroundProcessDonePush | ProcessExitedPush | ProcessLinePush;
export type WindowModelEvent = WindowModelChangedPush;

/**
 * Every method a client calls, by wire name: who may call it, how igni
 * answers it, how long it takes, and what it streams.
 */
export const METHODS: Record<string, MethodSpec> = {
  "add_marketplace": { wire: "add_marketplace", python: "igni.marketplaces.add", scope: "igni", access: "window", reply: "message", streams: [], mayStream: [], duration: "long", timeoutSeconds: 600, correlate: null, followed: false },
  "approve_plan": { wire: "approve_plan", python: "session.plan.approve", scope: "session", access: "approver", reply: "rpc_response", streams: ["push_notification:permission_mode_changed", "push_notification:plan_decided"], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: { by: "payload.run_id", source: "args.run_id" }, followed: true },
  "attach_session": { wire: "attach_session", python: "igni.sessions.attach", scope: "session", access: "client", reply: "rpc_response", streams: ["content_delta", "error", "info", "model_completed", "reasoning_started", "requirement_details", "run_completed", "run_error", "run_paused", "run_started", "stream_end", "streaming_done", "task_created", "task_iteration", "task_state_updated", "task_updated", "tool_completed", "tool_error", "tool_started"], mayStream: ["push_notification:background_process_done", "push_notification:file_edited", "push_notification:http_retry_attempt", "push_notification:http_retry_succeeded", "push_notification:orchestrate_event", "push_notification:permission_mode_changed", "push_notification:plan_submitted", "push_notification:process_exited", "push_notification:process_line", "push_notification:process_started", "push_notification:todos_updated"], duration: "io", timeoutSeconds: 30, correlate: { by: "id", source: "request.id" }, followed: true },
  "cancel_agent_run": { wire: "cancel_agent_run", python: "igni.agents.cancel_run", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "cancel_pending_loop": { wire: "cancel_pending_loop", python: "session.loop.cancel", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "cancel_run": { wire: "cancel_run", python: "session.cancel", scope: "session", access: "client", reply: "rpc_response", streams: ["info", "stream_end"], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: { by: "session_id", source: "request.session_id" }, followed: true },
  "cancel_scheduled_task": { wire: "cancel_scheduled_task", python: "session.scheduler.cancel", scope: "session", access: "client", reply: "message", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "cancel_workflow": { wire: "cancel_workflow", python: "session.workflows.cancel", scope: "session", access: "client", reply: "rpc_response", streams: ["push_notification:workflow_event"], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: { by: "payload.workflow_run_id", source: "args.workflow_run_id" }, followed: true },
  "check_for_update": { wire: "check_for_update", python: "igni.check_for_update", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "network", timeoutSeconds: 60, correlate: null, followed: false },
  "check_permission": { wire: "check_permission", python: "session.permissions.check", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "clear_cloud_credentials": { wire: "clear_cloud_credentials", python: "session.auth.sign_out", scope: "session", access: "window", reply: "message", streams: ["push_notification:notifications_changed"], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: { by: "payload.cause", equals: "signed_out" }, followed: true },
  "compact_if_needed": { wire: "compact_if_needed", python: "session.context.compact", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "long", timeoutSeconds: 600, correlate: null, followed: false },
  "complete_files": { wire: "complete_files", python: "session.files.complete", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "count_context_tokens": { wire: "count_context_tokens", python: "session.context.tokens", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "discard_ephemeral_agent": { wire: "discard_ephemeral_agent", python: "session.agents.discard", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "discard_interrupted_run": { wire: "discard_interrupted_run", python: "session.runs.discard_interrupted", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "discard_pending_message": { wire: "discard_pending_message", python: "session.runs.discard_pending", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "discover_server": { wire: "discover_server", python: "igni.auth.discover_server", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "network", timeoutSeconds: 60, correlate: null, followed: false },
  "dismiss_plan": { wire: "dismiss_plan", python: "session.plan.dismiss", scope: "session", access: "client", reply: "rpc_response", streams: ["push_notification:plan_decided"], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: { by: "payload.run_id", source: "args.run_id" }, followed: true },
  "dispatch_visualization_action": { wire: "dispatch_visualization_action", python: "session.visualization_action", scope: "session", access: "client", reply: "rpc_response", streams: ["push_notification:visualization_action_dispatched"], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: { by: "payload.action", source: "args.action" }, followed: true },
  "ensure_mcp": { wire: "ensure_mcp", python: "session.mcp.ensure", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "long", timeoutSeconds: 600, correlate: null, followed: false },
  "execute_scheduled_task": { wire: "execute_scheduled_task", python: "session.scheduler.execute", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: ["push_notification:background_process_done", "push_notification:file_edited", "push_notification:http_retry_attempt", "push_notification:http_retry_succeeded", "push_notification:orchestrate_event", "push_notification:permission_mode_changed", "push_notification:plan_submitted", "push_notification:process_exited", "push_notification:process_line", "push_notification:process_started", "push_notification:todos_updated"], duration: "long", timeoutSeconds: 600, correlate: { by: "run_id", source: "result.run_id" }, followed: true },
  "extract_learnings": { wire: "extract_learnings", python: "session.extract_learnings", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "fire_session_start_hook": { wire: "fire_session_start_hook", python: "session.fire_session_start_hook", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "long", timeoutSeconds: 600, correlate: null, followed: false },
  "get_agent_details": { wire: "get_agent_details", python: "session.agents.list", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_chat_history": { wire: "get_chat_history", python: "session.history.get", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "get_cloud_plan": { wire: "get_cloud_plan", python: "session.auth.plan", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "network", timeoutSeconds: 60, correlate: null, followed: false },
  "get_context_breakdown": { wire: "get_context_breakdown", python: "session.context.breakdown", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "get_display_config": { wire: "get_display_config", python: "session.display_config", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_group_policy": { wire: "get_group_policy", python: "igni.group_policy", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "get_hooks_details": { wire: "get_hooks_details", python: "session.hooks.list", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_interrupted_runs": { wire: "get_interrupted_runs", python: "session.runs.interrupted", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "get_latest_plan": { wire: "get_latest_plan", python: "session.plan.latest", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_marketplaces": { wire: "get_marketplaces", python: "igni.marketplaces.list", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "get_mcp_server_details": { wire: "get_mcp_server_details", python: "session.mcp.server_details", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "network", timeoutSeconds: 60, correlate: null, followed: false },
  "get_mcp_servers": { wire: "get_mcp_servers", python: "session.mcp.servers", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_mcp_status": { wire: "get_mcp_status", python: "session.mcp.status", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_model_registry": { wire: "get_model_registry", python: "session.models.list", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_output_styles": { wire: "get_output_styles", python: "session.output_styles", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_pending_messages": { wire: "get_pending_messages", python: "session.runs.pending_messages", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "get_plugin_contents": { wire: "get_plugin_contents", python: "session.plugins.contents", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "get_plugin_details": { wire: "get_plugin_details", python: "session.plugins.list", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "get_processing": { wire: "get_processing", python: "session.is_processing", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_project_dir": { wire: "get_project_dir", python: "session.get_project_dir", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_run_timeout": { wire: "get_run_timeout", python: "session.run_timeout", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_scheduled_tasks": { wire: "get_scheduled_tasks", python: "session.scheduler.list", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "get_session_id": { wire: "get_session_id", python: "session.current_id", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_skill_definitions": { wire: "get_skill_definitions", python: "session.skills.definitions", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_skill_details": { wire: "get_skill_details", python: "session.skills.list", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_skill_names": { wire: "get_skill_names", python: "session.skills.names", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_slash_commands": { wire: "get_slash_commands", python: "session.slash_commands", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_status": { wire: "get_status", python: "session.status", scope: "session", access: "client", reply: "message", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_todos": { wire: "get_todos", python: "session.todos", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "get_workspace_trust": { wire: "get_workspace_trust", python: "session.workspace.trust", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "install_plugin": { wire: "install_plugin", python: "session.plugins.install", scope: "session", access: "window", reply: "message", streams: [], mayStream: [], duration: "long", timeoutSeconds: 600, correlate: null, followed: false },
  "list_background_processes": { wire: "list_background_processes", python: "igni.processes.list", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "list_dirs": { wire: "list_dirs", python: "igni.files.list_dirs", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "list_extensions": { wire: "list_extensions", python: "igni.extensions.list", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "list_mcp_approvals": { wire: "list_mcp_approvals", python: "session.mcp.list_approvals", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "list_sessions": { wire: "list_sessions", python: "session.list_sessions", scope: "session", access: "client", reply: "message", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "list_workflows": { wire: "list_workflows", python: "session.workflows.list", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "login": { wire: "login", python: "igni.auth.login", scope: "igni", access: "window", reply: "rpc_response", streams: ["push_notification:login_result", "push_notification:login_status", "push_notification:notifications_changed"], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: { by: "payload.flow_id", source: "result.flow_id" }, followed: true },
  "loop_pause": { wire: "loop_pause", python: "session.loop.pause", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "loop_resume": { wire: "loop_resume", python: "session.loop.resume", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "loop_status": { wire: "loop_status", python: "session.loop.status", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "mcp_connect": { wire: "mcp_connect", python: "session.mcp.connect", scope: "session", access: "client", reply: "message", streams: [], mayStream: [], duration: "network", timeoutSeconds: 60, correlate: null, followed: false },
  "mcp_disconnect": { wire: "mcp_disconnect", python: "session.mcp.disconnect", scope: "session", access: "client", reply: "message", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "mint_approver_token": { wire: "mint_approver_token", python: "igni.approvers.mint_token", scope: "igni", access: "window", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "notifications_counts": { wire: "notifications_counts", python: "igni.notifications.counts", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "notifications_list": { wire: "notifications_list", python: "igni.notifications.list", scope: "igni", access: "client", reply: "rpc_response", streams: ["push_notification:notifications_changed"], mayStream: [], duration: "network", timeoutSeconds: 60, correlate: { by: "payload.cause", equals: "listed" }, followed: true },
  "notifications_mark_read": { wire: "notifications_mark_read", python: "igni.notifications.mark_read", scope: "igni", access: "client", reply: "rpc_response", streams: ["push_notification:notifications_changed"], mayStream: [], duration: "network", timeoutSeconds: 60, correlate: { by: "payload.cause", equals: "marked_read" }, followed: true },
  "pick_dir_native": { wire: "pick_dir_native", python: "session.files.pick_dir", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "person", timeoutSeconds: null, correlate: null, followed: false },
  "pop_pending_loop_iteration": { wire: "pop_pending_loop_iteration", python: "session.loop.next_iteration", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "preview_plugin": { wire: "preview_plugin", python: "session.plugins.preview", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "long", timeoutSeconds: 600, correlate: null, followed: false },
  "promote_ephemeral_agent": { wire: "promote_ephemeral_agent", python: "session.agents.promote", scope: "session", access: "window", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "read_file": { wire: "read_file", python: "session.files.read", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "read_process_tail": { wire: "read_process_tail", python: "igni.processes.tail", scope: "igni", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "refresh_marketplaces": { wire: "refresh_marketplaces", python: "igni.marketplaces.refresh", scope: "igni", access: "client", reply: "message", streams: [], mayStream: [], duration: "long", timeoutSeconds: 600, correlate: null, followed: false },
  "reload_cloud_credentials": { wire: "reload_cloud_credentials", python: "session.auth.reload_credentials", scope: "session", access: "window", reply: "message", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "reload_hooks": { wire: "reload_hooks", python: "session.hooks.reload", scope: "session", access: "client", reply: "message", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "remove_marketplace": { wire: "remove_marketplace", python: "igni.marketplaces.remove", scope: "igni", access: "window", reply: "message", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "remove_plugin": { wire: "remove_plugin", python: "session.plugins.remove", scope: "session", access: "window", reply: "message", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "report_visualization_verdict": { wire: "report_visualization_verdict", python: "session.visualization_verdict", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "revoke_approver_tokens": { wire: "revoke_approver_tokens", python: "igni.approvers.revoke_tokens", scope: "igni", access: "window", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "run_shell": { wire: "run_shell", python: "session.run_shell", scope: "session", access: "window", reply: "rpc_response", streams: ["push_notification:background_process_done", "push_notification:process_exited", "push_notification:process_line", "push_notification:process_started"], mayStream: [], duration: "long", timeoutSeconds: 600, correlate: { by: "payload.pid", source: "result.pid" }, followed: true },
  "run_workflow": { wire: "run_workflow", python: "session.workflows.run", scope: "session", access: "client", reply: "rpc_response", streams: ["push_notification:workflow_event"], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: { by: "payload.workflow_run_id", source: "result.workflow_run_id" }, followed: true },
  "save_permission_rule": { wire: "save_permission_rule", python: "session.permissions.save_rule", scope: "session", access: "window", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "search_chat": { wire: "search_chat", python: "session.history.search", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "search_code": { wire: "search_code", python: "session.files.search", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "set_extension_settings": { wire: "set_extension_settings", python: "igni.extensions.set_settings", scope: "igni", access: "window", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "set_mcp_approval": { wire: "set_mcp_approval", python: "session.mcp.set_approval", scope: "session", access: "window", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "set_mcp_tool_enabled": { wire: "set_mcp_tool_enabled", python: "session.mcp.set_tool_enabled", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "set_plugin_enabled": { wire: "set_plugin_enabled", python: "session.plugins.set_enabled", scope: "session", access: "window", reply: "message", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "set_server": { wire: "set_server", python: "igni.auth.set_server", scope: "igni", access: "window", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "set_workspace_trust": { wire: "set_workspace_trust", python: "session.workspace.set_trust", scope: "session", access: "window", reply: "rpc_response", streams: ["push_notification:workspace_trust_required"], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: { by: "payload.path", source: "result.path" }, followed: true },
  "shutdown": { wire: "shutdown", python: "session.shutdown", scope: "session", access: "window", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "start_scheduler": { wire: "start_scheduler", python: "session.scheduler.start", scope: "session", access: "client", reply: "rpc_response", streams: ["push_notification:scheduler_completed", "push_notification:scheduler_started"], mayStream: ["push_notification:background_process_done", "push_notification:file_edited", "push_notification:http_retry_attempt", "push_notification:http_retry_succeeded", "push_notification:orchestrate_event", "push_notification:permission_mode_changed", "push_notification:plan_submitted", "push_notification:process_exited", "push_notification:process_line", "push_notification:process_started", "push_notification:todos_updated"], duration: "io", timeoutSeconds: 30, correlate: { by: "channel" }, followed: true },
  "stop_background_process": { wire: "stop_background_process", python: "igni.processes.stop", scope: "igni", access: "client", reply: "rpc_response", streams: ["push_notification:background_process_done", "push_notification:process_exited", "push_notification:process_line"], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: { by: "payload.pid", source: "args.pid" }, followed: true },
  "switch_model": { wire: "switch_model", python: "session.models.switch", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "switch_session": { wire: "switch_session", python: "session.switch", scope: "session", access: "client", reply: "message", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "toggle_verbose": { wire: "toggle_verbose", python: "session.toggle_verbose", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: null, followed: false },
  "truncate_history": { wire: "truncate_history", python: "session.history.truncate", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "update_plugin": { wire: "update_plugin", python: "session.plugins.update", scope: "session", access: "window", reply: "message", streams: [], mayStream: [], duration: "long", timeoutSeconds: 600, correlate: null, followed: false },
  "upload_attachment": { wire: "upload_attachment", python: "session.upload_attachment", scope: "session", access: "client", reply: "rpc_response", streams: [], mayStream: [], duration: "io", timeoutSeconds: 30, correlate: null, followed: false },
  "window_model": { wire: "window_model", python: "igni.window.model", scope: "igni", access: "window", reply: "rpc_response", streams: ["push_notification:window_model_changed"], mayStream: [], duration: "instant", timeoutSeconds: 10, correlate: { by: "payload.token", source: "args.token" }, followed: true },
};

/** igni's methods a client never sends: an extension page's and the platform's. */
export const NOT_FOR_CLIENTS: ReadonlySet<string> = new Set([
  "deliver_service_events",
  "extension_service_token",
  "host_model",
  "vm_sign_in",
]);

/** Sub-agents' runs, wherever they are going. */
export class IgniAgents {
  constructor(readonly caller: Caller) {}

  /**
   * Stop one sub-agent's run, leaving the rest of the turn going.
   *
   * `run_id` is the sub-agent run's id, as its events carry it.
   * Returns `ok: true` when the run was cancelled, or `ok: false`
   * with `error` when `run_id` is empty, no such run is running, or
   * the cancellation failed.
   */
  cancel_run(run_id?: string): Promise<CancelAgentRunResult> {
    return this.caller.rpc<CancelAgentRunResult>("cancel_agent_run", { run_id: run_id });
  }
}

/** Approver tokens: what lets a program answer approval requests. */
export class IgniApprovers {
  constructor(readonly caller: Caller) {}

  /**
   * Make a token that lets a program answer the agent's approval requests.
   *
   * Takes no arguments. Returns `token`: a program that connects with it
   * stands as an approver — it may answer approval requests and approve a
   * plan, once each time, but saves no rule and changes no permission mode.
   * The token lives in memory until igni exits or the tokens are revoked,
   * and is sent only to the connection that asked.
   *
   * Fails when this igni's transport takes no token at all, so every
   * connection may already answer approval requests.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  mint_token(): Promise<ApproverTokenMinted> {
    return this.caller.rpc<ApproverTokenMinted>("mint_approver_token", {});
  }

  /**
   * Forget every approver token, so no program answers approval requests any more.
   *
   * Takes no arguments. Returns `revoked`: how many tokens were
   * forgotten (`0` when there were none, or when this igni takes no
   * token). Connections that attached with a revoked token lose their
   * approver standing.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  revoke_tokens(): Promise<ApproverTokensRevoked> {
    return this.caller.rpc<ApproverTokensRevoked>("revoke_approver_tokens", {});
  }
}

/** Signing igni in to igni server, and choosing which server. */
export class IgniAuth {
  constructor(readonly caller: Caller) {}

  /**
   * Cancel the sign-in to igni server that ``igni.auth.login()`` started.
   *
   * igni answers nothing; the sign-in's ``login_result`` push says it ended.
   *
   * Sent as igni's `cancel_login` message.
   */
  cancel_login(): Promise<void> {
    return this.caller.sendMessage("cancel_login", {});
  }

  /**
   * Find the igni server an email address's organisation runs.
   *
   * `email` is the person's work address. igni reads the record the
   * organisation publishes on the address's domain (a well-known URL,
   * then DNS) and changes nothing. Returns `api_url` and `portal_url`,
   * with `source` saying where they were found; when nothing usable
   * was found both are empty and `reason` says why.
   */
  discover_server(email: string): Promise<ServerFound> {
    return this.caller.rpc<ServerFound>("discover_server", { email: email });
  }

  /**
   * Start signing in to igni server through the person's browser.
   *
   * Takes no arguments, and answers at once with `started: true`; a
   * sign-in already in progress is cancelled first. The sign-in itself
   * goes on in the background: `login_status` pushes say what it is
   * doing (the local callback server starting, the URL to open, the
   * account being read), and one `login_result` push ends it, with
   * `success` and, in `result`, the signed-in email or the reason it
   * failed. On success the person's notifications are read and
   * `notifications_changed` follows.
   *
   * ``async with`` the call to follow it: it yields the ``login_status`` pushes and ends with the ``login_result`` one. igni signs in one way at a time — a new ``login`` cancels the one going — so these are the sign-in igni is doing.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  login(): Call<LoginStarted, LoginEvent> {
    return this.caller.follow<LoginStarted, LoginEvent>("login", {});
  }

  /**
   * Choose the igni server to sign in to, and remember it for the next launch.
   *
   * `api_url` is the server's API address: `https`, or `http` to
   * `localhost`, `127.0.0.1` or `::1` for a local deployment;
   * `portal_url` its portal, empty to derive it from `api_url`, and
   * held to the same rule when given. Returns the server as stored, or,
   * when the choice is refused (an empty `api_url`, or an address that
   * breaks that rule), `error` saying why and nothing stored. Fails when the user configuration file cannot be read or
   * written.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  set_server(api_url: string, portal_url?: string): Promise<ServerChoice> {
    return this.caller.rpc<ServerChoice>("set_server", { api_url: api_url, portal_url: portal_url });
  }
}

/** The extensions installed into this igni, and their settings. */
export class IgniExtensions {
  constructor(readonly caller: Caller) {}

  /**
   * List the installed extensions, including the ones that failed to start.
   *
   * Takes no arguments. Returns each extension's id, name, version and
   * `state` — a failed one with its `reason`, rather than left out —
   * with what it adds to igni's window (pages, menu items, indicators),
   * its settings and their values, and the addresses of its UI, its web
   * home and its service.
   */
  list(): Promise<ExtensionListResult> {
    return this.caller.rpc<ExtensionListResult>("list_extensions", {});
  }

  /**
   * Change an installed extension's settings.
   *
   * `extension_id` is the extension; `values` the settings to
   * change, by key, merged over what is stored. The extension reads them
   * the next time it starts. Returns the whole list, as
   * `list_extensions` does. Fails when the extension is not
   * installed, a key is not one of its settings, a value is not one of
   * a setting's options, or igni has no extension support.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  set_settings(extension_id: string, values: Record<string, JsonValue>): Promise<ExtensionListResult> {
    return this.caller.rpc<ExtensionListResult>("set_extension_settings", { extension_id: extension_id, values: values });
  }
}

/** Folders on the machine igni runs on. */
export class IgniFiles {
  constructor(readonly caller: Caller) {}

  /**
   * List the folders inside a folder on igni's machine, for picking a project.
   *
   * `path` is the folder to list (the home folder when absent or
   * empty); `show_hidden` includes folders whose names start with a
   * dot. Returns the resolved `path`, its `parent` (empty at the
   * root), the folder names in it (`dirs`, sorted), the home folder,
   * and `error` when it could not be read.
   */
  list_dirs(path?: string | null, show_hidden?: boolean): Promise<DirListResult> {
    return this.caller.rpc<DirListResult>("list_dirs", { path: path, show_hidden: show_hidden });
  }
}

/** Plugin marketplaces: where plugins are installed from. */
export class IgniMarketplaces {
  constructor(readonly caller: Caller) {}

  /**
   * Add a plugin marketplace and read its catalogue.
   *
   * `url` is the marketplace's git URL. Returns an `info` message,
   * sent in place of an `rpc_response`, whose text says how many
   * plugins it catalogues — or why it was not added: the
   * organisation's policy, a git error, an unreadable catalogue.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  add(url: string): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("add_marketplace", { url: url });
  }

  /**
   * List the plugin marketplaces igni knows, with their catalogues.
   *
   * Takes no arguments. Returns each marketplace's name, URL, when it
   * was last fetched, and the plugins it offers.
   */
  list(): Promise<MarketplaceInfo[]> {
    return this.caller.rpc<MarketplaceInfo[]>("get_marketplaces", {});
  }

  /**
   * Fetch marketplaces' catalogues again.
   *
   * `name` is one marketplace; absent or empty refreshes every one.
   * Returns an `info` message, sent in place of an `rpc_response`,
   * whose text says what was refreshed, or why not.
   */
  refresh(name?: string | null): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("refresh_marketplaces", { name: name });
  }

  /**
   * Forget a plugin marketplace.
   *
   * `name` is the marketplace. Returns an `info` message, sent in
   * place of an `rpc_response`, whose text says it was removed, or
   * that there is no such marketplace.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  remove(name: string): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("remove_marketplace", { name: name });
  }
}

/** The signed-in person's notifications, and what extensions posted. */
export class IgniNotifications {
  constructor(readonly caller: Caller) {}

  /**
   * Count the person's unread notifications, in all and per extension.
   *
   * Takes no arguments. Answers from what was last read, asking nobody;
   * `notifications_changed` pushes the counts whenever they move.
   */
  counts(): Promise<NotificationCounts> {
    return this.caller.rpc<NotificationCounts>("notifications_counts", {});
  }

  /**
   * List the signed-in person's notifications, newest first.
   *
   * Takes no arguments. Reads igni server again and merges in what
   * extensions on this machine posted. Returns at most 100
   * `notifications` (each with its source, title, body, target and
   * whether it is read), the unread `counts` in all and per
   * extension, and `server_error` when igni server could not be
   * read. The fresh counts are also pushed as `notifications_changed`.
   *
   * ``async with`` the call to follow it: it yields the ``notifications_changed`` push that says the list was read, and ends with the answer.
   */
  list(): Call<NotificationsListResult, NotificationsListEvent> {
    return this.caller.follow<NotificationsListResult, NotificationsListEvent>("notifications_list", {});
  }

  /**
   * Mark notifications read.
   *
   * `ids` names the notifications; `source` (an extension id) marks
   * all of that extension's; neither marks every notification. Returns
   * the unread `counts` afterwards, also pushed as
   * `notifications_changed`, and `server_error` when igni server
   * could not be told.
   *
   * ``async with`` the call to follow it: it yields the ``notifications_changed`` push that says the notifications were marked read, and ends with the answer.
   */
  mark_read(ids?: string[] | null, source?: string | null): Call<NotificationsReadResult, NotificationsMarkReadEvent> {
    return this.caller.follow<NotificationsReadResult, NotificationsMarkReadEvent>("notifications_mark_read", { ids: ids, source: source });
  }
}

/** Background processes igni tracks, in every session. */
export class IgniProcesses {
  constructor(readonly caller: Caller) {}

  /**
   * List the background processes igni is tracking, in every session.
   *
   * Takes no arguments. Returns each process's `pid`, command, how
   * long it has run, whether it is still running, and its exit code
   * once it has ended.
   */
  list(): Promise<ProcessRow[]> {
    return this.caller.rpc<ProcessRow[]>("list_background_processes", {});
  }

  /**
   * Stop a background process.
   *
   * `pid` is the process. Returns `killed: true` once it was told to
   * stop — its last lines, `process_exited` and
   * `background_process_done` follow — or `killed: false` with a
   * `message` when igni is not tracking it or it had already ended.
   *
   * ``async with`` the call to follow it: it yields the ``process_line``, ``process_exited`` and ``background_process_done`` pushes of ``pid`` and ends with ``background_process_done``, or with the answer when ``killed`` is false.
   */
  stop(pid: number): Call<StopProcessResult, StopBackgroundProcessEvent> {
    return this.caller.follow<StopProcessResult, StopBackgroundProcessEvent>("stop_background_process", { pid: pid });
  }

  /**
   * Read the last lines a background process printed.
   *
   * `pid` is the process; `tail` how many lines (default 200).
   * Returns its `output`, whether it `is_running`, and its
   * `exit_code` once it has ended. An unknown `pid` answers empty
   * output, not running.
   */
  tail(pid: number, tail?: number): Promise<ProcessTailResult> {
    return this.caller.rpc<ProcessTailResult>("read_process_tail", { pid: pid, tail: tail });
  }
}

/** igni's sessions: attach one, or make a new one in a project folder. */
export class IgniSessions {
  constructor(readonly caller: Caller) {}

  /**
   * Bind to a session — an existing one, or a new one in a project folder.
   *
   * `session_id` names the session to resume; `project_dir` the folder
   * it works in. Neither: the default session. Only `project_dir`: a new
   * session locked to that folder. Both: that session, which must belong
   * to that folder. The session is made live if it is not. An id igni has
   * no session by is not an error: a new, empty session starts under that
   * id, so check `session_id` against the session list first when it
   * must already exist.
   *
   * Returns the `session_id` and `project_dir` actually bound; send
   * later requests for that session with this `session_id` on the
   * envelope. Right after the answer, every approval the session is
   * waiting on is shown again (a `run_paused` carrying its
   * `hitl_request` items), since a client that reloaded lost its
   * dialog; a run igni was continuing when it stopped is reported with
   * an `info`, and a sub-agent's interrupted run is continued, which
   * streams as any run does. Each of those messages carries this
   * request's `id`, and a `stream_end` of that `id` ends them.
   *
   * Fails when `project_dir` is not a directory, or the session belongs
   * to another project folder — an attach never moves a session.
   *
   * ``async with`` the call to follow it: it yields the approvals the session is still waiting for and the run it continues again — every message of them carries the attach's own request id — and ends with the ``stream_end`` that closes them.
   */
  attach(project_dir?: string, session_id?: string): Call<AttachSessionResult, AttachSessionEvent> {
    return this.caller.follow<AttachSessionResult, AttachSessionEvent>("attach_session", { project_dir: project_dir, session_id: session_id });
  }
}

/** igni's own window's model — its fields, toasts and dialog. */
export class IgniWindow {
  constructor(readonly caller: Caller) {}

  /**
   * Read or change the calling window's own model: its fields, toasts and dialog.
   *
   * A window spans sessions, so this is not tied to one. `op` says what
   * to do (see the arguments); `window` is the window's own stable id.
   * The window is the one on the connection the request came on.
   *
   * Returns, by `op`: `hydrate` the whole model (`state`), its
   * revision (`rev`) and the fields nobody set (`unset`); `write`,
   * `dismiss_toast` the new `rev`; `toast` the toast as shown, with
   * its id; `open_dialog` the dialog as shown; `answer_dialog`
   * whether that dialog was still the open one (`answered`). Every
   * change is pushed to every window as `window_model_changed`.
   *
   * Fails when the model refuses the write (an unknown field, a field
   * that is not writable, a value that does not fit its type), or when
   * the window's saved state could not be read or written.
   *
   * ``async with`` the call to follow it: it yields the ``window_model_changed`` push that carries this change, and ends with the answer. The change's token is the one given; igni-client makes one when the caller does not, so the push can be told from another window's.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  model(op: "hydrate" | "write" | "toast" | "dismiss_toast" | "open_dialog" | "answer_dialog", window: string, connection_id?: string, dialog_id?: string, field?: string, kind?: string, token?: string, value?: JsonValue): Call<WindowModelResult, WindowModelEvent> {
    return this.caller.follow<WindowModelResult, WindowModelEvent>("window_model", { connection_id: connection_id, dialog_id: dialog_id, field: field, kind: kind, op: op, token: token ?? this.caller.newId("change"), value: value, window: window });
  }
}

/** The agents this session can hand work to. */
export class SessionAgents {
  constructor(readonly caller: Caller) {}

  /**
   * Delete an agent made during this session.
   *
   * `name` is the ephemeral agent. Returns `ok` with its `name`;
   * or `ok: false` with `reason` when it is unknown or not
   * ephemeral.
   */
  discard(name: string): Promise<DiscardEphemeralResult> {
    return this.caller.rpc<DiscardEphemeralResult>("discard_ephemeral_agent", { name: name });
  }

  /**
   * List the agents this session can hand work to.
   *
   * Takes no arguments. Returns each agent's name, description, tools,
   * model, MCP servers, tags, system prompt, where it was defined, and
   * whether it is ephemeral (made during this session, not yet saved).
   */
  list(): Promise<AgentInfo[]> {
    return this.caller.rpc<AgentInfo[]>("get_agent_details", {});
  }

  /**
   * Keep an agent made during this session, as a project or personal agent.
   *
   * `name` is the ephemeral agent; `target` is `project` (the
   * default: the project's agents) or `personal` (the person's own).
   * Returns `ok` with the agent's `name` and where it was saved
   * (`dest`); or `ok: false` with `reason` when the agent is
   * unknown, not ephemeral, or the destination exists.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  promote(name: string, target?: string | null): Promise<PromoteEphemeralResult> {
    return this.caller.rpc<PromoteEphemeralResult>("promote_ephemeral_agent", { name: name, target: target });
  }
}

/** This session's sign-in to igni server. */
export class SessionAuth {
  constructor(readonly caller: Caller) {}

  /**
   * Read who is signed in to igni server, and their organisation's plan.
   *
   * Takes no arguments. Asks igni server with this session's sign-in and
   * returns the person's `email` and `full_name`, the organisation's
   * display name (`org_name`) and plan `tier`; any of them may be
   * null when igni server does not say. Returns `null` when nobody is
   * signed in or igni server could not be asked.
   */
  plan(): Promise<CloudPlan | null> {
    return this.caller.rpc<CloudPlan | null>("get_cloud_plan", {});
  }

  /**
   * Read the saved sign-in again, so this session acts as whoever is signed in now.
   *
   * Takes no arguments. Use it after a sign-in made elsewhere (another
   * session, another window). Returns the session's status afterwards —
   * model, cloud connection, account, context size, permission mode — as
   * a `status_update` message, sent in place of an `rpc_response`.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  reload_credentials(): Promise<StatusUpdate> {
    return this.caller.rpc<StatusUpdate>("reload_cloud_credentials", {});
  }

  /**
   * Sign this session out of igni server.
   *
   * Takes no arguments. The session forgets its cloud credentials, and
   * the signed-in person's notifications stop arriving and leave the
   * badges (`notifications_changed`). Returns the session's status
   * afterwards as a `status_update` message, sent in place of an
   * `rpc_response`.
   *
   * ``async with`` the call to follow it: it yields the ``notifications_changed`` push that says the person signed out, and ends with the answer — the session's status.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  sign_out(): Call<StatusUpdate, ClearCloudCredentialsEvent> {
    return this.caller.follow<StatusUpdate, ClearCloudCredentialsEvent>("clear_cloud_credentials", {});
  }
}

/** This session's context window: how full it is, and compacting it. */
export class SessionContext {
  constructor(readonly caller: Caller) {}

  /**
   * Split this session's context into what compaction can shrink and what it cannot.
   *
   * Takes no arguments. Returns the `total` tokens, the part taken by
   * the conversation's runs (`runs`, which `/compact` can shrink),
   * and the `floor` — instructions, tools and the rest that stays.
   * Zeros when it cannot be measured.
   */
  breakdown(): Promise<ContextBreakdown> {
    return this.caller.rpc<ContextBreakdown>("get_context_breakdown", {});
  }

  /**
   * Compact this session's conversation when its context is nearly full.
   *
   * `ctx_tokens` is the context the last turn used and `max_ctx`
   * the model's window; at 80% or more the conversation is summarised
   * and replaced by the summary (the `PreCompact` hooks may refuse).
   * Returns `compacted` and, when it was, the `summary`.
   */
  compact(ctx_tokens: number, max_ctx: number): Promise<CompactionOutcome> {
    return this.caller.rpc<CompactionOutcome>("compact_if_needed", { ctx_tokens: ctx_tokens, max_ctx: max_ctx });
  }

  /**
   * Estimate how many tokens this session's conversation takes up.
   *
   * Takes no arguments. Returns the estimate (`0` when it cannot be
   * read); a positive estimate also becomes the context size
   * `get_status` reports.
   */
  tokens(): Promise<number> {
    return this.caller.rpc<number>("count_context_tokens", {});
  }
}

/** Files in this session's project folder. */
export class SessionFiles {
  constructor(readonly caller: Caller) {}

  /**
   * Complete a file path typed after `@`, from this session's project.
   *
   * `query` is what was typed so far (empty matches everything);
   * `limit` caps the matches returned (default 50). Returns the
   * matching project-relative paths, best first, and `total`: how
   * many matched before the cap. The project's file list is read once
   * per session.
   */
  complete(limit?: number, query?: string): Promise<FileCompletion> {
    return this.caller.rpc<FileCompletion>("complete_files", { limit: limit, query: query });
  }

  /**
   * Open the operating system's folder picker on igni's machine and return the choice.
   *
   * `start` is the folder the picker opens in (this session's project
   * when absent or empty). igni runs on the person's machine, so the
   * dialog appears on their desktop; it waits as long as they take, so
   * give the call a long timeout. Returns the chosen `path`, or
   * `cancelled`, or `error` when no native dialog is available.
   */
  pick_dir(start?: string | null): Promise<PickDirResult> {
    return this.caller.rpc<PickDirResult>("pick_dir_native", { start: start });
  }

  /**
   * Read a file for preview: one of this session's project, igni's data, or an attachment.
   *
   * `path` is relative to the project, absolute, or an
   * `attachment:<id>` reference. Returns the resolved `path`, its
   * `contents` and `size`, and a `language` hint for highlighting;
   * or `error` when the file is missing, a directory, too large to
   * preview (256 KiB), unreadable, or outside the folders igni lets a
   * client read.
   */
  read(path: string): Promise<ReadFileResult> {
    return this.caller.rpc<ReadFileResult>("read_file", { path: path });
  }

  /**
   * Find where a snippet of code appears in this session's project.
   *
   * `query` is the snippet, matched exactly; one shorter than five
   * characters finds nothing. Returns up to 20 `matches` (path, first
   * and last line, a preview), `truncated` when there may be more or
   * the search timed out, and `error` when it failed.
   */
  search(query: string): Promise<SearchCodeResult> {
    return this.caller.rpc<SearchCodeResult>("search_code", { query: query });
  }
}

/** This session's conversation as stored: read, search, cut back. */
export class SessionHistory {
  constructor(readonly caller: Caller) {}

  /**
   * Read a session's conversation, turn by turn, as a client draws it.
   *
   * `session_id` names the session. Returns the conversation in
   * order, one entry per item, told apart by `role`: the person's
   * message (`user`), the agent's answer (`assistant`), its
   * reasoning (`thinking`), a tool call and its result (`tool`), a
   * submitted plan (`plan`), a run's token counts (`stats`), and a
   * view the agent drew (`visualization`). Sub-agents' runs are left
   * out.
   */
  get(): Promise<ChatTurn[]> {
    return this.caller.rpc<ChatTurn[]>("get_chat_history", { session_id: this.caller.sessionId });
  }

  /**
   * Find text in a session's conversation.
   *
   * `session_id` names the session; `query` is the text to find
   * (case-insensitive; blank finds nothing); `limit` caps the hits
   * (default 50). Returns one hit per match, in conversation order:
   * its index in `get_chat_history`, its role and run, a snippet
   * around it, and where the match sits in the snippet.
   */
  search(query: string, limit?: number): Promise<ChatSearchHit[]> {
    return this.caller.rpc<ChatSearchHit[]>("search_chat", { limit: limit, query: query, session_id: this.caller.sessionId });
  }

  /**
   * Drop a run from a session's history, with every run after it.
   *
   * `session_id` names the session; `run_id` the first run to drop
   * (a top-level run, as `get_chat_history` carries it). Use it to
   * edit and resend a message. Returns how many runs were `removed`,
   * or `error` when the session or the run is not found or the
   * history could not be saved.
   */
  truncate(run_id: string): Promise<TruncateHistoryResult> {
    return this.caller.rpc<TruncateHistoryResult>("truncate_history", { run_id: run_id, session_id: this.caller.sessionId });
  }
}

/** The hooks that run on this session's events. */
export class SessionHooks {
  constructor(readonly caller: Caller) {}

  /**
   * List the hooks this session runs.
   *
   * Takes no arguments. Returns one row per hook: the `event` it runs
   * on, its `type` (`command`, `http`, `prompt` or `mcp_tool`)
   * and the `command` or `url` it runs, the `matcher` that narrows
   * it, its timeout, whether it runs in the background, and the HTTP
   * headers it sends.
   */
  list(): Promise<HookEntryView[]> {
    return this.caller.rpc<HookEntryView[]>("get_hooks_details", {});
  }

  /**
   * Read this session's hook configuration again.
   *
   * Takes no arguments. Returns an `info` message, sent in place of an
   * `rpc_response`, saying how many hooks are now active.
   */
  reload(): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("reload_hooks", {});
  }
}

/** This session's loop: a task the agent repeats until it is done. */
export class SessionLoop {
  constructor(readonly caller: Caller) {}

  /**
   * End this session's running `/loop`.
   *
   * Takes no arguments. Returns `true` when a loop was ended;
   * `false` when there was none or it is paused (a paused loop is
   * resumed or left alone, not cancelled).
   */
  cancel(): Promise<boolean> {
    return this.caller.rpc<boolean>("cancel_pending_loop", {});
  }

  /**
   * Take the next step of this session's `/loop`, for the client to send.
   *
   * Takes no arguments. Returns `null` when there is no loop or it is
   * paused. Otherwise `kind` says what happened: `step` carries the
   * `prompt` to send as the next message (and `display_prompt` to
   * show), the iteration number and how many remain; `completed`
   * says the loop reached its cap and ended; `safety_paused` says it
   * reached the hard cap and paused.
   */
  next_iteration(): Promise<LoopAdvance | null> {
    return this.caller.rpc<LoopAdvance | null>("pop_pending_loop_iteration", {});
  }

  /**
   * Pause this session's `/loop` after the current iteration.
   *
   * Takes no arguments. Returns `true` when the loop is now paused
   * (or already was), `false` when there is no loop.
   */
  pause(): Promise<boolean> {
    return this.caller.rpc<boolean>("loop_pause", {});
  }

  /**
   * Resume this session's paused `/loop`.
   *
   * Takes no arguments. Returns the prompt of the iteration to run next,
   * for the client to send as a message — nothing runs on its own — or
   * `""` when there is no paused loop.
   */
  resume(): Promise<string> {
    return this.caller.rpc<string>("loop_resume", {});
  }

  /**
   * Read the state of this session's `/loop`.
   *
   * Takes no arguments. Returns whether a loop is `active` and
   * `paused`, its prompt, which iteration it is on and how many
   * remain, whether its cap was set explicitly, and the total the agent
   * announced, if any.
   */
  status(): Promise<LoopStatusSnapshot> {
    return this.caller.rpc<LoopStatusSnapshot>("loop_status", {});
  }
}

/** MCP servers this session connects to, and their tools. */
export class SessionMcp {
  constructor(readonly caller: Caller) {}

  /**
   * Connect one configured MCP server to this session.
   *
   * `server_name` is the server's name in the MCP configuration.
   * Returns an `info` message, sent in place of an `rpc_response`,
   * once it is connected. Fails with the reason when it did not connect
   * (not configured, refused by policy, no tools, approval denied); the
   * reason is also `get_mcp_server_details`'s `error` for it.
   */
  connect(server_name: string): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("mcp_connect", { server_name: server_name });
  }

  /**
   * Disconnect one MCP server from this session.
   *
   * `server_name` is the server's name in the MCP configuration.
   * Returns an `info` message, sent in place of an `rpc_response`,
   * whether or not the server was connected.
   */
  disconnect(server_name: string): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("mcp_disconnect", { server_name: server_name });
  }

  /**
   * Connect this session's configured MCP servers, once.
   *
   * Takes no arguments. The first call connects every configured server
   * and rebuilds the agent with their tools; later calls do nothing.
   * Returns the servers `connected`, the ones that `failed` with
   * their errors, whether the agent was `rebuilt`, and, when nothing
   * was done, `skipped_reason` (`already_initialized`,
   * `no_configured_servers`, `no_clients_connected`).
   */
  ensure(): Promise<McpInitResult> {
    return this.caller.rpc<McpInitResult>("ensure_mcp", {});
  }

  /**
   * List this session's MCP servers that need a first-use approval.
   *
   * Takes no arguments. Returns one row per configured server — its
   * `name`, where it is configured (`source`, `source_path`) and
   * whether it is `approved`. A server from a project's or a plugin's
   * `.mcp.json` runs a command or opens a connection as the person, so
   * it never connects until approved; without a terminal to ask on,
   * igni's window asks instead and answers with `set_mcp_approval`. An
   * extension's own service is approved by its install and not listed.
   */
  list_approvals(): Promise<McpApproval[]> {
    return this.caller.rpc<McpApproval[]>("list_mcp_approvals", {});
  }

  /**
   * Describe each of this session's MCP servers in full.
   *
   * Takes no arguments. Returns one row per server: whether it is
   * connected, its transport, its tools (names, descriptions, the ones
   * switched off), its resources and prompts, the last error connecting
   * it, and whether policy blocks it. Each server is asked in turn, so
   * a slow one slows the answer.
   */
  server_details(): Promise<McpServerSnapshot[]> {
    return this.caller.rpc<McpServerSnapshot[]>("get_mcp_server_details", {});
  }

  /**
   * List this session's configured MCP servers, in configuration order.
   *
   * Takes no arguments. Returns one `{name, connected}` row per
   * server.
   */
  servers(): Promise<McpServerSummary[]> {
    return this.caller.rpc<McpServerSummary[]>("get_mcp_servers", {});
  }

  /**
   * Approve a configured MCP server, or withdraw its approval.
   *
   * `server_name` names the server; `approved` is the answer.
   * Approving records it for that server from that configuration file
   * (in `~/.igni/mcp-approved.json`, which every session reads again
   * when it changes); the server connects on the next `mcp_connect` or
   * start. Withdrawing disconnects it if it is connected. Returns the
   * server's row as `list_mcp_approvals` would. Fails for a server not
   * configured, an extension's, or the user's own `~/.igni/.mcp.json`,
   * which is always trusted. Only igni's window may call it.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  set_approval(approved: boolean, server_name: string): Promise<McpApproval> {
    return this.caller.rpc<McpApproval>("set_mcp_approval", { approved: approved, server_name: server_name });
  }

  /**
   * Switch one MCP server's tool on or off for this project.
   *
   * `server` and `tool` name the tool; `enabled` is its new state.
   * The choice is saved in the project's `.igni/mcp-tool-state.json`.
   * Returns the `server`, `tool` and `enabled` as recorded; the
   * server and tool are not checked to exist. Fails when the state file
   * cannot be written.
   */
  set_tool_enabled(enabled: boolean, server: string, tool: string): Promise<McpToolToggleResult> {
    return this.caller.rpc<McpToolToggleResult>("set_mcp_tool_enabled", { enabled: enabled, server: server, tool: tool });
  }

  /**
   * List this session's MCP servers and whether each is connected.
   *
   * Takes no arguments. Returns one `{name, connected}` row per
   * server, in no particular order.
   */
  status(): Promise<McpServerStatus[]> {
    return this.caller.rpc<McpServerStatus[]>("get_mcp_status", {});
  }
}

/** The models this session can use, and switching between them. */
export class SessionModels {
  constructor(readonly caller: Caller) {}

  /**
   * List the models this session can run on.
   *
   * Takes no arguments. Returns the `default` model's name, the
   * largest context window configured, and `registry`: every model by
   * name, with its provider and settings.
   */
  list(): Promise<ModelRegistryResult> {
    return this.caller.rpc<ModelRegistryResult>("get_model_registry", {});
  }

  /**
   * Make another model the one this session's agent runs on.
   *
   * `model_name` is a name from the model registry
   * (`get_model_registry`). The choice is also saved as the default
   * for new sessions. Returns `text`, saying the model switched, with a
   * note for any part of the choice that could not be saved. Fails when
   * the model is not in the registry.
   */
  switch(model_name: string): Promise<ModelSwitched> {
    return this.caller.rpc<ModelSwitched>("switch_model", { model_name: model_name });
  }
}

/** Saved permission rules for tool calls. */
export class SessionPermissions {
  constructor(readonly caller: Caller) {}

  /**
   * Look up the saved permission level for one tool call.
   *
   * `tool_name` and `func_name` name the tool and its function;
   * `tool_args` are the call's arguments, which argument rules match
   * against. The rules are read from this session's project and the
   * person's settings files. Returns `allow`, `ask` or `deny`:
   * the last matching argument rule, else the tool's own level, else
   * `ask`. The session's permission mode is not applied.
   */
  check(func_name: string, tool_args: ToolCallArgs, tool_name: string): Promise<"allow" | "ask" | "deny"> {
    return this.caller.rpc<"allow" | "ask" | "deny">("check_permission", { func_name: func_name, tool_args: tool_args, tool_name: tool_name });
  }

  /**
   * Save a permission rule for this session's project.
   *
   * `rule` is a permission rule (`Bash(git status)`, a tool name);
   * `level` is `allow`, `ask` or `deny`. The rule is written to
   * the project's `.igni/settings.local.json` (the person's own when
   * there is no project), and the session follows it from its next tool
   * call. Returns nothing. Fails when the settings file cannot be
   * written.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  save_rule(level: "allow" | "ask" | "deny", rule: string): Promise<null> {
    return this.caller.rpc<null>("save_permission_rule", { level: level, rule: rule });
  }
}

/** Plan mode: the plan the agent submitted, and the person's decision. */
export class SessionPlan {
  constructor(readonly caller: Caller) {}

  /**
   * Approve the plan the agent submitted, so it leaves plan mode and carries it out.
   *
   * `run_id` is the run that submitted the plan (`plan_submitted`
   * carries it). The decision is recorded, the session's permission
   * mode returns to the one it started in (`permission_mode_changed`
   * when it changes), and `plan_decided` tells every window. Returns
   * the `run_id`, the `decision`, `mode_status` describing the
   * mode change, and `ok`; `ok: false` with `error` when
   * `run_id` is empty or the decision could not be recorded.
   *
   * ``async with`` the call to follow it: it yields the ``plan_decided`` push whose ``run_id`` is this call's, and ends with it, or with the answer when ``ok`` is false. A change of permission mode is in the answer's ``mode_status``.
   *
   * Access: ``approver``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop, a program needs an approver token the window minted (``Local(approver_token=...)``); with the lockfile's token it gets ``AccessRefused``.
   */
  approve(run_id?: string): Call<PlanDecisionResult, ApprovePlanEvent> {
    return this.caller.follow<PlanDecisionResult, ApprovePlanEvent>("approve_plan", { run_id: run_id });
  }

  /**
   * Send the submitted plan back for refining, staying in plan mode.
   *
   * `run_id` is the run that submitted the plan. The decision is
   * recorded and `plan_decided` tells every window. Returns the same
   * shape as `approve_plan`, with an empty `mode_status`; `ok:
   * false` with `error` when `run_id` is empty.
   *
   * ``async with`` the call to follow it: it yields the ``plan_decided`` push whose ``run_id`` is this call's, and ends with it, or with the answer when ``ok`` is false.
   */
  dismiss(run_id?: string): Call<PlanDecisionResult, DismissPlanEvent> {
    return this.caller.follow<PlanDecisionResult, DismissPlanEvent>("dismiss_plan", { run_id: run_id });
  }

  /**
   * Read the plan the agent last submitted in this session, with its task list.
   *
   * Takes no arguments. Returns the `latest` plan's text, every plan
   * submitted before it (`history`), the to-do list (`tasks`), and
   * `state`: `pending` while a plan is waiting for a decision, empty
   * when none was submitted.
   */
  latest(): Promise<LatestPlanResult> {
    return this.caller.rpc<LatestPlanResult>("get_latest_plan", {});
  }
}

/** Plugins installed into this session's project. */
export class SessionPlugins {
  constructor(readonly caller: Caller) {}

  /**
   * Show what an installed plugin contains.
   *
   * `name` is the installed plugin. Returns its folder and its
   * skills, agents, hooks, MCP servers and tools, with its README; or
   * `error` when no such plugin is installed.
   */
  contents(name: string): Promise<PluginContents> {
    return this.caller.rpc<PluginContents>("get_plugin_contents", { name: name });
  }

  /**
   * Install a plugin from a git repository or a marketplace.
   *
   * `ref` is a git URL or `@<marketplace>/<plugin>`; `install_ref`
   * the branch, tag or commit to check out (the marketplace's, or the
   * default branch, when absent). The plugin is active in this session
   * at once. Returns an `info` message, sent in place of an
   * `rpc_response`, whose text says what was installed — or why not:
   * git missing, an unknown marketplace entry, the organisation's
   * policy, a git error.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  install(ref: string, install_ref?: string | null): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("install_plugin", { install_ref: install_ref, ref: ref });
  }

  /**
   * List the installed plugins.
   *
   * Takes no arguments. Returns each plugin's name, version,
   * description, where it came from, whether it is enabled (a plugin
   * the organisation manages always is), the commit it is pinned to,
   * and what it brings: skills, agents, hooks, MCP servers.
   */
  list(): Promise<PluginInfo[]> {
    return this.caller.rpc<PluginInfo[]>("get_plugin_details", {});
  }

  /**
   * Show what a plugin contains without installing it.
   *
   * `source` is the plugin's git URL (optionally followed by a
   * subfolder); `branch` the branch, tag or commit to read (the
   * default branch when absent); `subdir` the plugin's folder inside
   * the repository, which wins over one in `source`. The repository
   * is cloned to a temporary place. Returns the same shape as
   * `get_plugin_contents`, with `preview_source` naming what was
   * read; or `error` when the organisation's policy refuses the
   * source, git is missing, or the clone failed.
   */
  preview(source: string, branch?: string | null, subdir?: string | null): Promise<PluginContents> {
    return this.caller.rpc<PluginContents>("preview_plugin", { branch: branch, source: source, subdir: subdir });
  }

  /**
   * Uninstall a plugin.
   *
   * `name` is the installed plugin. Returns an `info` message, sent
   * in place of an `rpc_response`, whose text says it was removed, or
   * why not.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  remove(name: string): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("remove_plugin", { name: name });
  }

  /**
   * Switch an installed plugin on or off.
   *
   * `name` is the installed plugin; `enabled` its new state. The
   * choice is saved and this session reloads its plugins. Returns an
   * `info` message, sent in place of an `rpc_response`, whose text
   * says what happened — including a refusal: no such plugin, or one
   * the organisation manages.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  set_enabled(enabled: boolean, name: string): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("set_plugin_enabled", { enabled: enabled, name: name });
  }

  /**
   * Move an installed plugin to another commit.
   *
   * `name` is the installed plugin; `install_ref` the branch, tag
   * or commit to move to (the remote's default branch when absent).
   * Returns an `info` message, sent in place of an `rpc_response`,
   * whose text names the commit now installed, or why not.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  update(name: string, install_ref?: string | null): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("update_plugin", { install_ref: install_ref, name: name });
  }
}

/** This session's runs that were received but not finished. */
export class SessionRuns {
  constructor(readonly caller: Caller) {}

  /**
   * Forget one interrupted run, so it is not offered again.
   *
   * `message_id` names the run (from `get_interrupted_runs`);
   * `session_id` the session it belongs to; only that session's
   * interrupted run is deleted. Returns `ok: true` — also when no such
   * run exists, so a retry is harmless — or `ok: false` with `error`
   * when `message_id` is empty or the store could not be written.
   */
  discard_interrupted(message_id: string): Promise<DiscardInterruptedRunResult> {
    return this.caller.rpc<DiscardInterruptedRunResult>("discard_interrupted_run", { message_id: message_id, session_id: this.caller.sessionId });
  }

  /**
   * Forget one pending message, so it is not offered again.
   *
   * `message_id` names the message (from `get_pending_messages`);
   * `session_id` the session it belongs to; only that session's
   * pending message is deleted. Returns `ok: true` — also when no such
   * message is pending, so a retry is harmless — or `ok: false` with
   * `error` when `message_id` is empty, the message arrived less than
   * a minute ago while this igni runs (its run may still be finishing),
   * or the store could not be written.
   */
  discard_pending(message_id: string): Promise<DiscardPendingMessageResult> {
    return this.caller.rpc<DiscardPendingMessageResult>("discard_pending_message", { message_id: message_id, session_id: this.caller.sessionId });
  }

  /**
   * List a session's runs that stopped before they finished.
   *
   * `session_id` names the session. Returns one row per run that was
   * cancelled, failed or never finished: the `message_id` and text of
   * the message that started it, when it arrived and when it stopped, why
   * (`cancelled`, `errored`, or `abandoned` when igni stopped while
   * it ran) and the last error. A client offers to retry,
   * discard or edit each. A storage failure answers an empty list.
   */
  interrupted(): Promise<InterruptedRun[]> {
    return this.caller.rpc<InterruptedRun[]>("get_interrupted_runs", { session_id: this.caller.sessionId });
  }

  /**
   * List a session's messages whose run started but never finished.
   *
   * `session_id` names the session. Returns the user messages still
   * pending — typically left by a crash — oldest first, each with its
   * text, when it arrived and its `message_id`: one saved before this
   * igni started at once, one it received itself a minute after it
   * arrived. A storage failure answers an empty list.
   */
  pending_messages(): Promise<PendingMessage[]> {
    return this.caller.rpc<PendingMessage[]>("get_pending_messages", { session_id: this.caller.sessionId });
  }
}

/** Scheduled tasks of this session's project. */
export class SessionScheduler {
  constructor(readonly caller: Caller) {}

  /**
   * Cancel a scheduled task of this session's project.
   *
   * `task_id` is the task's `id` (from `get_scheduled_tasks`). The
   * task is marked cancelled, so it does not run again; a run already
   * going is not stopped, but its outcome is not recorded. Returns an
   * `info` message, sent in place of an `rpc_response`. Fails for
   * an id the project has no task for, and for a task that already
   * completed, failed or was cancelled, whose record is left as it is.
   */
  cancel(task_id: string): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("cancel_scheduled_task", { task_id: task_id });
  }

  /**
   * Run a scheduled task's work now, in this session, and wait for the answer.
   *
   * `description` is what the task asks the agent to do (a scheduled
   * task's `description`). The agent runs it as a stored task firing,
   * not as a live message: its run is not streamed to the windows, and
   * the task's own record is not touched. What its tools push while
   * they work still goes out. It is the session's run while it goes:
   * it waits for a turn already running, `get_processing` reports
   * it, and `cancel_run` stops it. Returns the agent's answer as
   * text with the run's `run_id` — the one given, or one made — which
   * every push the run's tools make carries too. Fails when the
   * organisation's group policy refuses the run, the run is cancelled,
   * or the run fails.
   *
   * ``async with`` the call to follow it: it yields the pushes of the run it starts — what its tools do while it works — as they come, and ends with the answer, which is the agent's own words. The run's id is the one given; igni-client makes one when the caller does not, so the pushes can be told from another run's.
   */
  execute(description: string, run_id?: string): Call<ScheduledTaskRunResult, ExecuteScheduledTaskEvent> {
    return this.caller.follow<ScheduledTaskRunResult, ExecuteScheduledTaskEvent>("execute_scheduled_task", { description: description, run_id: run_id ?? this.caller.newId("run") });
  }

  /**
   * List the scheduled tasks of this session's project.
   *
   * `include_done` (default `true`) lists finished, failed and
   * cancelled tasks too. Returns the tasks, latest scheduled first:
   * each one's `id`, `description`, when it is scheduled and was
   * created, its `status`, its `result` or `error`, and its
   * `recurrence` (empty for a one-shot task).
   */
  list(include_done?: boolean): Promise<ScheduledTask[]> {
    return this.caller.rpc<ScheduledTask[]>("get_scheduled_tasks", { include_done: include_done });
  }

  /**
   * Start running this project's scheduled tasks as they fall due.
   *
   * Takes no arguments and returns nothing; a scheduler already running
   * is left as it is. From then on each due task runs through the
   * agent: `scheduler_started` when it starts, `scheduler_completed`
   * with its result when it ends, and whatever its tools push between.
   *
   * ``async with`` the call to follow it: it yields this session's ``scheduler_started`` and ``scheduler_completed`` pushes for as long as the block runs. What a task's tools push meanwhile carries nothing that says which run it came from, so it is not yielded; read it from ``igni.events()``.
   */
  start(): Call<null, StartSchedulerEvent> {
    return this.caller.follow<null, StartSchedulerEvent>("start_scheduler", {});
  }
}

/** The skills this session's agent can use. */
export class SessionSkills {
  constructor(readonly caller: Caller) {}

  /**
   * List this session's skills with what each tells the agent.
   *
   * Takes no arguments. Returns each skill's `name`, `description`
   * and `prompt` (the skill's body).
   */
  definitions(): Promise<SkillDefinition[]> {
    return this.caller.rpc<SkillDefinition[]>("get_skill_definitions", {});
  }

  /**
   * Describe each of this session's skills in full.
   *
   * Takes no arguments. Returns each skill's name, description,
   * version, category, argument hint, the context and agent it runs
   * in, whether a person can invoke it, its body and its folder.
   */
  list(): Promise<SkillInfo[]> {
    return this.caller.rpc<SkillInfo[]>("get_skill_details", {});
  }

  /**
   * List the names of the skills this session has loaded.
   *
   * Takes no arguments. Returns the names, each usable as `/<name>`.
   */
  names(): Promise<string[]> {
    return this.caller.rpc<string[]>("get_skill_names", {});
  }
}

/** Workflows: scripted runs this session starts and follows. */
export class SessionWorkflows {
  constructor(readonly caller: Caller) {}

  /**
   * Stop a running workflow of this session.
   *
   * `workflow_run_id` is the run (from `run_workflow`). The
   * workflow is asked to stop, then terminated after a grace period;
   * its last `workflow_event` says it was cancelled. Returns
   * `cancelled: true` when a live run was stopped, `false` when
   * there was no such run or it had already ended, with the
   * `workflow_run_id` asked about.
   *
   * ``async with`` the call to follow it: it yields the ``workflow_event`` pushes of ``workflow_run_id`` and ends with the run's last, or with the answer when ``cancelled`` is false.
   */
  cancel(workflow_run_id: string): Call<WorkflowCancelResponse, CancelWorkflowEvent> {
    return this.caller.follow<WorkflowCancelResponse, CancelWorkflowEvent>("cancel_workflow", { workflow_run_id: workflow_run_id });
  }

  /**
   * List the workflows this session's project can run.
   *
   * Takes no arguments (any it is sent are ignored). Returns each workflow in
   * `.igni/workflows/*.mjs` (a project's shadowing the person's own
   * of the same name), sorted by name: its `name`, `description`,
   * `whenToUse`, `phases` and `path`. A file whose metadata cannot
   * be read is left out.
   */
  list(): Promise<WorkflowListItem[]> {
    return this.caller.rpc<WorkflowListItem[]>("list_workflows", {});
  }

  /**
   * Start a workflow in this session and return its run id at once.
   *
   * `name` is the workflow (from `list_workflows`); `args` its
   * input, a JSON object the workflow reads as it defines. Returns the
   * `workflow_run_id` and `name`. The run goes on in the
   * background: each step it takes is pushed as `workflow_event`
   * carrying that id, ending with `workflow_completed` or
   * `workflow_failed`. Fails when there is no such workflow or the
   * workflow runtime is missing.
   *
   * ``async with`` the call to follow it: it yields every ``workflow_event`` push carrying the ``workflow_run_id`` igni answered with — those that came before the answer too — and ends with the run's ``workflow_completed`` or ``workflow_failed``.
   */
  run(name: string, args?: Record<string, JsonValue>): Call<WorkflowRunResponse, RunWorkflowEvent> {
    return this.caller.follow<WorkflowRunResponse, RunWorkflowEvent>("run_workflow", { args: args, name: name });
  }
}

/** Whether this session's project folder is trusted. */
export class SessionWorkspace {
  constructor(readonly caller: Caller) {}

  /**
   * Answer "Trust this folder?" for this session's project folder.
   *
   * `decision` is `trust` (remembered), `once` (until igni exits)
   * or `distrust`. When trust changed, the session is rebuilt so the
   * folder's tools, hooks, plugins, language servers and configuration
   * come in or go. Every window showing the dialog for that folder is
   * told the new status (`workspace_trust_required`). Returns the new
   * status. Fails when the organisation's policy does not let the folder
   * be trusted.
   *
   * ``async with`` the call to follow it: it yields the ``workspace_trust_required`` push that tells the windows the folder's trust changed, and ends with the answer — the new status.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  set_trust(decision: "trust" | "distrust" | "once"): Call<WorkspaceTrustStatus, SetWorkspaceTrustEvent> {
    return this.caller.follow<WorkspaceTrustStatus, SetWorkspaceTrustEvent>("set_workspace_trust", { decision: decision });
  }

  /**
   * Read whether this session's project folder is trusted.
   *
   * Takes no arguments. Returns the folder's trust `state`
   * (`trusted`, `untrusted`, or `ask` when the person has not
   * decided), whether it `can_trust` it under the organisation's
   * policy and, if not, the `reason`, plus where the decision came
   * from. Until a folder is trusted its own tools, hooks, plugins and
   * configuration are not loaded.
   */
  trust(): Promise<WorkspaceTrustStatus> {
    return this.caller.rpc<WorkspaceTrustStatus>("get_workspace_trust", {});
  }
}

/** The methods igni answers for igni as a whole; `IgniClient` is one. */
export class IgniApi {
  /** Sub-agents' runs, wherever they are going. */
  readonly agents: IgniAgents;
  /** Approver tokens: what lets a program answer approval requests. */
  readonly approvers: IgniApprovers;
  /** Signing igni in to igni server, and choosing which server. */
  readonly auth: IgniAuth;
  /** The extensions installed into this igni, and their settings. */
  readonly extensions: IgniExtensions;
  /** Folders on the machine igni runs on. */
  readonly files: IgniFiles;
  /** Plugin marketplaces: where plugins are installed from. */
  readonly marketplaces: IgniMarketplaces;
  /** The signed-in person's notifications, and what extensions posted. */
  readonly notifications: IgniNotifications;
  /** Background processes igni tracks, in every session. */
  readonly processes: IgniProcesses;
  /** igni's sessions: attach one, or make a new one in a project folder. */
  readonly sessions: IgniSessions;
  /** igni's own window's model — its fields, toasts and dialog. */
  readonly window: IgniWindow;

  constructor(readonly caller: Caller) {
    this.agents = new IgniAgents(caller);
    this.approvers = new IgniApprovers(caller);
    this.auth = new IgniAuth(caller);
    this.extensions = new IgniExtensions(caller);
    this.files = new IgniFiles(caller);
    this.marketplaces = new IgniMarketplaces(caller);
    this.notifications = new IgniNotifications(caller);
    this.processes = new IgniProcesses(caller);
    this.sessions = new IgniSessions(caller);
    this.window = new IgniWindow(caller);
  }

  /**
   * Ask whether a newer igni release is available.
   *
   * Takes no arguments. Returns the newer release — its version, the
   * version installed, where to get it — or `null` when there is none
   * (or update checks are switched off). Fails when the check could not
   * reach an answer (network, HTTP status, an unreadable reply), so a
   * caller can tell that from "no update".
   */
  check_for_update(): Promise<UpdateAvailable | null> {
    return this.caller.rpc<UpdateAvailable | null>("check_for_update", {});
  }

  /**
   * Read which organisation group's policy igni follows.
   *
   * Takes no arguments. Returns the group's id and name, when its
   * policy pack was fetched, how many entries it has and the default
   * model it sets; nulls and zero when igni follows no group.
   */
  group_policy(): Promise<GroupPolicyPackResult> {
    return this.caller.rpc<GroupPolicyPackResult>("get_group_policy", {});
  }
}

/** The methods igni answers for one session; `Session` is one. */
export class SessionApi {
  /** The agents this session can hand work to. */
  readonly agents: SessionAgents;
  /** This session's sign-in to igni server. */
  readonly auth: SessionAuth;
  /** This session's context window: how full it is, and compacting it. */
  readonly context: SessionContext;
  /** Files in this session's project folder. */
  readonly files: SessionFiles;
  /** This session's conversation as stored: read, search, cut back. */
  readonly history: SessionHistory;
  /** The hooks that run on this session's events. */
  readonly hooks: SessionHooks;
  /** This session's loop: a task the agent repeats until it is done. */
  readonly loop: SessionLoop;
  /** MCP servers this session connects to, and their tools. */
  readonly mcp: SessionMcp;
  /** The models this session can use, and switching between them. */
  readonly models: SessionModels;
  /** Saved permission rules for tool calls. */
  readonly permissions: SessionPermissions;
  /** Plan mode: the plan the agent submitted, and the person's decision. */
  readonly plan: SessionPlan;
  /** Plugins installed into this session's project. */
  readonly plugins: SessionPlugins;
  /** This session's runs that were received but not finished. */
  readonly runs: SessionRuns;
  /** Scheduled tasks of this session's project. */
  readonly scheduler: SessionScheduler;
  /** The skills this session's agent can use. */
  readonly skills: SessionSkills;
  /** Workflows: scripted runs this session starts and follows. */
  readonly workflows: SessionWorkflows;
  /** Whether this session's project folder is trusted. */
  readonly workspace: SessionWorkspace;

  constructor(readonly caller: Caller) {
    this.agents = new SessionAgents(caller);
    this.auth = new SessionAuth(caller);
    this.context = new SessionContext(caller);
    this.files = new SessionFiles(caller);
    this.history = new SessionHistory(caller);
    this.hooks = new SessionHooks(caller);
    this.loop = new SessionLoop(caller);
    this.mcp = new SessionMcp(caller);
    this.models = new SessionModels(caller);
    this.permissions = new SessionPermissions(caller);
    this.plan = new SessionPlan(caller);
    this.plugins = new SessionPlugins(caller);
    this.runs = new SessionRuns(caller);
    this.scheduler = new SessionScheduler(caller);
    this.skills = new SessionSkills(caller);
    this.workflows = new SessionWorkflows(caller);
    this.workspace = new SessionWorkspace(caller);
  }

  /**
   * Stop the turn this session is running.
   *
   * Takes no arguments. Returns `cancelled`: whether a turn was
   * running or paused on an approval. Either way the session then
   * streams an `info` saying it was cancelled and a `stream_end`,
   * after the answer; the run is recorded as interrupted, and a
   * foreground shell command the turn started is killed. A turn paused
   * on an approval has its waiting approvals dropped: answering one
   * afterwards runs nothing, and a window that attaches is not offered
   * it. Ending a paused turn
   * refuses its approval, so it takes what answering takes: from a
   * program without an approver token it is refused, `forbidden`,
   * and nothing is dropped. With no turn running or paused nothing
   * happens and nothing is streamed.
   *
   * ``async with`` the call to follow it: it yields the ``info`` and ``stream_end`` of the turn it stops, running or paused on an approval, and ends with the ``stream_end`` of that ``info``'s stream — not one of another stream of the session, such as the ``stream_end`` an attach ends the approvals it shows again with, which can come after ``sessions.open()`` returned. With no turn running or paused nothing is streamed, and the answer says so.
   *
   * While the session waits on an approval, only igni's window or an approver ends its run: ending it refuses the approval. A program without an approver token gets ``AccessRefused``, and nothing is dropped. A run that is working any connection may stop.
   */
  cancel(): Call<CancelRunResult, CancelRunEvent> {
    return this.caller.follow<CancelRunResult, CancelRunEvent>("cancel_run", {});
  }

  /**
   * Run a slash command in this session, as typed in igni's composer: ``/help``, ``/compact``, ``/model``.
   *
   * ``text`` is the command line, its leading ``/`` optional. Returns igni's ``command_result``: its ``kind`` (``markdown``, ``info``, ``error`` or ``action``), the ``content`` to show and the ``action`` the command asks a client to take. The commands that switch approvals off, change what igni loads or whom it signs in to (``/bypass``, ``/accept``, ``/plugin``, ``/eject``, ``/login``, ``/logout``) answer an ``error`` to anything but igni's window.
   *
   * Sent as igni's `command` message. igni answers with `command_result`.
   */
  command(text?: string): Promise<CommandResult> {
    return this.caller.request<CommandResult>("command", { text: text });
  }

  /**
   * Read the id of the session this request reached.
   *
   * Takes no arguments. Returns the session's current id, which can
   * differ from the one the request was routed by after `/clear` or
   * `switch_session`.
   */
  current_id(): Promise<string> {
    return this.caller.rpc<string>("get_session_id", {});
  }

  /**
   * Read this session's display settings.
   *
   * Takes no arguments. Returns how output is shown: markdown rendering,
   * tool calls, routing, reasoning, the colour theme, and how many lines
   * of a tool result and a message are shown before truncating.
   */
  display_config(): Promise<DisplayConfig> {
    return this.caller.rpc<DisplayConfig>("get_display_config", {});
  }

  /**
   * Let igni learn from one finished turn, in the background.
   *
   * `user_msg` and `assistant_msg` are the turn's message and
   * answer. Returns at once with nothing; what is learnt is kept for
   * later sessions, and a failure is only logged.
   */
  extract_learnings(assistant_msg: string, user_msg: string): Promise<null> {
    return this.caller.rpc<null>("extract_learnings", { assistant_msg: assistant_msg, user_msg: user_msg });
  }

  /**
   * Run this session's `SessionStart` hooks.
   *
   * Takes no arguments and returns nothing. The organisation's group
   * policy is checked again first. Every call runs the hooks again;
   * their failures are logged, not raised.
   */
  fire_session_start_hook(): Promise<null> {
    return this.caller.rpc<null>("fire_session_start_hook", {});
  }

  /**
   * Read the folder this session is locked to.
   *
   * Takes no arguments. Returns the absolute path the agent's tools and
   * shell commands work in.
   */
  get_project_dir(): Promise<string> {
    return this.caller.rpc<string>("get_project_dir", {});
  }

  /**
   * Say whether this session is running a turn right now.
   *
   * Takes no arguments. Returns `true` while a turn the person (or a
   * client) started is starting, streaming or finishing.
   */
  is_processing(): Promise<boolean> {
    return this.caller.rpc<boolean>("get_processing", {});
  }

  /**
   * List the sessions kept in this session's project.
   *
   * Takes no arguments. Returns a `session_list_result` message, sent
   * in place of an `rpc_response`: each session's id, name, when it
   * was created and last updated, how many runs it has, a summary and
   * the agent it runs. A storage failure answers an empty list.
   */
  list_sessions(): Promise<SessionListResult> {
    return this.caller.rpc<SessionListResult>("list_sessions", {});
  }

  /**
   * List the output styles this session can answer in, and the active one.
   *
   * Takes no arguments. Returns the `active` style's name (empty for
   * none) and every style's `name` and `description`.
   */
  output_styles(): Promise<OutputStylesResult> {
    return this.caller.rpc<OutputStylesResult>("get_output_styles", {});
  }

  /**
   * Run a shell command in this session's project folder and return its output.
   *
   * `command` is the command line (what follows `$` in the
   * composer); blank runs nothing. Output is captured, not interactive.
   * Returns `output` (the tail, at most 100 KB) and `exit_code`
   * (`-1` when it could not start). A command still running after two
   * minutes moves to the background: the answer then comes at once with
   * `exit_code` 0 and a note, and the process goes on as a background
   * process — `process_started`, a `process_line` per line,
   * `process_exited` and `background_process_done`.
   *
   * ``async with`` the call to follow it: a command that finishes inside the wait pushes nothing, and the answer is its output. A command that outlives the wait moves to the background: the answer names the pid, and the ``process_started``, ``process_line``, ``process_exited`` and ``background_process_done`` pushes of that pid follow, ending with the last of them.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  run_shell(command?: string): Call<RunShellResult, RunShellEvent> {
    return this.caller.follow<RunShellResult, RunShellEvent>("run_shell", { command: command });
  }

  /**
   * Read how long, in seconds, a client should wait for one run.
   *
   * Takes no arguments. Returns the configured maximum run time; igni
   * does not stop a run at it, the client decides what to do.
   */
  run_timeout(): Promise<number> {
    return this.caller.rpc<number>("get_run_timeout", {});
  }

  /**
   * Wind this session down: its hooks, its agents, its MCP servers, its scheduler.
   *
   * Takes no arguments and returns nothing once done. Runs the session's
   * `SessionEnd` hooks, cleans up its ephemeral agents, disconnects its
   * MCP servers and stops its scheduler — once: a session already wound
   * down is left as it is. Background processes are igni's, not the
   * session's, and are left running; they end when igni does. It does
   * not stop igni or close the connection. Each step's failure is
   * logged, not raised. Only igni's window may call it.
   *
   * Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
   */
  shutdown(): Promise<null> {
    return this.caller.rpc<null>("shutdown", {});
  }

  /**
   * List every slash command this session takes.
   *
   * Takes no arguments. Returns igni's built-in commands, commands
   * written as markdown files, skills a person can invoke, and
   * extensions' commands, told apart by `source`; each with its
   * `name`, `description` and `argument_hint`.
   */
  slash_commands(): Promise<SlashCommand[]> {
    return this.caller.rpc<SlashCommand[]>("get_slash_commands", {});
  }

  /**
   * Read this session's status: model, account, context size and permission mode.
   *
   * Takes no arguments. Returns a `status_update` message, sent in
   * place of an `rpc_response`: the model and whether it is
   * configured, the igni server connection and account, the context
   * used and its window, the permission mode and the theme.
   */
  status(): Promise<StatusUpdate> {
    return this.caller.rpc<StatusUpdate>("get_status", {});
  }

  /**
   * Make the session this request is routed to continue another stored session.
   *
   * `session_id` is the stored session to continue; the conversation,
   * its history and its runs are read from it from now on. Returns an
   * `info` message, sent in place of an `rpc_response`, naming the
   * session switched to. The id is not checked: an unknown one starts
   * an empty session under that id.
   */
  switch(session_id: string): Promise<InfoMessage> {
    return this.caller.rpc<InfoMessage>("switch_session", { session_id: session_id });
  }

  /**
   * Read the agent's to-do list in this session.
   *
   * Takes no arguments. Returns each item's `content`, `status`
   * (`pending`, `in_progress`, `completed`) and `activeForm`
   * (how it reads while in progress). `todos_updated` pushes the list
   * whenever the agent changes it.
   */
  todos(): Promise<TodoItem[]> {
    return this.caller.rpc<TodoItem[]>("get_todos", {});
  }

  /**
   * Turn showing the agent's routing decisions on or off for this session.
   *
   * Takes no arguments. Returns the new setting: `true` when routing is
   * now shown. Not saved; the session's next settings reload resets it.
   */
  toggle_verbose(): Promise<boolean> {
    return this.caller.rpc<boolean>("toggle_verbose", {});
  }

  /**
   * Show what this client is typing to every other client of this session.
   *
   * ``text`` is the whole draft, not a change to it; empty clears it. igni relays it to every client attached, this one included, as a ``Typing`` event.
   *
   * Sent as igni's `typing` message.
   */
  typing(text?: string): Promise<void> {
    return this.caller.sendMessage("typing", { client_id: this.caller.clientId, text: text });
  }

  /**
   * Store a file for this session, so a message can refer to it.
   *
   * `filename` is the file's name (made safe for the disk; a clash gets
   * a `-N` suffix); `content_base64` its bytes, base64-encoded.
   * Returns `path` — the stored file's path, or an `attachment:<id>`
   * reference when attachments are kept in shared storage — and its
   * `size` in bytes; or `error` when the content is not valid base64.
   * Fails when the file cannot be stored.
   */
  upload_attachment(content_base64: string, filename: string): Promise<UploadAttachmentResult> {
    return this.caller.rpc<UploadAttachmentResult>("upload_attachment", { content_base64: content_base64, filename: filename });
  }

  /**
   * Tell this session the person used a control in a view the agent drew.
   *
   * `action` is the control's action name; `params` the values the
   * view attached to it (JSON). The action is pushed to every window,
   * extension and SDK program as `visualization_action_dispatched`.
   * It does not reach the agent: whoever receives it decides whether
   * and when to tell the agent, for example by posting a message once
   * its own request has finished. Returns the action and params as
   * recorded, with `ok`.
   *
   * ``async with`` the call to follow it: it yields the ``visualization_action_dispatched`` push of this session carrying this ``action`` and ``params``, and ends with it.
   */
  visualization_action(action?: string, params?: Record<string, JsonValue> | null): Call<VisualizationActionResult, DispatchVisualizationActionEvent> {
    return this.caller.follow<VisualizationActionResult, DispatchVisualizationActionEvent>("dispatch_visualization_action", { action: action, params: params });
  }

  /**
   * Tell this session what the client drew of a card the agent drew.
   *
   * `spec_id` is the card, `revision` which draw of it (the first
   * is 1), `total` how many elements the card has, `failed` the
   * elements the client could not draw — each with its type and the
   * client's word for why — and `issues` what was wrong with the
   * card's shape. The verdict is kept against that card and draw,
   * and the visualizer's recap quotes it, so the agent says what is
   * on the screen. Returns the card, the draw and how much of it
   * was drawn.
   */
  visualization_verdict(spec_id: string, failed?: ElementFailureArgs[], issues?: string[], revision?: number, total?: number): Promise<VisualizationVerdictResult> {
    return this.caller.rpc<VisualizationVerdictResult>("report_visualization_verdict", { failed: failed, issues: issues, revision: revision, spec_id: spec_id, total: total });
  }
}

"""Every method a client calls, typed: igni's RPC methods by namespace.

GENERATED from igni-core's RPC contract (version 1) by igni-sdk's tools/client_codegen.py — do not edit. Run `make client-api` after refreshing contracts/rpc-contract.json.

`IgniApi` is what `IgniClient` adds for igni as a whole, and `SessionApi`
what `Session` adds for one session. A method that streams returns a
`Call`: await it for the result, or `async with` it to follow its events too.
"""

from __future__ import annotations

import builtins
from typing import Literal

from pydantic import JsonValue, TypeAdapter

from igni_client.calls import Call, Caller, MethodSpec
from igni_client.follow import Correlation
from igni_client.models import (
    AgentInfo,
    AgentNameArgs,
    AgentRunArgs,
    ApproverTokenMinted,
    ApproverTokensRevoked,
    AttachSessionParams,
    AttachSessionResult,
    BackgroundProcessDonePush,
    CancelAgentRunResult,
    CancelLogin,
    CancelRunResult,
    ChatSearchHit,
    ChatTurn,
    CheckPermissionArgs,
    CloudPlan,
    Command,
    CommandResult,
    CompactIfNeededArgs,
    CompactionOutcome,
    CompleteFilesArgs,
    ContentDelta,
    ContextBreakdown,
    DirListResult,
    DiscardEphemeralResult,
    DiscardInterruptedRunResult,
    DiscoverServerArgs,
    DisplayConfig,
    ErrorMessage,
    ExecuteScheduledTaskArgs,
    ExtensionListResult,
    ExtractLearningsArgs,
    FileCompletion,
    FileEditedPush,
    GroupPolicyPackResult,
    HookEntryView,
    HttpRetryAttemptPush,
    HttpRetrySucceededPush,
    InfoMessage,
    InstallPluginArgs,
    InterruptedRun,
    InterruptedRunArgs,
    LatestPlanResult,
    ListDirsArgs,
    LoginResultPush,
    LoginStarted,
    LoginStatusPush,
    LoopAdvance,
    LoopStatusSnapshot,
    MarketplaceInfo,
    MarketplaceNameArgs,
    MarketplaceUrlArgs,
    MarkReadArgs,
    McpInitResult,
    McpServerArgs,
    McpServerSnapshot,
    McpServerStatus,
    McpServerSummary,
    McpToolEnabledArgs,
    McpToolToggleResult,
    ModelCompleted,
    ModelRegistryResult,
    NoArgs,
    NotificationCounts,
    NotificationsChangedPush,
    NotificationsListResult,
    NotificationsReadResult,
    OrchestrateEventPush,
    OutputStylesResult,
    PendingMessage,
    PermissionModeChangedPush,
    PickDirArgs,
    PickDirResult,
    PlanDecidedPush,
    PlanDecisionResult,
    PlanRunArgs,
    PlanSubmittedPush,
    PluginContents,
    PluginEnabledArgs,
    PluginInfo,
    PluginNameArgs,
    PreviewPluginArgs,
    ProcessArgs,
    ProcessExitedPush,
    ProcessLinePush,
    ProcessRow,
    ProcessStartedPush,
    ProcessTailArgs,
    ProcessTailResult,
    PromoteAgentArgs,
    PromoteEphemeralResult,
    ReadFileArgs,
    ReadFileResult,
    ReasoningStarted,
    RefreshMarketplacesArgs,
    RequirementDetails,
    RunCompleted,
    RunError,
    RunPaused,
    RunShellArgs,
    RunShellResult,
    RunStarted,
    SavePermissionRuleArgs,
    ScheduledTask,
    ScheduledTaskArgs,
    ScheduledTaskRunResult,
    ScheduledTasksArgs,
    SchedulerCompletedPush,
    SchedulerStartedPush,
    SearchChatArgs,
    SearchCodeArgs,
    SearchCodeResult,
    ServerChoice,
    ServerFound,
    SessionIdArgs,
    SessionListResult,
    SetExtensionSettingsArgs,
    SetServerArgs,
    SkillDefinition,
    SkillInfo,
    SlashCommand,
    StatusUpdate,
    StopProcessResult,
    StreamEnd,
    StreamingDone,
    SwitchModelArgs,
    TaskCreated,
    TaskIteration,
    TaskStateUpdated,
    TaskUpdated,
    TodoItem,
    TodosUpdatedPush,
    ToolCallArgs,
    ToolCompleted,
    ToolError,
    ToolStarted,
    TruncateHistoryArgs,
    TruncateHistoryResult,
    TrustDecisionArgs,
    Typing,
    UpdateAvailable,
    UpdatePluginArgs,
    UploadAttachmentArgs,
    UploadAttachmentResult,
    VisualizationActionArgs,
    VisualizationActionDispatchedPush,
    VisualizationActionResult,
    WindowModelArgs,
    WindowModelChangedPush,
    WindowModelResult,
    WorkflowCancelRequest,
    WorkflowCancelResponse,
    WorkflowEventPush,
    WorkflowListItem,
    WorkflowListRequest,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkspaceTrustRequiredPush,
    WorkspaceTrustStatus,
)

# What each method answers, read with these.
_ADD_MARKETPLACE: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_APPROVE_PLAN: TypeAdapter[PlanDecisionResult] = TypeAdapter(PlanDecisionResult)
_ATTACH_SESSION: TypeAdapter[AttachSessionResult] = TypeAdapter(AttachSessionResult)
_CANCEL_AGENT_RUN: TypeAdapter[CancelAgentRunResult] = TypeAdapter(CancelAgentRunResult)
_CANCEL_PENDING_LOOP: TypeAdapter[bool] = TypeAdapter(bool)
_CANCEL_RUN: TypeAdapter[CancelRunResult] = TypeAdapter(CancelRunResult)
_CANCEL_SCHEDULED_TASK: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_CANCEL_WORKFLOW: TypeAdapter[WorkflowCancelResponse] = TypeAdapter(WorkflowCancelResponse)
_CHECK_FOR_UPDATE: TypeAdapter[UpdateAvailable | None] = TypeAdapter(UpdateAvailable | None)
_CHECK_PERMISSION: TypeAdapter[Literal["allow", "ask", "deny"]] = TypeAdapter(
    Literal["allow", "ask", "deny"]
)
_CLEAR_CLOUD_CREDENTIALS: TypeAdapter[StatusUpdate] = TypeAdapter(StatusUpdate)
_COMPACT_IF_NEEDED: TypeAdapter[CompactionOutcome] = TypeAdapter(CompactionOutcome)
_COMPLETE_FILES: TypeAdapter[FileCompletion] = TypeAdapter(FileCompletion)
_COUNT_CONTEXT_TOKENS: TypeAdapter[int] = TypeAdapter(int)
_DISCARD_EPHEMERAL_AGENT: TypeAdapter[DiscardEphemeralResult] = TypeAdapter(DiscardEphemeralResult)
_DISCARD_INTERRUPTED_RUN: TypeAdapter[DiscardInterruptedRunResult] = TypeAdapter(
    DiscardInterruptedRunResult
)
_DISCOVER_SERVER: TypeAdapter[ServerFound] = TypeAdapter(ServerFound)
_DISMISS_PLAN: TypeAdapter[PlanDecisionResult] = TypeAdapter(PlanDecisionResult)
_DISPATCH_VISUALIZATION_ACTION: TypeAdapter[VisualizationActionResult] = TypeAdapter(
    VisualizationActionResult
)
_ENSURE_MCP: TypeAdapter[McpInitResult] = TypeAdapter(McpInitResult)
_EXECUTE_SCHEDULED_TASK: TypeAdapter[ScheduledTaskRunResult] = TypeAdapter(ScheduledTaskRunResult)
_EXTRACT_LEARNINGS: TypeAdapter[None] = TypeAdapter(None)
_FIRE_SESSION_START_HOOK: TypeAdapter[None] = TypeAdapter(None)
_GET_AGENT_DETAILS: TypeAdapter[list[AgentInfo]] = TypeAdapter(list[AgentInfo])
_GET_CHAT_HISTORY: TypeAdapter[list[ChatTurn]] = TypeAdapter(list[ChatTurn])
_GET_CLOUD_PLAN: TypeAdapter[CloudPlan | None] = TypeAdapter(CloudPlan | None)
_GET_CONTEXT_BREAKDOWN: TypeAdapter[ContextBreakdown] = TypeAdapter(ContextBreakdown)
_GET_DISPLAY_CONFIG: TypeAdapter[DisplayConfig] = TypeAdapter(DisplayConfig)
_GET_GROUP_POLICY: TypeAdapter[GroupPolicyPackResult] = TypeAdapter(GroupPolicyPackResult)
_GET_HOOKS_DETAILS: TypeAdapter[list[HookEntryView]] = TypeAdapter(list[HookEntryView])
_GET_INTERRUPTED_RUNS: TypeAdapter[list[InterruptedRun]] = TypeAdapter(list[InterruptedRun])
_GET_LATEST_PLAN: TypeAdapter[LatestPlanResult] = TypeAdapter(LatestPlanResult)
_GET_MARKETPLACES: TypeAdapter[list[MarketplaceInfo]] = TypeAdapter(list[MarketplaceInfo])
_GET_MCP_SERVER_DETAILS: TypeAdapter[list[McpServerSnapshot]] = TypeAdapter(list[McpServerSnapshot])
_GET_MCP_SERVERS: TypeAdapter[list[McpServerSummary]] = TypeAdapter(list[McpServerSummary])
_GET_MCP_STATUS: TypeAdapter[list[McpServerStatus]] = TypeAdapter(list[McpServerStatus])
_GET_MODEL_REGISTRY: TypeAdapter[ModelRegistryResult] = TypeAdapter(ModelRegistryResult)
_GET_OUTPUT_STYLES: TypeAdapter[OutputStylesResult] = TypeAdapter(OutputStylesResult)
_GET_PENDING_MESSAGES: TypeAdapter[list[PendingMessage]] = TypeAdapter(list[PendingMessage])
_GET_PLUGIN_CONTENTS: TypeAdapter[PluginContents] = TypeAdapter(PluginContents)
_GET_PLUGIN_DETAILS: TypeAdapter[list[PluginInfo]] = TypeAdapter(list[PluginInfo])
_GET_PROCESSING: TypeAdapter[bool] = TypeAdapter(bool)
_GET_PROJECT_DIR: TypeAdapter[str] = TypeAdapter(str)
_GET_RUN_TIMEOUT: TypeAdapter[int] = TypeAdapter(int)
_GET_SCHEDULED_TASKS: TypeAdapter[list[ScheduledTask]] = TypeAdapter(list[ScheduledTask])
_GET_SESSION_ID: TypeAdapter[str] = TypeAdapter(str)
_GET_SKILL_DEFINITIONS: TypeAdapter[list[SkillDefinition]] = TypeAdapter(list[SkillDefinition])
_GET_SKILL_DETAILS: TypeAdapter[list[SkillInfo]] = TypeAdapter(list[SkillInfo])
_GET_SKILL_NAMES: TypeAdapter[list[str]] = TypeAdapter(list[str])
_GET_SLASH_COMMANDS: TypeAdapter[list[SlashCommand]] = TypeAdapter(list[SlashCommand])
_GET_STATUS: TypeAdapter[StatusUpdate] = TypeAdapter(StatusUpdate)
_GET_TODOS: TypeAdapter[list[TodoItem]] = TypeAdapter(list[TodoItem])
_GET_WORKSPACE_TRUST: TypeAdapter[WorkspaceTrustStatus] = TypeAdapter(WorkspaceTrustStatus)
_INSTALL_PLUGIN: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_LIST_BACKGROUND_PROCESSES: TypeAdapter[list[ProcessRow]] = TypeAdapter(list[ProcessRow])
_LIST_DIRS: TypeAdapter[DirListResult] = TypeAdapter(DirListResult)
_LIST_EXTENSIONS: TypeAdapter[ExtensionListResult] = TypeAdapter(ExtensionListResult)
_LIST_SESSIONS: TypeAdapter[SessionListResult] = TypeAdapter(SessionListResult)
_LIST_WORKFLOWS: TypeAdapter[list[WorkflowListItem]] = TypeAdapter(list[WorkflowListItem])
_LOGIN: TypeAdapter[LoginStarted] = TypeAdapter(LoginStarted)
_LOOP_PAUSE: TypeAdapter[bool] = TypeAdapter(bool)
_LOOP_RESUME: TypeAdapter[str] = TypeAdapter(str)
_LOOP_STATUS: TypeAdapter[LoopStatusSnapshot] = TypeAdapter(LoopStatusSnapshot)
_MCP_CONNECT: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_MCP_DISCONNECT: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_MINT_APPROVER_TOKEN: TypeAdapter[ApproverTokenMinted] = TypeAdapter(ApproverTokenMinted)
_NOTIFICATIONS_COUNTS: TypeAdapter[NotificationCounts] = TypeAdapter(NotificationCounts)
_NOTIFICATIONS_LIST: TypeAdapter[NotificationsListResult] = TypeAdapter(NotificationsListResult)
_NOTIFICATIONS_MARK_READ: TypeAdapter[NotificationsReadResult] = TypeAdapter(
    NotificationsReadResult
)
_PICK_DIR_NATIVE: TypeAdapter[PickDirResult] = TypeAdapter(PickDirResult)
_POP_PENDING_LOOP_ITERATION: TypeAdapter[LoopAdvance | None] = TypeAdapter(LoopAdvance | None)
_PREVIEW_PLUGIN: TypeAdapter[PluginContents] = TypeAdapter(PluginContents)
_PROMOTE_EPHEMERAL_AGENT: TypeAdapter[PromoteEphemeralResult] = TypeAdapter(PromoteEphemeralResult)
_READ_FILE: TypeAdapter[ReadFileResult] = TypeAdapter(ReadFileResult)
_READ_PROCESS_TAIL: TypeAdapter[ProcessTailResult] = TypeAdapter(ProcessTailResult)
_REFRESH_MARKETPLACES: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_RELOAD_CLOUD_CREDENTIALS: TypeAdapter[StatusUpdate] = TypeAdapter(StatusUpdate)
_RELOAD_HOOKS: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_REMOVE_MARKETPLACE: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_REMOVE_PLUGIN: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_REVOKE_APPROVER_TOKENS: TypeAdapter[ApproverTokensRevoked] = TypeAdapter(ApproverTokensRevoked)
_RUN_SHELL: TypeAdapter[RunShellResult] = TypeAdapter(RunShellResult)
_RUN_WORKFLOW: TypeAdapter[WorkflowRunResponse] = TypeAdapter(WorkflowRunResponse)
_SAVE_PERMISSION_RULE: TypeAdapter[None] = TypeAdapter(None)
_SEARCH_CHAT: TypeAdapter[list[ChatSearchHit]] = TypeAdapter(list[ChatSearchHit])
_SEARCH_CODE: TypeAdapter[SearchCodeResult] = TypeAdapter(SearchCodeResult)
_SET_EXTENSION_SETTINGS: TypeAdapter[ExtensionListResult] = TypeAdapter(ExtensionListResult)
_SET_MCP_TOOL_ENABLED: TypeAdapter[McpToolToggleResult] = TypeAdapter(McpToolToggleResult)
_SET_PLUGIN_ENABLED: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_SET_SERVER: TypeAdapter[ServerChoice] = TypeAdapter(ServerChoice)
_SET_WORKSPACE_TRUST: TypeAdapter[WorkspaceTrustStatus] = TypeAdapter(WorkspaceTrustStatus)
_SHUTDOWN: TypeAdapter[None] = TypeAdapter(None)
_START_SCHEDULER: TypeAdapter[None] = TypeAdapter(None)
_STOP_BACKGROUND_PROCESS: TypeAdapter[StopProcessResult] = TypeAdapter(StopProcessResult)
_SWITCH_MODEL: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_SWITCH_SESSION: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_TOGGLE_VERBOSE: TypeAdapter[bool] = TypeAdapter(bool)
_TRUNCATE_HISTORY: TypeAdapter[TruncateHistoryResult] = TypeAdapter(TruncateHistoryResult)
_UPDATE_PLUGIN: TypeAdapter[InfoMessage] = TypeAdapter(InfoMessage)
_UPLOAD_ATTACHMENT: TypeAdapter[UploadAttachmentResult] = TypeAdapter(UploadAttachmentResult)
_WINDOW_MODEL: TypeAdapter[WindowModelResult] = TypeAdapter(WindowModelResult)
_COMMAND: TypeAdapter[CommandResult] = TypeAdapter(CommandResult)


# What each method that is followed causes.
type ApprovePlanEvent = PermissionModeChangedPush | PlanDecidedPush
type AttachSessionEvent = (
    ContentDelta
    | ErrorMessage
    | InfoMessage
    | ModelCompleted
    | ReasoningStarted
    | RequirementDetails
    | RunCompleted
    | RunError
    | RunPaused
    | RunStarted
    | StreamEnd
    | StreamingDone
    | TaskCreated
    | TaskIteration
    | TaskStateUpdated
    | TaskUpdated
    | ToolCompleted
    | ToolError
    | ToolStarted
    | BackgroundProcessDonePush
    | FileEditedPush
    | HttpRetryAttemptPush
    | HttpRetrySucceededPush
    | OrchestrateEventPush
    | PermissionModeChangedPush
    | PlanSubmittedPush
    | ProcessExitedPush
    | ProcessLinePush
    | ProcessStartedPush
    | TodosUpdatedPush
)
type CancelRunEvent = InfoMessage | StreamEnd
type CancelWorkflowEvent = WorkflowEventPush
type ClearCloudCredentialsEvent = NotificationsChangedPush
type DismissPlanEvent = PlanDecidedPush
type DispatchVisualizationActionEvent = VisualizationActionDispatchedPush
type ExecuteScheduledTaskEvent = (
    BackgroundProcessDonePush
    | FileEditedPush
    | HttpRetryAttemptPush
    | HttpRetrySucceededPush
    | OrchestrateEventPush
    | PermissionModeChangedPush
    | PlanSubmittedPush
    | ProcessExitedPush
    | ProcessLinePush
    | ProcessStartedPush
    | TodosUpdatedPush
)
type LoginEvent = LoginResultPush | LoginStatusPush | NotificationsChangedPush
type NotificationsListEvent = NotificationsChangedPush
type NotificationsMarkReadEvent = NotificationsChangedPush
type RunShellEvent = (
    BackgroundProcessDonePush | ProcessExitedPush | ProcessLinePush | ProcessStartedPush
)
type RunWorkflowEvent = WorkflowEventPush
type SetWorkspaceTrustEvent = WorkspaceTrustRequiredPush
type StartSchedulerEvent = (
    SchedulerCompletedPush
    | SchedulerStartedPush
    | BackgroundProcessDonePush
    | FileEditedPush
    | HttpRetryAttemptPush
    | HttpRetrySucceededPush
    | OrchestrateEventPush
    | PermissionModeChangedPush
    | PlanSubmittedPush
    | ProcessExitedPush
    | ProcessLinePush
    | ProcessStartedPush
    | TodosUpdatedPush
)
type StopBackgroundProcessEvent = BackgroundProcessDonePush | ProcessExitedPush | ProcessLinePush
type WindowModelEvent = WindowModelChangedPush

#: Every method a client calls, by wire name: who may call it, how igni
#: answers it, how long it takes, and what it streams.
METHODS: dict[str, MethodSpec] = {
    "add_marketplace": MethodSpec(
        wire="add_marketplace",
        python="igni.marketplaces.add",
        scope="igni",
        access="window",
        reply="message",
        streams=(),
        may_stream=(),
        duration="long",
        timeout_seconds=600,
        correlate=None,
        followed=False,
    ),
    "approve_plan": MethodSpec(
        wire="approve_plan",
        python="session.plan.approve",
        scope="session",
        access="approver",
        reply="rpc_response",
        streams=(
            "push_notification:permission_mode_changed",
            "push_notification:plan_decided",
        ),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=Correlation(by="payload.run_id", source="args.run_id"),
        followed=True,
    ),
    "attach_session": MethodSpec(
        wire="attach_session",
        python="igni.sessions.attach",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(
            "content_delta",
            "error",
            "info",
            "model_completed",
            "reasoning_started",
            "requirement_details",
            "run_completed",
            "run_error",
            "run_paused",
            "run_started",
            "stream_end",
            "streaming_done",
            "task_created",
            "task_iteration",
            "task_state_updated",
            "task_updated",
            "tool_completed",
            "tool_error",
            "tool_started",
        ),
        may_stream=(
            "push_notification:background_process_done",
            "push_notification:file_edited",
            "push_notification:http_retry_attempt",
            "push_notification:http_retry_succeeded",
            "push_notification:orchestrate_event",
            "push_notification:permission_mode_changed",
            "push_notification:plan_submitted",
            "push_notification:process_exited",
            "push_notification:process_line",
            "push_notification:process_started",
            "push_notification:todos_updated",
        ),
        duration="io",
        timeout_seconds=30,
        correlate=Correlation(by="id", source="request.id"),
        followed=True,
    ),
    "cancel_agent_run": MethodSpec(
        wire="cancel_agent_run",
        python="igni.agents.cancel_run",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "cancel_pending_loop": MethodSpec(
        wire="cancel_pending_loop",
        python="session.loop.cancel",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "cancel_run": MethodSpec(
        wire="cancel_run",
        python="session.cancel",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(
            "info",
            "stream_end",
        ),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=Correlation(by="session_id", source="request.session_id"),
        followed=True,
    ),
    "cancel_scheduled_task": MethodSpec(
        wire="cancel_scheduled_task",
        python="session.scheduler.cancel",
        scope="session",
        access="client",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "cancel_workflow": MethodSpec(
        wire="cancel_workflow",
        python="session.workflows.cancel",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=("push_notification:workflow_event",),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=Correlation(by="payload.workflow_run_id", source="args.workflow_run_id"),
        followed=True,
    ),
    "check_for_update": MethodSpec(
        wire="check_for_update",
        python="igni.check_for_update",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="network",
        timeout_seconds=60,
        correlate=None,
        followed=False,
    ),
    "check_permission": MethodSpec(
        wire="check_permission",
        python="session.permissions.check",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "clear_cloud_credentials": MethodSpec(
        wire="clear_cloud_credentials",
        python="session.auth.sign_out",
        scope="session",
        access="window",
        reply="message",
        streams=("push_notification:notifications_changed",),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=Correlation(by="payload.cause", equals="signed_out"),
        followed=True,
    ),
    "compact_if_needed": MethodSpec(
        wire="compact_if_needed",
        python="session.context.compact",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="long",
        timeout_seconds=600,
        correlate=None,
        followed=False,
    ),
    "complete_files": MethodSpec(
        wire="complete_files",
        python="session.files.complete",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "count_context_tokens": MethodSpec(
        wire="count_context_tokens",
        python="session.context.tokens",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "discard_ephemeral_agent": MethodSpec(
        wire="discard_ephemeral_agent",
        python="session.agents.discard",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "discard_interrupted_run": MethodSpec(
        wire="discard_interrupted_run",
        python="session.runs.discard_interrupted",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "discover_server": MethodSpec(
        wire="discover_server",
        python="igni.auth.discover_server",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="network",
        timeout_seconds=60,
        correlate=None,
        followed=False,
    ),
    "dismiss_plan": MethodSpec(
        wire="dismiss_plan",
        python="session.plan.dismiss",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=("push_notification:plan_decided",),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=Correlation(by="payload.run_id", source="args.run_id"),
        followed=True,
    ),
    "dispatch_visualization_action": MethodSpec(
        wire="dispatch_visualization_action",
        python="session.visualization_action",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=("push_notification:visualization_action_dispatched",),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=Correlation(by="payload.action", source="args.action"),
        followed=True,
    ),
    "ensure_mcp": MethodSpec(
        wire="ensure_mcp",
        python="session.mcp.ensure",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="long",
        timeout_seconds=600,
        correlate=None,
        followed=False,
    ),
    "execute_scheduled_task": MethodSpec(
        wire="execute_scheduled_task",
        python="session.scheduler.execute",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(
            "push_notification:background_process_done",
            "push_notification:file_edited",
            "push_notification:http_retry_attempt",
            "push_notification:http_retry_succeeded",
            "push_notification:orchestrate_event",
            "push_notification:permission_mode_changed",
            "push_notification:plan_submitted",
            "push_notification:process_exited",
            "push_notification:process_line",
            "push_notification:process_started",
            "push_notification:todos_updated",
        ),
        duration="long",
        timeout_seconds=600,
        correlate=Correlation(by="run_id", source="result.run_id"),
        followed=True,
    ),
    "extract_learnings": MethodSpec(
        wire="extract_learnings",
        python="session.extract_learnings",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "fire_session_start_hook": MethodSpec(
        wire="fire_session_start_hook",
        python="session.fire_session_start_hook",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="long",
        timeout_seconds=600,
        correlate=None,
        followed=False,
    ),
    "get_agent_details": MethodSpec(
        wire="get_agent_details",
        python="session.agents.list",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_chat_history": MethodSpec(
        wire="get_chat_history",
        python="session.history.get",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "get_cloud_plan": MethodSpec(
        wire="get_cloud_plan",
        python="session.auth.plan",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="network",
        timeout_seconds=60,
        correlate=None,
        followed=False,
    ),
    "get_context_breakdown": MethodSpec(
        wire="get_context_breakdown",
        python="session.context.breakdown",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "get_display_config": MethodSpec(
        wire="get_display_config",
        python="session.display_config",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_group_policy": MethodSpec(
        wire="get_group_policy",
        python="igni.group_policy",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "get_hooks_details": MethodSpec(
        wire="get_hooks_details",
        python="session.hooks.list",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_interrupted_runs": MethodSpec(
        wire="get_interrupted_runs",
        python="session.runs.interrupted",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "get_latest_plan": MethodSpec(
        wire="get_latest_plan",
        python="session.plan.latest",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_marketplaces": MethodSpec(
        wire="get_marketplaces",
        python="igni.marketplaces.list",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "get_mcp_server_details": MethodSpec(
        wire="get_mcp_server_details",
        python="session.mcp.server_details",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="network",
        timeout_seconds=60,
        correlate=None,
        followed=False,
    ),
    "get_mcp_servers": MethodSpec(
        wire="get_mcp_servers",
        python="session.mcp.servers",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_mcp_status": MethodSpec(
        wire="get_mcp_status",
        python="session.mcp.status",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_model_registry": MethodSpec(
        wire="get_model_registry",
        python="session.models.list",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_output_styles": MethodSpec(
        wire="get_output_styles",
        python="session.output_styles",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_pending_messages": MethodSpec(
        wire="get_pending_messages",
        python="session.runs.pending_messages",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "get_plugin_contents": MethodSpec(
        wire="get_plugin_contents",
        python="session.plugins.contents",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "get_plugin_details": MethodSpec(
        wire="get_plugin_details",
        python="session.plugins.list",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "get_processing": MethodSpec(
        wire="get_processing",
        python="session.is_processing",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_project_dir": MethodSpec(
        wire="get_project_dir",
        python="session.get_project_dir",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_run_timeout": MethodSpec(
        wire="get_run_timeout",
        python="session.run_timeout",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_scheduled_tasks": MethodSpec(
        wire="get_scheduled_tasks",
        python="session.scheduler.list",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "get_session_id": MethodSpec(
        wire="get_session_id",
        python="session.current_id",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_skill_definitions": MethodSpec(
        wire="get_skill_definitions",
        python="session.skills.definitions",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_skill_details": MethodSpec(
        wire="get_skill_details",
        python="session.skills.list",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_skill_names": MethodSpec(
        wire="get_skill_names",
        python="session.skills.names",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_slash_commands": MethodSpec(
        wire="get_slash_commands",
        python="session.slash_commands",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_status": MethodSpec(
        wire="get_status",
        python="session.status",
        scope="session",
        access="client",
        reply="message",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_todos": MethodSpec(
        wire="get_todos",
        python="session.todos",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "get_workspace_trust": MethodSpec(
        wire="get_workspace_trust",
        python="session.workspace.trust",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "install_plugin": MethodSpec(
        wire="install_plugin",
        python="session.plugins.install",
        scope="session",
        access="window",
        reply="message",
        streams=(),
        may_stream=(),
        duration="long",
        timeout_seconds=600,
        correlate=None,
        followed=False,
    ),
    "list_background_processes": MethodSpec(
        wire="list_background_processes",
        python="igni.processes.list",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "list_dirs": MethodSpec(
        wire="list_dirs",
        python="igni.files.list_dirs",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "list_extensions": MethodSpec(
        wire="list_extensions",
        python="igni.extensions.list",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "list_sessions": MethodSpec(
        wire="list_sessions",
        python="session.list_sessions",
        scope="session",
        access="client",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "list_workflows": MethodSpec(
        wire="list_workflows",
        python="session.workflows.list",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "login": MethodSpec(
        wire="login",
        python="igni.auth.login",
        scope="igni",
        access="window",
        reply="rpc_response",
        streams=(
            "push_notification:login_result",
            "push_notification:login_status",
            "push_notification:notifications_changed",
        ),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=Correlation(by="payload.flow_id", source="result.flow_id"),
        followed=True,
    ),
    "loop_pause": MethodSpec(
        wire="loop_pause",
        python="session.loop.pause",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "loop_resume": MethodSpec(
        wire="loop_resume",
        python="session.loop.resume",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "loop_status": MethodSpec(
        wire="loop_status",
        python="session.loop.status",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "mcp_connect": MethodSpec(
        wire="mcp_connect",
        python="session.mcp.connect",
        scope="session",
        access="client",
        reply="message",
        streams=(),
        may_stream=(),
        duration="network",
        timeout_seconds=60,
        correlate=None,
        followed=False,
    ),
    "mcp_disconnect": MethodSpec(
        wire="mcp_disconnect",
        python="session.mcp.disconnect",
        scope="session",
        access="client",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "mint_approver_token": MethodSpec(
        wire="mint_approver_token",
        python="igni.approvers.mint_token",
        scope="igni",
        access="window",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "notifications_counts": MethodSpec(
        wire="notifications_counts",
        python="igni.notifications.counts",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "notifications_list": MethodSpec(
        wire="notifications_list",
        python="igni.notifications.list",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=("push_notification:notifications_changed",),
        may_stream=(),
        duration="network",
        timeout_seconds=60,
        correlate=Correlation(by="payload.cause", equals="listed"),
        followed=True,
    ),
    "notifications_mark_read": MethodSpec(
        wire="notifications_mark_read",
        python="igni.notifications.mark_read",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=("push_notification:notifications_changed",),
        may_stream=(),
        duration="network",
        timeout_seconds=60,
        correlate=Correlation(by="payload.cause", equals="marked_read"),
        followed=True,
    ),
    "pick_dir_native": MethodSpec(
        wire="pick_dir_native",
        python="session.files.pick_dir",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="person",
        timeout_seconds=None,
        correlate=None,
        followed=False,
    ),
    "pop_pending_loop_iteration": MethodSpec(
        wire="pop_pending_loop_iteration",
        python="session.loop.next_iteration",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "preview_plugin": MethodSpec(
        wire="preview_plugin",
        python="session.plugins.preview",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="long",
        timeout_seconds=600,
        correlate=None,
        followed=False,
    ),
    "promote_ephemeral_agent": MethodSpec(
        wire="promote_ephemeral_agent",
        python="session.agents.promote",
        scope="session",
        access="window",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "read_file": MethodSpec(
        wire="read_file",
        python="session.files.read",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "read_process_tail": MethodSpec(
        wire="read_process_tail",
        python="igni.processes.tail",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "refresh_marketplaces": MethodSpec(
        wire="refresh_marketplaces",
        python="igni.marketplaces.refresh",
        scope="igni",
        access="client",
        reply="message",
        streams=(),
        may_stream=(),
        duration="long",
        timeout_seconds=600,
        correlate=None,
        followed=False,
    ),
    "reload_cloud_credentials": MethodSpec(
        wire="reload_cloud_credentials",
        python="session.auth.reload_credentials",
        scope="session",
        access="window",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "reload_hooks": MethodSpec(
        wire="reload_hooks",
        python="session.hooks.reload",
        scope="session",
        access="client",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "remove_marketplace": MethodSpec(
        wire="remove_marketplace",
        python="igni.marketplaces.remove",
        scope="igni",
        access="window",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "remove_plugin": MethodSpec(
        wire="remove_plugin",
        python="session.plugins.remove",
        scope="session",
        access="window",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "revoke_approver_tokens": MethodSpec(
        wire="revoke_approver_tokens",
        python="igni.approvers.revoke_tokens",
        scope="igni",
        access="window",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "run_shell": MethodSpec(
        wire="run_shell",
        python="session.run_shell",
        scope="session",
        access="window",
        reply="rpc_response",
        streams=(
            "push_notification:background_process_done",
            "push_notification:process_exited",
            "push_notification:process_line",
            "push_notification:process_started",
        ),
        may_stream=(),
        duration="long",
        timeout_seconds=600,
        correlate=Correlation(by="payload.pid", source="result.pid"),
        followed=True,
    ),
    "run_workflow": MethodSpec(
        wire="run_workflow",
        python="session.workflows.run",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=("push_notification:workflow_event",),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=Correlation(by="payload.workflow_run_id", source="result.workflow_run_id"),
        followed=True,
    ),
    "save_permission_rule": MethodSpec(
        wire="save_permission_rule",
        python="session.permissions.save_rule",
        scope="session",
        access="window",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "search_chat": MethodSpec(
        wire="search_chat",
        python="session.history.search",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "search_code": MethodSpec(
        wire="search_code",
        python="session.files.search",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "set_extension_settings": MethodSpec(
        wire="set_extension_settings",
        python="igni.extensions.set_settings",
        scope="igni",
        access="window",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "set_mcp_tool_enabled": MethodSpec(
        wire="set_mcp_tool_enabled",
        python="session.mcp.set_tool_enabled",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "set_plugin_enabled": MethodSpec(
        wire="set_plugin_enabled",
        python="session.plugins.set_enabled",
        scope="session",
        access="window",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "set_server": MethodSpec(
        wire="set_server",
        python="igni.auth.set_server",
        scope="igni",
        access="window",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "set_workspace_trust": MethodSpec(
        wire="set_workspace_trust",
        python="session.workspace.set_trust",
        scope="session",
        access="window",
        reply="rpc_response",
        streams=("push_notification:workspace_trust_required",),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=Correlation(by="payload.path", source="result.path"),
        followed=True,
    ),
    "shutdown": MethodSpec(
        wire="shutdown",
        python="session.shutdown",
        scope="session",
        access="window",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "start_scheduler": MethodSpec(
        wire="start_scheduler",
        python="session.scheduler.start",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(
            "push_notification:scheduler_completed",
            "push_notification:scheduler_started",
        ),
        may_stream=(
            "push_notification:background_process_done",
            "push_notification:file_edited",
            "push_notification:http_retry_attempt",
            "push_notification:http_retry_succeeded",
            "push_notification:orchestrate_event",
            "push_notification:permission_mode_changed",
            "push_notification:plan_submitted",
            "push_notification:process_exited",
            "push_notification:process_line",
            "push_notification:process_started",
            "push_notification:todos_updated",
        ),
        duration="io",
        timeout_seconds=30,
        correlate=Correlation(by="channel"),
        followed=True,
    ),
    "stop_background_process": MethodSpec(
        wire="stop_background_process",
        python="igni.processes.stop",
        scope="igni",
        access="client",
        reply="rpc_response",
        streams=(
            "push_notification:background_process_done",
            "push_notification:process_exited",
            "push_notification:process_line",
        ),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=Correlation(by="payload.pid", source="args.pid"),
        followed=True,
    ),
    "switch_model": MethodSpec(
        wire="switch_model",
        python="session.models.switch",
        scope="session",
        access="client",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "switch_session": MethodSpec(
        wire="switch_session",
        python="session.switch",
        scope="session",
        access="client",
        reply="message",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "toggle_verbose": MethodSpec(
        wire="toggle_verbose",
        python="session.toggle_verbose",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=None,
        followed=False,
    ),
    "truncate_history": MethodSpec(
        wire="truncate_history",
        python="session.history.truncate",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "update_plugin": MethodSpec(
        wire="update_plugin",
        python="session.plugins.update",
        scope="session",
        access="window",
        reply="message",
        streams=(),
        may_stream=(),
        duration="long",
        timeout_seconds=600,
        correlate=None,
        followed=False,
    ),
    "upload_attachment": MethodSpec(
        wire="upload_attachment",
        python="session.upload_attachment",
        scope="session",
        access="client",
        reply="rpc_response",
        streams=(),
        may_stream=(),
        duration="io",
        timeout_seconds=30,
        correlate=None,
        followed=False,
    ),
    "window_model": MethodSpec(
        wire="window_model",
        python="igni.window.model",
        scope="igni",
        access="window",
        reply="rpc_response",
        streams=("push_notification:window_model_changed",),
        may_stream=(),
        duration="instant",
        timeout_seconds=10,
        correlate=Correlation(by="payload.token", source="args.token"),
        followed=True,
    ),
}

#: igni's methods a client never calls, and why.
NOT_FOR_CLIENTS: dict[str, str] = {
    "deliver_service_events": "the platform's call: Fleet delivers an extension service's events on its own control connection",
    "extension_service_token": "an extension page's call: it hands the page its service's token, and only igni's window speaks for a page",
    "host_model": "an extension page's call: igni's window makes it for the page it hosts, setting `caller`, which igni honours from no other connection",
    "vm_sign_in": "the platform's call: Fleet signs a VM's igni in on its control connection",
}

#: Methods that stream, but whose events igni gives a client nothing to
#: tell apart from another call's: they return their result only.
UNFOLLOWED: dict[str, str] = {}


class IgniAgents:
    """Sub-agents' runs, wherever they are going."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def cancel_run(self, run_id: str = "") -> CancelAgentRunResult:
        """Stop one sub-agent's run, leaving the rest of the turn going.

        `run_id` is the sub-agent run's id, as its events carry it.
        Returns `ok: true` when the run was cancelled, or `ok: false`
        with `error` when `run_id` is empty, no such run is running, or
        the cancellation failed.
        """
        return await self._caller.rpc(
            "cancel_agent_run", AgentRunArgs, {"run_id": run_id}, _CANCEL_AGENT_RUN
        )


class IgniApprovers:
    """Approver tokens: what lets a program answer approval requests."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def mint_token(self) -> ApproverTokenMinted:
        """Make a token that lets a program answer the agent's approval requests.

        Takes no arguments. Returns `token`: a program that connects with it
        stands as an approver — it may answer approval requests and approve a
        plan, once each time, but saves no rule and changes no permission mode.
        The token lives in memory until igni exits or the tokens are revoked,
        and is sent only to the connection that asked.

        Fails when this igni's transport takes no token at all, so every
        connection may already answer approval requests.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc("mint_approver_token", NoArgs, {}, _MINT_APPROVER_TOKEN)

    async def revoke_tokens(self) -> ApproverTokensRevoked:
        """Forget every approver token, so no program answers approval requests any more.

        Takes no arguments. Returns `revoked`: how many tokens were
        forgotten (`0` when there were none, or when this igni takes no
        token). Connections that attached with a revoked token lose their
        approver standing.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc("revoke_approver_tokens", NoArgs, {}, _REVOKE_APPROVER_TOKENS)


class IgniAuth:
    """Signing igni in to igni server, and choosing which server."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def cancel_login(self) -> None:
        """Cancel the sign-in to igni server that ``igni.auth.login()`` started.

        igni answers nothing; the sign-in's ``login_result`` push says it ended.

        Sent as igni's ``cancel_login`` message.
        """
        await self._caller.send(CancelLogin, {})

    async def discover_server(self, email: str) -> ServerFound:
        """Find the igni server an email address's organisation runs.

        `email` is the person's work address. igni reads the record the
        organisation publishes on the address's domain (a well-known URL,
        then DNS) and changes nothing. Returns `api_url` and `portal_url`,
        with `source` saying where they were found; when nothing usable
        was found both are empty and `reason` says why.
        """
        return await self._caller.rpc(
            "discover_server", DiscoverServerArgs, {"email": email}, _DISCOVER_SERVER
        )

    def login(self) -> Call[LoginStarted, LoginEvent]:
        """Start signing in to igni server through the person's browser.

        Takes no arguments, and answers at once with `started: true`; a
        sign-in already in progress is cancelled first. The sign-in itself
        goes on in the background: `login_status` pushes say what it is
        doing (the local callback server starting, the URL to open, the
        account being read), and one `login_result` push ends it, with
        `success` and, in `result`, the signed-in email or the reason it
        failed. On success the person's notifications are read and
        `notifications_changed` follows.

        ``async with`` the call to follow it: it yields the ``login_status`` pushes and ends with the ``login_result`` one. igni signs in one way at a time — a new ``login`` cancels the one going — so these are the sign-in igni is doing.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return self._caller.follow("login", NoArgs, {}, _LOGIN)

    async def set_server(self, api_url: str, *, portal_url: str = "") -> ServerChoice:
        """Choose the igni server to sign in to, and remember it for the next launch.

        `api_url` is the server's API address (`https` only);
        `portal_url` its portal, empty to derive it from `api_url`.
        Returns the server as stored, or, when the choice is refused (an
        empty or non-`https` address), `error` saying why and nothing
        stored. Fails when the user configuration file cannot be read or
        written.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "set_server", SetServerArgs, {"api_url": api_url, "portal_url": portal_url}, _SET_SERVER
        )


class IgniExtensions:
    """The extensions installed into this igni, and their settings."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def list(self) -> ExtensionListResult:
        """List the installed extensions, including the ones that failed to start.

        Takes no arguments. Returns each extension's id, name, version and
        `state` — a failed one with its `reason`, rather than left out —
        with what it adds to igni's window (pages, menu items, indicators),
        its settings and their values, and the addresses of its UI, its web
        home and its service.
        """
        return await self._caller.rpc("list_extensions", NoArgs, {}, _LIST_EXTENSIONS)

    async def set_settings(
        self, *, extension_id: str, values: dict[str, JsonValue]
    ) -> ExtensionListResult:
        """Change an installed extension's settings.

        `extension_id` is the extension; `values` the settings to
        change, by key, merged over what is stored. The extension reads them
        the next time it starts. Returns the whole list, as
        `list_extensions` does. Fails when the extension is not
        installed, a key is not one of its settings, a value is not one of
        a setting's options, or igni has no extension support.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "set_extension_settings",
            SetExtensionSettingsArgs,
            {"extension_id": extension_id, "values": values},
            _SET_EXTENSION_SETTINGS,
        )


class IgniFiles:
    """Folders on the machine igni runs on."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def list_dirs(
        self, *, path: str | None = None, show_hidden: bool = False
    ) -> DirListResult:
        """List the folders inside a folder on igni's machine, for picking a project.

        `path` is the folder to list (the home folder when absent or
        empty); `show_hidden` includes folders whose names start with a
        dot. Returns the resolved `path`, its `parent` (empty at the
        root), the folder names in it (`dirs`, sorted), the home folder,
        and `error` when it could not be read.
        """
        return await self._caller.rpc(
            "list_dirs", ListDirsArgs, {"path": path, "show_hidden": show_hidden}, _LIST_DIRS
        )


class IgniMarketplaces:
    """Plugin marketplaces: where plugins are installed from."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def add(self, url: str) -> InfoMessage:
        """Add a plugin marketplace and read its catalogue.

        `url` is the marketplace's git URL. Returns an `info` message,
        sent in place of an `rpc_response`, whose text says how many
        plugins it catalogues — or why it was not added: the
        organisation's policy, a git error, an unreadable catalogue.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "add_marketplace", MarketplaceUrlArgs, {"url": url}, _ADD_MARKETPLACE
        )

    async def list(self) -> builtins.list[MarketplaceInfo]:
        """List the plugin marketplaces igni knows, with their catalogues.

        Takes no arguments. Returns each marketplace's name, URL, when it
        was last fetched, and the plugins it offers.
        """
        return await self._caller.rpc("get_marketplaces", NoArgs, {}, _GET_MARKETPLACES)

    async def refresh(self, name: str | None = None) -> InfoMessage:
        """Fetch marketplaces' catalogues again.

        `name` is one marketplace; absent or empty refreshes every one.
        Returns an `info` message, sent in place of an `rpc_response`,
        whose text says what was refreshed, or why not.
        """
        return await self._caller.rpc(
            "refresh_marketplaces", RefreshMarketplacesArgs, {"name": name}, _REFRESH_MARKETPLACES
        )

    async def remove(self, name: str) -> InfoMessage:
        """Forget a plugin marketplace.

        `name` is the marketplace. Returns an `info` message, sent in
        place of an `rpc_response`, whose text says it was removed, or
        that there is no such marketplace.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "remove_marketplace", MarketplaceNameArgs, {"name": name}, _REMOVE_MARKETPLACE
        )


class IgniNotifications:
    """The signed-in person's notifications, and what extensions posted."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def counts(self) -> NotificationCounts:
        """Count the person's unread notifications, in all and per extension.

        Takes no arguments. Answers from what was last read, asking nobody;
        `notifications_changed` pushes the counts whenever they move.
        """
        return await self._caller.rpc("notifications_counts", NoArgs, {}, _NOTIFICATIONS_COUNTS)

    def list(self) -> Call[NotificationsListResult, NotificationsListEvent]:
        """List the signed-in person's notifications, newest first.

        Takes no arguments. Reads igni server again and merges in what
        extensions on this machine posted. Returns at most 100
        `notifications` (each with its source, title, body, target and
        whether it is read), the unread `counts` in all and per
        extension, and `server_error` when igni server could not be
        read. The fresh counts are also pushed as `notifications_changed`.

        ``async with`` the call to follow it: it yields the ``notifications_changed`` push that says the list was read, and ends with the answer.
        """
        return self._caller.follow("notifications_list", NoArgs, {}, _NOTIFICATIONS_LIST)

    def mark_read(
        self, *, ids: builtins.list[str] | None = None, source: str | None = None
    ) -> Call[NotificationsReadResult, NotificationsMarkReadEvent]:
        """Mark notifications read.

        `ids` names the notifications; `source` (an extension id) marks
        all of that extension's; neither marks every notification. Returns
        the unread `counts` afterwards, also pushed as
        `notifications_changed`, and `server_error` when igni server
        could not be told.

        ``async with`` the call to follow it: it yields the ``notifications_changed`` push that says the notifications were marked read, and ends with the answer.
        """
        return self._caller.follow(
            "notifications_mark_read",
            MarkReadArgs,
            {"ids": ids, "source": source},
            _NOTIFICATIONS_MARK_READ,
        )


class IgniProcesses:
    """Background processes igni tracks, in every session."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def list(self) -> builtins.list[ProcessRow]:
        """List the background processes igni is tracking, in every session.

        Takes no arguments. Returns each process's `pid`, command, how
        long it has run, whether it is still running, and its exit code
        once it has ended.
        """
        return await self._caller.rpc(
            "list_background_processes", NoArgs, {}, _LIST_BACKGROUND_PROCESSES
        )

    def stop(self, pid: int) -> Call[StopProcessResult, StopBackgroundProcessEvent]:
        """Stop a background process.

        `pid` is the process. Returns `killed: true` once it was told to
        stop — its last lines, `process_exited` and
        `background_process_done` follow — or `killed: false` with a
        `message` when igni is not tracking it or it had already ended.

        ``async with`` the call to follow it: it yields the ``process_line``, ``process_exited`` and ``background_process_done`` pushes of ``pid`` and ends with ``background_process_done``, or with the answer when ``killed`` is false.
        """
        return self._caller.follow(
            "stop_background_process", ProcessArgs, {"pid": pid}, _STOP_BACKGROUND_PROCESS
        )

    async def tail(self, pid: int, *, tail: int = 200) -> ProcessTailResult:
        """Read the last lines a background process printed.

        `pid` is the process; `tail` how many lines (default 200).
        Returns its `output`, whether it `is_running`, and its
        `exit_code` once it has ended. An unknown `pid` answers empty
        output, not running.
        """
        return await self._caller.rpc(
            "read_process_tail", ProcessTailArgs, {"pid": pid, "tail": tail}, _READ_PROCESS_TAIL
        )


class IgniSessions:
    """igni's sessions: attach one, or make a new one in a project folder.

    The generated base of ``igni_client.sessions.Sessions``, which is ``igni.sessions``.
    """

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    def attach(
        self, *, project_dir: str = "", session_id: str = ""
    ) -> Call[AttachSessionResult, AttachSessionEvent]:
        """Bind to a session — an existing one, or a new one in a project folder.

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
        streams as any run does. Each of those messages carries this
        request's `id`, and a `stream_end` of that `id` ends them.

        Fails when `project_dir` is not a directory, or the session belongs
        to another project folder — an attach never moves a session.

        ``async with`` the call to follow it: it yields the approvals the session is still waiting for and the run it continues again — every message of them carries the attach's own request id — and ends with the ``stream_end`` that closes them.
        """
        return self._caller.follow(
            "attach_session",
            AttachSessionParams,
            {"project_dir": project_dir, "session_id": session_id},
            _ATTACH_SESSION,
        )


class IgniWindow:
    """igni's own window's model — its fields, toasts and dialog."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    def model(
        self,
        *,
        op: Literal["hydrate", "write", "toast", "dismiss_toast", "open_dialog", "answer_dialog"],
        window: str,
        connection_id: str = "",
        dialog_id: str = "",
        field: str = "",
        kind: str = "",
        token: str = "",
        value: JsonValue = None,
    ) -> Call[WindowModelResult, WindowModelEvent]:
        """Read or change the calling window's own model: its fields, toasts and dialog.

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

        ``async with`` the call to follow it: it yields the ``window_model_changed`` push that carries this change, and ends with the answer. The change's token is the one given; igni-client makes one when the caller does not, so the push can be told from another window's.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return self._caller.follow(
            "window_model",
            WindowModelArgs,
            {
                "connection_id": connection_id,
                "dialog_id": dialog_id,
                "field": field,
                "kind": kind,
                "op": op,
                "token": token or self._caller.new_id("change"),
                "value": value,
                "window": window,
            },
            _WINDOW_MODEL,
        )


class SessionAgents:
    """The agents this session can hand work to."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def discard(self, name: str) -> DiscardEphemeralResult:
        """Delete an agent made during this session.

        `name` is the ephemeral agent. Returns `ok` with its `name`;
        or `ok: false` with `reason` when it is unknown or not
        ephemeral.
        """
        return await self._caller.rpc(
            "discard_ephemeral_agent", AgentNameArgs, {"name": name}, _DISCARD_EPHEMERAL_AGENT
        )

    async def list(self) -> builtins.list[AgentInfo]:
        """List the agents this session can hand work to.

        Takes no arguments. Returns each agent's name, description, tools,
        model, MCP servers, tags, system prompt, where it was defined, and
        whether it is ephemeral (made during this session, not yet saved).
        """
        return await self._caller.rpc("get_agent_details", NoArgs, {}, _GET_AGENT_DETAILS)

    async def promote(self, name: str, *, target: str | None = None) -> PromoteEphemeralResult:
        """Keep an agent made during this session, as a project or personal agent.

        `name` is the ephemeral agent; `target` is `project` (the
        default: the project's agents) or `personal` (the person's own).
        Returns `ok` with the agent's `name` and where it was saved
        (`dest`); or `ok: false` with `reason` when the agent is
        unknown, not ephemeral, or the destination exists.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "promote_ephemeral_agent",
            PromoteAgentArgs,
            {"name": name, "target": target},
            _PROMOTE_EPHEMERAL_AGENT,
        )


class SessionAuth:
    """This session's sign-in to igni server."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def plan(self) -> CloudPlan | None:
        """Read who is signed in to igni server, and their organisation's plan.

        Takes no arguments. Asks igni server with this session's sign-in and
        returns the person's `email` and `full_name`, the organisation's
        display name (`org_name`) and plan `tier`; any of them may be
        null when igni server does not say. Returns `null` when nobody is
        signed in or igni server could not be asked.
        """
        return await self._caller.rpc("get_cloud_plan", NoArgs, {}, _GET_CLOUD_PLAN)

    async def reload_credentials(self) -> StatusUpdate:
        """Read the saved sign-in again, so this session acts as whoever is signed in now.

        Takes no arguments. Use it after a sign-in made elsewhere (another
        session, another window). Returns the session's status afterwards —
        model, cloud connection, account, context size, permission mode — as
        a `status_update` message, sent in place of an `rpc_response`.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "reload_cloud_credentials", NoArgs, {}, _RELOAD_CLOUD_CREDENTIALS
        )

    def sign_out(self) -> Call[StatusUpdate, ClearCloudCredentialsEvent]:
        """Sign this session out of igni server.

        Takes no arguments. The session forgets its cloud credentials, and
        the signed-in person's notifications stop arriving and leave the
        badges (`notifications_changed`). Returns the session's status
        afterwards as a `status_update` message, sent in place of an
        `rpc_response`.

        ``async with`` the call to follow it: it yields the ``notifications_changed`` push that says the person signed out, and ends with the answer — the session's status.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return self._caller.follow("clear_cloud_credentials", NoArgs, {}, _CLEAR_CLOUD_CREDENTIALS)


class SessionContext:
    """This session's context window: how full it is, and compacting it."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def breakdown(self) -> ContextBreakdown:
        """Split this session's context into what compaction can shrink and what it cannot.

        Takes no arguments. Returns the `total` tokens, the part taken by
        the conversation's runs (`runs`, which `/compact` can shrink),
        and the `floor` — instructions, tools and the rest that stays.
        Zeros when it cannot be measured.
        """
        return await self._caller.rpc("get_context_breakdown", NoArgs, {}, _GET_CONTEXT_BREAKDOWN)

    async def compact(self, *, ctx_tokens: int, max_ctx: int) -> CompactionOutcome:
        """Compact this session's conversation when its context is nearly full.

        `ctx_tokens` is the context the last turn used and `max_ctx`
        the model's window; at 80% or more the conversation is summarised
        and replaced by the summary (the `PreCompact` hooks may refuse).
        Returns `compacted` and, when it was, the `summary`.
        """
        return await self._caller.rpc(
            "compact_if_needed",
            CompactIfNeededArgs,
            {"ctx_tokens": ctx_tokens, "max_ctx": max_ctx},
            _COMPACT_IF_NEEDED,
        )

    async def tokens(self) -> int:
        """Estimate how many tokens this session's conversation takes up.

        Takes no arguments. Returns the estimate (`0` when it cannot be
        read); a positive estimate also becomes the context size
        `get_status` reports.
        """
        return await self._caller.rpc("count_context_tokens", NoArgs, {}, _COUNT_CONTEXT_TOKENS)


class SessionFiles:
    """Files in this session's project folder."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def complete(self, *, limit: int = 50, query: str = "") -> FileCompletion:
        """Complete a file path typed after `@`, from this session's project.

        `query` is what was typed so far (empty matches everything);
        `limit` caps the matches returned (default 50). Returns the
        matching project-relative paths, best first, and `total`: how
        many matched before the cap. The project's file list is read once
        per session.
        """
        return await self._caller.rpc(
            "complete_files", CompleteFilesArgs, {"limit": limit, "query": query}, _COMPLETE_FILES
        )

    async def pick_dir(self, start: str | None = None) -> PickDirResult:
        """Open the operating system's folder picker on igni's machine and return the choice.

        `start` is the folder the picker opens in (this session's project
        when absent or empty). igni runs on the person's machine, so the
        dialog appears on their desktop; it waits as long as they take, so
        give the call a long timeout. Returns the chosen `path`, or
        `cancelled`, or `error` when no native dialog is available.
        """
        return await self._caller.rpc(
            "pick_dir_native", PickDirArgs, {"start": start}, _PICK_DIR_NATIVE
        )

    async def read(self, path: str) -> ReadFileResult:
        """Read a file for preview: one of this session's project, igni's data, or an attachment.

        `path` is relative to the project, absolute, or an
        `attachment:<id>` reference. Returns the resolved `path`, its
        `contents` and `size`, and a `language` hint for highlighting;
        or `error` when the file is missing, a directory, too large to
        preview (256 KiB), unreadable, or outside the folders igni lets a
        client read.
        """
        return await self._caller.rpc("read_file", ReadFileArgs, {"path": path}, _READ_FILE)

    async def search(self, query: str) -> SearchCodeResult:
        """Find where a snippet of code appears in this session's project.

        `query` is the snippet, matched exactly; one shorter than five
        characters finds nothing. Returns up to 20 `matches` (path, first
        and last line, a preview), `truncated` when there may be more or
        the search timed out, and `error` when it failed.
        """
        return await self._caller.rpc("search_code", SearchCodeArgs, {"query": query}, _SEARCH_CODE)


class SessionHistory:
    """This session's conversation as stored: read, search, cut back."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def get(self) -> list[ChatTurn]:
        """Read a session's conversation, turn by turn, as a client draws it.

        `session_id` names the session. Returns the conversation in
        order, one entry per item, told apart by `role`: the person's
        message (`user`), the agent's answer (`assistant`), its
        reasoning (`thinking`), a tool call and its result (`tool`), a
        submitted plan (`plan`), a run's token counts (`stats`), and a
        view the agent drew (`visualization`). Sub-agents' runs are left
        out.
        """
        return await self._caller.rpc(
            "get_chat_history",
            SessionIdArgs,
            {"session_id": self._caller.session_id},
            _GET_CHAT_HISTORY,
        )

    async def search(self, query: str, *, limit: int = 50) -> list[ChatSearchHit]:
        """Find text in a session's conversation.

        `session_id` names the session; `query` is the text to find
        (case-insensitive; blank finds nothing); `limit` caps the hits
        (default 50). Returns one hit per match, in conversation order:
        its index in `get_chat_history`, its role and run, a snippet
        around it, and where the match sits in the snippet.
        """
        return await self._caller.rpc(
            "search_chat",
            SearchChatArgs,
            {"limit": limit, "query": query, "session_id": self._caller.session_id},
            _SEARCH_CHAT,
        )

    async def truncate(self, run_id: str) -> TruncateHistoryResult:
        """Drop a run from a session's history, with every run after it.

        `session_id` names the session; `run_id` the first run to drop
        (a top-level run, as `get_chat_history` carries it). Use it to
        edit and resend a message. Returns how many runs were `removed`,
        or `error` when the session or the run is not found or the
        history could not be saved.
        """
        return await self._caller.rpc(
            "truncate_history",
            TruncateHistoryArgs,
            {"run_id": run_id, "session_id": self._caller.session_id},
            _TRUNCATE_HISTORY,
        )


class SessionHooks:
    """The hooks that run on this session's events."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def list(self) -> builtins.list[HookEntryView]:
        """List the hooks this session runs.

        Takes no arguments. Returns one row per hook: the `event` it runs
        on, its `type` (a shell `command` or an HTTP `url`), the
        `matcher` that narrows it, its timeout, whether it runs in the
        background, and the HTTP headers it sends.
        """
        return await self._caller.rpc("get_hooks_details", NoArgs, {}, _GET_HOOKS_DETAILS)

    async def reload(self) -> InfoMessage:
        """Read this session's hook configuration again.

        Takes no arguments. Returns an `info` message, sent in place of an
        `rpc_response`, saying how many hooks are now active.
        """
        return await self._caller.rpc("reload_hooks", NoArgs, {}, _RELOAD_HOOKS)


class SessionLoop:
    """This session's loop: a task the agent repeats until it is done."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def cancel(self) -> bool:
        """End this session's running `/loop`.

        Takes no arguments. Returns `true` when a loop was ended;
        `false` when there was none or it is paused (a paused loop is
        resumed or left alone, not cancelled).
        """
        return await self._caller.rpc("cancel_pending_loop", NoArgs, {}, _CANCEL_PENDING_LOOP)

    async def next_iteration(self) -> LoopAdvance | None:
        """Take the next step of this session's `/loop`, for the client to send.

        Takes no arguments. Returns `null` when there is no loop or it is
        paused. Otherwise `kind` says what happened: `step` carries the
        `prompt` to send as the next message (and `display_prompt` to
        show), the iteration number and how many remain; `completed`
        says the loop reached its cap and ended; `safety_paused` says it
        reached the hard cap and paused.
        """
        return await self._caller.rpc(
            "pop_pending_loop_iteration", NoArgs, {}, _POP_PENDING_LOOP_ITERATION
        )

    async def pause(self) -> bool:
        """Pause this session's `/loop` after the current iteration.

        Takes no arguments. Returns `true` when the loop is now paused
        (or already was), `false` when there is no loop.
        """
        return await self._caller.rpc("loop_pause", NoArgs, {}, _LOOP_PAUSE)

    async def resume(self) -> str:
        """Resume this session's paused `/loop`.

        Takes no arguments. Returns the prompt of the iteration to run next,
        for the client to send as a message — nothing runs on its own — or
        `""` when there is no paused loop.
        """
        return await self._caller.rpc("loop_resume", NoArgs, {}, _LOOP_RESUME)

    async def status(self) -> LoopStatusSnapshot:
        """Read the state of this session's `/loop`.

        Takes no arguments. Returns whether a loop is `active` and
        `paused`, its prompt, which iteration it is on and how many
        remain, whether its cap was set explicitly, and the total the agent
        announced, if any.
        """
        return await self._caller.rpc("loop_status", NoArgs, {}, _LOOP_STATUS)


class SessionMcp:
    """MCP servers this session connects to, and their tools."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def connect(self, server_name: str) -> InfoMessage:
        """Connect one configured MCP server to this session.

        `server_name` is the server's name in the MCP configuration.
        Returns an `info` message, sent in place of an `rpc_response`,
        once it is connected. Fails with the reason when it did not connect
        (not configured, refused by policy, no tools, approval denied); the
        reason is also `get_mcp_server_details`'s `error` for it.
        """
        return await self._caller.rpc(
            "mcp_connect", McpServerArgs, {"server_name": server_name}, _MCP_CONNECT
        )

    async def disconnect(self, server_name: str) -> InfoMessage:
        """Disconnect one MCP server from this session.

        `server_name` is the server's name in the MCP configuration.
        Returns an `info` message, sent in place of an `rpc_response`,
        whether or not the server was connected.
        """
        return await self._caller.rpc(
            "mcp_disconnect", McpServerArgs, {"server_name": server_name}, _MCP_DISCONNECT
        )

    async def ensure(self) -> McpInitResult:
        """Connect this session's configured MCP servers, once.

        Takes no arguments. The first call connects every configured server
        and rebuilds the agent with their tools; later calls do nothing.
        Returns the servers `connected`, the ones that `failed` with
        their errors, whether the agent was `rebuilt`, and, when nothing
        was done, `skipped_reason` (`already_initialized`,
        `no_configured_servers`, `no_clients_connected`).
        """
        return await self._caller.rpc("ensure_mcp", NoArgs, {}, _ENSURE_MCP)

    async def server_details(self) -> list[McpServerSnapshot]:
        """Describe each of this session's MCP servers in full.

        Takes no arguments. Returns one row per server: whether it is
        connected, its transport, its tools (names, descriptions, the ones
        switched off), its resources and prompts, the last error connecting
        it, and whether policy blocks it. Each server is asked in turn, so
        a slow one slows the answer.
        """
        return await self._caller.rpc("get_mcp_server_details", NoArgs, {}, _GET_MCP_SERVER_DETAILS)

    async def servers(self) -> list[McpServerSummary]:
        """List this session's configured MCP servers, in configuration order.

        Takes no arguments. Returns one `{name, connected}` row per
        server.
        """
        return await self._caller.rpc("get_mcp_servers", NoArgs, {}, _GET_MCP_SERVERS)

    async def set_tool_enabled(
        self, *, enabled: bool, server: str, tool: str
    ) -> McpToolToggleResult:
        """Switch one MCP server's tool on or off for this project.

        `server` and `tool` name the tool; `enabled` is its new state.
        The choice is saved in the project's `.igni/mcp-tool-state.json`.
        Returns the `server`, `tool` and `enabled` as recorded; the
        server and tool are not checked to exist. Fails when the state file
        cannot be written.
        """
        return await self._caller.rpc(
            "set_mcp_tool_enabled",
            McpToolEnabledArgs,
            {"enabled": enabled, "server": server, "tool": tool},
            _SET_MCP_TOOL_ENABLED,
        )

    async def status(self) -> list[McpServerStatus]:
        """List this session's MCP servers and whether each is connected.

        Takes no arguments. Returns one `{name, connected}` row per
        server, in no particular order.
        """
        return await self._caller.rpc("get_mcp_status", NoArgs, {}, _GET_MCP_STATUS)


class SessionModels:
    """The models this session can use, and switching between them."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def list(self) -> ModelRegistryResult:
        """List the models this session can run on.

        Takes no arguments. Returns the `default` model's name, the
        largest context window configured, and `registry`: every model by
        name, with its provider and settings.
        """
        return await self._caller.rpc("get_model_registry", NoArgs, {}, _GET_MODEL_REGISTRY)

    async def switch(self, model_name: str) -> InfoMessage:
        """Make another model the one this session's agent runs on.

        `model_name` is a name from the model registry
        (`get_model_registry`). The choice is also saved as the default
        for new sessions. Returns an `info` message, sent in place of an
        `rpc_response`, saying the model switched, with a note for any
        part of the choice that could not be saved. Fails when the model is
        not in the registry.
        """
        return await self._caller.rpc(
            "switch_model", SwitchModelArgs, {"model_name": model_name}, _SWITCH_MODEL
        )


class SessionPermissions:
    """Saved permission rules for tool calls."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def check(
        self, *, func_name: str, tool_args: ToolCallArgs, tool_name: str
    ) -> Literal["allow", "ask", "deny"]:
        """Look up the saved permission level for one tool call.

        `tool_name` and `func_name` name the tool and its function;
        `tool_args` are the call's arguments, which argument rules match
        against. The rules are read from this session's project and the
        person's settings files. Returns `allow`, `ask` or `deny`:
        the last matching argument rule, else the tool's own level, else
        `ask`. The session's permission mode is not applied.
        """
        return await self._caller.rpc(
            "check_permission",
            CheckPermissionArgs,
            {"func_name": func_name, "tool_args": tool_args, "tool_name": tool_name},
            _CHECK_PERMISSION,
        )

    async def save_rule(self, *, level: Literal["allow", "ask", "deny"], rule: str) -> None:
        """Save a permission rule for this session's project.

        `rule` is a permission rule (`Bash(git status)`, a tool name);
        `level` is `allow`, `ask` or `deny`. The rule is written to
        the project's `.igni/settings.local.json` (the person's own when
        there is no project), and the session follows it from its next tool
        call. Returns nothing. Fails when the settings file cannot be
        written.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "save_permission_rule",
            SavePermissionRuleArgs,
            {"level": level, "rule": rule},
            _SAVE_PERMISSION_RULE,
        )


class SessionPlan:
    """Plan mode: the plan the agent submitted, and the person's decision."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    def approve(self, run_id: str = "") -> Call[PlanDecisionResult, ApprovePlanEvent]:
        """Approve the plan the agent submitted, so it leaves plan mode and carries it out.

        `run_id` is the run that submitted the plan (`plan_submitted`
        carries it). The decision is recorded, the session's permission
        mode returns to the one it started in (`permission_mode_changed`
        when it changes), and `plan_decided` tells every window. Returns
        the `run_id`, the `decision`, `mode_status` describing the
        mode change, and `ok`; `ok: false` with `error` when
        `run_id` is empty or the decision could not be recorded.

        ``async with`` the call to follow it: it yields the ``plan_decided`` push whose ``run_id`` is this call's, and ends with it, or with the answer when ``ok`` is false. A change of permission mode is in the answer's ``mode_status``.

        Access: ``approver``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop, a program needs an approver token the window minted (``Local(approver_token=...)``); with the lockfile's token it gets ``AccessRefused``.
        """
        return self._caller.follow("approve_plan", PlanRunArgs, {"run_id": run_id}, _APPROVE_PLAN)

    def dismiss(self, run_id: str = "") -> Call[PlanDecisionResult, DismissPlanEvent]:
        """Send the submitted plan back for refining, staying in plan mode.

        `run_id` is the run that submitted the plan. The decision is
        recorded and `plan_decided` tells every window. Returns the same
        shape as `approve_plan`, with an empty `mode_status`; `ok:
        false` with `error` when `run_id` is empty.

        ``async with`` the call to follow it: it yields the ``plan_decided`` push whose ``run_id`` is this call's, and ends with it, or with the answer when ``ok`` is false.
        """
        return self._caller.follow("dismiss_plan", PlanRunArgs, {"run_id": run_id}, _DISMISS_PLAN)

    async def latest(self) -> LatestPlanResult:
        """Read the plan the agent last submitted in this session, with its task list.

        Takes no arguments. Returns the `latest` plan's text, every plan
        submitted before it (`history`), the to-do list (`tasks`), and
        `state`: `pending` while a plan is waiting for a decision, empty
        when none was submitted.
        """
        return await self._caller.rpc("get_latest_plan", NoArgs, {}, _GET_LATEST_PLAN)


class SessionPlugins:
    """Plugins installed into this session's project."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def contents(self, name: str) -> PluginContents:
        """Show what an installed plugin contains.

        `name` is the installed plugin. Returns its folder and its
        skills, agents, hooks, MCP servers and tools, with its README; or
        `error` when no such plugin is installed.
        """
        return await self._caller.rpc(
            "get_plugin_contents", PluginNameArgs, {"name": name}, _GET_PLUGIN_CONTENTS
        )

    async def install(self, ref: str, *, install_ref: str | None = None) -> InfoMessage:
        """Install a plugin from a git repository or a marketplace.

        `ref` is a git URL or `@<marketplace>/<plugin>`; `install_ref`
        the branch, tag or commit to check out (the marketplace's, or the
        default branch, when absent). The plugin is active in this session
        at once. Returns an `info` message, sent in place of an
        `rpc_response`, whose text says what was installed — or why not:
        git missing, an unknown marketplace entry, the organisation's
        policy, a git error.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "install_plugin",
            InstallPluginArgs,
            {"install_ref": install_ref, "ref": ref},
            _INSTALL_PLUGIN,
        )

    async def list(self) -> builtins.list[PluginInfo]:
        """List the installed plugins.

        Takes no arguments. Returns each plugin's name, version,
        description, where it came from, whether it is enabled (a plugin
        the organisation manages always is), the commit it is pinned to,
        and what it brings: skills, agents, hooks, MCP servers.
        """
        return await self._caller.rpc("get_plugin_details", NoArgs, {}, _GET_PLUGIN_DETAILS)

    async def preview(
        self, source: str, *, branch: str | None = None, subdir: str | None = None
    ) -> PluginContents:
        """Show what a plugin contains without installing it.

        `source` is the plugin's git URL (optionally followed by a
        subfolder); `branch` the branch, tag or commit to read (the
        default branch when absent); `subdir` the plugin's folder inside
        the repository, which wins over one in `source`. The repository
        is cloned to a temporary place. Returns the same shape as
        `get_plugin_contents`, with `preview_source` naming what was
        read; or `error` when the organisation's policy refuses the
        source, git is missing, or the clone failed.
        """
        return await self._caller.rpc(
            "preview_plugin",
            PreviewPluginArgs,
            {"branch": branch, "source": source, "subdir": subdir},
            _PREVIEW_PLUGIN,
        )

    async def remove(self, name: str) -> InfoMessage:
        """Uninstall a plugin.

        `name` is the installed plugin. Returns an `info` message, sent
        in place of an `rpc_response`, whose text says it was removed, or
        why not.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "remove_plugin", PluginNameArgs, {"name": name}, _REMOVE_PLUGIN
        )

    async def set_enabled(self, *, enabled: bool, name: str) -> InfoMessage:
        """Switch an installed plugin on or off.

        `name` is the installed plugin; `enabled` its new state. The
        choice is saved and this session reloads its plugins. Returns an
        `info` message, sent in place of an `rpc_response`, whose text
        says what happened — including a refusal: no such plugin, or one
        the organisation manages.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "set_plugin_enabled",
            PluginEnabledArgs,
            {"enabled": enabled, "name": name},
            _SET_PLUGIN_ENABLED,
        )

    async def update(self, name: str, *, install_ref: str | None = None) -> InfoMessage:
        """Move an installed plugin to another commit.

        `name` is the installed plugin; `install_ref` the branch, tag
        or commit to move to (the remote's default branch when absent).
        Returns an `info` message, sent in place of an `rpc_response`,
        whose text names the commit now installed, or why not.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc(
            "update_plugin",
            UpdatePluginArgs,
            {"install_ref": install_ref, "name": name},
            _UPDATE_PLUGIN,
        )


class SessionRuns:
    """This session's runs that were received but not finished."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def discard_interrupted(self, message_id: str) -> DiscardInterruptedRunResult:
        """Forget one interrupted run, so it is not offered again.

        `message_id` names the run (from `get_interrupted_runs`);
        `session_id` the session it belongs to; only that session's
        interrupted run is deleted. Returns `ok: true` — also when no such
        run exists, so a retry is harmless — or `ok: false` with `error`
        when `message_id` is empty or the store could not be written.
        """
        return await self._caller.rpc(
            "discard_interrupted_run",
            InterruptedRunArgs,
            {"message_id": message_id, "session_id": self._caller.session_id},
            _DISCARD_INTERRUPTED_RUN,
        )

    async def interrupted(self) -> list[InterruptedRun]:
        """List a session's runs that stopped before they finished.

        `session_id` names the session. Returns one row per run that was
        cancelled or failed: the `message_id` and text of the message that
        started it, when it arrived and when it stopped, why (`cancelled`
        or `errored`) and the last error. A client offers to retry,
        discard or edit each. A storage failure answers an empty list.
        """
        return await self._caller.rpc(
            "get_interrupted_runs",
            SessionIdArgs,
            {"session_id": self._caller.session_id},
            _GET_INTERRUPTED_RUNS,
        )

    async def pending_messages(self) -> list[PendingMessage]:
        """List a session's messages that were received but never answered.

        `session_id` names the session. Returns the user messages still
        pending at least a minute after they arrived — typically left by a
        crash — oldest first, each with its text, when it arrived and its
        `message_id`. A storage failure answers an empty list.
        """
        return await self._caller.rpc(
            "get_pending_messages",
            SessionIdArgs,
            {"session_id": self._caller.session_id},
            _GET_PENDING_MESSAGES,
        )


class SessionScheduler:
    """Scheduled tasks of this session's project."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def cancel(self, task_id: str) -> InfoMessage:
        """Cancel a scheduled task of this session's project.

        `task_id` is the task's `id` (from `get_scheduled_tasks`). The
        task is marked cancelled, so it does not run again; a run already
        going is not stopped, but its outcome is not recorded. Returns an
        `info` message, sent in place of an `rpc_response`. Fails for
        an id the project has no task for, and for a task that already
        completed, failed or was cancelled, whose record is left as it is.
        """
        return await self._caller.rpc(
            "cancel_scheduled_task", ScheduledTaskArgs, {"task_id": task_id}, _CANCEL_SCHEDULED_TASK
        )

    def execute(
        self, description: str, *, run_id: str = ""
    ) -> Call[ScheduledTaskRunResult, ExecuteScheduledTaskEvent]:
        """Run a scheduled task's work now, in this session, and wait for the answer.

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

        ``async with`` the call to follow it: it yields the pushes of the run it starts — what its tools do while it works — as they come, and ends with the answer, which is the agent's own words. The run's id is the one given; igni-client makes one when the caller does not, so the pushes can be told from another run's.
        """
        return self._caller.follow(
            "execute_scheduled_task",
            ExecuteScheduledTaskArgs,
            {"description": description, "run_id": run_id or self._caller.new_id("run")},
            _EXECUTE_SCHEDULED_TASK,
        )

    async def list(self, include_done: bool = True) -> builtins.list[ScheduledTask]:
        """List the scheduled tasks of this session's project.

        `include_done` (default `true`) lists finished, failed and
        cancelled tasks too. Returns the tasks, latest scheduled first:
        each one's `id`, `description`, when it is scheduled and was
        created, its `status`, its `result` or `error`, and its
        `recurrence` (empty for a one-shot task).
        """
        return await self._caller.rpc(
            "get_scheduled_tasks",
            ScheduledTasksArgs,
            {"include_done": include_done},
            _GET_SCHEDULED_TASKS,
        )

    def start(self) -> Call[None, StartSchedulerEvent]:
        """Start running this project's scheduled tasks as they fall due.

        Takes no arguments and returns nothing; a scheduler already running
        is left as it is. From then on each due task runs through the
        agent: `scheduler_started` when it starts, `scheduler_completed`
        with its result when it ends, and whatever its tools push between.

        ``async with`` the call to follow it: it yields this session's ``scheduler_started`` and ``scheduler_completed`` pushes for as long as the block runs. What a task's tools push meanwhile carries nothing that says which run it came from, so it is not yielded; read it from ``igni.events()``.
        """
        return self._caller.follow("start_scheduler", NoArgs, {}, _START_SCHEDULER)


class SessionSkills:
    """The skills this session's agent can use."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    async def definitions(self) -> builtins.list[SkillDefinition]:
        """List this session's skills with what each tells the agent.

        Takes no arguments. Returns each skill's `name`, `description`
        and `prompt` (the skill's body).
        """
        return await self._caller.rpc("get_skill_definitions", NoArgs, {}, _GET_SKILL_DEFINITIONS)

    async def list(self) -> builtins.list[SkillInfo]:
        """Describe each of this session's skills in full.

        Takes no arguments. Returns each skill's name, description,
        version, category, argument hint, the context and agent it runs
        in, whether a person can invoke it, its body and its folder.
        """
        return await self._caller.rpc("get_skill_details", NoArgs, {}, _GET_SKILL_DETAILS)

    async def names(self) -> builtins.list[str]:
        """List the names of the skills this session has loaded.

        Takes no arguments. Returns the names, each usable as `/<name>`.
        """
        return await self._caller.rpc("get_skill_names", NoArgs, {}, _GET_SKILL_NAMES)


class SessionWorkflows:
    """Workflows: scripted runs this session starts and follows."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    def cancel(self, workflow_run_id: str) -> Call[WorkflowCancelResponse, CancelWorkflowEvent]:
        """Stop a running workflow of this session.

        `workflow_run_id` is the run (from `run_workflow`). The
        workflow is asked to stop, then terminated after a grace period;
        its last `workflow_event` says it was cancelled. Returns
        `cancelled: true` when a live run was stopped, `false` when
        there was no such run or it had already ended, with the
        `workflow_run_id` asked about.

        ``async with`` the call to follow it: it yields the ``workflow_event`` pushes of ``workflow_run_id`` and ends with the run's last, or with the answer when ``cancelled`` is false.
        """
        return self._caller.follow(
            "cancel_workflow",
            WorkflowCancelRequest,
            {"workflow_run_id": workflow_run_id},
            _CANCEL_WORKFLOW,
        )

    async def list(self) -> builtins.list[WorkflowListItem]:
        """List the workflows this session's project can run.

        Takes no arguments (any it is sent are ignored). Returns each workflow in
        `.igni/workflows/*.mjs` (a project's shadowing the person's own
        of the same name), sorted by name: its `name`, `description`,
        `whenToUse`, `phases` and `path`. A file whose metadata cannot
        be read is left out.
        """
        return await self._caller.rpc("list_workflows", WorkflowListRequest, {}, _LIST_WORKFLOWS)

    def run(
        self, name: str, *, args: dict[str, JsonValue] | None = None
    ) -> Call[WorkflowRunResponse, RunWorkflowEvent]:
        """Start a workflow in this session and return its run id at once.

        `name` is the workflow (from `list_workflows`); `args` its
        input, a JSON object the workflow reads as it defines. Returns the
        `workflow_run_id` and `name`. The run goes on in the
        background: each step it takes is pushed as `workflow_event`
        carrying that id, ending with `workflow_completed` or
        `workflow_failed`. Fails when there is no such workflow or the
        workflow runtime is missing.

        ``async with`` the call to follow it: it yields every ``workflow_event`` push carrying the ``workflow_run_id`` igni answered with — those that came before the answer too — and ends with the run's ``workflow_completed`` or ``workflow_failed``.
        """
        return self._caller.follow(
            "run_workflow",
            WorkflowRunRequest,
            {"args": ({} if args is None else args), "name": name},
            _RUN_WORKFLOW,
        )


class SessionWorkspace:
    """Whether this session's project folder is trusted."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller

    def set_trust(
        self, decision: Literal["trust", "distrust", "once"]
    ) -> Call[WorkspaceTrustStatus, SetWorkspaceTrustEvent]:
        """Answer "Trust this folder?" for this session's project folder.

        `decision` is `trust` (remembered), `once` (until igni exits)
        or `distrust`. When trust changed, the session is rebuilt so the
        folder's tools, hooks, plugins, language servers and configuration
        come in or go. Every window showing the dialog for that folder is
        told the new status (`workspace_trust_required`). Returns the new
        status. Fails when the organisation's policy does not let the folder
        be trusted.

        ``async with`` the call to follow it: it yields the ``workspace_trust_required`` push that tells the windows the folder's trust changed, and ends with the answer — the new status.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return self._caller.follow(
            "set_workspace_trust", TrustDecisionArgs, {"decision": decision}, _SET_WORKSPACE_TRUST
        )

    async def trust(self) -> WorkspaceTrustStatus:
        """Read whether this session's project folder is trusted.

        Takes no arguments. Returns the folder's trust `state`
        (`trusted`, `untrusted`, or `ask` when the person has not
        decided), whether it `can_trust` it under the organisation's
        policy and, if not, the `reason`, plus where the decision came
        from. Until a folder is trusted its own tools, hooks, plugins and
        configuration are not loaded.
        """
        return await self._caller.rpc("get_workspace_trust", NoArgs, {}, _GET_WORKSPACE_TRUST)


class IgniApi:
    """The methods igni answers for igni as a whole; `IgniClient` is one."""

    agents: IgniAgents
    """Sub-agents' runs, wherever they are going."""
    approvers: IgniApprovers
    """Approver tokens: what lets a program answer approval requests."""
    auth: IgniAuth
    """Signing igni in to igni server, and choosing which server."""
    extensions: IgniExtensions
    """The extensions installed into this igni, and their settings."""
    files: IgniFiles
    """Folders on the machine igni runs on."""
    marketplaces: IgniMarketplaces
    """Plugin marketplaces: where plugins are installed from."""
    notifications: IgniNotifications
    """The signed-in person's notifications, and what extensions posted."""
    processes: IgniProcesses
    """Background processes igni tracks, in every session."""
    window: IgniWindow
    """igni's own window's model — its fields, toasts and dialog."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller
        self.agents = IgniAgents(caller)
        self.approvers = IgniApprovers(caller)
        self.auth = IgniAuth(caller)
        self.extensions = IgniExtensions(caller)
        self.files = IgniFiles(caller)
        self.marketplaces = IgniMarketplaces(caller)
        self.notifications = IgniNotifications(caller)
        self.processes = IgniProcesses(caller)
        self.window = IgniWindow(caller)

    async def check_for_update(self) -> UpdateAvailable | None:
        """Ask whether a newer igni release is available.

        Takes no arguments. Returns the newer release — its version, the
        version installed, where to get it — or `null` when there is none
        (or update checks are switched off). Fails when the check could not
        reach an answer (network, HTTP status, an unreadable reply), so a
        caller can tell that from "no update".
        """
        return await self._caller.rpc("check_for_update", NoArgs, {}, _CHECK_FOR_UPDATE)

    async def group_policy(self) -> GroupPolicyPackResult:
        """Read which organisation group's policy igni follows.

        Takes no arguments. Returns the group's id and name, when its
        policy pack was fetched, how many entries it has and the default
        model it sets; nulls and zero when igni follows no group.
        """
        return await self._caller.rpc("get_group_policy", NoArgs, {}, _GET_GROUP_POLICY)


class SessionApi:
    """The methods igni answers for one session; `Session` is one."""

    agents: SessionAgents
    """The agents this session can hand work to."""
    auth: SessionAuth
    """This session's sign-in to igni server."""
    context: SessionContext
    """This session's context window: how full it is, and compacting it."""
    files: SessionFiles
    """Files in this session's project folder."""
    history: SessionHistory
    """This session's conversation as stored: read, search, cut back."""
    hooks: SessionHooks
    """The hooks that run on this session's events."""
    loop: SessionLoop
    """This session's loop: a task the agent repeats until it is done."""
    mcp: SessionMcp
    """MCP servers this session connects to, and their tools."""
    models: SessionModels
    """The models this session can use, and switching between them."""
    permissions: SessionPermissions
    """Saved permission rules for tool calls."""
    plan: SessionPlan
    """Plan mode: the plan the agent submitted, and the person's decision."""
    plugins: SessionPlugins
    """Plugins installed into this session's project."""
    runs: SessionRuns
    """This session's runs that were received but not finished."""
    scheduler: SessionScheduler
    """Scheduled tasks of this session's project."""
    skills: SessionSkills
    """The skills this session's agent can use."""
    workflows: SessionWorkflows
    """Workflows: scripted runs this session starts and follows."""
    workspace: SessionWorkspace
    """Whether this session's project folder is trusted."""

    def __init__(self, caller: Caller) -> None:
        self._caller = caller
        self.agents = SessionAgents(caller)
        self.auth = SessionAuth(caller)
        self.context = SessionContext(caller)
        self.files = SessionFiles(caller)
        self.history = SessionHistory(caller)
        self.hooks = SessionHooks(caller)
        self.loop = SessionLoop(caller)
        self.mcp = SessionMcp(caller)
        self.models = SessionModels(caller)
        self.permissions = SessionPermissions(caller)
        self.plan = SessionPlan(caller)
        self.plugins = SessionPlugins(caller)
        self.runs = SessionRuns(caller)
        self.scheduler = SessionScheduler(caller)
        self.skills = SessionSkills(caller)
        self.workflows = SessionWorkflows(caller)
        self.workspace = SessionWorkspace(caller)

    def cancel(self) -> Call[CancelRunResult, CancelRunEvent]:
        """Stop the turn this session is running.

        Takes no arguments. Returns `cancelled`: whether a turn was
        running. Its stream then ends with an `info` saying it was
        cancelled and its `stream_end`, and the run is recorded as
        interrupted; a foreground shell command the turn started is killed.
        With no turn running nothing happens and nothing is streamed.

        ``async with`` the call to follow it: it yields the ``info`` and ``stream_end`` of the turn it stops, and ends with the ``stream_end``. With no turn running nothing is streamed, and the answer says so.
        """
        return self._caller.follow("cancel_run", NoArgs, {}, _CANCEL_RUN)

    async def command(self, text: str = "") -> CommandResult:
        """Run a slash command in this session, as typed in igni's composer: ``/help``, ``/compact``, ``/model``.

        ``text`` is the command line, its leading ``/`` optional. Returns igni's ``command_result``: its ``kind`` (``markdown``, ``info``, ``error`` or ``action``), the ``content`` to show and the ``action`` the command asks a client to take. The commands that switch approvals off, change what igni loads or whom it signs in to (``/bypass``, ``/accept``, ``/plugin``, ``/eject``, ``/login``, ``/logout``) answer an ``error`` to anything but igni's window.

        Sent as igni's ``command`` message. igni answers with ``command_result``.
        """
        return await self._caller.request(Command, {"text": text}, _COMMAND)

    async def current_id(self) -> str:
        """Read the id of the session this request reached.

        Takes no arguments. Returns the session's current id, which can
        differ from the one the request was routed by after `/clear` or
        `switch_session`.
        """
        return await self._caller.rpc("get_session_id", NoArgs, {}, _GET_SESSION_ID)

    async def display_config(self) -> DisplayConfig:
        """Read this session's display settings.

        Takes no arguments. Returns how output is shown: markdown rendering,
        tool calls, routing, reasoning, the colour theme, and how many lines
        of a tool result and a message are shown before truncating.
        """
        return await self._caller.rpc("get_display_config", NoArgs, {}, _GET_DISPLAY_CONFIG)

    async def extract_learnings(self, *, assistant_msg: str, user_msg: str) -> None:
        """Let igni learn from one finished turn, in the background.

        `user_msg` and `assistant_msg` are the turn's message and
        answer. Returns at once with nothing; what is learnt is kept for
        later sessions, and a failure is only logged.
        """
        return await self._caller.rpc(
            "extract_learnings",
            ExtractLearningsArgs,
            {"assistant_msg": assistant_msg, "user_msg": user_msg},
            _EXTRACT_LEARNINGS,
        )

    async def fire_session_start_hook(self) -> None:
        """Run this session's `SessionStart` hooks.

        Takes no arguments and returns nothing. The organisation's group
        policy is checked again first. Every call runs the hooks again;
        their failures are logged, not raised.
        """
        return await self._caller.rpc(
            "fire_session_start_hook", NoArgs, {}, _FIRE_SESSION_START_HOOK
        )

    async def get_project_dir(self) -> str:
        """Read the folder this session is locked to.

        Takes no arguments. Returns the absolute path the agent's tools and
        shell commands work in.
        """
        return await self._caller.rpc("get_project_dir", NoArgs, {}, _GET_PROJECT_DIR)

    async def is_processing(self) -> bool:
        """Say whether this session is running a turn right now.

        Takes no arguments. Returns `true` while a turn the person (or a
        client) started is starting, streaming or finishing.
        """
        return await self._caller.rpc("get_processing", NoArgs, {}, _GET_PROCESSING)

    async def list_sessions(self) -> SessionListResult:
        """List the sessions kept in this session's project.

        Takes no arguments. Returns a `session_list_result` message, sent
        in place of an `rpc_response`: each session's id, name, when it
        was created and last updated, how many runs it has, a summary and
        the agent it runs. A storage failure answers an empty list.
        """
        return await self._caller.rpc("list_sessions", NoArgs, {}, _LIST_SESSIONS)

    async def output_styles(self) -> OutputStylesResult:
        """List the output styles this session can answer in, and the active one.

        Takes no arguments. Returns the `active` style's name (empty for
        none) and every style's `name` and `description`.
        """
        return await self._caller.rpc("get_output_styles", NoArgs, {}, _GET_OUTPUT_STYLES)

    def run_shell(self, command: str = "") -> Call[RunShellResult, RunShellEvent]:
        """Run a shell command in this session's project folder and return its output.

        `command` is the command line (what follows `$` in the
        composer); blank runs nothing. Output is captured, not interactive.
        Returns `output` (the tail, at most 100 KB) and `exit_code`
        (`-1` when it could not start). A command still running after two
        minutes moves to the background: the answer then comes at once with
        `exit_code` 0 and a note, and the process goes on as a background
        process — `process_started`, a `process_line` per line,
        `process_exited` and `background_process_done`.

        ``async with`` the call to follow it: a command that finishes inside the wait pushes nothing, and the answer is its output. A command that outlives the wait moves to the background: the answer names the pid, and the ``process_started``, ``process_line``, ``process_exited`` and ``background_process_done`` pushes of that pid follow, ending with the last of them.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return self._caller.follow("run_shell", RunShellArgs, {"command": command}, _RUN_SHELL)

    async def run_timeout(self) -> int:
        """Read how long, in seconds, a client should wait for one run.

        Takes no arguments. Returns the configured maximum run time; igni
        does not stop a run at it, the client decides what to do.
        """
        return await self._caller.rpc("get_run_timeout", NoArgs, {}, _GET_RUN_TIMEOUT)

    async def shutdown(self) -> None:
        """Wind this session down: its hooks, its agents, its MCP servers, its scheduler.

        Takes no arguments and returns nothing once done. Runs the session's
        `SessionEnd` hooks, cleans up its ephemeral agents, disconnects its
        MCP servers and stops its scheduler — once: a session already wound
        down is left as it is. Background processes are igni's, not the
        session's, and are left running; they end when igni does. It does
        not stop igni or close the connection. Each step's failure is
        logged, not raised. Only igni's window may call it.

        Access: ``window``. Through Fleet's gateway every connection stands as igni's window and makes this call. On the desktop only the app's own window does: a program — with the lockfile's token or an approver token — gets ``AccessRefused``.
        """
        return await self._caller.rpc("shutdown", NoArgs, {}, _SHUTDOWN)

    async def slash_commands(self) -> list[SlashCommand]:
        """List every slash command this session takes.

        Takes no arguments. Returns igni's built-in commands, commands
        written as markdown files, skills a person can invoke, and
        extensions' commands, told apart by `source`; each with its
        `name`, `description` and `argument_hint`.
        """
        return await self._caller.rpc("get_slash_commands", NoArgs, {}, _GET_SLASH_COMMANDS)

    async def status(self) -> StatusUpdate:
        """Read this session's status: model, account, context size and permission mode.

        Takes no arguments. Returns a `status_update` message, sent in
        place of an `rpc_response`: the model and whether it is
        configured, the igni server connection and account, the context
        used and its window, the permission mode and the theme.
        """
        return await self._caller.rpc("get_status", NoArgs, {}, _GET_STATUS)

    async def switch(self, session_id: str) -> InfoMessage:
        """Make the session this request is routed to continue another stored session.

        `session_id` is the stored session to continue; the conversation,
        its history and its runs are read from it from now on. Returns an
        `info` message, sent in place of an `rpc_response`, naming the
        session switched to. The id is not checked: an unknown one starts
        an empty session under that id.
        """
        return await self._caller.rpc(
            "switch_session", SessionIdArgs, {"session_id": session_id}, _SWITCH_SESSION
        )

    async def todos(self) -> list[TodoItem]:
        """Read the agent's to-do list in this session.

        Takes no arguments. Returns each item's `content`, `status`
        (`pending`, `in_progress`, `completed`) and `activeForm`
        (how it reads while in progress). `todos_updated` pushes the list
        whenever the agent changes it.
        """
        return await self._caller.rpc("get_todos", NoArgs, {}, _GET_TODOS)

    async def toggle_verbose(self) -> bool:
        """Turn showing the agent's routing decisions on or off for this session.

        Takes no arguments. Returns the new setting: `true` when routing is
        now shown. Not saved; the session's next settings reload resets it.
        """
        return await self._caller.rpc("toggle_verbose", NoArgs, {}, _TOGGLE_VERBOSE)

    async def typing(self, text: str = "") -> None:
        """Show what this client is typing to every other client of this session.

        ``text`` is the whole draft, not a change to it; empty clears it. igni relays it to every client attached, this one included, as a ``Typing`` event.

        Sent as igni's ``typing`` message.
        """
        await self._caller.send(Typing, {"client_id": self._caller.client_id, "text": text})

    async def upload_attachment(
        self, *, content_base64: str, filename: str
    ) -> UploadAttachmentResult:
        """Store a file for this session, so a message can refer to it.

        `filename` is the file's name (made safe for the disk; a clash gets
        a `-N` suffix); `content_base64` its bytes, base64-encoded.
        Returns `path` — the stored file's path, or an `attachment:<id>`
        reference when attachments are kept in shared storage — and its
        `size` in bytes; or `error` when the content is not valid base64.
        Fails when the file cannot be stored.
        """
        return await self._caller.rpc(
            "upload_attachment",
            UploadAttachmentArgs,
            {"content_base64": content_base64, "filename": filename},
            _UPLOAD_ATTACHMENT,
        )

    def visualization_action(
        self, *, action: str = "", params: dict[str, JsonValue] | None = None
    ) -> Call[VisualizationActionResult, DispatchVisualizationActionEvent]:
        """Tell this session the person used a control in a view the agent drew.

        `action` is the control's action name; `params` the values the
        view attached to it (JSON). The action is kept for the agent and
        pushed to every window as `visualization_action_dispatched`.
        Returns the action and params as recorded, with `ok`.

        ``async with`` the call to follow it: it yields the ``visualization_action_dispatched`` push of this session carrying this ``action`` and ``params``, and ends with it.
        """
        return self._caller.follow(
            "dispatch_visualization_action",
            VisualizationActionArgs,
            {"action": action, "params": params},
            _DISPATCH_VISUALIZATION_ACTION,
        )

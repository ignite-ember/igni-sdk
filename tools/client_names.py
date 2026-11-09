"""What each of igni's RPC methods is called in igni-client — the one hand-kept table.

The contract (``contracts/rpc-contract.json``) says what every method takes,
returns, streams and acts on. It does not say what a Python programmer
should type, so that is decided here, once per method, and the generator
(``tools/client_codegen.py``) refuses a contract with a method this table
does not place. A new method in igni-core is a failing check here until it
is given a name or a reason it is not for clients.

A name is ``owner.namespace.method`` or ``owner.method``:

* ``igni`` — on ``IgniClient``, for a method whose contract scope is
  ``igni`` (igni as a whole, whichever session the call reaches);
* ``session`` — on ``Session``, for a method whose scope is ``session``.

``SCOPE_EXCEPTIONS`` lists the few placed against their scope, with why.
"""

from __future__ import annotations

#: Every method a client calls, by wire name.
METHODS: dict[str, str] = {
    # ── igni as a whole ──────────────────────────────────────────────
    "attach_session": "igni.sessions.attach",
    "check_for_update": "igni.check_for_update",
    "cancel_agent_run": "igni.agents.cancel_run",
    "get_group_policy": "igni.group_policy",
    "list_dirs": "igni.files.list_dirs",
    "list_background_processes": "igni.processes.list",
    "read_process_tail": "igni.processes.tail",
    "stop_background_process": "igni.processes.stop",
    "list_extensions": "igni.extensions.list",
    "set_extension_settings": "igni.extensions.set_settings",
    "get_marketplaces": "igni.marketplaces.list",
    "add_marketplace": "igni.marketplaces.add",
    "remove_marketplace": "igni.marketplaces.remove",
    "refresh_marketplaces": "igni.marketplaces.refresh",
    "notifications_list": "igni.notifications.list",
    "notifications_counts": "igni.notifications.counts",
    "notifications_mark_read": "igni.notifications.mark_read",
    "login": "igni.auth.login",
    "discover_server": "igni.auth.discover_server",
    "set_server": "igni.auth.set_server",
    "mint_approver_token": "igni.approvers.mint_token",
    "revoke_approver_tokens": "igni.approvers.revoke_tokens",
    "window_model": "igni.window.model",
    # ── One session ──────────────────────────────────────────────────
    "get_status": "session.status",
    "get_session_id": "session.current_id",
    "get_project_dir": "session.get_project_dir",
    "get_processing": "session.is_processing",
    "get_run_timeout": "session.run_timeout",
    "switch_session": "session.switch",
    "list_sessions": "session.list_sessions",
    "cancel_run": "session.cancel",
    "shutdown": "session.shutdown",
    "fire_session_start_hook": "session.fire_session_start_hook",
    "upload_attachment": "session.upload_attachment",
    "get_todos": "session.todos",
    "get_output_styles": "session.output_styles",
    "get_slash_commands": "session.slash_commands",
    "get_display_config": "session.display_config",
    "toggle_verbose": "session.toggle_verbose",
    "extract_learnings": "session.extract_learnings",
    "run_shell": "session.run_shell",
    "dispatch_visualization_action": "session.visualization_action",
    "get_pending_messages": "session.runs.pending_messages",
    "get_interrupted_runs": "session.runs.interrupted",
    "discard_interrupted_run": "session.runs.discard_interrupted",
    "get_chat_history": "session.history.get",
    "search_chat": "session.history.search",
    "truncate_history": "session.history.truncate",
    "count_context_tokens": "session.context.tokens",
    "get_context_breakdown": "session.context.breakdown",
    "compact_if_needed": "session.context.compact",
    "loop_status": "session.loop.status",
    "loop_pause": "session.loop.pause",
    "loop_resume": "session.loop.resume",
    "pop_pending_loop_iteration": "session.loop.next_iteration",
    "cancel_pending_loop": "session.loop.cancel",
    "get_latest_plan": "session.plan.latest",
    "approve_plan": "session.plan.approve",
    "dismiss_plan": "session.plan.dismiss",
    "get_model_registry": "session.models.list",
    "switch_model": "session.models.switch",
    "check_permission": "session.permissions.check",
    "save_permission_rule": "session.permissions.save_rule",
    "get_workspace_trust": "session.workspace.trust",
    "set_workspace_trust": "session.workspace.set_trust",
    "complete_files": "session.files.complete",
    "read_file": "session.files.read",
    "search_code": "session.files.search",
    "pick_dir_native": "session.files.pick_dir",
    "get_agent_details": "session.agents.list",
    "promote_ephemeral_agent": "session.agents.promote",
    "discard_ephemeral_agent": "session.agents.discard",
    "get_skill_names": "session.skills.names",
    "get_skill_definitions": "session.skills.definitions",
    "get_skill_details": "session.skills.list",
    "get_hooks_details": "session.hooks.list",
    "reload_hooks": "session.hooks.reload",
    "start_scheduler": "session.scheduler.start",
    "get_scheduled_tasks": "session.scheduler.list",
    "execute_scheduled_task": "session.scheduler.execute",
    "cancel_scheduled_task": "session.scheduler.cancel",
    "list_workflows": "session.workflows.list",
    "run_workflow": "session.workflows.run",
    "cancel_workflow": "session.workflows.cancel",
    "ensure_mcp": "session.mcp.ensure",
    "get_mcp_status": "session.mcp.status",
    "get_mcp_servers": "session.mcp.servers",
    "get_mcp_server_details": "session.mcp.server_details",
    "mcp_connect": "session.mcp.connect",
    "mcp_disconnect": "session.mcp.disconnect",
    "set_mcp_tool_enabled": "session.mcp.set_tool_enabled",
    "get_plugin_details": "session.plugins.list",
    "get_plugin_contents": "session.plugins.contents",
    "preview_plugin": "session.plugins.preview",
    "install_plugin": "session.plugins.install",
    "update_plugin": "session.plugins.update",
    "remove_plugin": "session.plugins.remove",
    "set_plugin_enabled": "session.plugins.set_enabled",
    "reload_cloud_credentials": "session.auth.reload_credentials",
    "get_cloud_plan": "session.auth.plan",
    "clear_cloud_credentials": "session.auth.sign_out",
}

#: Methods placed against their contract scope, and why.
SCOPE_EXCEPTIONS: dict[str, str] = {
    "attach_session": (
        "a session is attached before there is a `Session` to call it on; "
        "`igni.sessions.create()` and `.open()` are built on it"
    ),
}

#: Methods a client cannot call, and why. They are not generated.
NOT_FOR_CLIENTS: dict[str, str] = {
    "host_model": (
        "an extension page's call: igni's window makes it for the page it hosts, "
        "setting `caller`, which igni honours from no other connection"
    ),
    "extension_service_token": (
        "an extension page's call: it hands the page its service's token, "
        "and only igni's window speaks for a page"
    ),
    "deliver_service_events": (
        "the platform's call: Fleet delivers an extension service's events "
        "on its own control connection"
    ),
    "vm_sign_in": "the platform's call: Fleet signs a VM's igni in on its control connection",
}

#: Methods whose `session_id` argument names the session they act on. On a
#: `Session` it is that session's own id, so the method does not take it.
OWN_SESSION_ARG: frozenset[str] = frozenset(
    {
        "get_chat_history",
        "search_chat",
        "truncate_history",
        "get_pending_messages",
        "get_interrupted_runs",
        "discard_interrupted_run",
    }
)

#: What each namespace is, for its class's docstring and the README.
NAMESPACES: dict[str, str] = {
    "igni.sessions": "igni's sessions: attach one, or make a new one in a project folder.",
    "igni.agents": "Sub-agents' runs, wherever they are going.",
    "igni.files": "Folders on the machine igni runs on.",
    "igni.processes": "Background processes igni tracks, in every session.",
    "igni.extensions": "The extensions installed into this igni, and their settings.",
    "igni.marketplaces": "Plugin marketplaces: where plugins are installed from.",
    "igni.notifications": "The signed-in person's notifications, and what extensions posted.",
    "igni.auth": "Signing igni in to igni server, and choosing which server.",
    "igni.approvers": "Approver tokens: what lets a program answer approval requests.",
    "igni.window": "igni's own window's model — its fields, toasts and dialog.",
    "session.runs": "This session's runs that were received but not finished.",
    "session.history": "This session's conversation as stored: read, search, cut back.",
    "session.context": "This session's context window: how full it is, and compacting it.",
    "session.loop": "This session's loop: a task the agent repeats until it is done.",
    "session.plan": "Plan mode: the plan the agent submitted, and the person's decision.",
    "session.models": "The models this session can use, and switching between them.",
    "session.permissions": "Saved permission rules for tool calls.",
    "session.workspace": "Whether this session's project folder is trusted.",
    "session.files": "Files in this session's project folder.",
    "session.agents": "The agents this session can hand work to.",
    "session.skills": "The skills this session's agent can use.",
    "session.hooks": "The hooks that run on this session's events.",
    "session.scheduler": "Scheduled tasks of this session's project.",
    "session.workflows": "Workflows: scripted runs this session starts and follows.",
    "session.mcp": "MCP servers this session connects to, and their tools.",
    "session.plugins": "Plugins installed into this session's project.",
    "session.auth": "This session's sign-in to igni server.",
}

#: Namespaces igni-client extends by hand, and where. The generated class is
#: their base; the client attaches the hand-written one.
HAND_WRITTEN_NAMESPACES: dict[str, str] = {
    "igni.sessions": "igni_client.sessions.Sessions",
}

#: Methods that stream whose events igni-client follows, and how it tells
#: this call's events from every other's. Each returns a `Call`
#: (`igni_client.calls`); `igni_client.follow` holds the rule that matches.
FOLLOWED: dict[str, str] = {
    "approve_plan": (
        "``async with`` the call to follow it: it yields the ``plan_decided`` push whose "
        "``run_id`` is this call's, and ends with it, or with the answer when ``ok`` is false. "
        "A change of permission mode is in the answer's ``mode_status``."
    ),
    "dismiss_plan": (
        "``async with`` the call to follow it: it yields the ``plan_decided`` push whose "
        "``run_id`` is this call's, and ends with it, or with the answer when ``ok`` is false."
    ),
    "run_workflow": (
        "``async with`` the call to follow it: it yields every ``workflow_event`` push "
        "carrying the ``workflow_run_id`` igni answered with — those that came before the "
        "answer too — and ends with the run's ``workflow_completed`` or ``workflow_failed``."
    ),
    "cancel_workflow": (
        "``async with`` the call to follow it: it yields the ``workflow_event`` pushes of "
        "``workflow_run_id`` and ends with the run's last, or with the answer when "
        "``cancelled`` is false."
    ),
    "stop_background_process": (
        "``async with`` the call to follow it: it yields the ``process_line``, "
        "``process_exited`` and ``background_process_done`` pushes of ``pid`` and ends "
        "with ``background_process_done``, or with the answer when ``killed`` is false."
    ),
    "dispatch_visualization_action": (
        "``async with`` the call to follow it: it yields the "
        "``visualization_action_dispatched`` push of this session carrying this "
        "``action`` and ``params``, and ends with it."
    ),
    "start_scheduler": (
        "``async with`` the call to follow it: it yields this session's "
        "``scheduler_started`` and ``scheduler_completed`` pushes for as long as the "
        "block runs. What a task's tools push meanwhile carries nothing that says which "
        "run it came from, so it is not yielded; read it from ``igni.events()``."
    ),
    "login": (
        "``async with`` the call to follow it: it yields the ``login_status`` pushes and "
        "ends with the ``login_result`` one. igni signs in one way at a time — a new "
        "``login`` cancels the one going — so these are the sign-in igni is doing."
    ),
}

#: Methods that stream whose events igni gives a client nothing to tell apart
#: from another call's. They return their result only; the reason says why
#: and where the events can be watched instead.
UNFOLLOWED: dict[str, str] = {
    "attach_session": (
        "the approvals and runs it shows again carry no request id and no end, and every "
        "client attaching the session shows them again; watch them with "
        "``session.events()``, which offers each waiting approval as an "
        "``ApprovalRequested``."
    ),
    "cancel_run": (
        "the ``info`` and ``stream_end`` it causes belong to the turn it stops, whose own "
        "stream (``session.send()``) ends with them; with no turn going nothing follows, "
        "and the answer does not say which it was."
    ),
    "run_shell": (
        "a command that moves to the background is reported by ``process_*`` pushes "
        "carrying its ``pid``, but the answer does not say the ``pid``; watch "
        "``igni.processes.list()`` or ``igni.events()``."
    ),
    "execute_scheduled_task": (
        "what the task's tools push carries nothing that says which run it came from, so "
        "it cannot be told from another run's in the same session; watch ``igni.events()``."
    ),
    "clear_cloud_credentials": (
        "``notifications_changed`` carries the new counts, not what changed them; read "
        "``igni.notifications.counts()``."
    ),
    "notifications_list": (
        "the ``notifications_changed`` push repeats the counts the answer carries, to "
        "every client, and does not say what caused it."
    ),
    "notifications_mark_read": (
        "the ``notifications_changed`` push repeats the counts the answer carries, to "
        "every client, and does not say what caused it."
    ),
    "set_workspace_trust": (
        "igni pushes ``workspace_trust_required`` only to the windows showing the trust "
        "dialog; the answer is the new status."
    ),
    "window_model": (
        "a ``window_model_changed`` push says which window changed and its new "
        "revision, but not which request changed it, and a request that changes "
        "nothing pushes nothing."
    ),
}

#: Messages a client sends that igni-client exposes as methods: the message
#: igni answers with (or ``""`` for none), and the method.
MESSAGE_METHODS: dict[str, tuple[str, str]] = {
    "command": ("command_result", "session.command"),
    "typing": ("", "session.typing"),
    "cancel_login": ("", "igni.auth.cancel_login"),
}

#: Messages a client sends that hand-written code builds, and where.
MESSAGES_SENT_BY_HAND: dict[str, str] = {
    "user_message": "`session.send()` and `session.ask()`",
    "queue_message": "`session.queue()`",
    "hitl_response_batch": "`ApprovalRequested.approve()`, `.reject()` and `.decide()`",
    "hitl_decision": "a row of `hitl_response_batch`",
    "rpc_request": "every generated method",
}

#: Messages a client could send but igni-client does not, and why.
MESSAGES_NOT_SENT: dict[str, str] = {
    "shutdown": (
        "stops igni itself, for every window and program attached, and only igni's "
        "window may; `session.shutdown()` winds one session down instead"
    ),
    "cancel": "`cancel_run` does the same and answers, so `session.cancel()` calls it",
    "hitl_response": (
        "answers one call of a pause and leaves the rest refused; `hitl_response_batch` "
        "answers every call of it, which is what `ApprovalRequested` sends"
    ),
    "session_list": "the method `list_sessions` answers the same, so `session.list_sessions()` calls it",
    "session_switch": "the method `switch_session` does the same, so `session.switch()` calls it",
    "model_switch": "the method `switch_model` does the same, so `session.models.switch()` calls it",
    "mcp_toggle": (
        "the methods `mcp_connect` and `mcp_disconnect` do the same, so "
        "`session.mcp.connect()` and `.disconnect()` call them"
    ),
}

#: Names for the contract's unions of types, by their members.
UNION_NAMES: dict[frozenset[str], str] = {
    frozenset(
        {
            "UserTurn",
            "AssistantTurn",
            "ThinkingTurn",
            "ToolTurn",
            "PlanTurn",
            "StatsTurn",
            "VisualizationTurn",
        }
    ): "ChatTurn",
    frozenset(
        {
            "BuiltinSlashCommand",
            "MarkdownSlashCommand",
            "SkillSlashCommand",
            "ExtensionSlashCommand",
        }
    ): "SlashCommand",
    frozenset(
        {"Hydrated", "Written", "ToastAdded", "Revised", "DialogShown", "DialogAnswered"}
    ): "WindowModelResult",
    frozenset(
        {
            "ToolStartedEvent",
            "ToolCompletedEvent",
            "AgentStartedEvent",
            "AgentPausedEvent",
            "AgentCompletedEvent",
            "RunErrorEvent",
            "ContentPreviewEvent",
            "TaskCreatedEvent",
            "TaskUpdatedEvent",
            "VisualizationDeltaPayload",
        }
    ): "OrchestrateEvent",
    frozenset({"PermissionModeChangedPayload", "PlanModeEnteredPayload"}): "PermissionModeChange",
}

#: Python class names for the contract's defs where its own name would read
#: badly in Python, or clash with igni-client's hand-written API.
CLASS_NAMES: dict[str, str] = {
    "Error": "ErrorMessage",
    "Info": "InfoMessage",
    "HITLRequest": "Requirement",
    "HITLDecision": "HitlDecision",
    "HITLResponse": "HitlResponse",
    "HITLResponseBatch": "HitlResponseBatch",
    "RPCRequest": "RpcRequest",
    "RPCResponse": "RpcResponse",
    "MCPToggle": "McpToggle",
    "MCPPrompt": "McpPrompt",
    "MCPResource": "McpResource",
    "MCPServerSnapshot": "McpServerSnapshot",
    "MCPServerSummary": "McpServerSummary",
    "MCPToolToggleResult": "McpToolToggleResult",
    "PluginMCPServerInfo": "PluginMcpServerInfo",
    "TodoItemWire": "TodoItem",
    # The payload of the `host_signal` push; `HostSignalPush` is that push's class.
    "HostSignalPush": "HostSignal",
}

__all__ = [
    "CLASS_NAMES",
    "FOLLOWED",
    "HAND_WRITTEN_NAMESPACES",
    "MESSAGES_NOT_SENT",
    "MESSAGES_SENT_BY_HAND",
    "MESSAGE_METHODS",
    "METHODS",
    "NAMESPACES",
    "NOT_FOR_CLIENTS",
    "OWN_SESSION_ARG",
    "SCOPE_EXCEPTIONS",
    "UNFOLLOWED",
    "UNION_NAMES",
]

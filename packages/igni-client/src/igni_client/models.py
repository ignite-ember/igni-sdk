"""Every type igni-client sends or reads, as igni-core's RPC contract defines it.

GENERATED from igni-core's RPC contract (version 1) by igni-sdk's tools/client_codegen.py — do not edit. Run `make client-api` after refreshing contracts/rpc-contract.json.

Messages a client reads are `Event`s (a run's, `RunEvent`s); messages it
sends are `Frame`s; arguments are `Args`; everything else is a `Model`.
A model a client reads keeps a field a newer igni adds (`extra="allow"`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue

from igni_client.wire import Args, Event, Frame, Model, RunEvent

#: Closed set of actions a ``CommandResult`` can request.
#:
#: Was an unconstrained ``str`` field — comparisons in
#: ``app.py``/``commands.py`` used string literals like
#: ``"quit"``, ``"clear"``, which made typos silent (mismatched
#: arm would never fire) and made it hard to know the full
#: surface from one place. ``StrEnum`` keeps wire compatibility
#: (Pydantic serialises enum values to their strings) while
#: giving the dispatch sites a single authoritative list.
#:
#: There is deliberately no ``UNKNOWN`` member and no ``_missing_``
#: override here (unlike the ingest-side enums — see the module
#: docstring). Every ``CommandAction`` is stamped in-process by this
#: backend's own command handlers; nothing parses one back off the
#: wire on the Python side, so an unlisted value means a producer
#: typo and should raise at construction rather than degrade into a
#: silent no-op. ``NONE`` (``""``) is the real "no action" value.
type CommandAction = Literal[
    "",
    "quit",
    "clear",
    "fork",
    "sessions",
    "model",
    "model_switched",
    "login",
    "logout",
    "help",
    "mcp",
    "plugins",
    "extensions",
    "agents",
    "skills",
    "hooks",
    "loop",
    "schedule",
    "watcher",
    "compact",
    "ctx",
    "programs",
    "run_prompt",
]


#: How the FE should render a ``CommandResult.content`` payload.
#:
#: Was a free-string field so producers and consumers had to agree
#: on literals like ``"info"`` / ``"markdown"`` without any
#: type-checker help. Wire format stays string-compatible via
#: ``StrEnum``.
#:
#: * ``MARKDOWN`` — render as rich markdown (default for slash
#:   commands that emit long-form help text).
#: * ``INFO`` — single-line dim chat line (status updates,
#:   confirmations).
#: * ``ERROR`` — single-line red chat line.
#: * ``ACTION`` — no content to render directly; the FE
#:   dispatches off ``action`` to open a panel / picker / etc.
type CommandResultKind = Literal["markdown", "info", "error", "action"]


#: Which of the two paths a notification came by.
type NotificationOrigin = Literal["server", "local"]


#: Top-level permission posture for a session.
#:
#: Defaults to ``DEFAULT``. ``DONT_ASK`` is the headless/CI mode
#: (never prompt, deny unmatched). ``ACCEPT_EDITS`` auto-approves
#: file mutation tools. ``BYPASS_PERMISSIONS`` runs without
#: prompts unless an explicit deny / ask rule matches.
#: ``PLAN`` forbids source edits entirely.
type PermissionMode = Literal["default", "dontAsk", "acceptEdits", "bypassPermissions", "plan"]


#: User-recorded decision for a plan submitted via
#: ``exit_plan_mode``. Concrete values match the historic
#: wire strings so serialised blobs round-trip cleanly.
type PlanDecision = Literal["approved", "dismissed"]


#: Lifecycle of one scheduled task.
type TaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class AgentCompletedEvent(Model):
    """AgentCompletedEvent."""

    agent_path: str
    card_id: str | None = None
    input_tokens: int = 0
    is_error: bool = False
    output_tokens: int = 0
    reasoning_tokens: int = 0
    type: Literal["agent_completed"] = "agent_completed"


class AgentInfo(Model):
    """Wire format for one agent — emitted by
    :meth:`BackendServer.get_agent_details`, consumed by the
    agents panel.

    Sub-set of :class:`AgentDefinition` adapted for JSON transport:
    ``source_path`` is widened to ``str`` (Path doesn't serialize),
    and ``is_ephemeral`` is computed at the backend.
    """

    can_orchestrate: bool = True
    color: str = ""
    description: str = ""
    is_ephemeral: bool = False
    mcp_servers: list[str]
    model: str = ""
    name: str
    source_path: str = ""
    system_prompt: str = ""
    tags: list[str]
    tools: list[str]
    unknown_tools: list[str]


class AgentNameArgs(Args):
    """``discard_ephemeral_agent``: the ephemeral agent to drop."""

    name: str


class AgentPausedEvent(Model):
    """AgentPausedEvent."""

    agent_path: str
    card_id: str | None = None
    count: int = 1
    type: Literal["agent_paused"] = "agent_paused"


class AgentRunArgs(Args):
    """``cancel_agent_run``: the sub-agent run to stop (empty is refused
    by the controller).
    """

    run_id: str = ""


class AgentStartedEvent(Model):
    """AgentStartedEvent."""

    agent: str
    agent_path: str
    card_id: str | None = None
    parent: str | None = None
    run_id: str | None = None
    task: str | None = None
    type: Literal["agent_started"] = "agent_started"


class ApproverTokenMinted(Model):
    """``mint_approver_token``'s answer: the token, for the window that asked."""

    token: str


class ApproverTokensRevoked(Model):
    """``revoke_approver_tokens``'s answer: how many were forgotten."""

    revoked: int


class AssistantTurn(Model):
    """An assistant-visible-reply turn (may be one of many per run
    when the original stream interleaved ``<think>`` blocks).
    """

    content: str = ""
    created_at: int = 0
    role: Literal["assistant"] = "assistant"
    run_id: str = ""


class AttachSessionParams(Args):
    """``attach_session``: which session, and in which directory; empty for neither."""

    project_dir: str = ""
    session_id: str = ""


class AttachSessionResult(Model):
    """Wire shape for the ``attach_session`` RPC — the FE learns
    which session id + project directory the pool actually bound.
    """

    project_dir: str
    session_id: str


class BackgroundProcessDonePayload(Model):
    """Channel ``background_process_done``. Best-effort ping so the
    UI can badge the watcher panel when a backgrounded shell command
    finishes. The queue-injected assistant nudge carries the tail
    output; this payload is a lightweight header.
    """

    cmd: str
    duration_seconds: float
    exit_code: int | None
    pid: int | None


class BuiltinSlashCommand(Model):
    """A built-in slash command exposed to completion UIs."""

    argument_hint: str = ""
    description: str = ""
    name: str
    source: Literal["builtin"] = "builtin"


class Cancel(Frame):
    """Cancel current run.

    On the wire: ``cancel``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    type: Literal["cancel"] = "cancel"


class CancelAgentRunResult(Model):
    """Wire shape for :meth:`RunCoordinator.cancel_agent_run` —
    the FE renders a toast on ``ok=False`` so ``error``
    differentiates the unknown-run-id case from a live cancel
    error.
    """

    error: str = ""
    ok: bool


class CancelLogin(Frame):
    """Cancel an in-progress login flow.

    On the wire: ``cancel_login``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    type: Literal["cancel_login"] = "cancel_login"


class ChatSearchHit(Model):
    """One match returned by
    :meth:`SessionsController.search_chat` /
    :meth:`igni_core.backend.chat_history_searcher.ChatHistorySearcher.search`.

    Wire shape: ``{history_index, role, run_id, snippet, match_start,
    match_end, created_at}``. ``history_index`` MUST align with the
    emission order of :meth:`ChatHistoryRebuilder.rebuild` — the FE
    keeps a parallel ``historyIndex → itemIndex`` map built at
    session load, so any drift breaks the "click result → jump to
    chat item" mapping.

    ``match_start`` / ``match_end`` are positions within
    ``snippet`` (not the original content) — keeps the FE highlight
    logic trivial.
    """

    created_at: int = 0
    history_index: int = 0
    match_end: int = 0
    match_start: int = 0
    role: str = ""
    run_id: str = ""
    snippet: str = ""


class CheckPermissionArgs(Args):
    """``check_permission``: one tool call to look up a level for."""

    func_name: str
    tool_args: ToolCallArgs
    tool_name: str


class CloudPlan(Model):
    """Wire shape for :meth:`AuthController.get_cloud_plan` — tier +
    org name for the org popover badge. Nullable fields because the
    token validation response may omit either.
    """

    email: str | None = None
    full_name: str | None = None
    org_name: str | None
    tier: str | None


class Command(Frame):
    """Slash command from user.

    On the wire: ``command``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    text: str = ""
    type: Literal["command"] = "command"


class CommandResult(Event):
    """Result of a slash command.

    Canonical wire model. The single Python subclass
    :class:`igni_core.backend.command_result.CommandResult` inherits
    from this class, adds the semantic + generic classmethod factories
    (``markdown`` / ``info`` / ``error`` / ``fork`` / ``for_action``),
    and hangs the behaviour methods (``is_error`` / ``is_action`` /
    ``render_line``) on it — the backend class IS the wire model, so
    ``server.handle_command`` returns it directly instead of rebuilding
    a twin. See that module for the layering rationale (protocol is
    the leaf layer; backend depends on protocol, never vice versa).

    Fields are enum-typed (``CommandResultKind`` / ``CommandAction``)
    rather than free strings — Pydantic still serialises them to their
    string values on the wire, so FE parsers that key off literals
    like ``"markdown"`` / ``"quit"`` are unaffected. Producers gain
    autocompletion and typo-checking; a raw ``kind="markdon"`` now
    fails Pydantic validation instead of silently rendering as
    generic-info on the FE.

    ``display_content`` is the optional chat-render override for the
    ``run_prompt`` action: the loop slash command sets it to the
    unwrapped prompt while ``content`` carries the wrapped form
    (with the ``<loop-iteration>`` meta tag) for the agent. When
    empty, the FE displays ``content`` directly — the normal case
    for skill prompts and any other ``run_prompt`` action.

    On the wire: ``command_result``.
    """

    action: CommandAction = ""
    content: str = ""
    display_content: str = ""
    event_seq: int = 0
    id: str = ""
    kind: CommandResultKind = "info"
    session_id: str = ""
    type: Literal["command_result"] = "command_result"


class CompactIfNeededArgs(Args):
    """``compact_if_needed``: the turn's context size against its window."""

    ctx_tokens: int
    max_ctx: int


class CompleteFilesArgs(Args):
    """``complete_files``: the typed prefix and how many matches to return."""

    limit: int = 50
    query: str = ""


class ContentDelta(Event):
    """Streamed text chunk from the model.

    On the wire: ``content_delta``.
    """

    event_seq: int = 0
    id: str = ""
    is_thinking: bool = False
    session_id: str = ""
    text: str = ""
    type: Literal["content_delta"] = "content_delta"


class ContentPreviewEvent(Model):
    """ContentPreviewEvent."""

    agent_path: str
    card_id: str | None = None
    text: str
    type: Literal["content_preview"] = "content_preview"


class ContextBreakdown(Model):
    """Per-component token breakdown of the current context.

    ``total = runs + floor`` (``floor`` clamped to ``0`` in case
    of tokenizer inconsistency where ``runs`` > ``total``).
    Consumed by the ``/ctx`` slash command to explain the
    irreducible portion ``/compact`` cannot shrink.

    Construct via :meth:`from_totals` so the floor-clamp
    invariant lives on the model, not scattered at every call
    site.
    """

    floor: int
    runs: int
    total: int


class DialogAnswered(Model):
    """DialogAnswered."""

    answered: bool
    rev: int


class DialogShown(Model):
    """DialogShown."""

    dialog: dict[str, JsonValue]
    rev: int


class DirListResult(Model):
    """Wire shape for the ``list_dirs`` RPC — GUI folder browser."""

    dirs: list[str]
    error: str
    home: str
    parent: str
    path: str


class DiscardEphemeralResult(Model):
    """Typed result for :meth:`AgentsPanelController.discard`."""

    name: str
    ok: bool
    reason: str = ""


class DiscardInterruptedRunResult(Model):
    """Wire shape for :meth:`ContextController.discard_interrupted_run`.
    ``ok`` is ``False`` when the row didn't exist (idempotent — the
    FE can treat the row as gone regardless).
    """

    error: str = ""
    ok: bool


class DiscoverServerArgs(Args):
    """``discover_server`` RPC args: the address to look the server up from."""

    email: str


class DisplayConfig(Model):
    """DisplayConfig."""

    color_theme: str = "auto"
    markdown: bool = True
    message_truncate_lines: int = 10
    show_reasoning: bool = False
    show_routing: bool = False
    show_tool_calls: bool = True
    tool_result_preview_lines: int = 4


class ErrorMessage(Event):
    """Error message.

    On the wire: ``error``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    text: str = ""
    type: Literal["error"] = "error"


class ExecuteScheduledTaskArgs(Args):
    """``execute_scheduled_task``: what the task asks the agent to do."""

    description: str


class ExtensionIndicator(Model):
    """A status chip the host renders in its own chrome."""

    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    id: str
    interval_seconds: float = Field(default=30.0, alias="intervalSeconds")
    label: str
    opens: str = ""
    source: str


class ExtensionListResult(Model):
    """Every installed extension, in a stable order."""

    extensions: list[ExtensionSummary]


class ExtensionMenuEntry(Model):
    """ExtensionMenuEntry."""

    command: str
    desc: str
    label: str


class ExtensionPage(Model):
    """A surface the extension renders, as the sidebar needs it."""

    entry: str = "index.html"
    kind: str
    label: str
    sidebar: bool = False


class ExtensionSetting(Model):
    """One configurable value, as the host's settings surface needs it."""

    default: JsonValue = None
    """Any JSON value."""
    key: str
    label: str
    options: list[str]
    type: str


class ExtensionSlashCommand(Model):
    """A slash command an installed extension answers.

    Carries ``owner`` because a command that fails should be
    attributable: "/compliance did not answer" is a support ticket,
    and "acme.scanner did not answer /compliance" is a thing an
    administrator can act on.
    """

    argument_hint: str = ""
    description: str = ""
    name: str
    owner: str = ""
    source: Literal["extension"] = "extension"


class ExtensionSummary(Model):
    """One installed extension, as the frontend sees it."""

    allow: list[str]
    dropped: list[ExtensionSwitchedOff]
    faulty: str = ""
    host: list[str]
    id: str
    indicators: list[ExtensionIndicator]
    menu: list[ExtensionMenuEntry]
    name: str
    origin: str = ""
    pages: list[ExtensionPage]
    problems: list[str]
    reason: str = ""
    sandbox: str = ""
    service_url: str | None = None
    settings: list[ExtensionSetting]
    state: str
    switched_off: list[ExtensionSwitchedOff]
    tools: list[ExtensionTool]
    values: dict[str, JsonValue]
    version: str
    web_url: str | None = None


class ExtensionSwitchedOff(Model):
    """One thing an extension does not get, because it collides with another."""

    claim: str
    reason: str


class ExtensionTool(Model):
    """One tool an extension gives the agent, as the panel lists it."""

    hints: str
    name: str


class ExternalOpen(Model):
    """The ``open_external`` push: which window opens which link, for whom."""

    source: str
    url: str
    window: str


class ExtractLearningsArgs(Args):
    """``extract_learnings``: the turn's user and assistant messages."""

    assistant_msg: str
    user_msg: str


class FileCompletion(Model):
    """Wire shape for the ``complete_files`` RPC — @-mention picker
    hits + a running total (used to render "N more matches" when the
    limit was reached).
    """

    matches: list[str]
    total: int


class FileEditedPayload(Model):
    """Channel ``file_edited``. Fired every time an edit tool writes
    to disk. A client with an editor buffer can refresh it; neither
    the desktop app nor the web client acts on it today.
    """

    path: str


class FloorNotification(Model):
    """One notification, as the client draws it."""

    actor: str = ""
    body: str = ""
    created_at: datetime | None = None
    id: str
    kind: str = ""
    org_id: str = ""
    org_name: str = ""
    origin: NotificationOrigin
    read: bool = False
    source: str
    target: NotificationTarget | None = None
    title: str = ""


class GroupPolicyPackResult(Model):
    """Wire shape for the ``get_group_policy`` RPC — the active
    group's pack for the current user. Nullable because
    a user may belong to no group.
    """

    default_model: str | None = None
    entry_count: int = 0
    fetched_at: str | None = None
    group_id: str | None = None
    group_name: str | None = None


class HitlDecision(Frame):
    """One row inside a ``HITLResponseBatch``. See :class:`HITLResponse`
    for the ``action`` / ``choice`` typing note.

    ``set_permission_mode`` is an optional atomic-mode-flip: when
    set, the BE applies the named mode to the session BEFORE
    resuming the agent — so the very next tool check after the
    HITL pause resolves sees the new mode. Used by the FE's
    "Accept all edits during this session" shortcut: a previous
    version fired a separate ``/accept on`` slash command that
    raced the resume and lost ~half the time, causing the next
    edit to re-prompt instead of auto-approving. Default ``None``
    keeps the wire shape unchanged for existing clients.

    On the wire: ``hitl_decision``.
    """

    action: str = ""
    choice: str = ""
    event_seq: int = 0
    id: str = ""
    requirement_id: str = ""
    session_id: str = ""
    set_permission_mode: str = ""
    type: Literal["hitl_decision"] = "hitl_decision"


class Requirement(Event):
    """Permission dialog needed — BE pauses until FE responds.

    On the wire: ``hitl_request``.
    """

    agent_path: list[str]
    details: str = ""
    details_pending: bool = False
    event_seq: int = 0
    friendly_name: str = ""
    id: str = ""
    requirement_id: str = ""
    session_id: str = ""
    tool_args: dict[str, JsonValue]
    tool_name: str = ""
    type: Literal["hitl_request"] = "hitl_request"


class HitlResponse(Frame):
    """User responded to a permission dialog.

    ``action`` / ``choice`` stay as raw ``str`` on the wire; use
    :class:`HITLAction` / :class:`HITLChoice` members at producer
    callsites for autocompletion + typo-checking. ``StrEnum``
    coerces to the underlying string on assignment.

    On the wire: ``hitl_response``.
    """

    action: str = ""
    choice: str = ""
    event_seq: int = 0
    id: str = ""
    requirement_id: str = ""
    session_id: str = ""
    type: Literal["hitl_response"] = "hitl_response"


class HitlResponseBatch(Frame):
    """User responded to *every* requirement in a multi-req pause.

    Agno's ``acontinue_run`` treats requirements not in the resolution
    list as denied, so a per-req resolve loop dropped 7-of-8 calls in
    a batched tool plan. The batch envelope carries every decision in
    one round-trip so the backend can call ``acontinue_run`` exactly
    once with the full set of resolved requirements.

    On the wire: ``hitl_response_batch``.
    """

    decisions: list[HitlDecision] = Field(default_factory=list)
    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    type: Literal["hitl_response_batch"] = "hitl_response_batch"


class HookEntryView(Model):
    """Flat, wire-friendly view of one hook for the hooks panel.

    The heterogeneous ``session.hooks_map`` may hold command hooks,
    HTTP hooks, MCP-tool hooks etc. — this projection collapses the
    union into a single dict-shaped record. Fields not applicable
    to a given hook type default to empty (``command`` on an HTTP
    hook, ``url`` on a command hook, etc.).
    """

    background: bool = False
    command: str = ""
    event: str
    header_names: list[str]
    matcher: str = ""
    timeout_ms: int = 0
    type: str = ""
    url: str = ""


class HostSignal(Model):
    """The ``host_signal`` push: one signal for one extension's pages."""

    extension_id: str
    signal: str
    value: JsonValue = None
    """Any JSON value."""


class HttpRetryAttemptPayload(Model):
    """The ``http_retry_attempt`` broadcast, sent before each retry."""

    attempt: int
    delay_seconds: float


class HttpRetrySucceededPayload(Model):
    """The ``http_retry_succeeded`` broadcast, sent when a fetch
    succeeds after at least one retry.
    """

    attempt_count: int
    delay_seconds: float
    url: str


class Hydrated(Model):
    """The whole model, its revision, and the fields nobody set."""

    rev: int
    state: dict[str, JsonValue]
    unset: list[str]


class InfoMessage(Event):
    """Informational message.

    On the wire: ``info``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    text: str = ""
    type: Literal["info"] = "info"


class InstallPluginArgs(Args):
    """``install_plugin``: a git URL or ``@<marketplace>/<plugin>`` ref,
    and the branch / tag / SHA to check out (the default when absent).
    """

    install_ref: str | None = None
    ref: str


class InterruptedRun(Model):
    """Wire shape for one explicitly-interrupted run surfaced by
    :meth:`ContextController.get_interrupted_runs`.

    A row is "interrupted" when the cancel or error path in
    :class:`RunController` stamped it with ``interrupted_at`` and
    ``interrupted_reason``. The FE renders this as the banner on
    the assistant bubble that was in-flight when the run stopped,
    with Retry / Discard / Edit-prompt actions.

    ``reason`` is the storage column's :data:`InterruptedReason`.
    ``last_error`` is set when
    ``reason == "errored"`` and ``None`` otherwise.
    """

    content: str
    interrupted_at: int
    last_error: str | None = None
    message_id: str
    reason: Literal["cancelled", "errored", "abandoned"]
    received_at: int


class InterruptedRunArgs(Args):
    """``discard_interrupted_run``: one interrupted run of one session.
    An empty ``message_id`` reaches the controller, which refuses it.
    """

    message_id: str
    session_id: str


class LatestPlanResult(Model):
    """Wire shape for :meth:`PlanSnapshotBuilder.latest` — the
    plan-mode panel reads this on open + after each ``exit_plan_mode``.

    ``state`` is ``"pending"`` when a plan exists (user hasn't
    approved/dismissed yet) or ``""`` when no plan submitted.
    ``tasks`` mirrors :attr:`TodoStore.items` (each row dumps
    ``activeForm`` camelCase on its own, see :class:`TodoItemWire`) so the FE renders the plan and task list from a
    single payload.
    """

    history: list[str]
    latest: str = ""
    state: Literal["pending", "approved", "dismissed", ""] = ""
    tasks: list[TodoItem]


class ListDirsArgs(Args):
    """``list_dirs``: the folder to list (the home folder when absent or
    empty) and whether dot-dirs are shown.
    """

    path: str | None = None
    show_hidden: bool = False


class LoginResultPayload(Model):
    """Channel ``login_result``. Terminal result of a login attempt
    (success + reason string). Pushed after the RPC ack, once the
    Anthropic OAuth flow completes.
    """

    result: str
    success: bool


class LoginStarted(Model):
    """Wire shape for the ``login`` RPC — one-field ack that a login
    task is now in flight; the actual result arrives asynchronously
    via a ``login_result`` push notification.
    """

    started: bool


class LoginStatusPayload(Model):
    """Channel ``login_status``. Human-readable status text streamed
    while a login attempt is in flight.
    """

    text: str


class LoopAdvance(Model):
    """Wire shape for :meth:`LoopController.advance_loop`.

    Three effective variants, discriminated by ``kind``:

    * ``kind="completed"`` — explicit cap hit; ``total_iterations``
      carries the final count.
    * ``kind="safety_paused"`` — implicit loop hit ``LOOP_HARD_CAP``;
      ``iteration`` carries the count reached.
    * ``kind="step"`` — normal advance: ``prompt`` /
      ``display_prompt`` / ``iteration`` / ``remaining`` /
      ``cap_explicit`` populated. ``auto_extended`` flags the
      one-shot iteration right after the implicit safety net rolled
      over.

    Flat shape (rather than a tagged union) so wire consumers keep
    the same JSON payload; a model-level validator enforces that
    each ``kind`` only carries its own fields. Build via the three
    named classmethods — they are the only spellings
    :class:`LoopController` uses.
    """

    auto_extended: bool = False
    cap_explicit: bool = False
    completed: bool = False
    display_prompt: str = ""
    iteration: int = 0
    kind: Literal["completed", "safety_paused", "step"] = "step"
    prompt: str = ""
    remaining: int = 0
    safety_cap_paused: bool = False
    total_iterations: int = 0


class LoopStatusSnapshot(Model):
    """RPC wire shape for :meth:`LoopController.status`.

    Renamed from the old inline ``LoopStatus`` (in ``server_loop.py``)
    to avoid colliding with the sibling :class:`LoopStatusView` chat
    card in this same module. Same eight fields, same wire contract
    (the RPC layer serialises via ``.model_dump()`` so the FE JSON
    payload is byte-identical).

    ``from_session`` is the canonical constructor — it encapsulates
    the announced-total lookup on :class:`LoopProgressStore` so
    :class:`LoopController` doesn't have to know that the total lives
    on a per-run key/value store.
    """

    active: bool
    announced_total: int | None
    cap_explicit: bool
    iteration_index: int
    iterations_remaining: int
    paused: bool
    prompt: str


class McpPrompt(Model):
    """Wire shape for one MCP prompt entry.

    ``arguments`` is a flat ``list[str]`` of argument names —
    the panel only needs the identity list, not the full
    argument metadata. If a future consumer needs the type /
    required-flag columns, add fields here and update
    :meth:`from_sdk` to project them.
    """

    arguments: list[str]
    description: str = ""
    name: str


class McpResource(Model):
    """Wire shape for one MCP resource entry.

    Fields are the four columns the panel actually renders —
    ``uri`` is the only required identity field, the rest
    default to ``""`` so servers that omit optional metadata
    still serialize cleanly.
    """

    description: str = ""
    mime_type: str = ""
    name: str = ""
    uri: str


class McpServerSnapshot(Model):
    """Full expanded-row payload returned by
    :meth:`McpController.server_details`.

    Nine wire fields — preserved verbatim from the previous
    raw-dict shape:

    * ``name`` — server key from the config file.
    * ``connected`` — currently in ``mgr.list_connected()``.
    * ``transport`` — ``config.type`` (``stdio`` / ``sse``) or
      ``"unknown"`` if no config was found.
    * ``tool_names`` — every tool the server advertised at connect
      time (including individually-disabled ones).
    * ``tool_descriptions`` — ``{tool_name: description}``.
    * ``tools_disabled`` — tools the user has toggled off.
    * ``resources`` — MCP ``list_resources`` result (async fetch),
      typed as :class:`MCPResource` for the wire.
    * ``prompts`` — MCP ``list_prompts`` result (async fetch),
      typed as :class:`MCPPrompt` for the wire.
    * ``error`` — last connection error string, or ``""``.
    * ``policy_blocked`` — managed policy denies this server.
    """

    connected: bool
    error: str = ""
    name: str
    policy_blocked: bool = False
    prompts: list[McpPrompt]
    resources: list[McpResource]
    tool_descriptions: dict[str, str]
    tool_names: list[str]
    tools_disabled: list[str]
    transport: str


class McpServerSummary(Model):
    """Cheap two-field ``(name, connected)`` row returned by
    :meth:`McpController.servers`.

    Used when the panel just needs the connected-flag column
    without paying for the tools / resources / prompts fetch
    per row.
    """

    connected: bool
    name: str


class McpToggle(Frame):
    """Toggle MCP server connection.

    On the wire: ``mcp_toggle``.
    """

    connect: bool = True
    event_seq: int = 0
    id: str = ""
    server_name: str = ""
    session_id: str = ""
    type: Literal["mcp_toggle"] = "mcp_toggle"


class McpToolToggleResult(Model):
    """Wire shape for :meth:`McpController.set_tool_enabled` —
    the panel reads it back to confirm the row's new state without
    needing a second RPC roundtrip.
    """

    enabled: bool
    server: str
    tool: str


class MarkReadArgs(Args):
    """``notifications_mark_read``: ``{ids}``, ``{source}``, or ``{}`` for all."""

    ids: list[str] | None = None
    source: str | None = None


class MarkdownSlashCommand(Model):
    """A user-authored ``.md`` slash command (CC-parity file drop)."""

    argument_hint: str = ""
    description: str = ""
    name: str
    source: Literal["markdown"] = "markdown"


class MarketplaceInfo(Model):
    """Wire format for one registered marketplace — registry-level
    metadata plus the cached catalog at the time of the last fetch.
    """

    last_fetched: str = ""
    name: str
    plugins: list[MarketplacePluginInfo] = Field(default_factory=list)
    url: str


class MarketplaceNameArgs(Args):
    """``remove_marketplace``: the registered marketplace to drop."""

    name: str


class MarketplacePluginInfo(Model):
    """Wire format for one plugin entry inside a marketplace catalog."""

    branch: str = ""
    description: str = ""
    name: str
    source: str
    version: str = ""


class MarketplaceUrlArgs(Args):
    """``add_marketplace``: the catalog's URL."""

    url: str


class McpInitResult(Model):
    """Pattern-3 envelope returned by :meth:`McpInitPhase.ensure`
    (forwarded by :meth:`SessionStartupCoordinator.ensure_mcp`).

    Callers used to grep the log stream to know how many servers
    connected on first-message init. The envelope surfaces the
    same information at the return-value boundary so RPC clients
    (``BackendServer.ensure_mcp`` / ``McpController.ensure``) can
    project it back to the FE without side-channel scraping.

    Fields:

    * ``connected`` — sorted names of servers that came online.
    * ``failed`` — mapping ``name → error string`` for each server
      whose ``connect`` returned ``None``.
    * ``rebuilt`` — ``True`` iff the agent pool + main team were
      rebuilt with at least one live client (matches the pre-
      refactor log line "agents + main team rebuilt").
    * ``skipped_reason`` — set when :meth:`ensure` short-circuited
      before reaching the connect loop. ``None`` when a connect
      pass was actually executed.
    """

    connected: list[str]
    failed: dict[str, str]
    rebuilt: bool = False
    skipped_reason: (
        Literal["already_initialized", "no_configured_servers", "no_clients_connected"] | None
    ) = None


class McpServerArgs(Args):
    """``mcp_connect`` / ``mcp_disconnect``: the server to act on."""

    server_name: str


class McpServerStatus(Model):
    """Typed row for :meth:`McpLifecycleCoordinator.status`.

    Replaces the raw ``(name, connected)`` tuple so consumers
    (backend RPC, TUI panel) reach for named attributes instead
    of positional indexing.
    """

    connected: bool
    name: str


class McpToolEnabledArgs(Args):
    """``set_mcp_tool_enabled``: one tool of one server, on or off."""

    enabled: bool
    server: str
    tool: str


class ModelCompleted(RunEvent):
    """Model finished — token counts available.

    On the wire: ``model_completed``.
    """

    event_seq: int = 0
    id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    parent_run_id: str = ""
    run_id: str = ""
    session_id: str = ""
    type: Literal["model_completed"] = "model_completed"


class ModelRegistryEntryView(Model):
    """One model as a client sees it: what it is and how it runs, never its key.

    :class:`ModelRegistryEntry` holds the key itself (``api_key``), the
    command that prints it (``api_key_cmd``), and whatever extra keys the
    configuration carried; none of that is a client's to read. The URL
    loses anything that can carry a credential.
    """

    context_window: int | None = None
    effort: str | None = None
    has_api_key: bool
    max_tokens: int | None = None
    model_id: str
    prompt_caching: bool
    provider: str
    source: str = ""
    temperature: float | None = None
    thinking: dict[str, JsonValue] | None = None
    timeout: int
    url: str | None = None
    vision: bool


class ModelRegistryResult(Model):
    """Wire shape for the ``get_model_registry`` RPC — the FE's
    model-picker source of truth (default, ceiling, per-model
    metadata rows).
    """

    default: str
    max_context_window: int
    registry: dict[str, ModelRegistryEntryView]


class ModelSwitch(Frame):
    """Switch model.

    On the wire: ``model_switch``.
    """

    event_seq: int = 0
    id: str = ""
    model_name: str = ""
    session_id: str = ""
    type: Literal["model_switch"] = "model_switch"


class NoArgs(Args):
    """The arguments of a call that takes none: ``{}``."""


class NotificationCounts(Model):
    """Unread, in all and per source — the badge on each extension."""

    by_source: dict[str, int]
    unread: int = 0


class NotificationTarget(Model):
    """Where opening a notification goes: one of its extension's pages."""

    page: str = Field(min_length=1)
    params: dict[str, str]


class NotificationsChanged(Model):
    """The ``notifications_changed`` push: the counts moved."""

    counts: NotificationCounts


class NotificationsListResult(Model):
    """``notifications_list``: both paths, newest first, and the counts."""

    counts: NotificationCounts
    notifications: list[FloorNotification]
    server_error: str = ""


class NotificationsReadResult(Model):
    """``notifications_mark_read``: the counts after marking."""

    counts: NotificationCounts
    server_error: str = ""


class OutputStyleChangedPayload(Model):
    """The ``output_style_changed`` broadcast, emitted by
    :meth:`RuntimeModeCoordinator.set_output_style` after the
    active style has been swapped. The FE refreshes the status
    chip that shows the active style without polling.
    """

    previous: str
    style: str


class OutputStyleInfo(Model):
    """One output-style entry in :attr:`OutputStylesResult.styles`."""

    description: str
    name: str


class OutputStylesResult(Model):
    """Wire shape for :meth:`OutputStylesCatalog.snapshot` —
    discovered styles + the currently-applied one for the picker
    chip.
    """

    active: str
    styles: list[OutputStyleInfo]


class PendingMessage(Model):
    """One pre-persisted user message row surfaced by
    :meth:`ContextController.get_pending_messages`. ``role`` is
    always ``"user"`` — only user turns get pre-persisted.

    Build one from a storage-row dataclass via
    :meth:`from_pending_row`.
    """

    content: str
    message_id: str
    received_at: int
    role: Literal["user"] = "user"


class PermissionModeChangedPayload(Model):
    """The ``permission_mode_changed`` broadcast, emitted by
    :meth:`RuntimeModeCoordinator.set_permission_mode` after the
    live :class:`PermissionEvaluator` mode flip.
    """

    mode: PermissionMode
    previous: PermissionMode


class PickDirArgs(Args):
    """``pick_dir_native``: where the OS picker opens (the project folder
    when absent or empty).
    """

    start: str | None = None


class PickDirResult(Model):
    """Wire shape for the ``pick_dir_native`` RPC — OS folder picker."""

    cancelled: bool
    error: str
    path: str


class PlanDecidedPayload(Model):
    """The ``plan_decided`` broadcast. The FE listens on this
    channel to flip the plan card from pending to
    approved/dismissed.
    """

    decision: PlanDecision
    run_id: str


class PlanDecisionResult(Model):
    """Pattern-3 envelope for :meth:`PlanCoordinator.approve` /
    :meth:`PlanCoordinator.dismiss`.

    Surfaced to the FE via the ``APPROVE_PLAN`` / ``DISMISS_PLAN``
    RPCs; the transport serializer auto-converts via
    :meth:`model_dump` so the wire keeps its dict shape.

    Fields:

    * ``run_id`` — the run in which ``exit_plan_mode`` was
      called; identifies the specific plan the user decided on.
    * ``decision`` — the :class:`PlanDecision` StrEnum value the
      user chose (``"approved"`` / ``"dismissed"``). StrEnum
      dumps as its ``.value`` on the wire so existing consumers
      keying on ``"approved"`` / ``"dismissed"`` are unaffected.
    * ``mode_status`` — human-readable one-line summary of any
      permission-mode change triggered by the decision (empty
      for dismiss; ``"mode → default"``-shaped for approve).
    * ``ok`` — ``True`` on success; ``False`` when the
      coordinator refused the record (empty run_id, missing
      plan_store, missing persistence, or DB failure on the
      flip path). Callers key on this to surface an inline
      error to the FE.
    * ``error`` — human-readable error string when ``ok=False``;
      ``None`` on success.
    """

    decision: PlanDecision
    error: str | None = None
    mode_status: str = ""
    ok: bool = True
    run_id: str


class PlanModeEnteredPayload(Model):
    """The ``permission_mode_changed`` broadcast the plan tool fires
    after switching into plan mode. The base flip is already
    broadcast by :class:`RuntimeModeCoordinator`; this follow-up
    carries the agent-attribution + reason string the FE renders as
    a small banner.
    """

    mode: Literal["default", "plan", "acceptEdits", "bypassPermissions"]
    reason: str = ""
    source: Literal["agent", "user"]


class PlanRunArgs(Args):
    """``approve_plan`` / ``dismiss_plan``: the run that submitted the plan.
    Empty is refused in the answer (``ok: false``), not as an argument; a
    number is taken as its string.
    """

    run_id: str = ""


class PlanSubmittedPayload(Model):
    """The ``plan_submitted`` broadcast queued by
    :meth:`PlanTool.exit_plan_mode`. ``tasks`` rides along so
    the FE seeds the PlanCard checklist on first render — later
    ``todos_updated`` pushes refresh statuses live.

    The rows are :class:`TodoItemWire` checklist rows — the same
    shape the ``todos_updated`` broadcast carries, so the FE reads
    one row type for both channels.
    """

    plan: str
    run_id: str | None = None
    tasks: list[TodoItem]


class PlanTurn(Model):
    """A PlanCard turn synthesized in place of an ``exit_plan_mode``
    tool result. ``state`` uses the empty-string sentinel during
    the walk — the post-walk pass rewrites it to
    ``"pending"``/``"approved"``/``"dismissed"``. The empty-string
    default is preserved (rather than ``None``) so the wire dump
    keeps the same shape the FE reads today.
    """

    created_at: int = 0
    plan: str = ""
    role: Literal["plan"] = "plan"
    run_id: str = ""
    state: Literal["pending", "approved", "dismissed", ""] = ""
    tasks: list[JsonValue]


class PluginAgentInfo(Model):
    """One agent entry in :attr:`PluginContents.agents`."""

    description: str = ""
    name: str


class PluginContents(Model):
    """Wire shape returned by :meth:`PluginDirectoryScanner.scan`
    (and the
    :meth:`igni_core.backend.plugin_controller.PluginController.preview`
    marketplace-preview path that unwraps a clone into the same
    shape).

    ``error`` is populated when the caller failed to construct
    the payload (plugin not found, git clone failed, etc.) — in
    that case the collection fields stay empty and the FE renders
    the error card.

    ``preview_source`` carries the structured ``(url, subdir)`` for
    preview payloads coming from the marketplace card so the FE can
    reconstruct the display without regex-parsing ``root_path``.
    Only populated by the preview path — the installed-plugin path
    leaves it ``None``.
    """

    agents: list[PluginAgentInfo] = Field(default_factory=list)
    error: str = ""
    hooks: list[PluginHookInfo] = Field(default_factory=list)
    mcp_servers: list[PluginMcpServerInfo] = Field(default_factory=list)
    name: str = ""
    preview_source: PluginPreviewSource | None = None
    readme: str = ""
    root_path: str = ""
    skills: list[PluginSkillInfo] = Field(default_factory=list)
    tools: list[PluginToolInfo] = Field(default_factory=list)


class PluginEnabledArgs(Args):
    """``set_plugin_enabled``: one installed plugin, on or off."""

    enabled: bool
    name: str


class PluginHookInfo(Model):
    """One hook-event entry in :attr:`PluginContents.hooks`.
    ``count`` is the number of handlers registered for the
    event.
    """

    count: int
    event: str


class PluginInfo(Model):
    """Wire format for one installed plugin — emitted by
    :meth:`BackendServer.get_plugin_details`, consumed by the
    plugins panel.
    """

    description: str = ""
    enabled: bool = True
    has_agents: bool = False
    has_hooks: bool = False
    has_lsp: bool = False
    has_mcp: bool = False
    has_monitors: bool = False
    has_skills: bool = False
    has_tools: bool = False
    managed: bool = False
    name: str
    path: str = ""
    pin: str = ""
    source_root: str = ""
    version: str = ""


class PluginMcpServerInfo(Model):
    """One MCP-server entry in :attr:`PluginContents.mcp_servers`."""

    command: str
    name: str
    transport: str


class PluginNameArgs(Args):
    """``get_plugin_contents`` / ``remove_plugin``: the installed plugin
    to act on.
    """

    name: str


class PluginPreviewSource(Model):
    """Structured form of the marketplace's ``"<url> [<subdir>]"``
    display string — parses back to (url, subdir) and formats back
    out. Single source of truth for the round-trip.
    """

    subdir: str = ""
    url: str


class PluginSkillInfo(Model):
    """One skill entry in :attr:`PluginContents.skills`."""

    description: str = ""
    name: str


class PluginToolInfo(Model):
    """One custom-tool entry in :attr:`PluginContents.tools`."""

    name: str


class PreviewPluginArgs(Args):
    """``preview_plugin``: the git source of a not-yet-installed plugin,
    with an optional branch and subdirectory inside the repo.
    """

    branch: str | None = None
    source: str
    subdir: str | None = None


class ProcessArgs(Args):
    """``stop_background_process``: the background process to stop."""

    pid: int


class ProcessExitedPayload(Model):
    """Channel ``process_exited``. A background process finished —
    the watcher panel flips its status pill.
    """

    cmd: str | None
    duration_seconds: float | None
    exit_code: int | None
    pid: int | None


class ProcessLinePayload(Model):
    """Channel ``process_line``. One line of stdout/stderr from a
    running background process (streamed live to the watcher panel).
    """

    line: str | None
    pid: int | None


class ProcessRow(Model):
    """One row of :meth:`ProcessesController.list`.

    ``is_running`` / ``exit_code`` default to "running" so an older
    client that predates them — and the test fixtures that build rows
    by hand — read a listed row the way they always did.
    """

    cmd: str
    elapsed_seconds: float
    exit_code: int | None = None
    is_running: bool = True
    pid: int


class ProcessStartedPayload(Model):
    """Channel ``process_started``. Emitted when the shell tool
    launches a new background process.
    """

    cmd: str | None
    pid: int | None
    started_at: float | None


class ProcessTailArgs(Args):
    """``read_process_tail``: the background process and how many lines."""

    pid: int
    tail: int = 200


class ProcessTailResult(Model):
    """Wire shape for :meth:`ProcessesController.read_tail`."""

    exit_code: int | None
    is_running: bool
    output: str
    pid: int


class PromoteAgentArgs(Args):
    """``promote_ephemeral_agent``: the agent, and ``"project"`` (the
    default) or ``"personal"``.
    """

    name: str
    target: str | None = None


class PromoteEphemeralResult(Model):
    """Typed result for :meth:`AgentsPanelController.promote`.

    Replaces the stringly-typed ``msg.Info(text=...)`` return that
    used to conflate success and failure. ``ok=False`` +
    ``reason=...`` carries the caught exception message; ``ok=True``
    + ``dest=...`` carries the persisted file path.
    """

    dest: str = ""
    name: str
    ok: bool
    reason: str = ""


class PushNotification(Event):
    """BE→FE push for callbacks (scheduler, progress, login status,
    permission-mode changes, background processes, file edits, …).

    The ``channel`` field discriminates which producer emitted the
    push; the FE routes on ``channel`` to render / dispatch. See
    :class:`PushChannel` for the catalogue of known channels — the
    producer set is open, so treat anything unlisted as a channel
    this module simply hasn't catalogued yet, not as invalid.

    Producers should prefer the :func:`push_*` factory helpers over
    hand-building the class — they take a typed payload model and
    dump it at the seam, matching every existing callsite's shape
    while keeping the boilerplate to one line.

    On the wire: ``push_notification``.
    """

    channel: str = ""
    event_seq: int = 0
    id: str = ""
    payload: dict[str, JsonValue]
    session_id: str = ""
    type: Literal["push_notification"] = "push_notification"


class QueueMessage(Frame):
    """User types while agent is running.

    On the wire: ``queue_message``.
    """

    client_id: str = ""
    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    text: str = ""
    type: Literal["queue_message"] = "queue_message"


class RpcRequest(Frame):
    """Generic RPC call for accessor/utility methods.

    On the wire: ``rpc_request``.
    """

    args: dict[str, JsonValue] = Field(default_factory=dict)
    caller: str | None = None
    event_seq: int = 0
    id: str = ""
    method: str = ""
    session_id: str = ""
    type: Literal["rpc_request"] = "rpc_request"


class RpcResponse(Event):
    """Response to an RPCRequest.

    Carries either ``result`` (success) or ``error`` (failure) —
    never both, but the invariant is by convention. Use the
    :classmethod:`ok` / :classmethod:`fail` factories to construct
    responses safely; they enforce the shape at the callsite.

    On the wire: ``rpc_response``.
    """

    error: str | None = None
    event_seq: int = 0
    id: str = ""
    result: JsonValue = None
    """Any JSON value."""
    session_id: str = ""
    type: Literal["rpc_response"] = "rpc_response"


class ReadFileArgs(Args):
    """``read_file``: the project file to read."""

    path: str


class ReadFileResult(Model):
    """Wire shape for :meth:`FilesController.read_file` — sandboxed
    FE preview.

    ``error`` is empty on success; ``language`` is the detected
    highlight hint (extension → name mapping) and stays empty on
    every non-success path so the FE never mis-highlights an
    error payload.
    """

    contents: str
    error: str = ""
    language: str = ""
    path: str
    size: int


class ReasoningStarted(RunEvent):
    """Model entered reasoning/thinking phase.

    On the wire: ``reasoning_started``.
    """

    event_seq: int = 0
    id: str = ""
    parent_run_id: str = ""
    run_id: str = ""
    session_id: str = ""
    type: Literal["reasoning_started"] = "reasoning_started"


class RefreshMarketplacesArgs(Args):
    """``refresh_marketplaces``: one marketplace, or every one when absent."""

    name: str | None = None


class RequirementDetails(Event):
    """The reason for an open HITL requirement, sent after its dialog.

    The Bypass safety check raises its dialog with ``details_pending``
    and no text, then sends this once the model has described the call
    (or with the plain reason when it could not). Views swap the
    spinner for ``details`` in place.

    On the wire: ``requirement_details``.
    """

    details: str = ""
    event_seq: int = 0
    id: str = ""
    requirement_id: str = ""
    session_id: str = ""
    type: Literal["requirement_details"] = "requirement_details"


class RequirementResolved(Event):
    """Broadcast when a HITL requirement is decided by any view, so
    the other views dismiss their (now stale) permission dialogs.

    On the wire: ``requirement_resolved``.
    """

    event_seq: int = 0
    id: str = ""
    requirement_id: str = ""
    session_id: str = ""
    type: Literal["requirement_resolved"] = "requirement_resolved"


class Revised(Model):
    """A change that answers nothing but the window's new revision."""

    rev: int


class RunCompleted(RunEvent):
    """An agent/team run has finished.

    On the wire: ``run_completed``.
    """

    duration: float = 0.0
    event_seq: int = 0
    id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    parent_run_id: str = ""
    reasoning_tokens: int = 0
    run_id: str = ""
    session_id: str = ""
    type: Literal["run_completed"] = "run_completed"


class RunError(Event):
    """Run-level error.

    On the wire: ``run_error``.
    """

    error: str = ""
    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    type: Literal["run_error"] = "run_error"


class RunErrorEvent(Model):
    """RunErrorEvent."""

    agent_path: str
    card_id: str | None = None
    error: str
    type: Literal["run_error"] = "run_error"


class RunPaused(RunEvent):
    """Run paused for HITL — wraps hitl_request with run context.

    On the wire: ``run_paused``.
    """

    event_seq: int = 0
    id: str = ""
    parent_run_id: str = ""
    requirements: list[Requirement]
    run_id: str = ""
    session_id: str = ""
    type: Literal["run_paused"] = "run_paused"


class RunShellArgs(Args):
    """``run_shell``: the ``$``-prefixed command line."""

    command: str = ""


class RunShellResult(Model):
    """Wire shape for the ``run_shell`` RPC — ``$``-prefix shell mode."""

    exit_code: int
    output: str


class RunStarted(RunEvent):
    """An agent/team run has begun.

    On the wire: ``run_started``.
    """

    agent_name: str = ""
    event_seq: int = 0
    id: str = ""
    model: str = ""
    parent_run_id: str = ""
    run_id: str = ""
    session_id: str = ""
    type: Literal["run_started"] = "run_started"


class SavePermissionRuleArgs(Args):
    """``save_permission_rule``: a rule and the level it is saved under."""

    level: Literal["allow", "ask", "deny"]
    rule: str


class ScheduledTask(Model):
    """A task scheduled for deferred execution.

    For recurring tasks, ``recurrence`` holds the repeat pattern in the
    canonical ``every N <minutes|hours|days|weeks>`` form ("every 1
    hours", "every 1 days", "every 7 days") — that is the only form the
    field validator below accepts. User-facing phrases ("daily",
    "weekly") are not valid here; run them through
    :meth:`Recurrence.parse` and persist ``.canonical()``. After
    completion, the runner creates the next occurrence automatically.
    """

    created_at: datetime
    description: str
    error: str = ""
    id: str
    recurrence: str = ""
    result: str = ""
    scheduled_at: datetime
    status: TaskStatus = "pending"


class ScheduledTaskArgs(Args):
    """``cancel_scheduled_task``: the task to cancel."""

    task_id: str


class ScheduledTasksArgs(Args):
    """``get_scheduled_tasks``: whether finished tasks are listed too."""

    include_done: bool = True


class SchedulerCompletedPayload(Model):
    """Channel ``scheduler_completed``. Terminal result of a
    scheduled task's execution.
    """

    description: str
    result: str
    task_id: str


class SchedulerEvent(Event):
    """Notification about a scheduled task.

    ``event_type`` stays a raw ``str`` on the wire; producers
    SHOULD use :class:`SchedulerEventType` members (``STARTED`` /
    ``COMPLETED`` / ``FAILED`` / ``ERROR``). Kept as ``str`` for
    forward-compat with any un-enumerated event kind Agno / a
    future scheduler emits.

    On the wire: ``scheduler_event``.
    """

    description: str = ""
    event_seq: int = 0
    event_type: str = ""
    id: str = ""
    result: str = ""
    session_id: str = ""
    task_id: str = ""
    type: Literal["scheduler_event"] = "scheduler_event"


class SchedulerStartedPayload(Model):
    """Channel ``scheduler_started``. The scheduled-task runner just
    picked up a task and started executing it.
    """

    description: str
    task_id: str


class SearchChatArgs(Args):
    """``search_chat``: the text to find in one session's history, and
    at most how many hits to return.
    """

    limit: int = 50
    query: str
    session_id: str


class SearchCodeArgs(Args):
    """``search_code``: the snippet to find across the project.

    A key it does not name is refused, not ignored: a call that sent the
    snippet under another name (``snippet``) was told only that ``query``
    was missing, and searched for nothing.
    """

    query: str


class SearchCodeMatch(Model):
    """One hit in :attr:`SearchCodeResult.matches`."""

    end_line: int
    line: int
    path: str
    preview: str


class SearchCodeResult(Model):
    """Wire shape for :meth:`SearchController.search_code` —
    composer paste decoration. ``truncated`` is True whenever the
    max-results cap was hit (or a search timed out) so the FE can
    render "and N more…". ``error`` is empty on success paths.
    """

    error: str = ""
    matches: list[SearchCodeMatch] = Field(default_factory=list)
    truncated: bool = False


class ServerChoice(Model):
    """``set_server`` RPC result: the server written down, or why it
    was refused. ``error`` is empty on success.
    """

    api_url: str = ""
    error: str = ""
    portal_url: str = ""


class ServerFound(Model):
    """``discover_server`` RPC result: where an address's organisation
    runs igni, or — with every URL empty — why nothing usable was
    published (``reason``).
    """

    api_url: str = ""
    portal_url: str = ""
    reason: str = ""
    source: str = ""


class SessionCleared(Event):
    """Session was compacted or cleared.

    On the wire: ``session_cleared``.
    """

    event_seq: int = 0
    id: str = ""
    new_session_id: str = ""
    session_id: str = ""
    summary: str = ""
    type: Literal["session_cleared"] = "session_cleared"


class SessionIdArgs(Args):
    """``get_chat_history`` / ``get_pending_messages`` / ``get_interrupted_runs`` /
    ``switch_session``: the session to act on.
    """

    session_id: str


class SessionList(Frame):
    """Request session list.

    On the wire: ``session_list``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    type: Literal["session_list"] = "session_list"


class SessionListEntry(Model):
    """One row of :attr:`SessionListResult.sessions`.

    Wire shape produced by
    :meth:`~igni_core.core.session.schemas.SessionListRow.from_agno`:
    ``{session_id, name, created_at, updated_at, run_count, summary,
    agent_name}``. Kept permissive (``extra='allow'``) so a future
    field on the persistence side lands on the wire without a
    schema-drift error at the boundary — the FE tolerates unknown
    keys.

    Named ``SessionListEntry`` rather than ``SessionSummary`` to
    avoid collision with Agno's ``agno.session.summary.SessionSummary``,
    which is used in
    :mod:`igni_core.core.session.compaction`. Defined in this
    module (not ``backend/schemas_history.py``) because ``protocol``
    is the leaf layer — the backend depends on protocol, never
    the reverse — and :class:`SessionListResult` needs to reference
    this schema at the wire boundary.
    """

    agent_name: str = ""
    created_at: int = 0
    name: str = ""
    run_count: int = 0
    session_id: str = ""
    summary: str = ""
    updated_at: int = 0


class SessionListResult(Event):
    """Response to session_list request.

    On the wire: ``session_list_result``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    sessions: list[SessionListEntry]
    type: Literal["session_list_result"] = "session_list_result"


class SessionNamedPayload(Model):
    """Channel ``session_named``. The BE picked an auto-generated
    display name for a freshly-created session.
    """

    name: str
    session_id: str


class SessionSwitch(Frame):
    """Switch to a different session.

    On the wire: ``session_switch``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    type: Literal["session_switch"] = "session_switch"


class SetExtensionSettingsArgs(Args):
    """``set_extension_settings``'s arguments: whose settings, and the new values."""

    extension_id: str
    values: dict[str, JsonValue]


class SetServerArgs(Args):
    """``set_server`` RPC args. An empty ``portal_url`` means "derive it"."""

    api_url: str
    portal_url: str = ""


class Shutdown(Frame):
    """Graceful shutdown.

    On the wire: ``shutdown``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    type: Literal["shutdown"] = "shutdown"


class SkillDefinition(Model):
    """Wire shape for one entry in the ``get_skill_definitions`` RPC
    response. Consumed by the FE autocomplete + SDK skill picker;
    ``prompt`` may be empty for manifest-only skills.
    """

    description: str
    name: str
    prompt: str


class SkillInfo(Model):
    """Wire format for one skill — emitted by
    :meth:`BackendServer.get_skill_details`, consumed by the skills
    panel.

    JSON-friendly subset of :class:`SkillDefinition`: ``source_dir``
    widened to ``str`` (Path doesn't round-trip), ``body`` is sent
    in full so the panel can head-clip for preview without an extra
    RPC. No ``render`` method — wire models are read-only.
    """

    agent: str = ""
    argument_hint: str = ""
    body: str = ""
    category: str = "development"
    context: str = "inline"
    description: str = ""
    name: str
    source_dir: str = ""
    user_invocable: bool = True
    version: str = "0.1.0"


class SkillSlashCommand(Model):
    """A user-invocable skill exposed as a slash command."""

    argument_hint: str = ""
    description: str = ""
    name: str
    source: Literal["skill"] = "skill"


class StatsTurn(Model):
    """The per-run input/output token badge. ``duration`` stays a
    float even when zero — the FE consumer treats ``0`` and
    ``0.0`` interchangeably but the persisted wire is float. No
    ``created_at`` on the wire (matches the pre-refactor output).
    """

    duration: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    role: Literal["stats"] = "stats"
    run_id: str = ""


class StatusUpdate(Event):
    """Status bar data pushed from BE.

    On the wire: ``status_update``.
    """

    cloud_connected: bool = False
    cloud_email: str = ""
    cloud_name: str = ""
    cloud_org: str = ""
    context_tokens: int = 0
    event_seq: int = 0
    id: str = ""
    input_tokens: int = 0
    max_context: int = 0
    model: str = ""
    model_configured: bool = True
    output_tokens: int = 0
    permission_mode: str = "default"
    session_id: str = ""
    theme: dict[str, JsonValue] | None = None
    type: Literal["status_update"] = "status_update"


class StopProcessResult(Model):
    """Wire shape for :meth:`ProcessesController.stop`."""

    killed: bool
    message: str
    pid: int


class StreamEnd(Event):
    """Marks end of a streaming response (run_message, resolve_hitl).

    On the wire: ``stream_end``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    type: Literal["stream_end"] = "stream_end"


class StreamingDone(RunEvent):
    """Emitted by the BE when the model's content stream has finished
    but the run's post-stream tail (compression, memory, persistence,
    metrics) is still draining inside Agno. The FE uses this to
    optimistically unblock user input — the agent is *logically* done
    from the user's POV even though the backend stream stays open for
    several more seconds. Without this event, ``_processing`` stays
    True for the entire Agno tail and the queue panel hangs around
    long after the response is visible.

    The BE still serialises subsequent ``run_message`` calls behind an
    internal lock so the next run can't start until the previous tail
    finishes — but that wait is invisible to the user, who sees the
    normal "Thinking" UI as soon as they submit.

    On the wire: ``streaming_done``.
    """

    event_seq: int = 0
    id: str = ""
    parent_run_id: str = ""
    run_id: str = ""
    session_id: str = ""
    type: Literal["streaming_done"] = "streaming_done"


class SwitchModelArgs(Args):
    """``switch_model``: the model to make current."""

    model_name: str


class TaskCreated(Event):
    """Orchestration task created.

    ``status`` is a raw ``str`` on the wire; producers SHOULD use
    :class:`OrchestrationTaskStatus` members (which coerce to their
    string values via ``StrEnum``). Kept as ``str`` rather than a
    strict enum so an Agno-emitted status we haven't yet enumerated
    survives verbatim through Pydantic instead of being rewritten
    to ``"unknown"`` by the enum's ``_missing_`` fallback.

    On the wire: ``task_created``.
    """

    assignee: str = ""
    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    status: str = "pending"
    task_id: str = ""
    title: str = ""
    type: Literal["task_created"] = "task_created"


class TaskCreatedEvent(Model):
    """TaskCreatedEvent."""

    agent_path: str
    assignee: str = ""
    card_id: str | None = None
    title: str = ""
    type: Literal["task_created"] = "task_created"


class TaskIteration(Event):
    """Task iteration progress.

    On the wire: ``task_iteration``.
    """

    event_seq: int = 0
    id: str = ""
    iteration: int = 0
    max_iterations: int = 0
    session_id: str = ""
    type: Literal["task_iteration"] = "task_iteration"


class TaskSnapshot(Model):
    """One task row inside a :class:`TaskStateUpdated` batch.

    Pre-refactor, ``TaskStateUpdated.tasks`` was
    ``list[dict[str, Any]]`` — an untyped bag that every callsite
    had to remember the keys of (``task_id`` / ``title`` /
    ``status`` / ``assignee``). Tightening it to this schema is
    wire-compatible: Pydantic serialises ``TaskSnapshot`` to the
    exact same JSON dict, and Pydantic's dict-coercion means
    ``TaskStateUpdated(tasks=[{...}])`` still works for callers
    that pass raw dicts.
    """

    assignee: str = ""
    status: str = ""
    task_id: str = ""
    title: str = ""


class TaskStateUpdated(Event):
    """Batch task state update.

    On the wire: ``task_state_updated``.
    """

    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    tasks: list[TaskSnapshot]
    type: Literal["task_state_updated"] = "task_state_updated"


class TaskUpdated(Event):
    """Orchestration task status changed.

    See :class:`TaskCreated` — ``status`` is a raw ``str`` for
    forward-compat with un-enumerated Agno statuses.

    On the wire: ``task_updated``.
    """

    assignee: str = ""
    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    status: str = ""
    task_id: str = ""
    type: Literal["task_updated"] = "task_updated"


class TaskUpdatedEvent(Model):
    """TaskUpdatedEvent."""

    agent_path: str
    card_id: str | None = None
    status: str = ""
    type: Literal["task_updated"] = "task_updated"


class ThinkingTurn(Model):
    """A synthesized ``thinking`` card — either from Agno's
    ``reasoning_content`` sidecar or from an inline ``<think>``
    block in the assistant content.
    """

    content: str = ""
    created_at: int = 0
    role: Literal["thinking"] = "thinking"
    run_id: str = ""


class ToastAdded(Model):
    """ToastAdded."""

    rev: int
    toast: dict[str, JsonValue]


class TodoItem(Model):
    """The canonical todo row — the one shape every boundary carries.

    ``activeForm`` is the verb-noun gerund the UI shows while the
    item is ``in_progress`` — e.g. ``"Running tests"`` (active)
    paired with ``content`` ``"Run tests"`` (imperative). The
    camelCase alias keeps CC parity: every ``.model_dump()`` emits
    ``activeForm``.
    """

    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    active_form: str = Field(default="", alias="activeForm")
    content: str
    status: Literal["pending", "in_progress", "completed"]


class TodosUpdatedPayload(Model):
    """The ``todos_updated`` broadcast: the full todo snapshot in
    its :class:`TodoItemWire` camelCase shape.
    """

    todos: list[TodoItem]


class ToolCallArgs(Args):
    """Typed replacement for the raw ``dict[str, Any]``
    ``tool_args`` payload at the RPC wire seam.

    Each tool defines its own arg keys (``command`` for bash,
    ``file_path`` for read/write, ``url`` for fetch, …); we don't
    enumerate every one here because the set grows with the tool
    registry. ``extra='allow'`` preserves every provided key at the
    Pydantic seam so the downstream ``ToolPermissions.check`` reads
    them unchanged. Named fields are the common ones — they give
    static coverage for the handful of well-known keys without
    forcing the schema to know every tool.
    """

    command: str = ""
    file_path: str = ""
    query: str = ""
    url: str = ""


class ToolCompleted(RunEvent):
    """A tool call has finished.

    On the wire: ``tool_completed``.
    """

    diff_rows: list[tuple[str, str]] | None = None
    event_seq: int = 0
    full_result: str = ""
    has_markup: bool = False
    id: str = ""
    is_error: bool = False
    is_rejected: bool = False
    parent_run_id: str = ""
    run_id: str = ""
    session_id: str = ""
    summary: str = ""
    type: Literal["tool_completed"] = "tool_completed"


class ToolCompletedEvent(Model):
    """ToolCompletedEvent."""

    agent_path: str
    card_id: str | None = None
    is_error: bool = False
    result: str = ""
    tool: str
    tool_call_id: str | None = None
    type: Literal["tool_completed"] = "tool_completed"


class ToolError(RunEvent):
    """A tool call failed.

    On the wire: ``tool_error``.
    """

    error: str = ""
    event_seq: int = 0
    id: str = ""
    parent_run_id: str = ""
    run_id: str = ""
    session_id: str = ""
    type: Literal["tool_error"] = "tool_error"


class ToolStarted(RunEvent):
    """A tool call has begun.

    On the wire: ``tool_started``.
    """

    args_summary: str = ""
    event_seq: int = 0
    friendly_name: str = ""
    id: str = ""
    parent_run_id: str = ""
    run_id: str = ""
    session_id: str = ""
    tool_name: str = ""
    type: Literal["tool_started"] = "tool_started"


class ToolStartedEvent(Model):
    """ToolStartedEvent."""

    agent_path: str
    args: str = ""
    card_id: str | None = None
    tool: str
    tool_call_id: str | None = None
    type: Literal["tool_started"] = "tool_started"


class ToolTurn(Model):
    """A rebuilt tool card (previously emitted live as
    ``tool_started`` + ``tool_completed`` events).
    """

    args: str = ""
    content: str = ""
    created_at: int = 0
    friendly_name: str = ""
    is_error: bool = False
    is_rejected: bool = False
    role: Literal["tool"] = "tool"
    run_id: str = ""
    tool_name: str = ""


class TruncateHistoryArgs(Args):
    """``truncate_history``: the run to drop, with every later run."""

    run_id: str
    session_id: str


class TruncateHistoryResult(Model):
    """Wire shape for :meth:`ContextController.truncate_history` —
    ``removed`` is the count of runs dropped (0 on any failure);
    ``error`` is empty on success.
    """

    error: str = ""
    removed: int


class TrustDecisionArgs(Args):
    """``set_workspace_trust``: the person's answer to "Trust this folder?"."""

    decision: Literal["trust", "distrust", "once"]


class Typing(Event):
    """Live draft of a client's composer, broadcast to every view.

    Carries the FULL draft text (not per-character deltas) so views
    can't drift on a dropped frame; senders throttle. Empty ``text``
    clears the remote draft (sent on submit/clear).

    On the wire: ``typing``.
    """

    client_id: str = ""
    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    text: str = ""
    type: Literal["typing"] = "typing"


class UpdateAvailable(Model):
    """Wire shape for the ``check_for_update`` RPC — package updater
    notice. ``None`` means no update is available.
    """

    available: bool
    current_version: str
    download_url: str
    latest_version: str
    pkg_name: str


class UpdatePluginArgs(Args):
    """``update_plugin``: the installed plugin and the branch / tag / SHA
    to reset it to (origin's HEAD when absent).
    """

    install_ref: str | None = None
    name: str


class UploadAttachmentArgs(Args):
    """``upload_attachment``: the file's name and its base64 contents."""

    content_base64: str
    filename: str


class UploadAttachmentResult(Model):
    """Wire shape for :meth:`FilesController.upload_attachment` —
    persisted FE-uploaded file location + byte count.
    """

    error: str = ""
    path: str
    size: int


class UserMessage(Frame):
    """User sends a chat message.

    ``client_id`` (mirroring) identifies the sending view so the BE's
    ``UserMessageReceived`` broadcast lets every OTHER view paint the
    bubble while the sender skips its own echo. Empty for views that
    predate mirroring — the echo then renders everywhere except
    nowhere, which is harmless for a single view.

    ``force`` (default ``False``) tells the BE to supersede any
    interrupted or pending rows for the session before starting the
    run. Used by the FE's "Retry" action on an interrupted-banner:
    discard the stale interrupted state, then start clean with the
    same prompt. Backwards compatible — pre-force clients keep the
    existing behaviour (the old rows linger until natural
    completion or explicit discard).

    On the wire: ``user_message``.
    """

    client_id: str = ""
    event_seq: int = 0
    file_contents: dict[str, str] = Field(default_factory=dict)
    force: bool = False
    id: str = ""
    session_id: str = ""
    text: str = ""
    type: Literal["user_message"] = "user_message"


class UserMessageReceived(Event):
    """Broadcast echo of an accepted user/queue message.

    The sending view already painted the bubble locally; other views
    paint it from this event (and the sender skips it by client_id).

    On the wire: ``user_message_received``.
    """

    client_id: str = ""
    event_seq: int = 0
    extension_id: str = ""
    id: str = ""
    queued: bool = False
    service_client_id: str = ""
    session_id: str = ""
    text: str = ""
    type: Literal["user_message_received"] = "user_message_received"


class UserTurn(Model):
    """A user-input turn."""

    content: str = ""
    created_at: int = 0
    role: Literal["user"] = "user"
    run_id: str = ""


class VisualizationActionArgs(Args):
    """``dispatch_visualization_action``: a component action and the
    JSON params the view attached to it.
    """

    action: str = ""
    params: dict[str, JsonValue] | None = None


class VisualizationActionDispatchedPayload(Model):
    """The ``visualization_action_dispatched`` broadcast, so log panels
    and dev tools can observe component interactions.
    """

    action: str
    params: dict[str, JsonValue]


class VisualizationActionResult(Model):
    """Wire shape for :meth:`VisualizationActionBus.dispatch` —
    the FE's tool result echo of the action name + user-supplied
    params so it can render "you clicked X" in the conversation.
    """

    action: str
    ok: bool
    params: dict[str, JsonValue]


class VisualizationDeltaPayload(Model):
    """The payload of a ``visualization_delta`` entry: the viz card.

    Subclasses the wire event the visualizer and the extensions send,
    so the log keeps one shape for a card; the two additions are the
    labels an extension's ``chat.append`` puts on its block — the
    card's ``title`` and the extension's id as ``source``. The
    visualizer sends neither, so both read empty.

    ``final`` defaults to ``True`` here (the wire event defaults to
    ``False``): a payload without the key means "the card is
    complete", which is the convention the view list and the history
    splicer have always read. The card's own fields default too — a
    producer that sends a partial card is logged as it sent it, and
    the readers skip what they can't use.
    """

    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    agent_path: str = ""
    final: bool = True
    json_: str = Field(default="", alias="json")
    source: str = ""
    spec_id: str = ""
    title: str = ""
    type: Literal["visualization_delta"] = "visualization_delta"


class VisualizationTurn(Model):
    """A visualizer card spliced from the session event log.

    ``spec`` stays a raw dict — the visualizer subagent owns the
    JSON schema and we don't validate it here. ``seq`` is the
    :class:`SessionEvent.seq` for ordering within a run. No
    ``created_at`` on the wire — the FE derives display time from
    the neighboring turns.
    """

    extension_id: str = ""
    role: Literal["visualization"] = "visualization"
    run_id: str = ""
    seq: int = 0
    source_agent: str = "visualizer"
    spec: dict[str, JsonValue]
    spec_id: str = ""
    title: str = ""


class VmCredentialState(Model):
    """``vm_sign_in``'s answer: the state of the VM's own credential after the sign-in.

    The layer's credential keeper answers with its own model; it is read
    into this one, so what goes on the wire is what is published.
    """

    message: str = ""
    state: Literal["ready", "needs_sign_in", "needs_reissue", "unreachable"]


class Welcome(Event):
    """First message the BE sends a newly attached client.

    ``client_id`` lets a view recognise its own broadcasts (e.g. skip
    rendering an echo of a message it already painted locally).

    On the wire: ``welcome``.
    """

    client_id: str = ""
    event_seq: int = 0
    id: str = ""
    session_id: str = ""
    type: Literal["welcome"] = "welcome"


class WindowChange(Model):
    """One change to one window's model, as listeners are told it."""

    answer: JsonValue = None
    """Any JSON value."""
    event: str = ""
    field: str
    item: dict[str, JsonValue] | None = None
    rev: int
    token: str = ""
    value: JsonValue = None
    """Any JSON value."""
    window: str


class WindowModelArgs(Args):
    """``window_model``: one window reading or writing its own model."""

    connection_id: str = ""
    dialog_id: str = ""
    field: str = ""
    kind: str = ""
    op: Literal["hydrate", "write", "toast", "dismiss_toast", "open_dialog", "answer_dialog"]
    token: str = ""
    value: JsonValue = None
    window: str = Field(min_length=1)


class WorkflowCancelRequest(Args):
    """``CANCEL_WORKFLOW`` params."""

    workflow_run_id: str = Field(min_length=1)


class WorkflowCancelResponse(Model):
    """``CANCEL_WORKFLOW`` response.

    ``cancelled`` is false when no such run is active — already
    finished, already cancelled, or an unknown id are the same
    outcome to the caller.
    """

    cancelled: bool
    workflow_run_id: str


class WorkflowEventRecord(Model):
    """One workflow event as the session log stores it and the frontend
    receives it on the ``workflow_event`` push channel.

    ``payload`` is the runtime's payload, forwarded as-is, or a dumped
    :class:`SyntheticTerminalPayload`.
    """

    name: str
    payload: dict[str, JsonValue]
    seq: int
    ts: int
    type: str
    workflow_run_id: str


class WorkflowListItem(Model):
    """One ``LIST_WORKFLOWS`` row: ``{name, description, whenToUse, phases, path}``.

    ``when_to_use`` goes out as ``whenToUse`` — the model serialises
    by alias, so the dispatcher's plain ``model_dump()`` emits the
    wire name.
    """

    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    description: str = ""
    name: str
    path: str
    phases: list[WorkflowPhase]
    when_to_use: str = Field(default="", alias="whenToUse")


class WorkflowListRequest(Args):
    """``LIST_WORKFLOWS`` params: none. Whatever the caller sends
    (``session_id`` and the like) is ignored.
    """


class WorkflowPhase(Model):
    """One phase in a workflow's published ``meta.phases`` list."""

    detail: str = ""
    title: str


class WorkflowRunRequest(Args):
    """``RUN_WORKFLOW`` params.

    ``name`` is the workflow; ``args`` is the workflow's own JSON
    input: it is handed to the script as-is, and each workflow defines
    and reads its own keys, so the only contract here is that it is a
    JSON object.
    """

    args: dict[str, JsonValue] = Field(default_factory=dict)
    name: str = Field(min_length=1)


class WorkflowRunResponse(Model):
    """``RUN_WORKFLOW`` response.

    Returned synchronously — the run is async on the BE side. The
    FE optimistically creates a workflow ``ChatItem`` keyed by
    ``workflow_run_id`` and folds subsequent ``workflow_event``
    pushes into it.
    """

    name: str
    workflow_run_id: str


class WorkspaceTrustStatus(Model):
    """What ``get_workspace_trust`` returns and ``workspace_trust_required`` carries."""

    can_trust: bool
    gated: str = "project tools, hooks, workflows, language servers, monitors, plugins, markdown-command shell tokens, and its permission and safety settings"
    path: str
    policy_mode: str
    reason: str
    remote: str | None = None
    source: str = ""
    state: Literal["trusted", "untrusted", "ask"]


class Written(Model):
    """Written."""

    rev: int


class BackgroundProcessDonePush(PushNotification):
    """A background process finished, as the agent is told.

    On the wire: ``push_notification`` on the channel ``background_process_done``.
    """

    channel: Literal["background_process_done"] = "background_process_done"
    payload: BackgroundProcessDonePayload  # type: ignore[assignment]


class FileEditedPush(PushNotification):
    """An edit tool wrote a file.

    On the wire: ``push_notification`` on the channel ``file_edited``.
    """

    channel: Literal["file_edited"] = "file_edited"
    payload: FileEditedPayload  # type: ignore[assignment]


class HostSignalPush(PushNotification):
    """A host-model signal for one extension's pages.

    On the wire: ``push_notification`` on the channel ``host_signal``.
    """

    channel: Literal["host_signal"] = "host_signal"
    payload: HostSignal  # type: ignore[assignment]


class HttpRetryAttemptPush(PushNotification):
    """A web fetch is about to be retried.

    On the wire: ``push_notification`` on the channel ``http_retry_attempt``.
    """

    channel: Literal["http_retry_attempt"] = "http_retry_attempt"
    payload: HttpRetryAttemptPayload  # type: ignore[assignment]


class HttpRetrySucceededPush(PushNotification):
    """A web fetch succeeded after retrying.

    On the wire: ``push_notification`` on the channel ``http_retry_succeeded``.
    """

    channel: Literal["http_retry_succeeded"] = "http_retry_succeeded"
    payload: HttpRetrySucceededPayload  # type: ignore[assignment]


class LoginResultPush(PushNotification):
    """How a sign-in started by ``login`` ended.

    On the wire: ``push_notification`` on the channel ``login_result``.
    """

    channel: Literal["login_result"] = "login_result"
    payload: LoginResultPayload  # type: ignore[assignment]


class LoginStatusPush(PushNotification):
    """What a sign-in started by ``login`` is doing now.

    On the wire: ``push_notification`` on the channel ``login_status``.
    """

    channel: Literal["login_status"] = "login_status"
    payload: LoginStatusPayload  # type: ignore[assignment]


class NotificationsChangedPush(PushNotification):
    """The person's unread notification counts moved.

    On the wire: ``push_notification`` on the channel ``notifications_changed``.
    """

    channel: Literal["notifications_changed"] = "notifications_changed"
    payload: NotificationsChanged  # type: ignore[assignment]


class OpenExternalPush(PushNotification):
    """An extension asked a window to open a link in the browser.

    On the wire: ``push_notification`` on the channel ``open_external``.
    """

    channel: Literal["open_external"] = "open_external"
    payload: ExternalOpen  # type: ignore[assignment]


class OrchestrateEventPush(PushNotification):
    """A sub-agent's progress (a tool call, its start, pause, end or error, a task) or a view the agent or an extension drew, told apart by ``type``.

    On the wire: ``push_notification`` on the channel ``orchestrate_event``.
    """

    channel: Literal["orchestrate_event"] = "orchestrate_event"
    payload: OrchestrateEvent  # type: ignore[assignment]


class OutputStyleChangedPush(PushNotification):
    """The session's output style changed.

    On the wire: ``push_notification`` on the channel ``output_style_changed``.
    """

    channel: Literal["output_style_changed"] = "output_style_changed"
    payload: OutputStyleChangedPayload  # type: ignore[assignment]


class PermissionModeChangedPush(PushNotification):
    """The session's permission mode changed: the switch itself (``mode`` and ``previous``), or the plan tool's note that the agent entered plan mode (``mode``, ``source``, ``reason``).

    On the wire: ``push_notification`` on the channel ``permission_mode_changed``.
    """

    channel: Literal["permission_mode_changed"] = "permission_mode_changed"
    payload: PermissionModeChange  # type: ignore[assignment]


class PlanDecidedPush(PushNotification):
    """A submitted plan was approved or dismissed.

    On the wire: ``push_notification`` on the channel ``plan_decided``.
    """

    channel: Literal["plan_decided"] = "plan_decided"
    payload: PlanDecidedPayload  # type: ignore[assignment]


class PlanSubmittedPush(PushNotification):
    """The agent submitted a plan for the person to decide on.

    On the wire: ``push_notification`` on the channel ``plan_submitted``.
    """

    channel: Literal["plan_submitted"] = "plan_submitted"
    payload: PlanSubmittedPayload  # type: ignore[assignment]


class ProcessExitedPush(PushNotification):
    """A background process exited.

    On the wire: ``push_notification`` on the channel ``process_exited``.
    """

    channel: Literal["process_exited"] = "process_exited"
    payload: ProcessExitedPayload  # type: ignore[assignment]


class ProcessLinePush(PushNotification):
    """A background process printed a line.

    On the wire: ``push_notification`` on the channel ``process_line``.
    """

    channel: Literal["process_line"] = "process_line"
    payload: ProcessLinePayload  # type: ignore[assignment]


class ProcessStartedPush(PushNotification):
    """A background process started.

    On the wire: ``push_notification`` on the channel ``process_started``.
    """

    channel: Literal["process_started"] = "process_started"
    payload: ProcessStartedPayload  # type: ignore[assignment]


class SchedulerCompletedPush(PushNotification):
    """A scheduled task finished: its result, or why it failed.

    On the wire: ``push_notification`` on the channel ``scheduler_completed``.
    """

    channel: Literal["scheduler_completed"] = "scheduler_completed"
    payload: SchedulerCompletedPayload  # type: ignore[assignment]


class SchedulerStartedPush(PushNotification):
    """A scheduled task started running.

    On the wire: ``push_notification`` on the channel ``scheduler_started``.
    """

    channel: Literal["scheduler_started"] = "scheduler_started"
    payload: SchedulerStartedPayload  # type: ignore[assignment]


class SessionNamedPush(PushNotification):
    """A session was given a name.

    On the wire: ``push_notification`` on the channel ``session_named``.
    """

    channel: Literal["session_named"] = "session_named"
    payload: SessionNamedPayload  # type: ignore[assignment]


class TodosUpdatedPush(PushNotification):
    """The agent's to-do list, whole, after it changed.

    On the wire: ``push_notification`` on the channel ``todos_updated``.
    """

    channel: Literal["todos_updated"] = "todos_updated"
    payload: TodosUpdatedPayload  # type: ignore[assignment]


class VisualizationActionDispatchedPush(PushNotification):
    """The person used a control in a view.

    On the wire: ``push_notification`` on the channel ``visualization_action_dispatched``.
    """

    channel: Literal["visualization_action_dispatched"] = "visualization_action_dispatched"
    payload: VisualizationActionDispatchedPayload  # type: ignore[assignment]


class VmCredentialPush(PushNotification):
    """A cloud VM's own credential changed state.

    On the wire: ``push_notification`` on the channel ``vm_credential``.
    """

    channel: Literal["vm_credential"] = "vm_credential"
    payload: VmCredentialState  # type: ignore[assignment]


class WindowModelChangedPush(PushNotification):
    """A window's model changed; the window it names applies it.

    On the wire: ``push_notification`` on the channel ``window_model_changed``.
    """

    channel: Literal["window_model_changed"] = "window_model_changed"
    payload: WindowChange  # type: ignore[assignment]


class WorkflowEventPush(PushNotification):
    """One step of a running workflow, keyed by its run id.

    On the wire: ``push_notification`` on the channel ``workflow_event``.
    """

    channel: Literal["workflow_event"] = "workflow_event"
    payload: WorkflowEventRecord  # type: ignore[assignment]


class WorkspaceTrustRequiredPush(PushNotification):
    """A folder's trust status: windows showing the trust dialog for it close it, or open it while ``state`` is ``ask``.

    On the wire: ``push_notification`` on the channel ``workspace_trust_required``.
    """

    channel: Literal["workspace_trust_required"] = "workspace_trust_required"
    payload: WorkspaceTrustStatus  # type: ignore[assignment]


#: One of 7 kinds, told apart by ``role``.
type ChatTurn = Annotated[
    UserTurn | AssistantTurn | ThinkingTurn | ToolTurn | PlanTurn | StatsTurn | VisualizationTurn,
    Field(discriminator="role"),
]


#: One of 10 kinds, told apart by ``type``.
type OrchestrateEvent = Annotated[
    ToolStartedEvent
    | ToolCompletedEvent
    | AgentStartedEvent
    | AgentPausedEvent
    | AgentCompletedEvent
    | RunErrorEvent
    | ContentPreviewEvent
    | TaskCreatedEvent
    | TaskUpdatedEvent
    | VisualizationDeltaPayload,
    Field(discriminator="type"),
]


#: One of 2 kinds. Nothing in the contract tells them apart: the one that fits best is taken.
type PermissionModeChange = PermissionModeChangedPayload | PlanModeEnteredPayload


#: One of 4 kinds, told apart by ``source``.
type SlashCommand = Annotated[
    BuiltinSlashCommand | MarkdownSlashCommand | SkillSlashCommand | ExtensionSlashCommand,
    Field(discriminator="source"),
]


#: One of 6 kinds. Nothing in the contract tells them apart: the one that fits best is taken.
type WindowModelResult = Hydrated | Written | ToastAdded | Revised | DialogShown | DialogAnswered


#: Every message igni sends, by its wire `type`.
EVENT_TYPES: dict[str, type[Event]] = {
    "command_result": CommandResult,
    "content_delta": ContentDelta,
    "error": ErrorMessage,
    "hitl_request": Requirement,
    "info": InfoMessage,
    "model_completed": ModelCompleted,
    "push_notification": PushNotification,
    "reasoning_started": ReasoningStarted,
    "requirement_details": RequirementDetails,
    "requirement_resolved": RequirementResolved,
    "rpc_response": RpcResponse,
    "run_completed": RunCompleted,
    "run_error": RunError,
    "run_paused": RunPaused,
    "run_started": RunStarted,
    "scheduler_event": SchedulerEvent,
    "session_cleared": SessionCleared,
    "session_list_result": SessionListResult,
    "status_update": StatusUpdate,
    "stream_end": StreamEnd,
    "streaming_done": StreamingDone,
    "task_created": TaskCreated,
    "task_iteration": TaskIteration,
    "task_state_updated": TaskStateUpdated,
    "task_updated": TaskUpdated,
    "tool_completed": ToolCompleted,
    "tool_error": ToolError,
    "tool_started": ToolStarted,
    "typing": Typing,
    "user_message_received": UserMessageReceived,
    "welcome": Welcome,
}

#: Every message a client sends, by its wire `type`.
FRAME_TYPES: dict[str, type[Frame | Event]] = {
    "cancel": Cancel,
    "cancel_login": CancelLogin,
    "command": Command,
    "hitl_decision": HitlDecision,
    "hitl_response": HitlResponse,
    "hitl_response_batch": HitlResponseBatch,
    "mcp_toggle": McpToggle,
    "model_switch": ModelSwitch,
    "queue_message": QueueMessage,
    "rpc_request": RpcRequest,
    "session_list": SessionList,
    "session_switch": SessionSwitch,
    "shutdown": Shutdown,
    "typing": Typing,
    "user_message": UserMessage,
}

#: Every push channel the contract types, by channel.
PUSH_TYPES: dict[str, type[PushNotification]] = {
    "background_process_done": BackgroundProcessDonePush,
    "file_edited": FileEditedPush,
    "host_signal": HostSignalPush,
    "http_retry_attempt": HttpRetryAttemptPush,
    "http_retry_succeeded": HttpRetrySucceededPush,
    "login_result": LoginResultPush,
    "login_status": LoginStatusPush,
    "notifications_changed": NotificationsChangedPush,
    "open_external": OpenExternalPush,
    "orchestrate_event": OrchestrateEventPush,
    "output_style_changed": OutputStyleChangedPush,
    "permission_mode_changed": PermissionModeChangedPush,
    "plan_decided": PlanDecidedPush,
    "plan_submitted": PlanSubmittedPush,
    "process_exited": ProcessExitedPush,
    "process_line": ProcessLinePush,
    "process_started": ProcessStartedPush,
    "scheduler_completed": SchedulerCompletedPush,
    "scheduler_started": SchedulerStartedPush,
    "session_named": SessionNamedPush,
    "todos_updated": TodosUpdatedPush,
    "visualization_action_dispatched": VisualizationActionDispatchedPush,
    "vm_credential": VmCredentialPush,
    "window_model_changed": WindowModelChangedPush,
    "workflow_event": WorkflowEventPush,
    "workspace_trust_required": WorkspaceTrustRequiredPush,
}

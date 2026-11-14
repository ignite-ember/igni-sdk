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

#: What a command result asks the client to do.
#:
#: * empty: nothing; just show `content`.
#: * `quit`: close the client.
#: * `clear`: clear the conversation view.
#: * `fork`: the session was duplicated; `content` is the new session's id.
#: * `sessions`: show the saved sessions.
#: * `model`: show the model picker.
#: * `model_switched`: the model changed; refresh what shows it.
#: * `login` / `logout`: start signing in / out of igni cloud.
#: * `help`: show help.
#: * `mcp`, `plugins`, `extensions`, `agents`, `skills`,
#:   `hooks`, `loop`, `schedule`: open the page that manages them.
#: * `watcher`: open the background-process panel.
#: * `compact`: compact the conversation.
#: * `ctx`: open the context-breakdown page.
#: * `programs`: open the approver-token page.
#: * `run_prompt`: send `content` to the agent as a prompt.
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


#: How a client should show a command result's `content`.
#:
#: * `markdown`: render as Markdown (long-form text such as help).
#: * `info`: a single, quiet line (status, confirmations).
#: * `error`: a single line shown as an error.
#: * `action`: nothing to show; act on the result's `action`
#:   instead (open a panel, a picker, ...).
type CommandResultKind = Literal["markdown", "info", "error", "action"]


#: Where a notification came from.
#:
#: * `server`: delivered by igni server, which keeps whether it was read.
#: * `local`: posted by an extension on this machine; this igni keeps
#:   whether it was read.
type NotificationOrigin = Literal["server", "local"]


#: Top-level permission posture for a session.
#:
#: Defaults to `DEFAULT`. `DONT_ASK` is the headless/CI mode
#: (never prompt, deny unmatched). `ACCEPT_EDITS` auto-approves
#: file mutation tools. `BYPASS_PERMISSIONS` runs without
#: prompts unless an explicit deny / ask rule matches.
#: `PLAN` forbids source edits entirely.
type PermissionMode = Literal["default", "dontAsk", "acceptEdits", "bypassPermissions", "plan"]


#: User-recorded decision for a plan submitted via
#: `exit_plan_mode`. Concrete values match the historic
#: wire strings so serialised blobs round-trip cleanly.
type PlanDecision = Literal["approved", "dismissed"]


#: Why a call failed, as a word a client can branch on; `error` beside
#: it is the sentence for a person.
type RpcErrorCode = Literal[
    "unknown_method",
    "invalid",
    "forbidden",
    "not_found",
    "refused",
    "unavailable",
    "cancelled",
    "failed",
]


#: Lifecycle of one scheduled task.
#:
#: `pending` (waiting for its time), `running` (executing now),
#: `completed` (finished successfully), `failed` (finished with an
#: error) or `cancelled` (cancelled before it ran).
type TaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class AgentCompletedEvent(Model):
    """A sub-agent finished its run, with its token usage."""

    agent_path: str
    """Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level)."""
    card_id: str | None = None
    """Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card."""
    input_tokens: int = 0
    """Input (prompt) tokens the sub-agent used."""
    is_error: bool = False
    """True when the sub-agent ended with an error."""
    output_tokens: int = 0
    """Output (completion) tokens the sub-agent produced."""
    reasoning_tokens: int = 0
    """Reasoning tokens the sub-agent used; 0 when the model reports none."""
    type: Literal["agent_completed"] = "agent_completed"
    """Always `agent_completed`: what kind of message this is."""


class AgentInfo(Model):
    """One agent available in the session, as shown in the agents panel."""

    can_orchestrate: bool = True
    """True when the agent may spawn sub-agents of its own."""
    color: str = ""
    """Display color declared for the agent. Empty when none."""
    description: str = ""
    """What the agent is for. Empty when not given."""
    is_ephemeral: bool = False
    """True for an agent created during this session that has not been saved to disk; it disappears when the session ends unless promoted."""
    mcp_servers: list[str] = Field(default_factory=list)
    """Names of the MCP servers whose tools the agent gets."""
    model: str = ""
    """Model the agent runs on. Empty to use the session's default model."""
    name: str
    """Agent name; plugin agents are prefixed with the plugin name (`plugin:agent`)."""
    source_path: str = ""
    """Path of the file the agent was loaded from. Empty for agents not loaded from a file."""
    system_prompt: str = ""
    """The agent's system prompt (the body of its definition file)."""
    tags: list[str] = Field(default_factory=list)
    """Free-form tags declared for the agent."""
    tools: list[str] = Field(default_factory=list)
    """Names of the tools the agent may use. Empty when not restricted."""
    unknown_tools: list[str] = Field(default_factory=list)
    """Tool names the agent declares that igni cannot find. Usually empty; when not, the agent fails when it is called."""


class AgentNameArgs(Args):
    """Arguments naming an agent created during the session."""

    name: str
    """Name of the agent created during the session."""


class AgentPausedEvent(Model):
    """A sub-agent paused because it needs user input (e.g. a tool
    approval): the run waits for someone to answer its approvals.
    """

    agent_path: str
    """Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level)."""
    card_id: str | None = None
    """Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card."""
    count: int = 1
    """Number of pending requests the agent is waiting on."""
    type: Literal["agent_paused"] = "agent_paused"
    """Always `agent_paused`: what kind of message this is."""


class AgentRunArgs(Args):
    """Arguments naming a sub-agent run to stop."""

    run_id: str = ""
    """Id of the sub-agent run, as its events carry it; must not be empty."""


class AgentStartedEvent(Model):
    """A member of the run started: a sub-agent began running a task."""

    agent: str
    """Name of the sub-agent that started."""
    agent_path: str
    """Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level)."""
    card_id: str | None = None
    """Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card."""
    parent: str | None = None
    """Path of the agent that spawned it. Null for a top-level spawn."""
    run_id: str | None = None
    """Identifier of the sub-agent's run, when known."""
    task: str | None = None
    """Task text given to the sub-agent, when known."""
    type: Literal["agent_started"] = "agent_started"
    """Always `agent_started`: what kind of message this is."""


class ApproverTokenMinted(Model):
    """A new token that lets a program answer the agent's approval requests."""

    token: str
    """The token. A program that connects with it may answer approval requests and approve plans. It is valid until igni exits or the tokens are revoked."""


class ApproverTokensRevoked(Model):
    """How many approver tokens were revoked."""

    revoked: int
    """The number of tokens revoked."""


class AssistantTurn(Model):
    """A visible reply from the assistant.

    One run can produce several of these when the reply was
    interleaved with thinking blocks.
    """

    content: str = ""
    """The reply text (Markdown)."""
    created_at: int = 0
    """When the message was created, in Unix epoch seconds; `0` if unknown."""
    role: Literal["assistant"] = "assistant"
    """Turn kind; always `assistant`."""
    run_id: str = ""
    """Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point."""


class AttachSessionParams(Args):
    """Which session to attach a connection to, and in which folder."""

    project_dir: str = ""
    """The folder the session works in; empty for igni's own."""
    session_id: str = ""
    """The session to attach to; empty for the default one, or a new one when `project_dir` is given."""


class AttachSessionResult(Model):
    """The session a connection is now attached to."""

    project_dir: str
    """The session's project folder, as an absolute path."""
    session_id: str
    """The id of the session that was attached."""


class BackgroundProcessDonePayload(Model):
    """Channel `background_process_done`. A shell command running in
    the background has finished. Sent alongside `process_exited`, for
    a client that only wants to show a notice. The agent is told about
    the output separately.
    """

    cmd: str
    """The command that ran."""
    duration_seconds: float
    """How long it ran, in seconds."""
    exit_code: int | None
    """Its exit code; `null` when unknown."""
    pid: int | None
    """The process's id; `null` when unknown."""


class BuiltinSlashCommand(Model):
    """A slash command built into igni."""

    argument_hint: str = ""
    """A hint for the arguments it takes; empty when it takes none."""
    description: str = ""
    """What the command does, in one line."""
    name: str
    """The command's name, without the leading `/`."""
    source: Literal["builtin"] = "builtin"
    """Always `builtin`: a command built into igni."""


class Cancel(Frame):
    """Stop the run in progress.

    On the wire: ``cancel``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["cancel"] = "cancel"
    """Always `cancel`: what kind of message this is."""


class CancelAgentRunResult(Model):
    """Result of cancelling one background agent run."""

    error: str = ""
    """Why the cancel failed, e.g. the run id is unknown; empty when `ok` is `true`."""
    ok: bool
    """`true` when the agent run was found and cancelled."""


class CancelLogin(Frame):
    """Cancel an in-progress login flow.

    On the wire: ``cancel_login``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["cancel_login"] = "cancel_login"
    """Always `cancel_login`: what kind of message this is."""


class CancelRunResult(Model):
    """Result of cancelling the current turn: whether one was running."""

    cancelled: bool
    """`true` when a turn was running and is being stopped: its stream ends with an `info` and a `stream_end`. `false` when nothing was running."""


class ChatSearchHit(Model):
    """One match from searching a session's chat history."""

    created_at: int = 0
    """When the turn was created, in Unix epoch seconds; `0` if unknown."""
    history_index: int = 0
    """Index of the matching turn in the list returned by `get_chat_history`; use it to jump to that turn."""
    match_end: int = 0
    """End offset (exclusive) of the match within `snippet`."""
    match_start: int = 0
    """Start offset of the match within `snippet` (not the full text)."""
    role: str = ""
    """Kind of the matching turn, e.g. `user`, `assistant` or `tool`."""
    run_id: str = ""
    """Id of the agent run the matching turn belongs to."""
    snippet: str = ""
    """Excerpt of the turn's text around the match."""


class CheckPermissionArgs(Args):
    """Arguments for looking up the permission level of one tool call."""

    func_name: str
    """Name of the tool's function being called."""
    tool_args: ToolCallArgs
    """The call's arguments, which argument-specific rules are matched against."""
    tool_name: str
    """Name of the tool."""


class CloudPlan(Model):
    """The signed-in account's plan and organisation on igni server.
    Any field may be `null` when the server did not report it.
    """

    email: str | None = None
    """The signed-in user's email address."""
    full_name: str | None = None
    """The signed-in user's full name."""
    org_name: str | None
    """The organisation's display name; `null` when not reported."""
    tier: str | None
    """The plan tier; `null` when not reported."""


class Command(Frame):
    """A slash command the person typed. igni answers with a `command_result`.

    On the wire: ``command``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    text: str = ""
    """The command as typed, slash included, e.g. `/help`."""
    type: Literal["command"] = "command"
    """Always `command`: what kind of message this is."""


class CommandResult(Event):
    """The result of a slash command: text to show, an action for the client to take, or both.

    On the wire: ``command_result``.
    """

    action: CommandAction = ""
    """What the client should do in response; empty for nothing but showing `content`."""
    content: str = ""
    """The text to show. For some actions it carries the action's value instead: the new session id for `fork`, the prompt to send for `run_prompt`."""
    display_content: str = ""
    """For `run_prompt`: the text to show in the chat in place of `content`, when the prompt sent to the agent differs from what the person should see. Empty to show `content`."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    kind: CommandResultKind = "info"
    """How to show `content`."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["command_result"] = "command_result"
    """Always `command_result`: what kind of message this is."""


class CompactIfNeededArgs(Args):
    """Arguments for compacting the conversation when its context is
    nearly full.
    """

    ctx_tokens: int
    """Tokens of context the last turn used."""
    max_ctx: int
    """The model's context window, in tokens. Compaction happens at 80% or more."""


class CompactionOutcome(Model):
    """Whether the conversation was compacted, and if so the summary it
    was replaced by.
    """

    compacted: bool
    """`false` when the context was below the threshold, a `PreCompact` hook refused, or there was nothing to compact."""
    new_session_id: str = ""
    """The session the conversation continues in (currently the same id); empty when not compacted."""
    summary: str = ""
    """What the compacted conversation was replaced by; empty when not compacted."""


class CompleteFilesArgs(Args):
    """Arguments for completing a file path typed after `@`."""

    limit: int = 50
    """Maximum number of matches to return."""
    query: str = ""
    """What was typed so far; empty matches every file."""


class Composer(Model):
    """A window's composer: its draft, the files it names and its mode."""

    attachments: list[str] = Field(default_factory=list)
    """The files the draft names, in order."""
    mode: str = "chat"
    """What the composer is in: `chat`, `command` (a slash command) or `shell`."""
    text: str = ""
    """The draft's text, as the person wrote it."""


class ContentDelta(Event):
    """A chunk of the model's reply, streamed as it is written.

    Append each chunk's `text` to what came before to build the reply.

    On the wire: ``content_delta``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    is_thinking: bool = False
    """True when the text is the model's reasoning rather than its visible reply."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    text: str = ""
    """The next piece of text, to append to the earlier ones."""
    type: Literal["content_delta"] = "content_delta"
    """Always `content_delta`: what kind of message this is."""


class ContentPreviewEvent(Model):
    """A short preview of what the agent is writing, mid-stream."""

    agent_path: str
    """Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level)."""
    card_id: str | None = None
    """Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card."""
    text: str
    """Preview text of the sub-agent's latest output."""
    type: Literal["content_preview"] = "content_preview"
    """Always `content_preview`: what kind of message this is."""


class ContextBreakdown(Model):
    """Token breakdown of the current context window.

    `total = runs + floor`. `floor` is the part that compacting the
    conversation (`/compact`) cannot shrink, such as the system prompt
    and tool definitions.
    """

    floor: int
    """Tokens that are always present regardless of history (system prompt, tool definitions and so on); never negative."""
    runs: int
    """Tokens taken by the conversation history (previous runs)."""
    total: int
    """Total tokens currently in the context."""


class Dialog(Model):
    """A dialog on screen: igni's own or an extension's. One at a time."""

    id: str
    """The dialog's own id: two writers cannot collide."""
    source: str | None = None
    """The extension that asked for it; null for igni's own."""
    spec: JsonValue | None = None
    """What the dialog shows: igni's own spec, or an extension's."""
    type: Literal["dialog"] = "dialog"
    """Always `dialog`: what this is."""


class DialogAnswered(Model):
    """The answer to `answer_dialog`: whether the dialog was still the open one, and the window's revision."""

    answered: bool
    """False when that dialog was no longer the open one, so the answer was not taken."""
    op: Literal["answer_dialog"] = "answer_dialog"
    """Always `answer_dialog`: the request this answers."""
    rev: int
    """The window's revision after the answer."""


class DialogShown(Model):
    """The answer to `open_dialog`: the dialog as shown, with its id, and the window's revision."""

    dialog: Dialog
    """The dialog as shown, its `id` included."""
    op: Literal["open_dialog"] = "open_dialog"
    """Always `open_dialog`: the request this answers."""
    rev: int
    """The window's revision after opening it."""


class DirListResult(Model):
    """The sub-folders of one folder, for browsing to a project folder."""

    dirs: list[str]
    """Names of the sub-folders in `path`, sorted case-insensitively. Hidden folders are left out unless they were asked for. Empty when the folder could not be read."""
    error: str
    """Why the folder could not be read; empty on success."""
    home: str
    """The user's home folder, as an absolute path."""
    parent: str
    """The folder above `path`; empty when `path` is the filesystem root."""
    path: str
    """The folder that was listed, as an absolute path."""


class DiscardEphemeralResult(Model):
    """The outcome of discarding an agent created during a session."""

    name: str
    """The agent's name."""
    ok: bool
    """Whether the agent was discarded."""
    reason: str = ""
    """Why it was not discarded; empty when `ok` is true."""


class DiscardInterruptedRunResult(Model):
    """The outcome of discarding an interrupted run."""

    error: str = ""
    """Why it failed; empty when `ok` is true."""
    ok: bool
    """`true` once no such interrupted run is left, also when there was none, so a retry is harmless. `false` when the id was empty or the change could not be saved."""


class DiscoverServerArgs(Args):
    """An email address to find the user's igni server from."""

    email: str
    """The user's email address; its domain is looked up for an igni server."""


class DisplayConfig(Model):
    """How the conversation is shown: the `display` section of igni's settings."""

    color_theme: str = "auto"
    """Color theme: `auto` (follow the terminal or system), `light` or `dark`."""
    markdown: bool = True
    """Render agent replies as Markdown rather than plain text."""
    message_truncate_lines: int = 10
    """Number of lines of a long message shown before it is truncated."""
    show_reasoning: bool = False
    """Show the model's reasoning, when it produces any."""
    show_routing: bool = False
    """Verbose mode: show which agent handles each step and how work is routed."""
    show_tool_calls: bool = True
    """Show the agent's tool calls in the conversation."""
    tool_result_preview_lines: int = 4
    """Number of lines of a tool's output shown before it is collapsed."""


class ErrorMessage(Event):
    """An error message to show the person.

    On the wire: ``error``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    text: str = ""
    """What went wrong."""
    type: Literal["error"] = "error"
    """Always `error`: what kind of message this is."""


class ExecuteScheduledTaskArgs(Args):
    """Arguments for running a scheduled task's work now."""

    description: str
    """What the task asks the agent to do (a scheduled task's `description`)."""
    run_id: str = ""
    """Id to give the run, so the caller can follow the run's pushes (their `run_id`) as they come; one is made when absent."""


class ExtensionIndicator(Model):
    """A small status indicator an extension shows in the client's own
    interface. The client gets its current value by calling a tool of
    the extension's every `intervalSeconds`.
    """

    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    id: str
    """The indicator's id, a reverse-DNS name."""
    interval_seconds: float = Field(default=30.0, alias="intervalSeconds")
    """How often to call `source`, in seconds."""
    label: str
    """The indicator's name, for a person."""
    opens: str = ""
    """The `kind` of the extension page to open when the indicator is clicked; empty for an indicator that only reports."""
    source: str
    """The extension tool to call for the current value; it answers `{label, tone, detail}`."""


class ExtensionListResult(Model):
    """Every installed extension, in a stable order."""

    extensions: list[ExtensionSummary] = Field(default_factory=list)
    """The installed extensions."""


class ExtensionMenuEntry(Model):
    """An entry an extension adds to the tools menu; choosing it runs a slash command."""

    command: str
    """The slash command it runs, e.g. `/review`."""
    desc: str
    """A one-line description of what it does."""
    label: str
    """The entry's text, for a person."""


class ExtensionPage(Model):
    """A page an extension contributes to the client."""

    entry: str = "index.html"
    """The file, relative to the extension's `origin`, the page loads."""
    kind: str
    """The page's kind, a reverse-DNS name unique across extensions, e.g. `com.example.notes`."""
    label: str
    """The page's title, for a person."""
    sidebar: bool = False
    """Whether the page is listed in the sidebar."""


class ExtensionSetting(Model):
    """One setting an extension can be configured with."""

    default: JsonValue = None
    """The value used when none is set."""
    key: str
    """The setting's key in `values`."""
    label: str
    """The setting's name, for a person."""
    options: list[str] = Field(default_factory=list)
    """The allowed values when `type` is `enum`; empty otherwise."""
    type: str
    """The kind of value: `string`, `number`, `boolean` or `enum`."""


class ExtensionSlashCommand(Model):
    """A slash command an installed extension answers."""

    argument_hint: str = ""
    """A hint for the arguments it takes; empty when it takes none."""
    description: str = ""
    """What the command does, in one line."""
    name: str
    """The command's name, without the leading `/`."""
    owner: str = ""
    """The id of the extension that answers it."""
    source: Literal["extension"] = "extension"
    """Always `extension`: a command an extension answers."""


class ExtensionSummary(Model):
    """One installed extension: who it is, what state it is in, where its
    pages are served, and what it contributes.
    """

    allow: list[str] = Field(default_factory=list)
    """The RPC methods its pages were granted. igni checks every call; this copy lets a client refuse early."""
    dropped: list[ExtensionSwitchedOff] = Field(default_factory=list)
    """Its prompt edits that have no effect, because another extension replaces that prompt and has no section the edit names."""
    faulty: str = ""
    """Why it is marked faulty (its calls timed out or crashed too often in a row, and igni restarted it); empty while it answers."""
    host: list[str] = Field(default_factory=list)
    """The host permissions it was granted, for display."""
    id: str
    """The extension's id, a reverse-DNS name."""
    indicators: list[ExtensionIndicator] = Field(default_factory=list)
    """Status indicators it contributes."""
    menu: list[ExtensionMenuEntry] = Field(default_factory=list)
    """Entries it adds to the tools menu."""
    name: str
    """The extension's display name."""
    origin: str = ""
    """Where its pages are served from; empty when it contributes none."""
    pages: list[ExtensionPage] = Field(default_factory=list)
    """Pages it contributes."""
    problems: list[str] = Field(default_factory=list)
    """Problems that do not stop it working, e.g. a tool reporting other hints than its manifest declares."""
    reason: str = ""
    """Why it is not `READY`, and what to do; empty when it is."""
    sandbox: str = ""
    """How its process runs, e.g. `sandboxed (seatbelt)` or `not sandboxed: <why>`; empty when igni starts no process for it. An unsandboxed process has the user's full file and network access."""
    service_url: str | None = None
    """The URL of its own service, as its pages reach it; `null` when it has none a page may reach."""
    settings: list[ExtensionSetting] = Field(default_factory=list)
    """The settings it can be configured with; their current values are in `values`."""
    state: str
    """What the extension is doing: `READY`, `PREPARING`, `DISABLED` or `FAILED`."""
    switched_off: list[ExtensionSwitchedOff] = Field(default_factory=list)
    """What it does not get because it collides with another extension. Usually empty."""
    tools: list[ExtensionTool] = Field(default_factory=list)
    """The tools it gives the agent."""
    values: dict[str, JsonValue] = Field(default_factory=dict)
    """The current setting values, by key, with defaults filled in and undeclared keys dropped. They reach its pages as launch parameters."""
    version: str
    """The installed version, a semantic version."""
    web_url: str | None = None
    """Its home on the web, when one is known; `null` otherwise."""


class ExtensionSwitchedOff(Model):
    """One thing an extension does not get, because it collides with another."""

    claim: str
    """What it claimed, e.g. `prompt:main.workflow`, `command:/review` or `agent:explorer`."""
    reason: str
    """Who decided against it, or that nobody has decided yet."""


class ExtensionTool(Model):
    """One tool an extension gives the agent, as the panel lists it."""

    hints: str
    """What the tool says about itself, for a person, e.g. `read-only, local, idempotent`."""
    name: str
    """The tool's name."""


class ExternalOpen(Model):
    """An extension asked for a link to be opened in the person's browser."""

    source: str
    """The id of the extension that asked."""
    url: str
    """The link to open."""
    window: str
    """The id of the window that should open it; other windows ignore it."""


class ExtractLearningsArgs(Args):
    """Arguments for learning from one finished turn."""

    assistant_msg: str
    """The assistant's answer in the turn."""
    user_msg: str
    """The user's message in the turn."""


class FileCompletion(Model):
    """Project files matching a partial name, for `@`-mention completion."""

    matches: list[str]
    """Matching file paths, relative to the project folder, best match first; at most the requested limit."""
    total: int
    """How many files matched in all; more than the length of `matches` when the list was cut at the limit."""


class FileEditedPayload(Model):
    """Channel `file_edited`. The agent has written a file. A client
    showing that file in an editor can reload it.
    """

    path: str
    """The file that was written."""


class FloorNotification(Model):
    """One notification for the person, from igni server or from an extension on this machine."""

    actor: str = ""
    """Who caused it, for display; empty when nobody in particular."""
    body: str = ""
    """The text under the headline; empty when there is none."""
    created_at: datetime | None = None
    """When it was created; null when unknown."""
    id: str
    """The notification's id; use it to mark it read."""
    kind: str = ""
    """The extension's own name for what kind of notification it is; empty when none."""
    org_id: str = ""
    """The organisation it happened in, for one from igni server; empty for a local one."""
    org_name: str = ""
    """That organisation's name, set only when the person belongs to more than one. Show it when it is set."""
    origin: NotificationOrigin
    """Where it came from."""
    read: bool = False
    """True once it has been marked read."""
    source: str
    """The id of the extension it is from."""
    target: NotificationTarget | None = None
    """The page to open when the person opens it; null when there is none."""
    title: str = ""
    """A one-line headline."""


class GroupPolicyPackResult(Model):
    """The policy pack of the group the current user belongs to on igni
    server. Every field is empty when the user belongs to no group.
    """

    default_model: str | None = None
    """The model this group's members get when nothing names one; `null` when the group sets none."""
    entry_count: int = 0
    """How many entries the pack holds."""
    fetched_at: str | None = None
    """When the pack was last fetched, as an ISO 8601 timestamp; `null` if never."""
    group_id: str | None = None
    """The group's id; `null` when in no group."""
    group_name: str | None = None
    """The group's name; `null` when in no group."""


class HitlDecision(Frame):
    """One answer inside a `hitl_response_batch`: as `hitl_response`,
    plus a permission mode to switch to before the run resumes
    (`set_permission_mode`), so the very next tool call is checked
    under it.

    On the wire: ``hitl_decision``.
    """

    action: Literal["confirm", "reject"] = "reject"
    """`confirm` to run the tool call, `reject` to refuse it."""
    choice: Literal["", "once", "always", "similar", "deny"] = ""
    """How long the answer stands. `once` (or empty): this call only. `always`: save a rule allowing this exact call. `similar`: save a rule allowing calls like it. `deny`: save a rule refusing it."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    requirement_id: str = ""
    """The approval request's id, from its `hitl_request`."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    set_permission_mode: Literal["", "default", "plan", "acceptEdits", "bypassPermissions"] = ""
    """A permission mode to switch to before the run resumes; empty to keep the current one."""
    type: Literal["hitl_decision"] = "hitl_decision"
    """Always `hitl_decision`: what kind of message this is."""


class Requirement(Event):
    """A tool call that needs the person's approval before it runs.

    The run waits until a client answers with `hitl_response` (or
    `hitl_response_batch`), quoting `requirement_id`.

    On the wire: ``hitl_request``.
    """

    agent_path: list[str] = Field(default_factory=list)
    """The chain of agents that made the call, outermost first. Empty (or one entry) for the main agent; for example `["architect", "reviewer"]` when a reviewer started by an architect asked."""
    details: str = ""
    """Why approval is being asked, for the person; empty when there is no reason given."""
    details_pending: bool = False
    """True when `details` is still being written; it arrives later in a `requirement_details` message. Show a placeholder until then."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    friendly_name: str = ""
    """A human-readable name for the tool, for display; empty when there is none."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    requirement_id: str = ""
    """The request's id; quote it in the answer."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    tool_args: dict[str, JsonValue] = Field(default_factory=dict)
    """The arguments the tool would be called with."""
    tool_name: str = ""
    """The tool's name, as the model called it."""
    type: Literal["hitl_request"] = "hitl_request"
    """Always `hitl_request`: what kind of message this is."""


class HitlResponse(Frame):
    """The person's answer to one approval request (from `run_paused`).

    On the wire: ``hitl_response``.
    """

    action: Literal["confirm", "reject"] = "reject"
    """`confirm` to run the tool call, `reject` to refuse it."""
    choice: Literal["", "once", "always", "similar", "deny"] = ""
    """How long the answer stands. `once` (or empty): this call only. `always`: save a rule allowing this exact call. `similar`: save a rule allowing calls like it. `deny`: save a rule refusing it."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    requirement_id: str = ""
    """The approval request's id, from its `hitl_request`."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["hitl_response"] = "hitl_response"
    """Always `hitl_response`: what kind of message this is."""


class HitlResponseBatch(Frame):
    """The person's answers to every approval request of one pause, sent
    together: a request left out is taken as rejected.

    On the wire: ``hitl_response_batch``.
    """

    decisions: list[HitlDecision] = Field(default_factory=list)
    """One answer per approval request."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["hitl_response_batch"] = "hitl_response_batch"
    """Always `hitl_response_batch`: what kind of message this is."""


class HookEntryView(Model):
    """One configured hook: what it runs, and on which event.

    Hooks come in several types (a shell command, an HTTP call, an MCP
    tool call, …). A field that does not apply to a hook's type is
    empty, e.g. `command` on an HTTP hook or `url` on a command hook.
    """

    background: bool = False
    """Whether the hook runs without making the agent wait for it."""
    command: str = ""
    """The shell command a `command` hook runs."""
    event: str
    """The event the hook runs on."""
    header_names: list[str] = Field(default_factory=list)
    """The names of the headers an `http` hook sends. Never their values, which may be credentials."""
    matcher: str = ""
    """Which targets the hook applies to; empty matches every target."""
    timeout_ms: int = 0
    """How long the hook may run, in milliseconds."""
    type: str = ""
    """The hook's type, e.g. `command` or `http`."""
    url: str = ""
    """The URL an `http` hook calls, with any credentials removed."""


class HostSignal(Model):
    """A signal for one extension's pages: pass it to every page of that extension you show."""

    extension_id: str
    """The id of the extension whose pages it is for."""
    signal: str
    """The signal's name, e.g. `chat.run_completed` or `session.switched`."""
    value: JsonValue = None
    """The signal's value; its shape depends on `signal`."""


class HttpRetryAttemptEventPayload(Model):
    """A web fetch failed with a temporary error and igni is about to retry it."""

    attempt: int
    """Number of the attempt about to be made, counting the first request as 1 (so the first retry is 2)."""
    delay_seconds: float
    """Seconds igni waits before making this attempt."""


class HttpRetrySucceededEventPayload(Model):
    """A web fetch succeeded after at least one retry."""

    attempt_count: int
    """Total number of requests made, including the first."""
    delay_seconds: float
    """Total seconds spent waiting between attempts."""
    url: str
    """URL that was fetched."""


class Hydrated(Model):
    """The answer to `hydrate`: the window's whole model, its revision, and the fields nobody has set."""

    op: Literal["hydrate"] = "hydrate"
    """Always `hydrate`: the request this answers."""
    rev: int
    """The window's revision."""
    state: WindowModelState
    """Every field of the window's model, as the model holds it."""
    unset: list[str]
    """The fields still at their defaults, never set."""


class InfoMessage(Event):
    """A short informational message to show the person.

    On the wire: ``info``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    text: str = ""
    """The message."""
    type: Literal["info"] = "info"
    """Always `info`: what kind of message this is."""


class InstallPluginArgs(Args):
    """Arguments for installing a plugin."""

    install_ref: str | None = None
    """Branch, tag or commit to check out; when absent, the marketplace's choice or the default branch."""
    ref: str
    """A git URL, or `@<marketplace>/<plugin>` for a marketplace plugin."""


class InterruptedRun(Model):
    """A run that stopped before it finished, and the user message that
    started it. A client can offer to retry it, discard it, or edit the
    message and send it again.
    """

    content: str
    """That message's text."""
    interrupted_at: int
    """When the run stopped, in seconds since the Unix epoch."""
    last_error: str | None = None
    """The error, when `reason` is `errored`; `null` otherwise."""
    message_id: str
    """The id of the user message that started the run."""
    reason: Literal["cancelled", "errored", "abandoned"]
    """Why it stopped: `cancelled` (the user stopped it), `errored` (it failed; see `last_error`) or `abandoned` (it never finished, e.g. igni stopped while it ran)."""
    received_at: int
    """When igni received the message, in seconds since the Unix epoch."""


class InterruptedRunArgs(Args):
    """Arguments naming one interrupted run of a session."""

    message_id: str
    """Id of the message that started the run, as listed by `get_interrupted_runs`; must not be empty."""
    session_id: str
    """Id of the session to act on."""


class LatestPlanResult(Model):
    """The session's current plan-mode plan and task list.

    Read it when opening a plan view and again after the agent submits
    a plan.
    """

    history: list[str] = Field(default_factory=list)
    """Earlier plans submitted in this session, oldest first."""
    latest: str = ""
    """The most recent plan text (Markdown); empty if none."""
    state: Literal["pending", "approved", "dismissed", ""] = ""
    """`pending` when a plan is waiting for the user to approve or dismiss it; `""` when no plan has been submitted."""
    tasks: list[TodoItem] = Field(default_factory=list)
    """The session's current task (todo) list."""


class ListDirsArgs(Args):
    """Arguments for listing the folders inside a folder."""

    path: str | None = None
    """The folder to list; the home folder when absent or empty."""
    show_hidden: bool = False
    """Include folders whose names start with a dot."""


class LoginResultPayload(Model):
    """Channel `login_result`. How a sign-in ended. Sent once, after
    the `login` call has returned and the sign-in has finished.
    """

    flow_id: str = ""
    """The sign-in it ends: the `flow_id` that `login` returned."""
    result: str
    """On success, the signed-in email address; on failure, why it failed. May be empty."""
    success: bool
    """Whether the user is now signed in."""


class LoginStarted(Model):
    """Confirms that a sign-in has started. Its progress and outcome
    arrive later as `login_status` and `login_result` pushes.
    """

    flow_id: str = ""
    """This sign-in's id, which its `login_status` and `login_result` pushes carry."""
    started: bool
    """`true` when the sign-in started."""


class LoginStatusPayload(Model):
    """Channel `login_status`. Progress of a sign-in that is under way,
    as text for a person.
    """

    flow_id: str = ""
    """The sign-in it is about: the `flow_id` that `login` returned."""
    text: str
    """The current status, for a person."""


class LoopAdvance(Model):
    """What happened when a repeating prompt loop moved to its next iteration.

    `kind` says which of three outcomes this is; only the fields
    belonging to that outcome are set, the rest keep their defaults:

    * `completed` - the loop reached the iteration count the user asked
      for and has ended; `total_iterations` holds that count.
    * `safety_paused` - a loop with no explicit count reached igni's
      safety limit and paused instead of ending; `iteration` holds the
      count reached.
    * `step` - a normal next iteration: `prompt`, `display_prompt`,
      `iteration`, `remaining` and `cap_explicit` are set.
    """

    auto_extended: bool = False
    """True on the first iteration after an open-ended loop's safety budget rolled over (it is extended every 30 iterations, up to 200)."""
    cap_explicit: bool = False
    """True when the user gave an explicit iteration count; false for an open-ended loop that runs until stopped or the safety limit."""
    completed: bool = False
    """True when `kind` is `completed`."""
    display_prompt: str = ""
    """The user's own prompt text, for showing in the chat. Set only when `kind` is `step`."""
    iteration: int = 0
    """1-based number of the iteration about to run (`step`), or the number reached when the loop paused (`safety_paused`)."""
    kind: Literal["completed", "safety_paused", "step"] = "step"
    """Which outcome this is: `completed` (loop finished its requested count), `safety_paused` (an open-ended loop hit the safety limit and paused) or `step` (a normal next iteration)."""
    prompt: str = ""
    """Full text sent to the agent for this iteration, including igni's loop instructions. Set only when `kind` is `step`."""
    remaining: int = 0
    """Iterations left after this one. Set only when `kind` is `step`."""
    safety_cap_paused: bool = False
    """True when `kind` is `safety_paused`."""
    total_iterations: int = 0
    """Number of iterations the loop ran. Set only when `kind` is `completed`."""


class LoopStatusSnapshot(Model):
    """Status of the session's `/loop` (a prompt the agent repeats
    over several iterations).
    """

    active: bool
    """`true` when a loop is running or paused."""
    announced_total: int | None
    """Total number of iterations the agent said the loop will take, for progress display (`N / total`); `null` if the agent has not said."""
    cap_explicit: bool
    """`true` when the user gave the iteration count (`/loop N <prompt>`), so the loop ends at the cap. `false`: the cap is a safety net that extends automatically."""
    iteration_index: int
    """Number of iterations started so far (1-based); `0` when idle."""
    iterations_remaining: int
    """Iterations left before the loop's cap is reached; `0` when idle."""
    paused: bool
    """`true` when the loop is paused and waits to be resumed: paused by hand, stopped at the hard iteration cap, or restored paused after igni restarted."""
    prompt: str
    """The prompt being looped; empty when no loop is active."""


class McpPrompt(Model):
    """One prompt template an MCP server offers."""

    arguments: list[str] = Field(default_factory=list)
    """Names of the arguments the prompt takes. Empty when it takes none."""
    description: str = ""
    """What the prompt is for. Empty when not given."""
    name: str
    """Name of the prompt on its server."""


class McpResource(Model):
    """One resource an MCP server offers (a file, document or other data it can return).

    Only `uri` is always set; the other fields are empty when the
    server does not provide them.
    """

    description: str = ""
    """What the resource contains. Empty when not given."""
    mime_type: str = ""
    """MIME type of the resource content, e.g. `text/plain`. Empty when unknown."""
    name: str = ""
    """Human-readable name of the resource. Empty when not given."""
    uri: str
    """URI that identifies the resource on its server."""


class McpServerSnapshot(Model):
    """Full details of one configured MCP server: connection state,
    tools, resources and prompts.
    """

    connected: bool
    """`true` when igni is currently connected to the server."""
    error: str = ""
    """The last connection error; empty if none."""
    name: str
    """The server's name, as configured."""
    policy_blocked: bool = False
    """`true` when an administrator policy forbids using this server."""
    prompts: list[McpPrompt] = Field(default_factory=list)
    """Prompts the server offers; empty when it is not connected."""
    resources: list[McpResource] = Field(default_factory=list)
    """Resources the server offers; empty when it is not connected."""
    tool_descriptions: dict[str, str] = Field(default_factory=dict)
    """Each tool's description, keyed by tool name."""
    tool_names: list[str] = Field(default_factory=list)
    """Every tool the server offered when it connected, including disabled ones."""
    tools_disabled: list[str] = Field(default_factory=list)
    """Tools the user has turned off; the agent cannot use them."""
    transport: str
    """How igni talks to the server, e.g. `stdio` or `sse`; `unknown` if it has no config."""


class McpServerSummary(Model):
    """An MCP server's name and whether it is connected.

    A cheap listing; use the server details call for tools,
    resources and prompts.
    """

    connected: bool
    """`true` when igni is currently connected to the server."""
    name: str
    """The server's name, as configured."""


class McpToggle(Frame):
    """Connect or disconnect one of the configured MCP servers.

    On the wire: ``mcp_toggle``.
    """

    connect: bool = True
    """True to connect, false to disconnect."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    server_name: str = ""
    """The MCP server's name, as configured."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["mcp_toggle"] = "mcp_toggle"
    """Always `mcp_toggle`: what kind of message this is."""


class McpToolToggleResult(Model):
    """Result of enabling or disabling one tool of an MCP server.

    Echoes the tool's new state, so no second call is needed to
    confirm it.
    """

    enabled: bool
    """The tool's state now: `true` if the agent may use it."""
    server: str
    """Name of the MCP server the tool belongs to."""
    tool: str
    """Name of the tool."""


class MarkReadArgs(Args):
    """Arguments for marking notifications read: give `ids`, or
    `source`, or neither to mark every notification read.
    """

    ids: list[str] | None = None
    """Ids of the notifications to mark read."""
    source: str | None = None
    """An extension id: marks all of that extension's notifications read."""


class MarkdownSlashCommand(Model):
    """A slash command the user wrote as a Markdown file."""

    argument_hint: str = ""
    """A hint for the arguments it takes; empty when it takes none."""
    description: str = ""
    """What the command does, in one line."""
    name: str
    """The command's name, without the leading `/`."""
    source: Literal["markdown"] = "markdown"
    """Always `markdown`: a command defined in a Markdown file."""


class MarketplaceInfo(Model):
    """A plugin marketplace registered with igni, with its catalog as of the last fetch."""

    last_fetched: str = ""
    """When the catalog was last fetched, as an ISO 8601 UTC timestamp. Empty if never."""
    name: str
    """Marketplace name."""
    plugins: list[MarketplacePluginInfo] = Field(default_factory=list)
    """Plugins in the catalog. Empty until the catalog has been fetched."""
    url: str
    """Git URL the marketplace catalog is fetched from."""


class MarketplaceNameArgs(Args):
    """Arguments naming a plugin marketplace."""

    name: str
    """Name of the marketplace."""


class MarketplacePluginInfo(Model):
    """One plugin listed in a marketplace's catalog, available to install."""

    branch: str = ""
    """Git branch to install from. Empty for the repository's default branch."""
    description: str = ""
    """What the plugin does. Empty when not given."""
    name: str
    """Plugin name; install it as `@<marketplace>/<name>`."""
    source: str
    """Where the plugin is fetched from: a git URL, followed by `[<subdirectory>]` when the plugin lives in a subdirectory of that repository."""
    version: str = ""
    """Version listed in the catalog. Empty when not given."""


class MarketplaceUrlArgs(Args):
    """Arguments for adding a plugin marketplace."""

    url: str
    """The marketplace's git URL."""


class McpInitResult(Model):
    """Outcome of connecting the session's configured MCP servers."""

    connected: list[str] = Field(default_factory=list)
    """Names of the servers that connected, sorted."""
    failed: dict[str, str] = Field(default_factory=dict)
    """Servers that failed to connect, mapped to the error for each."""
    rebuilt: bool = False
    """True when the session's agents were rebuilt so they can use the newly connected servers' tools."""
    skipped_reason: (
        Literal["already_initialized", "no_configured_servers", "no_clients_connected"] | None
    ) = None
    """Why no connection attempt was made, or why nothing changed: `already_initialized` (servers were connected earlier in the session), `no_configured_servers` (no MCP servers are configured) or `no_clients_connected` (every server failed, so the agents were not rebuilt). Null when a connection pass ran and at least one server connected."""


class McpServerArgs(Args):
    """Arguments naming a configured MCP server."""

    server_name: str
    """The server's name in the MCP configuration."""


class McpServerStatus(Model):
    """Connection state of one configured MCP server."""

    connected: bool
    """True when igni currently has a live connection to the server."""
    name: str
    """Name of the MCP server as configured."""


class McpToolEnabledArgs(Args):
    """Arguments for switching one MCP server tool on or off."""

    enabled: bool
    """The tool's new state: `true` lets the agent use it."""
    server: str
    """Name of the MCP server; not checked to exist."""
    tool: str
    """Name of the server's tool; not checked to exist."""


class ModelCompleted(RunEvent):
    """One model call within a run has finished; its token counts are known.

    On the wire: ``model_completed``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    input_tokens: int = 0
    """Tokens sent to the model in this call."""
    output_tokens: int = 0
    """Tokens the model produced in this call."""
    parent_run_id: str = ""
    """The id of the run that started this one, for a sub-agent's run; empty for a top-level run."""
    run_id: str = ""
    """The id of the run this event belongs to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["model_completed"] = "model_completed"
    """Always `model_completed`: what kind of message this is."""


class ModelRegistryEntryView(Model):
    """One configured model as a client sees it: what it is and how it
    runs. Its API key is never included, and its URL has any credentials
    removed.
    """

    context_window: int | None = None
    """The model's context window, in tokens; `null` when not set."""
    effort: str | None = None
    """The reasoning effort asked of the model, `low` to `max` (Anthropic models only); `null` when not set."""
    has_api_key: bool
    """Whether the entry says where its key comes from (a key, an environment variable or a command). Never the key itself."""
    max_tokens: int | None = None
    """Most tokens a reply may hold; `null` for the default."""
    model_id: str
    """The model's id as the provider knows it."""
    prompt_caching: bool
    """Whether the system prompt and tool list are sent as cacheable (Anthropic models only)."""
    provider: str
    """The provider that serves the model, e.g. `anthropic` or `openai_like`."""
    source: str = ""
    """Where the entry came from: `cloud` for igni server's models, empty for the local configuration's own."""
    temperature: float | None = None
    """Sampling temperature; `null` for the provider's default."""
    thinking: dict[str, JsonValue] | None = None
    """The `thinking` object sent to the model unchanged, e.g. `{"type": "adaptive"}` (Anthropic models only); `null` when not set."""
    timeout: int
    """How long a request may take, in seconds."""
    url: str | None = None
    """The endpoint the model is reached at, without credentials; `null` for the provider's default."""
    vision: bool
    """Whether the model accepts images."""


class ModelRegistryResult(Model):
    """The models a user can pick from, and which one is the default."""

    default: str
    """The name of the default model, a key of `registry`; empty means the first entry of `registry` is used."""
    max_context_window: int
    """The configured overall context-window limit, in tokens; also the size used while no model is configured."""
    registry: dict[str, ModelRegistryEntryView]
    """Every configured model, keyed by the name used to pick it."""


class ModelSwitch(Frame):
    """Switch the session to a different model.

    On the wire: ``model_switch``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    model_name: str = ""
    """The id of the model to switch to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["model_switch"] = "model_switch"
    """Always `model_switch`: what kind of message this is."""


class ModelSwitched(Model):
    """What a successful `switch_model` answers."""

    text: str
    """Says the model switched, with a note for any part of the choice that could not be saved."""


class NoArgs(Args):
    """The arguments of a call that takes none: `{}`."""


class NotificationCounts(Model):
    """How many notifications are unread, in all and per extension — the numbers for badges."""

    by_source: dict[str, int] = Field(default_factory=dict)
    """Unread notifications per extension id; an extension with none is left out."""
    unread: int = 0
    """Unread notifications in all."""


class NotificationTarget(Model):
    """Where opening a notification goes: one of its extension's pages."""

    page: str = Field(min_length=1)
    """The id of the extension's page to open."""
    params: dict[str, str] = Field(default_factory=dict)
    """The parameters to open the page with. Always strings: a number or a flag is given as its JSON text."""


class NotificationsChanged(Model):
    """The unread notification counts changed. Refetch the list if you are showing it."""

    cause: Literal["server", "listed", "marked_read", "extension", "signed_out"] = "server"
    """What changed them. `server`: igni server's list was fetched again on its own (after signing in, or when the server said something changed). `listed`: a `notifications_list` call fetched it. `marked_read`: a `notifications_mark_read` call. `extension`: an extension on this machine posted a notice. `signed_out`: the person signed out."""
    counts: NotificationCounts = Field(
        default_factory=lambda: NotificationCounts.model_validate({"by_source": {}, "unread": 0})
    )
    """The unread counts now."""


class NotificationsListResult(Model):
    """The person's notifications, newest first, with the unread counts."""

    counts: NotificationCounts = Field(
        default_factory=lambda: NotificationCounts.model_validate({"by_source": {}, "unread": 0})
    )
    """The unread counts."""
    notifications: list[FloorNotification] = Field(default_factory=list)
    """The notifications, newest first."""
    server_error: str = ""
    """Why igni server could not be asked, when it could not; empty otherwise. The local notifications and the last ones fetched from the server are still returned."""


class NotificationsReadResult(Model):
    """The unread counts after marking notifications read."""

    counts: NotificationCounts = Field(
        default_factory=lambda: NotificationCounts.model_validate({"by_source": {}, "unread": 0})
    )
    """The unread counts now."""
    server_error: str = ""
    """Why igni server could not be told, when it could not; empty otherwise. Notifications from the server may then still count as unread."""


class OrchestrateEventPayload(Model):
    """A sub-agent's progress (a tool call, its start, pause, end or error, a task) or a view the agent or an extension drew, told apart by `type`."""


class OutputStyleChangedEventPayload(Model):
    """The session's output style changed.

    Lets a client update whatever shows the active style without
    polling.
    """

    previous: str
    """Name of the output style in effect before the change."""
    style: str
    """Name of the output style now in effect."""


class OutputStyleInfo(Model):
    """One output style the agent can answer in."""

    description: str
    """What the style does, in one line."""
    name: str
    """The style's name, as it is chosen."""


class OutputStylesResult(Model):
    """The output styles available, and which one is in use."""

    active: str
    """The name of the style in use."""
    styles: list[OutputStyleInfo]
    """Every style that can be chosen."""


class Page(Model):
    """One level of a window's page stack."""

    kind: str
    """What kind of page this is: `plugins`, `extensions`, or an extension's own kind."""
    label: str = ""
    """The name shown for this page."""
    params: dict[str, str] = Field(default_factory=dict)
    """The page's parameters, as text: what the page was opened with."""


class Panel(Model):
    """The panel open over a window's chat. One at a time."""

    kind: str
    """What kind of panel this is: `notifications`, `search`, `login` or `dir-picker`."""
    params: dict[str, JsonValue] = Field(default_factory=dict)
    """The panel's own parameters: what the panel shows, in the panel's own shape."""


class PendingMessage(Model):
    """A user message whose run has started but not yet finished."""

    content: str
    """The message's text."""
    message_id: str
    """The message's id."""
    received_at: int
    """When igni received it, in seconds since the Unix epoch."""
    role: Literal["user"] = "user"
    """Always `user`."""


class PermissionModeChangedEventPayload(Model):
    """The session's permission mode was switched."""

    kind: Literal["switched"] = "switched"
    """Always `switched`: the mode was changed directly, as opposed to the agent entering plan mode on its own (reported with kind `plan_mode_entered`)."""
    mode: PermissionMode
    """Permission mode now in effect."""
    previous: PermissionMode
    """Permission mode in effect before the switch."""


class PermissionModeChangedPayload(Model):
    """The session's permission mode changed: the switch itself (`mode` and `previous`), or the plan tool's note that the agent entered plan mode (`mode`, `source`, `reason`)."""


class PickDirArgs(Args):
    """Arguments for opening the operating system's folder picker."""

    start: str | None = None
    """Folder the picker opens in; the session's project folder when absent or empty."""


class PickDirResult(Model):
    """The folder the user chose in the operating system's own folder picker."""

    cancelled: bool
    """`true` when the user closed the picker without choosing."""
    error: str
    """Why the picker could not be shown, e.g. no native dialog is available; empty otherwise."""
    path: str
    """The chosen folder; empty when none was chosen."""


class PlanDecidedEventPayload(Model):
    """A plan the agent proposed was approved or dismissed.

    Clients use it to move the plan card from pending to its final
    state.
    """

    decision: PlanDecision
    """The decision recorded: `approved` or `dismissed`."""
    run_id: str
    """Run in which the agent submitted the plan."""


class PlanDecisionResult(Model):
    """Outcome of approving or dismissing a plan the agent proposed."""

    decision: PlanDecision
    """The decision recorded: `approved` or `dismissed`."""
    error: str | None = None
    """Why the decision was not recorded. Null when `ok` is true."""
    mode_status: str = ""
    """One-line summary of the permission-mode change the decision caused (for example `mode → default` on approval). Empty when the mode did not change."""
    ok: bool = True
    """True when the decision was recorded; false when it could not be (for example an unknown run or a storage failure)."""
    run_id: str
    """Run in which the agent submitted the plan; identifies which plan was decided."""


class PlanModeEnteredEventPayload(Model):
    """Plan mode was entered, with who entered it and why.

    Sent on the same channel as a plain permission-mode switch, after
    it; a client can show it as a short banner explaining the switch.
    """

    kind: Literal["plan_mode_entered"] = "plan_mode_entered"
    """Always `plan_mode_entered`: tells this message apart from a plain mode switch (kind `switched`) on the same channel."""
    mode: Literal["default", "plan", "acceptEdits", "bypassPermissions"]
    """Permission mode now in effect: `default` (ask before risky actions), `plan` (read-only planning, no edits), `acceptEdits` (file edits approved automatically) or `bypassPermissions` (no approval prompts)."""
    reason: str = ""
    """Why plan mode was entered, as given. Empty when none was given."""
    source: Literal["agent", "user"]
    """Who entered plan mode: `agent` (the agent chose to plan first) or `user`."""


class PlanRunArgs(Args):
    """Arguments naming the run that submitted a plan.

    An empty `run_id` is refused in the answer (`ok: false`) rather
    than as an invalid argument; a number is taken as its string.
    """

    run_id: str = ""
    """Id of the run that submitted the plan, as `plan_submitted` carries it."""


class PlanSubmittedEventPayload(Model):
    """The agent submitted a plan for the user to approve or dismiss.

    `tasks` is the plan's initial checklist, in the same row shape
    as the `todos_updated` push; later `todos_updated` pushes
    update the rows' statuses as work proceeds.
    """

    plan: str
    """The plan text, in Markdown."""
    run_id: str | None = None
    """Run in which the plan was submitted; pass it back when approving or dismissing the plan. Omitted when not known."""
    tasks: list[TodoItem] = Field(default_factory=list)
    """Checklist of the plan's steps, all starting as `pending`. Empty when the plan has no task list."""


class PlanTurn(Model):
    """A plan the agent proposed in plan mode, shown in place of the
    `exit_plan_mode` tool call.
    """

    created_at: int = 0
    """When the message was created, in Unix epoch seconds; `0` if unknown."""
    plan: str = ""
    """The plan text (Markdown)."""
    role: Literal["plan"] = "plan"
    """Turn kind; always `plan`."""
    run_id: str = ""
    """Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point."""
    state: Literal["pending", "approved", "dismissed", ""] = ""
    """Whether the user acted on the plan: `pending` (not yet), `approved`, `dismissed`, or `""` if unknown."""
    tasks: list[JsonValue] = Field(default_factory=list)
    """The task list submitted with the plan."""


class PluginAgentInfo(Model):
    """An agent the plugin provides."""

    description: str = ""
    """What the agent does; may be empty."""
    name: str
    """The agent's name."""


class PluginContents(Model):
    """What a plugin contains: its skills, agents, hooks, MCP servers,
    tools and README.

    Describes an installed plugin, or one previewed from a marketplace
    before installing. When `error` is set, the lists are empty.
    """

    agents: list[PluginAgentInfo] = Field(default_factory=list)
    """Agents the plugin provides."""
    error: str = ""
    """Why the plugin could not be read (not found, git clone failed, ...); empty on success."""
    hooks: list[PluginHookInfo] = Field(default_factory=list)
    """Hooks the plugin registers, per event."""
    mcp_servers: list[PluginMcpServerInfo] = Field(default_factory=list)
    """MCP servers the plugin provides."""
    name: str = ""
    """The plugin's name."""
    preview_source: PluginPreviewSource | None = None
    """Where a previewed plugin comes from; `null` for an installed plugin."""
    readme: str = ""
    """The plugin's README (Markdown); empty if it has none."""
    root_path: str = ""
    """Folder the plugin was read from."""
    skills: list[PluginSkillInfo] = Field(default_factory=list)
    """Skills the plugin provides."""
    tools: list[PluginToolInfo] = Field(default_factory=list)
    """Custom tools the plugin provides."""


class PluginEnabledArgs(Args):
    """Arguments for switching an installed plugin on or off."""

    enabled: bool
    """The plugin's new state: `true` to switch it on."""
    name: str
    """Name of the installed plugin."""


class PluginHookInfo(Model):
    """Hooks the plugin registers for one event."""

    count: int
    """Number of hook handlers the plugin registers for the event."""
    event: str
    """The hook event, e.g. `PreToolUse` or `Stop`."""


class PluginInfo(Model):
    """One installed plugin, with what it bundles and whether it is enabled."""

    description: str = ""
    """What the plugin does. Empty when not given."""
    enabled: bool = True
    """True when the plugin is active in this session."""
    has_agents: bool = False
    """True when the plugin bundles agents."""
    has_hooks: bool = False
    """True when the plugin bundles hooks."""
    has_lsp: bool = False
    """True when the plugin bundles language-server configurations."""
    has_mcp: bool = False
    """True when the plugin bundles MCP server configurations."""
    has_monitors: bool = False
    """True when the plugin bundles monitors."""
    has_skills: bool = False
    """True when the plugin bundles skills."""
    has_tools: bool = False
    """True when the plugin bundles tools."""
    managed: bool = False
    """True when a system administrator installed the plugin; it is always enabled and cannot be disabled by the user."""
    name: str
    """Plugin name from its manifest."""
    path: str = ""
    """Directory the plugin is installed in."""
    pin: str = ""
    """Git commit the plugin is pinned to. Empty when it is not pinned."""
    source_root: str = ""
    """Where the plugin was found: `user-claude` (~/.claude/plugins), `user-igni` (~/.igni/plugins), `project-claude` (the project's .claude/plugins), `project-igni` (the project's .igni/plugins), `group-policy-igni` (installed by the organization's policy), `managed-claude` or `managed-igni` (installed by a system administrator)."""
    version: str = ""
    """Version from the plugin's manifest. Empty when not given."""


class PluginMcpServerInfo(Model):
    """An MCP server the plugin provides."""

    command: str
    """The command that starts the server (or its URL); may be empty."""
    name: str
    """The server's name."""
    transport: str
    """How igni talks to the server, e.g. `stdio` or `sse`."""


class PluginNameArgs(Args):
    """Arguments naming an installed plugin."""

    name: str
    """Name of the installed plugin."""


class PluginPreviewSource(Model):
    """Where a previewed plugin comes from: a git repository and,
    optionally, a folder inside it.

    Displayed as `"<url> [<subdir>]"`.
    """

    subdir: str = ""
    """Folder inside the repository that holds the plugin; empty for the root."""
    url: str
    """The plugin's git repository URL."""


class PluginSkillInfo(Model):
    """A skill the plugin provides."""

    description: str = ""
    """What the skill does; may be empty."""
    name: str
    """The skill's name."""


class PluginToolInfo(Model):
    """A custom tool the plugin provides."""

    name: str
    """The tool's name."""


class Preview(Model):
    """The file a window's preview shows."""

    path: str
    """The path of the file being previewed."""


class PreviewPluginArgs(Args):
    """Arguments for previewing a plugin from git without installing it."""

    branch: str | None = None
    """Branch, tag or commit to read; the default branch when absent."""
    source: str
    """The plugin's git URL, optionally followed by a folder inside the repository."""
    subdir: str | None = None
    """The plugin's folder inside the repository; overrides one given in `source`."""


class ProcessArgs(Args):
    """Arguments naming a background process."""

    pid: int
    """Operating-system process id of the background process."""


class ProcessExitedPayload(Model):
    """Channel `process_exited`. A background process has finished."""

    cmd: str | None
    """The command it ran; `null` when unknown."""
    duration_seconds: float | None
    """How long it ran, in seconds; `null` when unknown."""
    exit_code: int | None
    """Its exit code; `null` when unknown."""
    pid: int | None
    """The process's id; `null` when unknown."""


class ProcessLinePayload(Model):
    """Channel `process_line`. One line of output from a running
    background process, sent as it is printed.
    """

    line: str | None
    """The line, from stdout or stderr, without its line ending; `null` when there is none."""
    pid: int | None
    """The process's id; `null` when unknown."""


class ProcessRow(Model):
    """A background process the agent started, running or recently
    finished.
    """

    cmd: str
    """The command line that started the process."""
    elapsed_seconds: float
    """How long the process has run (or ran), in seconds."""
    exit_code: int | None = None
    """The process's exit code once it has finished; `null` while running."""
    is_running: bool = True
    """`true` while the process is still running."""
    pid: int
    """Operating-system process id."""


class ProcessStartedPayload(Model):
    """Channel `process_started`. A background process has started."""

    cmd: str | None
    """The command it runs; `null` when unknown."""
    pid: int | None
    """The process's id, which its later `process_*` pushes carry; `null` when unknown."""
    started_at: float | None
    """When it started, in seconds since the Unix epoch; `null` when unknown."""


class ProcessTailArgs(Args):
    """Arguments for reading the latest output of a background process."""

    pid: int
    """Operating-system process id of the background process."""
    tail: int = 200
    """How many of the last lines to return (at least 1)."""


class ProcessTailResult(Model):
    """The latest output of a background process."""

    exit_code: int | None
    """The exit code once the process has finished; `null` while running or if unknown."""
    is_running: bool
    """`true` while the process is still running; `false` for an unknown pid."""
    output: str
    """The last lines of the process's combined stdout and stderr; empty for an unknown pid."""
    pid: int
    """Operating-system process id that was asked for."""


class PromoteAgentArgs(Args):
    """Arguments for keeping an agent created during the session."""

    name: str
    """Name of the agent created during the session."""
    target: str | None = None
    """Where to save it: `project` (the project's agents; the default) or `personal` (the user's own agents)."""


class PromoteEphemeralResult(Model):
    """The outcome of saving an agent created during a session as a
    permanent agent file.
    """

    dest: str = ""
    """The file it was saved to; empty when `ok` is false."""
    name: str
    """The agent's name."""
    ok: bool
    """Whether the agent was saved."""
    reason: str = ""
    """Why it was not saved; empty when `ok` is true."""


class PushNotification(Event):
    """A push — the channel, and the payload that channel carries.

    Something happened that a client may want to show, sent without
    being asked. Scheduled tasks, login status, permission-mode
    changes, background processes, file edits and more each have a
    `channel`; the shape of `payload` depends on it. Ignore a
    channel you do not know.

    The `channel` field says which kind of event this is; a client
    routes on it to render or dispatch. See `PushChannel` for
    the catalogue of known channels — the producer set is open, so
    treat anything unlisted as a channel this module simply hasn't
    catalogued yet, not as invalid.

    `channel` stays a raw `str` on the wire (not a strict
    `PushChannel` enum field) so a producer emitting a channel
    the catalogue does not name yet survives verbatim — a strict enum
    with `_missing_` → `UNKNOWN` would rewrite the value to
    `"unknown"` and lose the routing information a client keys on.

    Producers should build their pushes with the `push_*` factories
    below rather than by hand: each takes that channel's payload
    model, so the channel and the payload cannot drift apart.

    On the wire: ``push_notification``.
    """

    channel: str = ""
    """What kind of push this is; it decides the shape of `payload`."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    """The push's data, shaped by `channel`."""
    run_id: str = ""
    """The run whose work sent this push, when igni chose that run's id; empty otherwise."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["push_notification"] = "push_notification"
    """Always `push_notification`: what kind of message this is."""


class QueueMessage(Frame):
    """A message the person sends while a run is still going; it is queued for the agent.

    On the wire: ``queue_message``.
    """

    client_id: str = ""
    """This client's id, from `welcome`, so it can recognise its own echo. Empty is allowed."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    text: str = ""
    """The message."""
    type: Literal["queue_message"] = "queue_message"
    """Always `queue_message`: what kind of message this is."""


class RpcRequest(Frame):
    """A call to one of igni's methods. igni answers with an `rpc_response` carrying the same `id`.

    On the wire: ``rpc_request``.
    """

    args: dict[str, JsonValue] = Field(default_factory=dict)
    """The method's arguments, by name."""
    caller: str | None = None
    """The id of the extension whose page is making the call; null for igni's own interface. Methods under `ext.` need it: an extension may reach only its own service."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    method: str = ""
    """The name of the method to call."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["rpc_request"] = "rpc_request"
    """Always `rpc_request`: what kind of message this is."""


class RpcResponse(Event):
    """The answer to an `rpc_request`, with the request's `id`.

    It carries either `result` (the call succeeded) or `error` and
    `code` (it failed), never both. The two factories build the two
    shapes; a frame that carries both is refused on the way in.

    On the wire: ``rpc_response``.
    """

    code: RpcErrorCode | None = None
    """Why the call failed, for a client to branch on; null on success."""
    error: str | None = None
    """What went wrong, as a sentence for a person; null on success."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    result: JsonValue = None
    """Any JSON value."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["rpc_response"] = "rpc_response"
    """Always `rpc_response`: what kind of message this is."""


class ReadFileArgs(Args):
    """Arguments for reading a file to preview it."""

    path: str
    """The file: relative to the project, absolute, or an `attachment:<id>` reference."""


class ReadFileResult(Model):
    """The contents of a text file, for previewing it.

    Only files inside the project or igni's data folder can be read,
    and large files are refused.
    """

    contents: str
    """The file's text; empty when `error` is set."""
    error: str = ""
    """Why the file could not be read; empty on success."""
    language: str = ""
    """Syntax-highlighting language guessed from the file extension (e.g. `python`); empty if unknown or on error."""
    path: str
    """The file's path (resolved to an absolute path when the read got that far)."""
    size: int
    """The file's size in bytes."""


class ReasoningStarted(RunEvent):
    """The model has started reasoning ("thinking") before it replies.

    On the wire: ``reasoning_started``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    parent_run_id: str = ""
    """The id of the run that started this one, for a sub-agent's run; empty for a top-level run."""
    run_id: str = ""
    """The id of the run this event belongs to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["reasoning_started"] = "reasoning_started"
    """Always `reasoning_started`: what kind of message this is."""


class RefreshMarketplacesArgs(Args):
    """Arguments for re-reading marketplace catalogues."""

    name: str | None = None
    """The marketplace to refresh; every marketplace when absent."""


class RequirementDetails(Event):
    """The reason for an open approval request, sent after the request itself.

    A request sent with `details_pending` set gets its `details`
    later in this message; show it in place of the placeholder.

    On the wire: ``requirement_details``.
    """

    details: str = ""
    """Why approval is being asked, for the person."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    requirement_id: str = ""
    """The id of the approval request."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["requirement_details"] = "requirement_details"
    """Always `requirement_details`: what kind of message this is."""


class RequirementResolved(Event):
    """An approval request was answered, in any client; close its dialog if you show one.

    On the wire: ``requirement_resolved``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    requirement_id: str = ""
    """The id of the approval request that was answered."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["requirement_resolved"] = "requirement_resolved"
    """Always `requirement_resolved`: what kind of message this is."""


class Revised(Model):
    """The answer to `dismiss_toast`: the window's new revision."""

    op: Literal["dismiss_toast"] = "dismiss_toast"
    """Always `dismiss_toast`: the request this answers."""
    rev: int
    """The window's revision after the toast was dismissed."""


class RunCompleted(RunEvent):
    """An agent or team run has finished.

    On the wire: ``run_completed``.
    """

    duration: float = 0.0
    """How long the run took, in seconds."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    input_tokens: int = 0
    """Tokens sent to the model over the whole run."""
    output_tokens: int = 0
    """Tokens the model produced over the whole run, reasoning included."""
    parent_run_id: str = ""
    """The id of the run that started this one, for a sub-agent's run; empty for a top-level run."""
    reasoning_tokens: int = 0
    """The part of `output_tokens` spent on the model's reasoning. The visible reply is `output_tokens - reasoning_tokens`."""
    run_id: str = ""
    """The id of the run this event belongs to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["run_completed"] = "run_completed"
    """Always `run_completed`: what kind of message this is."""


class RunError(Event):
    """The run failed and has stopped.

    On the wire: ``run_error``.
    """

    error: str = ""
    """What went wrong, as a human-readable message."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["run_error"] = "run_error"
    """Always `run_error`: what kind of message this is."""


class RunErrorEvent(Model):
    """A sub-agent's run failed."""

    agent_path: str
    """Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level)."""
    card_id: str | None = None
    """Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card."""
    error: str
    """Error message describing the failure."""
    type: Literal["run_error"] = "run_error"
    """Always `run_error`: what kind of message this is."""


class RunPaused(RunEvent):
    """The run is paused until the person approves or rejects one or more tool calls.

    Answer every request with `hitl_response_batch` (or each one with
    `hitl_response`) to let the run continue.

    On the wire: ``run_paused``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    parent_run_id: str = ""
    """The id of the run that started this one, for a sub-agent's run; empty for a top-level run."""
    requirements: list[Requirement] = Field(default_factory=list)
    """The tool calls waiting for an answer."""
    run_id: str = ""
    """The id of the run this event belongs to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["run_paused"] = "run_paused"
    """Always `run_paused`: what kind of message this is."""


class RunShellArgs(Args):
    """Arguments for running a shell command in the project folder."""

    command: str = ""
    """The command line to run (without a leading `$`); blank runs nothing."""


class RunShellResult(Model):
    """What a `$` command printed and how it ended — or, when it outlived
    the wait, that it went on in the background and under which `pid`,
    the id its `process_*` pushes carry.
    """

    backgrounded: bool = False
    """`true` when the command is still running, in the background."""
    exit_code: int
    """The exit code; `0` for a command still running in the background."""
    output: str
    """What the command printed, stdout and stderr together."""
    pid: int | None = None
    """The process's id, once it started; `null` when it could not start."""


class RunStarted(RunEvent):
    """An agent or team run has begun.

    On the wire: ``run_started``.
    """

    agent_name: str = ""
    """The name of the agent (or team) doing the run."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    model: str = ""
    """The id of the model the run uses."""
    parent_run_id: str = ""
    """The id of the run that started this one, for a sub-agent's run; empty for a top-level run."""
    run_id: str = ""
    """The id of the run this event belongs to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["run_started"] = "run_started"
    """Always `run_started`: what kind of message this is."""


class SavePermissionRuleArgs(Args):
    """Arguments for saving a permission rule for the project."""

    level: Literal["allow", "ask", "deny"]
    """What the rule does: `allow`, `ask` or `deny`."""
    rule: str
    """The permission rule: a tool name, or a tool with an argument pattern such as `Bash(git status)`."""


class ScheduledTask(Model):
    """A prompt scheduled to run at a later time, once or repeatedly.

    When a recurring task completes, igni schedules its next occurrence
    as a new task.
    """

    created_at: datetime | None = None
    """When the task was scheduled, in the machine's local time."""
    description: str
    """What the task does: the prompt igni runs when it is due."""
    error: str = ""
    """Error message when the run failed. Empty otherwise."""
    id: str
    """Short identifier of the task (8 hex characters)."""
    recurrence: str = ""
    """Repeat pattern in the form `every N <minutes|hours|days|weeks>` (e.g. `every 1 days`, `every 7 days`). Empty for a one-time task."""
    result: str = ""
    """Output of the run once it completed. Empty until then."""
    scheduled_at: datetime
    """When the task is due to run, in the machine's local time."""
    status: TaskStatus = "pending"
    """Where the task is in its lifecycle."""


class ScheduledTaskArgs(Args):
    """Arguments naming a scheduled task."""

    task_id: str
    """The task's `id`, as `get_scheduled_tasks` lists it."""


class ScheduledTaskRunResult(Model):
    """The answer of a scheduled task run, and the run's id."""

    result: str
    """The agent's answer, as text."""
    run_id: str
    """The run's id: the one asked for, or the one made."""


class ScheduledTasksArgs(Args):
    """Arguments for listing scheduled tasks."""

    include_done: bool = True
    """Also list completed, failed and cancelled tasks."""


class SchedulerCompletedPayload(Model):
    """Channel `scheduler_completed`. A scheduled task has finished."""

    description: str
    """What the task does, as it was scheduled."""
    result: str
    """The task's outcome, as text."""
    task_id: str
    """The scheduled task's id."""


class SchedulerEvent(Event):
    """A scheduled task started or finished.

    On the wire: ``scheduler_event``.
    """

    description: str = ""
    """What the task does, as it was scheduled."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    event_type: str = ""
    """What happened: `started`, `completed`, or `failed` (sometimes sent as `error`). Other values may appear; treat them as unknown."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    result: str = ""
    """The task's output when it finished, or the error when it failed; empty when it started."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    task_id: str = ""
    """The scheduled task's id."""
    type: Literal["scheduler_event"] = "scheduler_event"
    """Always `scheduler_event`: what kind of message this is."""


class SchedulerStartedPayload(Model):
    """Channel `scheduler_started`. A scheduled task has started running."""

    description: str
    """What the task does, as it was scheduled."""
    task_id: str
    """The scheduled task's id."""


class Scroll(Model):
    """Where a window's transcript is scrolled to."""

    at_bottom: bool = True
    """Whether the transcript is scrolled to its end."""
    message_id: str | None = None
    """The message the transcript is scrolled to; null when it is at the end."""


class SearchChatArgs(Args):
    """Arguments for searching a session's conversation."""

    limit: int = 50
    """Maximum number of hits to return."""
    query: str
    """Text to find, case-insensitive; blank finds nothing."""
    session_id: str
    """Id of the session to act on."""


class SearchCodeArgs(Args):
    """Arguments for finding where a code snippet appears in the project.

    Unknown keys are refused.
    """

    query: str
    """The snippet, matched exactly; shorter than 5 characters finds nothing."""


class SearchCodeMatch(Model):
    """One place in the project where the searched text occurs."""

    end_line: int
    """1-based line where the match ends (inclusive)."""
    line: int
    """1-based line where the match starts."""
    path: str
    """File path, relative to the project root."""
    preview: str
    """The first matching line, trimmed of surrounding whitespace."""


class SearchCodeResult(Model):
    """Where a piece of text (e.g. pasted code) occurs in the project.

    Text shorter than 5 characters is not searched and gives an empty
    result.
    """

    error: str = ""
    """Why the search failed, e.g. `search timed out`; empty on success."""
    matches: list[SearchCodeMatch] = Field(default_factory=list)
    """The matches found, up to the limit."""
    truncated: bool = False
    """`true` when the result limit was hit or the search timed out, so there may be more matches."""


class Selection(Model):
    """What is selected in a window. Each part is independent; `None` for nothing."""

    file: str | None = None
    """The file the selection is in; null when none is."""
    message_id: str | None = None
    """The message the selection starts in; null when nothing is selected."""
    text: str | None = None
    """The selected text; null when none is."""


class ServerChoice(Model):
    """The igni server now in use, or why the choice was refused."""

    api_url: str = ""
    """The server's API URL; empty when refused."""
    error: str = ""
    """Why the server was refused; empty on success."""
    portal_url: str = ""
    """Where a person signs in on that server; empty when refused."""


class ServerFound(Model):
    """Where an email address's organisation runs igni, or, with every
    URL empty, why nothing usable was found.
    """

    api_url: str = ""
    """The server's API URL; empty when none was found."""
    portal_url: str = ""
    """Where a person signs in; empty when it is derived from `api_url` or nothing was found."""
    reason: str = ""
    """Why nothing usable was found; empty when a server was found. A domain with no record is normal, not a fault."""
    source: str = ""
    """How the server was found: `well-known` (a document published on the domain) or `dns` (a DNS record); empty when nothing was found."""


class SessionCleared(Event):
    """The session's conversation was cleared or compacted (replaced by a summary) to free context.

    On the wire: ``session_cleared``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    new_session_id: str = ""
    """The session's id from now on; it may be the same as before."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    summary: str = ""
    """The summary that now stands in for the earlier conversation; empty when there is none."""
    type: Literal["session_cleared"] = "session_cleared"
    """Always `session_cleared`: what kind of message this is."""


class SessionIdArgs(Args):
    """Arguments naming a session."""

    session_id: str
    """Id of the session to act on."""


class SessionList(Frame):
    """Ask for the saved sessions. igni answers with a `session_list_result`.

    On the wire: ``session_list``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["session_list"] = "session_list"
    """Always `session_list`: what kind of message this is."""


class SessionListEntry(Model):
    """One saved session, as listed by `session_list`.

    More fields may be present than those listed here; ignore any you
    do not know.
    """

    agent_name: str = ""
    """The agent the session talks to."""
    created_at: int = 0
    """When the session was created, in Unix seconds."""
    name: str = ""
    """The session's name; empty when it has none."""
    run_count: int = 0
    """How many runs the session holds."""
    session_id: str = ""
    """The session's id."""
    summary: str = ""
    """A short summary of the conversation; empty when there is none."""
    updated_at: int = 0
    """When the session last changed, in Unix seconds."""


class SessionListResult(Event):
    """The answer to `session_list`: the saved sessions.

    On the wire: ``session_list_result``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    sessions: list[SessionListEntry] = Field(default_factory=list)
    """The saved sessions."""
    type: Literal["session_list_result"] = "session_list_result"
    """Always `session_list_result`: what kind of message this is."""


class SessionNamedPayload(Model):
    """Channel `session_named`. igni has given a new session a
    generated display name.
    """

    name: str
    """Its new display name."""
    session_id: str
    """The session that was named."""


class SessionSwitch(Frame):
    """Switch to a different saved session.

    On the wire: ``session_switch``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The id of the session to switch to."""
    type: Literal["session_switch"] = "session_switch"
    """Always `session_switch`: what kind of message this is."""


class SetExtensionSettingsArgs(Args):
    """New setting values for one extension."""

    extension_id: str
    """The id of the extension to configure."""
    values: dict[str, JsonValue]
    """Setting key to new value, merged over the stored values. A key the extension does not declare is refused."""


class SetServerArgs(Args):
    """The igni server to use from now on."""

    api_url: str
    """The server's API URL."""
    portal_url: str = ""
    """Where a person signs in; empty to derive it from `api_url`."""


class Shutdown(Frame):
    """Shut igni down cleanly.

    On the wire: ``shutdown``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["shutdown"] = "shutdown"
    """Always `shutdown`: what kind of message this is."""


class Sidebar(Model):
    """A window's sidebar: open or not, its width and its section."""

    open: bool = False
    """Whether the sidebar is open."""
    section: str | None = None
    """The section the sidebar shows; null for none."""
    width: int | None = None
    """The sidebar's width in pixels; null for igni's own sidebar."""


class SkillDefinition(Model):
    """One skill the agent can use."""

    description: str
    """What the skill does, in one line."""
    name: str
    """The skill's name, as typed after `/`."""
    prompt: str
    """The skill's instructions; may be empty for a skill that has only a manifest."""


class SkillInfo(Model):
    """One skill available in the session, as shown in the skills panel."""

    agent: str = ""
    """Agent the skill runs on when `context` is `fork`. Empty otherwise."""
    argument_hint: str = ""
    """Hint shown for the arguments the skill expects. Empty when it takes none."""
    body: str = ""
    """Full instruction text of the skill (its SKILL.md body)."""
    category: str = "development"
    """Category the skill is grouped under."""
    context: str = "inline"
    """How the skill runs: `inline` (on the default skills agent) or `fork` (on the agent named in `agent`)."""
    description: str = ""
    """What the skill does. Empty when not given."""
    name: str
    """Skill name, used to invoke it (e.g. `/deploy`)."""
    source_dir: str = ""
    """Directory the skill was loaded from. Empty when not loaded from disk."""
    user_invocable: bool = True
    """True when the user can invoke the skill directly."""
    version: str = "0.1.0"
    """Version declared by the skill."""


class SkillSlashCommand(Model):
    """A skill the user can run as a slash command."""

    argument_hint: str = ""
    """A hint for the arguments it takes; empty when it takes none."""
    description: str = ""
    """What the skill does, in one line."""
    name: str
    """The skill's name, without the leading `/`."""
    source: Literal["skill"] = "skill"
    """Always `skill`: a skill."""


class StatsTurn(Model):
    """Token usage and duration for one agent run, shown at the end of
    the run. Has no `created_at`.
    """

    duration: float = 0.0
    """How long the run took, in seconds."""
    input_tokens: int = 0
    """Input (prompt) tokens used by the run."""
    output_tokens: int = 0
    """Output tokens generated by the run."""
    reasoning_tokens: int = 0
    """Reasoning tokens generated by the run; `0` if the model reports none."""
    role: Literal["stats"] = "stats"
    """Turn kind; always `stats`."""
    run_id: str = ""
    """Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point."""


class StatusUpdate(Event):
    """The session's current state, for a status bar: token use, model, account and permission mode.

    On the wire: ``status_update``.
    """

    cloud_connected: bool = False
    """True when signed in to igni cloud."""
    cloud_email: str = ""
    """The signed-in account's email address; empty when not signed in."""
    cloud_name: str = ""
    """The signed-in account's display name. Empty until igni has fetched it; show `cloud_email` meanwhile."""
    cloud_org: str = ""
    """The igni cloud organisation signed in to; empty when not signed in."""
    context_tokens: int = 0
    """Tokens the conversation currently takes up in the model's context."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    input_tokens: int = 0
    """Tokens sent to the model so far in this session."""
    max_context: int = 0
    """The model's context window, in tokens; 0 when unknown."""
    model: str = ""
    """The id of the model in use."""
    model_configured: bool = True
    """False when no model is set up, so a run could not reach one."""
    output_tokens: int = 0
    """Tokens the model has produced so far in this session."""
    permission_mode: str = "default"
    """The active permission mode: `default`, `plan`, `acceptEdits`, `bypassPermissions` or `dontAsk`. Other values may appear; treat them as unknown."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    theme: dict[str, JsonValue] | None = None
    """Brand colour overrides from the signed-in account's group, keyed by theme token. Null for igni's own palette."""
    type: Literal["status_update"] = "status_update"
    """Always `status_update`: what kind of message this is."""


class StopProcessResult(Model):
    """Result of stopping a background process."""

    killed: bool
    """`true` when the process was stopped; `false` if it was unknown or had already exited."""
    message: str
    """Human-readable explanation of what happened."""
    pid: int
    """Operating-system process id that was asked for."""


class StreamEnd(Event):
    """Marks the end of a streamed answer, such as a run's events.

    On the wire: ``stream_end``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["stream_end"] = "stream_end"
    """Always `stream_end`: what kind of message this is."""


class StreamingDone(RunEvent):
    """The model's reply is complete, though the run is still wrapping up.

    igni may spend a few more seconds saving and summarising before
    `run_completed`. A client can let the person type and send their
    next message as soon as this arrives: igni starts the next run once
    the current one has fully finished.

    On the wire: ``streaming_done``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    parent_run_id: str = ""
    """The id of the run that started this one, for a sub-agent's run; empty for a top-level run."""
    run_id: str = ""
    """The id of the run this event belongs to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["streaming_done"] = "streaming_done"
    """Always `streaming_done`: what kind of message this is."""


class SwitchModelArgs(Args):
    """Arguments for switching the session's model."""

    model_name: str
    """A model name from the model registry (see `get_model_registry`)."""


class TaskCreated(Event):
    """A team run has created a task for one of its members.

    On the wire: ``task_created``.
    """

    assignee: str = ""
    """The name of the member doing it; empty when unassigned."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    status: str = "pending"
    """The task's status: `pending`, `running`, `completed`, `failed` or `cancelled`. Other values may appear; treat them as unknown."""
    task_id: str = ""
    """The task's id."""
    title: str = ""
    """What the task is, in a few words."""
    type: Literal["task_created"] = "task_created"
    """Always `task_created`: what kind of message this is."""


class TaskCreatedEvent(Model):
    """A task was added to a team's task list."""

    agent_path: str
    """Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level)."""
    assignee: str = ""
    """Name of the team member assigned the task. Empty when unassigned."""
    card_id: str | None = None
    """Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card."""
    title: str = ""
    """Task title. Empty when not given."""
    type: Literal["task_created"] = "task_created"
    """Always `task_created`: what kind of message this is."""


class TaskIteration(Event):
    """A team run has started another round of work on its tasks.

    On the wire: ``task_iteration``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    iteration: int = 0
    """The number of the round now under way."""
    max_iterations: int = 0
    """The most rounds the run will take."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["task_iteration"] = "task_iteration"
    """Always `task_iteration`: what kind of message this is."""


class TaskSnapshot(Model):
    """One task of a team run, as it stands now."""

    assignee: str = ""
    """The name of the member doing it; empty when unassigned."""
    status: str = ""
    """The task's status: `pending`, `running`, `completed`, `failed` or `cancelled`. Other values may appear; treat them as unknown."""
    task_id: str = ""
    """The task's id."""
    title: str = ""
    """What the task is, in a few words."""


class TaskStateUpdated(Event):
    """Every task of a team run, as they stand now.

    On the wire: ``task_state_updated``.
    """

    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    tasks: list[TaskSnapshot] = Field(default_factory=list)
    """All the run's tasks; replaces any earlier list."""
    type: Literal["task_state_updated"] = "task_state_updated"
    """Always `task_state_updated`: what kind of message this is."""


class TaskUpdated(Event):
    """A team run's task changed status or assignee.

    On the wire: ``task_updated``.
    """

    assignee: str = ""
    """The name of the member doing it; empty when unassigned."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    status: str = ""
    """The task's new status: `pending`, `running`, `completed`, `failed` or `cancelled`. Other values may appear; treat them as unknown."""
    task_id: str = ""
    """The task's id, as in `task_created`."""
    type: Literal["task_updated"] = "task_updated"
    """Always `task_updated`: what kind of message this is."""


class TaskUpdatedEvent(Model):
    """A task in a team's task list changed status."""

    agent_path: str
    """Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level)."""
    card_id: str | None = None
    """Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card."""
    status: str = ""
    """New task status, such as `running`, `completed` or `failed`. Empty when unknown."""
    type: Literal["task_updated"] = "task_updated"
    """Always `task_updated`: what kind of message this is."""


class ThinkingTurn(Model):
    """The model's reasoning ("thinking") for part of a run.

    Comes either from the model's separate reasoning output or from an
    inline `<think>` block in the reply.
    """

    content: str = ""
    """The reasoning text."""
    created_at: int = 0
    """When the message was created, in Unix epoch seconds; `0` if unknown."""
    role: Literal["thinking"] = "thinking"
    """Turn kind; always `thinking`."""
    run_id: str = ""
    """Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point."""


class Toast(Model):
    """A transient message on screen."""

    body: str | None = None
    """A second line; null when there is none."""
    id: str = ""
    """The toast's own id: two writers cannot collide."""
    kind: str
    """How it is styled: `info`, `success`, `warning` or `error`."""
    source: str | None = None
    """The extension that showed it; null for igni's own."""
    target: Page | None = None
    """Where clicking the toast goes; null when it goes nowhere."""
    text: str
    """The toast's first line."""
    type: Literal["toast"] = "toast"
    """Always `toast`: what this is."""


class ToastAdded(Model):
    """The answer to `toast`: the toast as shown, with its id, and the window's revision."""

    op: Literal["toast"] = "toast"
    """Always `toast`: the request this answers."""
    rev: int
    """The window's revision after showing it."""
    toast: Toast
    """The toast as shown, its `id` included."""


class TodoItem(Model):
    """One item in the agent's todo checklist."""

    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    active_form: str = Field(default="", alias="activeForm")
    """Present-tense form shown while the item is in progress, e.g. `Running tests`. Empty when the agent gave none."""
    content: str
    """What the item is, in imperative form, e.g. `Run tests`."""
    status: Literal["pending", "in_progress", "completed"]
    """Progress of the item: `pending` (not started), `in_progress` (being worked on now) or `completed`."""


class TodosUpdatedEventPayload(Model):
    """The agent's todo checklist changed; carries the whole new list."""

    todos: list[TodoItem]
    """The full checklist, in order. Replaces any list received before; empty when the agent cleared it."""


class ToolCallArgs(Args):
    """The arguments of a tool call, as a JSON object.

    Each tool defines its own keys; any key is accepted and kept. The
    common ones are named below; leave out the ones the tool does not
    use.
    """

    command: str = ""
    """Shell command, for shell tools."""
    file_path: str = ""
    """File path, for file read/write/edit tools."""
    query: str = ""
    """Search query, for search tools."""
    url: str = ""
    """URL, for web-fetch tools."""


class ToolCompleted(RunEvent):
    """A tool call has finished.

    On the wire: ``tool_completed``.
    """

    diff_rows: list[tuple[str, str]] | None = None
    """For a tool that changed a file: the diff to show, as `[text, style]` pairs, one per line. Null when the tool produced no diff."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    full_result: str = ""
    """The tool's full output."""
    has_markup: bool = False
    """True when `full_result` contains rich-text markup rather than plain text."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    is_error: bool = False
    """True when the tool failed: it raised, or returned text starting with `Error:`."""
    is_rejected: bool = False
    """True when the call never ran: the person rejected it when asked for approval, or nobody could be asked."""
    parent_run_id: str = ""
    """The id of the run that started this one, for a sub-agent's run; empty for a top-level run."""
    run_id: str = ""
    """The id of the run this event belongs to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    summary: str = ""
    """A short, one-line summary of the result."""
    type: Literal["tool_completed"] = "tool_completed"
    """Always `tool_completed`: what kind of message this is."""


class ToolCompletedEvent(Model):
    """A sub-agent's tool call finished — or failed, which is what
    `is_error` says.
    """

    agent_path: str
    """Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level)."""
    card_id: str | None = None
    """Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card."""
    is_error: bool = False
    """True when the tool call failed."""
    result: str = ""
    """Preview of the tool output, or the error message when `is_error` is true; may be truncated. Empty when none."""
    tool: str
    """Name of the tool that was called."""
    tool_call_id: str | None = None
    """Identifier of this tool call; matches the earlier `tool_started` event. Null when the model did not supply one."""
    type: Literal["tool_completed"] = "tool_completed"
    """Always `tool_completed`: what kind of message this is."""


class ToolError(RunEvent):
    """A tool call failed.

    On the wire: ``tool_error``.
    """

    error: str = ""
    """What went wrong, as a human-readable message."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    parent_run_id: str = ""
    """The id of the run that started this one, for a sub-agent's run; empty for a top-level run."""
    run_id: str = ""
    """The id of the run this event belongs to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["tool_error"] = "tool_error"
    """Always `tool_error`: what kind of message this is."""


class ToolStarted(RunEvent):
    """A tool call has begun.

    On the wire: ``tool_started``.
    """

    args_summary: str = ""
    """A short, human-readable summary of the call's arguments."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    friendly_name: str = ""
    """A human-readable name for the tool, for display; empty when there is none."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    parent_run_id: str = ""
    """The id of the run that started this one, for a sub-agent's run; empty for a top-level run."""
    run_id: str = ""
    """The id of the run this event belongs to."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    tool_name: str = ""
    """The tool's name, as the model called it."""
    type: Literal["tool_started"] = "tool_started"
    """Always `tool_started`: what kind of message this is."""


class ToolStartedEvent(Model):
    """A tool call started: a sub-agent began calling a tool."""

    agent_path: str
    """Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level)."""
    args: str = ""
    """Preview of the tool arguments as text (usually JSON, may be truncated). Empty when none."""
    card_id: str | None = None
    """Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card."""
    tool: str
    """Name of the tool being called."""
    tool_call_id: str | None = None
    """Identifier of this tool call; matches the `tool_completed` event for the same call. Null when the model did not supply one."""
    type: Literal["tool_started"] = "tool_started"
    """Always `tool_started`: what kind of message this is."""


class ToolTurn(Model):
    """One tool call the agent made, with its result.

    The history equivalent of the live `tool_started` and
    `tool_completed` events.
    """

    args: str = ""
    """The call's arguments, as display text."""
    content: str = ""
    """The tool's result text."""
    created_at: int = 0
    """When the message was created, in Unix epoch seconds; `0` if unknown."""
    friendly_name: str = ""
    """Human-readable tool name for display."""
    is_error: bool = False
    """`true` when the tool call failed."""
    is_rejected: bool = False
    """`true` when the user rejected the call, so it never ran."""
    role: Literal["tool"] = "tool"
    """Turn kind; always `tool`."""
    run_id: str = ""
    """Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point."""
    tool_name: str = ""
    """Internal name of the tool that was called."""


class TruncateHistoryArgs(Args):
    """Arguments for dropping a run, and every later run, from a
    session's history.
    """

    run_id: str
    """Id of the first run to drop: a top-level run, as `get_chat_history` carries it."""
    session_id: str
    """Id of the session to act on."""


class TruncateHistoryResult(Model):
    """The outcome of cutting a session's history back to before a given run."""

    error: str = ""
    """Why nothing was removed; empty on success."""
    removed: int
    """How many runs were removed, the given one included; `0` on failure."""


class TrustDecisionArgs(Args):
    """The user's answer to "Trust this folder?"."""

    decision: Literal["trust", "distrust", "once"]
    """`trust`: trust the folder and remember it. `once`: trust it until igni exits. `distrust`: do not trust it, and remember that."""


class Typing(Event):
    """What the person is typing in one client, shared with every other client of the session.

    Each message carries the whole draft, not a change to it. Send it at
    a modest rate while the person types.

    On the wire: ``typing``.
    """

    client_id: str = ""
    """The id of the client the person is typing in."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    text: str = ""
    """The whole draft so far; empty when it was sent or cleared."""
    type: Literal["typing"] = "typing"
    """Always `typing`: what kind of message this is."""


class UpdateAvailable(Model):
    """A newer igni release that can be installed. When no update is
    available the call returns `null` instead.
    """

    available: bool
    """Always `true`: an update is available."""
    current_version: str
    """The version running now."""
    download_url: str
    """Where the new version can be downloaded."""
    latest_version: str
    """The newest released version."""
    pkg_name: str
    """The name of the package to upgrade."""


class UpdatePluginArgs(Args):
    """Arguments for moving an installed plugin to another commit."""

    install_ref: str | None = None
    """Branch, tag or commit to move to; the remote's default branch when absent."""
    name: str
    """Name of the installed plugin."""


class UploadAttachmentArgs(Args):
    """Arguments for uploading a file to attach to a message."""

    content_base64: str
    """The file's bytes, base64-encoded."""
    filename: str
    """The file's name. It is made safe for the disk; a name clash gets a `-N` suffix."""


class UploadAttachmentResult(Model):
    """Where an uploaded attachment was saved."""

    error: str = ""
    """Why the upload failed, e.g. invalid base64; empty on success."""
    path: str
    """The stored file's path, or an `attachment:<id>` reference when attachments are kept in shared storage; use it to refer to the file in a message. Empty on error."""
    size: int
    """Size of the stored file in bytes; `0` on error."""


class UserMessage(Frame):
    """The person sends a chat message, starting a run.

    On the wire: ``user_message``.
    """

    client_id: str = ""
    """This client's id, from `welcome`. igni echoes the message to every other client attached to the session (`user_message_received`); the sender recognises its own by this id. Empty is allowed."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    file_contents: dict[str, str] = Field(default_factory=dict)
    """Files attached to the message: their contents, keyed by path."""
    force: bool = False
    """True to discard any interrupted or pending runs of the session first, then start afresh with this message; for retrying after an interruption."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    text: str = ""
    """The message."""
    type: Literal["user_message"] = "user_message"
    """Always `user_message`: what kind of message this is."""


class UserMessageReceived(Event):
    """A chat message igni accepted, sent to every client of the session so all show it.

    The client that sent it can recognise it by `client_id` and skip it.

    On the wire: ``user_message_received``.
    """

    client_id: str = ""
    """The id of the client that sent it; empty when no client did."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    extension_id: str = ""
    """Set when an extension posted the message (`host.chat.post`): show it as that extension's, not the person's. Empty otherwise."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    queued: bool = False
    """True when it was sent during a run and is queued for the agent."""
    service_client_id: str = ""
    """Set when the extension's service sent the message: that service's client id. `extension_id` is set too. Empty otherwise."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    text: str = ""
    """The message."""
    type: Literal["user_message_received"] = "user_message_received"
    """Always `user_message_received`: what kind of message this is."""


class UserTurn(Model):
    """A message the user sent."""

    content: str = ""
    """The text the user sent."""
    created_at: int = 0
    """When the message was created, in Unix epoch seconds; `0` if unknown."""
    role: Literal["user"] = "user"
    """Turn kind; always `user`."""
    run_id: str = ""
    """Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point."""


class VisualizationActionArgs(Args):
    """Arguments for reporting that the user used a control in a
    visualization the agent drew.
    """

    action: str = ""
    """The control's action name."""
    params: dict[str, JsonValue] | None = None
    """Values the visualization attached to the action; omit for none."""


class VisualizationActionDispatchedEventPayload(Model):
    """The `visualization_action_dispatched` broadcast, so log panels
    and dev tools can observe component interactions.
    """

    action: str
    """Name of the action the user triggered in the visualization."""
    params: dict[str, JsonValue]
    """Parameters the visualization attached to the action."""


class VisualizationActionResult(Model):
    """Confirmation that a visualization action was dispatched.

    Echoes the action and its parameters, e.g. to show "you clicked X"
    in the conversation.
    """

    action: str
    """Name of the action."""
    ok: bool
    """`true` when the action was dispatched."""
    params: dict[str, JsonValue] = Field(default_factory=dict)
    """Parameters attached to the action."""


class VisualizationDeltaPayload(Model):
    """A visualization card recorded in the session's event log.

    The card's spec arrives as JSON text, possibly in several partial
    updates sharing one `spec_id`; the update with `final` set holds
    the complete spec. `title` and `source` are set only for cards
    an extension added to the chat.
    """

    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    agent_path: str = ""
    """Dot-joined names of the agent that produced the card. Empty when not known."""
    card_id: str | None = None
    """The card this delta belongs to; it is not part of the event's wire shape."""
    final: bool = True
    """True when `json` holds the complete spec; false for an in-progress update."""
    json_: str = Field(default="", alias="json")
    """The card's visualization spec as JSON text. Partial (possibly incomplete JSON) until `final` is true."""
    source: str = ""
    """Id of the extension that added the card. Empty for cards produced by an agent."""
    spec_id: str = ""
    """Identifier of the card; later updates with the same id replace earlier ones."""
    title: str = ""
    """Card title given by the extension that added it. Empty otherwise."""
    type: Literal["visualization_delta"] = "visualization_delta"
    """Always `visualization_delta`: what kind of message this is."""


class VisualizationTurn(Model):
    """A visualization card (chart, diagram, extension view) shown in
    the chat during a run.

    Has no `created_at`; use the neighbouring turns for display
    time.
    """

    extension_id: str = ""
    """Id of the extension that appended the card; empty when the built-in visualizer made it. Show the extension's name."""
    role: Literal["visualization"] = "visualization"
    """Turn kind; always `visualization`."""
    run_id: str = ""
    """Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point."""
    seq: int = 0
    """Position of the card in the session's event log, for ordering within a run."""
    source_agent: str = "visualizer"
    """Name of the agent that produced the visualization."""
    spec: dict[str, JsonValue] = Field(default_factory=dict)
    """The visualization specification to render, as JSON. Not validated by igni."""
    spec_id: str = ""
    """Unique id of this visualization."""
    title: str = ""
    """The card's title, as given by the extension that appended it."""


class VmCredentialState(Model):
    """The state of a cloud VM's own credential after it signed in."""

    message: str = ""
    """What went wrong; empty when nothing did."""
    state: Literal["ready", "needs_sign_in", "needs_reissue", "unreachable"]
    """`ready`: the VM holds a credential and a token from it. `needs_sign_in`: the person must sign in through the gateway again. `needs_reissue`: an app VM's credential is gone and an organisation admin must re-issue it. `unreachable`: igni server could not be reached; the last token holds until it expires."""


class Welcome(Event):
    """The first message igni sends a newly attached client.

    On the wire: ``welcome``.
    """

    client_id: str = ""
    """The id igni gave this client. Send it with your messages; messages igni echoes to every client carry it, so you can skip your own."""
    event_seq: int = 0
    """The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni."""
    id: str = ""
    """Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied."""
    session_id: str = ""
    """The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular."""
    type: Literal["welcome"] = "welcome"
    """Always `welcome`: what kind of message this is."""


class WindowChange(Model):
    """One change to one window's model, as listeners are told it."""

    answer: JsonValue | None = None
    """The answer given to the dialog, as JSON; null when it was dismissed."""
    event: str = ""
    """What happened, for the fields that hold a list or a dialog: `toast_shown`, `toast_dismissed`, `dialog_opened` or `dialog_closed`; empty otherwise."""
    field: str
    """Which of the window's fields changed."""
    item: WindowItem | None = None
    """The toast or the dialog the event is about."""
    rev: int
    """The window's revision after the change."""
    token: str = ""
    """The writer's own name for the write, echoed so the window that wrote it knows its own write; empty for an extension's."""
    value: JsonValue | None = None
    """The field's new value, as JSON."""
    window: str
    """The window whose model changed."""


class WindowModelArgs(Args):
    """Arguments for a window reading or writing its own state (its
    window model).
    """

    connection_id: str = ""
    """The window's connection id, for transports without connections (a terminal socket, an in-process client). Ignored over a WebSocket: the request's own connection is used."""
    dialog_id: str = ""
    """The dialog an `answer_dialog` closes."""
    field: str = ""
    """The model field a `write` sets."""
    kind: str = ""
    """What kind of window this is, recorded when it opens."""
    op: Literal["hydrate", "write", "toast", "dismiss_toast", "open_dialog", "answer_dialog"]
    """What to do. `hydrate`: read the whole model, and report the window as open. `write`: set `field` to `value`. `toast`: show the toast `value`. `dismiss_toast`: remove the toast whose id is `value`. `open_dialog`: show igni's own dialog, `value` being its spec. `answer_dialog`: close dialog `dialog_id` with the answer `value` (`null`: dismissed)."""
    token: str = ""
    """The writer's own name for this change, echoed on `window_model_changed`."""
    value: JsonValue = None
    """What the op writes, shows or answers with; its shape depends on the op and field."""
    window: str = Field(min_length=1)
    """The window's id, chosen by the window and stable across its reloads."""


class WindowModelState(Model):
    """A window's whole model: every field, as a window hydrates from it."""

    composer: Composer = Field(
        default_factory=lambda: Composer.model_validate(
            {"attachments": [], "mode": "chat", "text": ""}
        )
    )
    """The window's composer."""
    dialog: Dialog | None = None
    """The dialog on screen."""
    focused: bool = False
    """Whether this window has the focus."""
    panel: Panel | None = None
    """The panel open over the chat."""
    preview: Preview | None = None
    """The file being previewed."""
    project_dir: str = ""
    """The folder the window shows."""
    route: list[Page] = Field(default_factory=list)
    """The window's page stack."""
    scroll: Scroll = Field(
        default_factory=lambda: Scroll.model_validate({"at_bottom": True, "message_id": None})
    )
    """Where the transcript is scrolled."""
    selection: Selection = Field(
        default_factory=lambda: Selection.model_validate(
            {"file": None, "message_id": None, "text": None}
        )
    )
    """What is selected."""
    session: str = ""
    """The session the window shows."""
    sidebar: Sidebar = Field(
        default_factory=lambda: Sidebar.model_validate(
            {"open": False, "section": None, "width": None}
        )
    )
    """The window's sidebar."""
    toasts: list[Toast] = Field(default_factory=list)
    """The toasts on screen."""


class WorkflowCancelRequest(Args):
    """Arguments for cancelling a running workflow."""

    workflow_run_id: str = Field(min_length=1)
    """Id of the workflow run to cancel."""


class WorkflowCancelResponse(Model):
    """Result of cancelling a workflow run."""

    cancelled: bool
    """`true` when the run was stopped. `false` when no such run is active: it already finished, was already cancelled, or the id is unknown."""
    workflow_run_id: str
    """Id of the run the request named."""


class WorkflowEventRecord(Model):
    """One progress event from a running workflow, as pushed on the
    `workflow_event` channel and kept in the session log.
    """

    name: str
    """Name of the workflow."""
    payload: dict[str, JsonValue]
    """Event details; keys depend on `type`. For the final event added by igni: `status` (`completed`, `failed` or `cancelled`), `exit_code` and `synthetic`."""
    seq: int
    """Order of the event within its run, from `0`. `-1` for the final event igni adds itself when the workflow process exits without reporting an end."""
    ts: int
    """When the event happened, in Unix epoch milliseconds."""
    type: str
    """Event kind, e.g. `workflow_meta`, `phase_*`, `agent_*`, `parallel_*`, `pipeline_*`, `log`, and the final `workflow_completed` or `workflow_failed`."""
    workflow_run_id: str
    """Id of the workflow run the event belongs to."""


class WorkflowListItem(Model):
    """A workflow script available to run in this project."""

    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    description: str = ""
    """What the workflow does; may be empty."""
    name: str
    """The workflow's name; pass it to run the workflow."""
    path: str
    """Where the workflow file is: relative to the project root, or absolute for a workflow outside the project (e.g. in the user's home)."""
    phases: list[WorkflowPhase]
    """The workflow's steps, in order."""
    when_to_use: str = Field(default="", alias="whenToUse")
    """When the workflow is the right choice; may be empty."""


class WorkflowListRequest(Args):
    """`LIST_WORKFLOWS` params: none. Whatever the caller sends
    (`session_id` and the like) is ignored.
    """


class WorkflowPhase(Model):
    """One step of a workflow, as the workflow describes itself."""

    detail: str = ""
    """Longer explanation of what the phase does; may be empty."""
    title: str
    """Short name of the phase."""


class WorkflowRunRequest(Args):
    """Arguments for starting a workflow."""

    args: dict[str, JsonValue] = Field(default_factory=dict)
    """The workflow's own input, passed to it unchanged. Each workflow defines the keys it reads; omit for none."""
    name: str = Field(min_length=1)
    """Name of the workflow to run."""


class WorkflowRunResponse(Model):
    """The workflow run that was started.

    Returned as soon as the run starts; its progress then arrives as
    `workflow_event` pushes carrying the same `workflow_run_id`.
    """

    name: str
    """Name of the workflow that was started."""
    workflow_run_id: str
    """Id of the new run; use it to match events and to cancel the run."""


class WorkspaceTrustStatus(Model):
    """Whether the project folder is trusted, and why.

    Until a folder is trusted, its own tools, hooks, plugins and
    configuration are not loaded.
    """

    can_trust: bool
    """`false` when the organisation's policy forbids trusting this folder."""
    gated: str = "project tools, hooks, workflows, language servers, monitors, plugins, markdown-command shell tokens, and its permission and safety settings"
    """Short summary of what an untrusted folder does not get, for showing to the user."""
    path: str
    """The folder's full canonical path."""
    policy_mode: str
    """The organisation's trust policy: `ask` (the user decides), `trusted_remotes` (only folders whose git remote is approved) or `never` (no folder is trusted)."""
    reason: str
    """Human-readable explanation of the current state."""
    remote: str | None = None
    """The folder's git remote URL, with any credentials removed; `null` if none."""
    source: str = ""
    """How the state was reached: `policy` (organisation policy), `run` (trusted once, until igni exits), `store` (the user's saved answer) or `unset` (no answer yet)."""
    state: Literal["trusted", "untrusted", "ask"]
    """`trusted`, `untrusted`, or `ask` when nobody has decided yet (the folder is treated as untrusted meanwhile)."""


class Written(Model):
    """The answer to `write`: the window's revision after it, and whether the value changed."""

    changed: bool = True
    """False when the field already held the value: nothing changed and no change was sent."""
    op: Literal["write"] = "write"
    """Always `write`: the request this answers."""
    rev: int
    """The window's revision after the write."""


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
    payload: HttpRetryAttemptEventPayload  # type: ignore[assignment]


class HttpRetrySucceededPush(PushNotification):
    """A web fetch succeeded after retrying.

    On the wire: ``push_notification`` on the channel ``http_retry_succeeded``.
    """

    channel: Literal["http_retry_succeeded"] = "http_retry_succeeded"
    payload: HttpRetrySucceededEventPayload  # type: ignore[assignment]


class LoginResultPush(PushNotification):
    """How a sign-in started by `login` ended.

    On the wire: ``push_notification`` on the channel ``login_result``.
    """

    channel: Literal["login_result"] = "login_result"
    payload: LoginResultPayload  # type: ignore[assignment]


class LoginStatusPush(PushNotification):
    """What a sign-in started by `login` is doing now.

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
    """A sub-agent's progress (a tool call, its start, pause, end or error, a task) or a view the agent or an extension drew, told apart by `type`.

    On the wire: ``push_notification`` on the channel ``orchestrate_event``.
    """

    channel: Literal["orchestrate_event"] = "orchestrate_event"
    payload: OrchestrateEventPayload  # type: ignore[assignment]


class OutputStyleChangedPush(PushNotification):
    """The session's output style changed.

    On the wire: ``push_notification`` on the channel ``output_style_changed``.
    """

    channel: Literal["output_style_changed"] = "output_style_changed"
    payload: OutputStyleChangedEventPayload  # type: ignore[assignment]


class PermissionModeChangedPush(PushNotification):
    """The session's permission mode changed: the switch itself (`mode` and `previous`), or the plan tool's note that the agent entered plan mode (`mode`, `source`, `reason`).

    On the wire: ``push_notification`` on the channel ``permission_mode_changed``.
    """

    channel: Literal["permission_mode_changed"] = "permission_mode_changed"
    payload: PermissionModeChangedPayload  # type: ignore[assignment]


class PlanDecidedPush(PushNotification):
    """A submitted plan was approved or dismissed.

    On the wire: ``push_notification`` on the channel ``plan_decided``.
    """

    channel: Literal["plan_decided"] = "plan_decided"
    payload: PlanDecidedEventPayload  # type: ignore[assignment]


class PlanSubmittedPush(PushNotification):
    """The agent submitted a plan for the person to decide on.

    On the wire: ``push_notification`` on the channel ``plan_submitted``.
    """

    channel: Literal["plan_submitted"] = "plan_submitted"
    payload: PlanSubmittedEventPayload  # type: ignore[assignment]


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
    payload: TodosUpdatedEventPayload  # type: ignore[assignment]


class VisualizationActionDispatchedPush(PushNotification):
    """The person used a control in a view.

    On the wire: ``push_notification`` on the channel ``visualization_action_dispatched``.
    """

    channel: Literal["visualization_action_dispatched"] = "visualization_action_dispatched"
    payload: VisualizationActionDispatchedEventPayload  # type: ignore[assignment]


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
    """A folder's trust status: windows showing the trust dialog for it close it, or open it while `state` is `ask`.

    On the wire: ``push_notification`` on the channel ``workspace_trust_required``.
    """

    channel: Literal["workspace_trust_required"] = "workspace_trust_required"
    payload: WorkspaceTrustStatus  # type: ignore[assignment]


#: One of 7 kinds, told apart by ``role``.
type ChatTurn = Annotated[
    UserTurn | AssistantTurn | ThinkingTurn | ToolTurn | PlanTurn | StatsTurn | VisualizationTurn,
    Field(discriminator="role"),
]


#: One of 4 kinds, told apart by ``source``.
type SlashCommand = Annotated[
    BuiltinSlashCommand | MarkdownSlashCommand | SkillSlashCommand | ExtensionSlashCommand,
    Field(discriminator="source"),
]


#: One of 2 kinds, told apart by ``type``.
type WindowItem = Annotated[Toast | Dialog, Field(discriminator="type")]


#: One of 6 kinds, told apart by ``op``.
type WindowModelResult = Annotated[
    Hydrated | Written | ToastAdded | Revised | DialogShown | DialogAnswered,
    Field(discriminator="op"),
]


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

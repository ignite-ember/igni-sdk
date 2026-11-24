// GENERATED from igni-core's RPC contract (version 1) by igni-sdk's tools/client_ts.py — do not edit. Run `make client-api` after refreshing contracts/rpc-contract.json.
//
// Every type igni-client sends or reads, as igni-core's RPC contract
// defines it. Messages a client reads keep a field a newer igni adds.

/** Any JSON value. */
export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };


/** What igni, or one of its chats, is doing: running, waiting on a person, or nothing. */
export type ActivityState = "idle" | "waiting" | "running";

/**
 * What a command result asks the client to do.
 *
 * * empty: nothing; just show `content`.
 * * `quit`: close the client.
 * * `clear`: clear the conversation view.
 * * `fork`: the session was duplicated; `content` is the new session's id.
 * * `sessions`: show the saved sessions.
 * * `model`: show the model picker.
 * * `model_switched`: the model changed; refresh what shows it.
 * * `login` / `logout`: start signing in / out of igni cloud.
 * * `help`: show help.
 * * `mcp`, `plugins`, `extensions`, `agents`, `skills`,
 *   `hooks`, `loop`, `schedule`: open the page that manages them.
 * * `watcher`: open the background-process panel.
 * * `compact`: compact the conversation.
 * * `ctx`: open the context-breakdown page.
 * * `programs`: open the approver-token page.
 * * `run_prompt`: send `content` to the agent as a prompt.
 */
export type CommandAction = "" | "quit" | "clear" | "fork" | "sessions" | "model" | "model_switched" | "login" | "logout" | "help" | "mcp" | "plugins" | "extensions" | "agents" | "skills" | "hooks" | "loop" | "schedule" | "watcher" | "compact" | "ctx" | "programs" | "run_prompt";

/**
 * How a client should show a command result's `content`.
 *
 * * `markdown`: render as Markdown (long-form text such as help).
 * * `info`: a single, quiet line (status, confirmations).
 * * `error`: a single line shown as an error.
 * * `action`: nothing to show; act on the result's `action`
 *   instead (open a panel, a picker, ...).
 */
export type CommandResultKind = "markdown" | "info" | "error" | "action";

/**
 * Where a notification came from.
 *
 * * `server`: delivered by igni server, which keeps whether it was read.
 * * `local`: posted by an extension on this machine; this igni keeps
 *   whether it was read.
 */
export type NotificationOrigin = "server" | "local";

/**
 * Top-level permission posture for a session.
 *
 * Defaults to `DEFAULT`. `DONT_ASK` is the headless/CI mode
 * (never prompt, deny unmatched). `ACCEPT_EDITS` auto-approves
 * file mutation tools. `BYPASS_PERMISSIONS` runs without
 * prompts unless an explicit deny / ask rule matches.
 * `PLAN` forbids source edits entirely.
 */
export type PermissionMode = "default" | "dontAsk" | "acceptEdits" | "bypassPermissions" | "plan";

/**
 * User-recorded decision for a plan submitted via
 * `exit_plan_mode`. Concrete values match the historic
 * wire strings so serialised blobs round-trip cleanly.
 */
export type PlanDecision = "approved" | "dismissed";

/**
 * Why a call failed, as a word a client can branch on; `error` beside
 * it is the sentence for a person.
 */
export type RpcErrorCode = "unknown_method" | "invalid" | "forbidden" | "not_found" | "refused" | "unavailable" | "cancelled" | "failed";

/**
 * Lifecycle of one scheduled task.
 *
 * `pending` (waiting for its time), `running` (executing now),
 * `completed` (finished successfully), `failed` (finished with an
 * error) or `cancelled` (cancelled before it ran).
 */
export type TaskStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

/** A sub-agent finished its run, with its token usage. */
export interface AgentCompletedEvent {
  /** Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level). */
  agent_path: string;
  /** Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card. */
  card_id?: string | null;
  /** Input (prompt) tokens the sub-agent used. */
  input_tokens?: number;
  /** True when the sub-agent ended with an error. */
  is_error?: boolean;
  /** Output (completion) tokens the sub-agent produced. */
  output_tokens?: number;
  /** Reasoning tokens the sub-agent used; 0 when the model reports none. */
  reasoning_tokens?: number;
  /** Always `agent_completed`: what kind of message this is. */
  type?: "agent_completed";
}

/** One agent available in the session, as shown in the agents panel. */
export interface AgentInfo {
  /** True when the agent may spawn sub-agents of its own. */
  can_orchestrate?: boolean;
  /** Display color declared for the agent. Empty when none. */
  color?: string;
  /** What the agent is for. Empty when not given. */
  description?: string;
  /** True for an agent created during this session that has not been saved to disk; it disappears when the session ends unless promoted. */
  is_ephemeral?: boolean;
  /** Names of the MCP servers whose tools the agent gets. */
  mcp_servers?: string[];
  /** Model the agent runs on. Empty to use the session's default model. */
  model?: string;
  /** Agent name; plugin agents are prefixed with the plugin name (`plugin:agent`). */
  name: string;
  /** Path of the file the agent was loaded from. Empty for agents not loaded from a file. */
  source_path?: string;
  /** The agent's system prompt (the body of its definition file). */
  system_prompt?: string;
  /** Free-form tags declared for the agent. */
  tags?: string[];
  /** Names of the tools the agent may use. Empty when not restricted. */
  tools?: string[];
  /** Tool names the agent declares that igni cannot find. Usually empty; when not, the agent fails when it is called. */
  unknown_tools?: string[];
}

/** Arguments naming an agent created during the session. */
export interface AgentNameArgs {
  /** Name of the agent created during the session. */
  name: string;
}

/**
 * A sub-agent paused because it needs user input (e.g. a tool
 * approval): the run waits for someone to answer its approvals.
 */
export interface AgentPausedEvent {
  /** Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level). */
  agent_path: string;
  /** Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card. */
  card_id?: string | null;
  /** Number of pending requests the agent is waiting on. */
  count?: number;
  /** Always `agent_paused`: what kind of message this is. */
  type?: "agent_paused";
}

/** Arguments naming a sub-agent run to stop. */
export interface AgentRunArgs {
  /** Id of the sub-agent run, as its events carry it; must not be empty. */
  run_id?: string;
}

/** A member of the run started: a sub-agent began running a task. */
export interface AgentStartedEvent {
  /** Name of the sub-agent that started. */
  agent: string;
  /** Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level). */
  agent_path: string;
  /** Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card. */
  card_id?: string | null;
  /** Path of the agent that spawned it. Null for a top-level spawn. */
  parent?: string | null;
  /** Identifier of the sub-agent's run, when known. */
  run_id?: string | null;
  /** Task text given to the sub-agent, when known. */
  task?: string | null;
  /** Always `agent_started`: what kind of message this is. */
  type?: "agent_started";
}

/** A new token that lets a program answer the agent's approval requests. */
export interface ApproverTokenMinted {
  /** The token. A program that connects with it may answer approval requests and approve plans. It is valid until igni exits or the tokens are revoked. */
  token: string;
}

/** How many approver tokens were revoked. */
export interface ApproverTokensRevoked {
  /** The number of tokens revoked. */
  revoked: number;
}

/**
 * A visible reply from the assistant.
 *
 * One run can produce several of these when the reply was
 * interleaved with thinking blocks.
 */
export interface AssistantTurn {
  /** The reply text (Markdown). */
  content?: string;
  /** When the message was created, in Unix epoch seconds; `0` if unknown. */
  created_at?: number;
  /** Turn kind; always `assistant`. */
  role?: "assistant";
  /** Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point. */
  run_id?: string;
}

/** Which session to attach a connection to, and in which folder. */
export interface AttachSessionParams {
  /** The folder the session works in; empty for igni's own. */
  project_dir?: string;
  /** The session to attach to; empty for the default one, or a new one when `project_dir` is given. */
  session_id?: string;
}

/** The session a connection is now attached to. */
export interface AttachSessionResult {
  /** The session's project folder, as an absolute path. */
  project_dir: string;
  /** The id of the session that was attached. */
  session_id: string;
}

/**
 * Channel `background_process_done`. A shell command running in
 * the background has finished. Sent alongside `process_exited`, for
 * a client that only wants to show a notice. The agent is told about
 * the output separately.
 */
export interface BackgroundProcessDonePayload {
  /** The command that ran. */
  cmd: string;
  /** How long it ran, in seconds. */
  duration_seconds: number;
  /** Its exit code; `null` when unknown. */
  exit_code: number | null;
  /** The process's id; `null` when unknown. */
  pid: number | null;
}

/** A slash command built into igni. */
export interface BuiltinSlashCommand {
  /** A hint for the arguments it takes; empty when it takes none. */
  argument_hint?: string;
  /** What the command does, in one line. */
  description?: string;
  /** The command's name, without the leading `/`. */
  name: string;
  /** Always `builtin`: a command built into igni. */
  source?: "builtin";
}

/**
 * Stop the run in progress.
 *
 * On the wire: `cancel`.
 */
export interface Cancel {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `cancel`: what kind of message this is. */
  type?: "cancel";
}

/** Result of cancelling one background agent run. */
export interface CancelAgentRunResult {
  /** Why the cancel failed, e.g. the run id is unknown; empty when `ok` is `true`. */
  error?: string;
  /** `true` when the agent run was found and cancelled. */
  ok: boolean;
}

/**
 * Cancel an in-progress login flow.
 *
 * On the wire: `cancel_login`.
 */
export interface CancelLogin {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `cancel_login`: what kind of message this is. */
  type?: "cancel_login";
}

/** Result of cancelling the current turn: whether one was running or paused. */
export interface CancelRunResult {
  /** `true` when a turn was running or paused on an approval and is being stopped: the session then streams an `info` and a `stream_end`. `false` when nothing was running or paused, and nothing is streamed. */
  cancelled: boolean;
}

/** One match from searching a session's chat history. */
export interface ChatSearchHit {
  /** When the turn was created, in Unix epoch seconds; `0` if unknown. */
  created_at?: number;
  /** Index of the matching turn in the list returned by `get_chat_history`; use it to jump to that turn. */
  history_index?: number;
  /** End offset (exclusive) of the match within `snippet`. */
  match_end?: number;
  /** Start offset of the match within `snippet` (not the full text). */
  match_start?: number;
  /** Kind of the matching turn, e.g. `user`, `assistant` or `tool`. */
  role?: string;
  /** Id of the agent run the matching turn belongs to. */
  run_id?: string;
  /** Excerpt of the turn's text around the match. */
  snippet?: string;
}

/** Arguments for looking up the permission level of one tool call. */
export interface CheckPermissionArgs {
  /** Name of the tool's function being called. */
  func_name: string;
  /** The call's arguments, which argument-specific rules are matched against. */
  tool_args: ToolCallArgs;
  /** Name of the tool. */
  tool_name: string;
}

/**
 * The signed-in account's plan and organisation on igni server.
 * Any field may be `null` when the server did not report it.
 */
export interface CloudPlan {
  /** The signed-in user's email address. */
  email?: string | null;
  /** The signed-in user's full name. */
  full_name?: string | null;
  /** The organisation's display name; `null` when not reported. */
  org_name: string | null;
  /** The plan tier; `null` when not reported. */
  tier: string | null;
}

/**
 * A slash command the person typed. igni answers with a `command_result`.
 *
 * On the wire: `command`.
 */
export interface Command {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The command as typed, slash included, e.g. `/help`. */
  text?: string;
  /** Always `command`: what kind of message this is. */
  type?: "command";
}

/**
 * The result of a slash command: text to show, an action for the client to take, or both.
 *
 * On the wire: `command_result`.
 */
export interface CommandResult {
  /** What the client should do in response; empty for nothing but showing `content`. */
  action?: CommandAction;
  /** The text to show. For some actions it carries the action's value instead: the new session id for `fork`, the prompt to send for `run_prompt`. */
  content?: string;
  /** For `run_prompt`: the text to show in the chat in place of `content`, when the prompt sent to the agent differs from what the person should see. Empty to show `content`. */
  display_content?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** How to show `content`. */
  kind?: CommandResultKind;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `command_result`: what kind of message this is. */
  type?: "command_result";
}

/**
 * Arguments for compacting the conversation when its context is
 * nearly full.
 */
export interface CompactIfNeededArgs {
  /** Tokens of context the last turn used. */
  ctx_tokens: number;
  /** The model's context window, in tokens. Compaction happens at 80% or more. */
  max_ctx: number;
}

/**
 * Whether the conversation was compacted, and if so the summary it
 * was replaced by.
 */
export interface CompactionOutcome {
  /** `false` when the context was below the threshold, a `PreCompact` hook refused, or there was nothing to compact. */
  compacted: boolean;
  /** The session the conversation continues in (currently the same id); empty when not compacted. */
  new_session_id?: string;
  /** What the compacted conversation was replaced by; empty when not compacted. */
  summary?: string;
}

/** Arguments for completing a file path typed after `@`. */
export interface CompleteFilesArgs {
  /** Maximum number of matches to return. */
  limit?: number;
  /** What was typed so far; empty matches every file. */
  query?: string;
}

/** A window's composer: its draft, the files it names and its mode. */
export interface Composer {
  /** The files the draft names, in order. */
  attachments?: string[];
  /** What the composer is in: `chat`, `command` (a slash command) or `shell`. */
  mode?: string;
  /** The draft's text, as the person wrote it. */
  text?: string;
}

/**
 * A chunk of the model's reply, streamed as it is written.
 *
 * Append each chunk's `text` to what came before to build the reply.
 *
 * On the wire: `content_delta`.
 */
export interface ContentDelta {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** True when the text is the model's reasoning rather than its visible reply. */
  is_thinking?: boolean;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The next piece of text, to append to the earlier ones. */
  text?: string;
  /** Always `content_delta`: what kind of message this is. */
  type?: "content_delta";
}

/** A short preview of what the agent is writing, mid-stream. */
export interface ContentPreviewEvent {
  /** Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level). */
  agent_path: string;
  /** Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card. */
  card_id?: string | null;
  /** Preview text of the sub-agent's latest output. */
  text: string;
  /** Always `content_preview`: what kind of message this is. */
  type?: "content_preview";
}

/**
 * Token breakdown of the current context window.
 *
 * `total = runs + floor`. `floor` is the part that compacting the
 * conversation (`/compact`) cannot shrink, such as the system prompt
 * and tool definitions.
 */
export interface ContextBreakdown {
  /** Tokens that are always present regardless of history (system prompt, tool definitions and so on); never negative. */
  floor: number;
  /** Tokens taken by the conversation history (previous runs). */
  runs: number;
  /** Total tokens currently in the context. */
  total: number;
}

/** A dialog on screen: igni's own or an extension's. One at a time. */
export interface Dialog {
  /** The dialog's own id: two writers cannot collide. */
  id: string;
  /** The extension that asked for it; null for igni's own. */
  source?: string | null;
  /** What the dialog shows: igni's own spec, or an extension's. */
  spec?: JsonValue | null;
  /** Always `dialog`: what this is. */
  type?: "dialog";
}

/** The answer to `answer_dialog`: whether the dialog was still the open one, and the window's revision. */
export interface DialogAnswered {
  /** False when that dialog was no longer the open one, so the answer was not taken. */
  answered: boolean;
  /** Always `answer_dialog`: the request this answers. */
  op?: "answer_dialog";
  /** The window's revision after the answer. */
  rev: number;
}

/** The answer to `open_dialog`: the dialog as shown, with its id, and the window's revision. */
export interface DialogShown {
  /** The dialog as shown, its `id` included. */
  dialog: Dialog;
  /** Always `open_dialog`: the request this answers. */
  op?: "open_dialog";
  /** The window's revision after opening it. */
  rev: number;
}

/** The sub-folders of one folder, for browsing to a project folder. */
export interface DirListResult {
  /** Names of the sub-folders in `path`, sorted case-insensitively. Hidden folders are left out unless they were asked for. Empty when the folder could not be read. */
  dirs: string[];
  /** Why the folder could not be read; empty on success. */
  error: string;
  /** The user's home folder, as an absolute path. */
  home: string;
  /** The folder above `path`; empty when `path` is the filesystem root. */
  parent: string;
  /** The folder that was listed, as an absolute path. */
  path: string;
}

/** The outcome of discarding an agent created during a session. */
export interface DiscardEphemeralResult {
  /** The agent's name. */
  name: string;
  /** Whether the agent was discarded. */
  ok: boolean;
  /** Why it was not discarded; empty when `ok` is true. */
  reason?: string;
}

/** The outcome of discarding an interrupted run. */
export interface DiscardInterruptedRunResult {
  /** Why it failed; empty when `ok` is true. */
  error?: string;
  /** `true` once no such interrupted run is left, also when there was none, so a retry is harmless. `false` when the id was empty or the change could not be saved. */
  ok: boolean;
}

/** The outcome of discarding a pending message. */
export interface DiscardPendingMessageResult {
  /** Why it failed; empty when `ok` is true. */
  error?: string;
  /** `true` once the message is no longer pending, also when it was not, so a retry is harmless. `false` when the id was empty, the message is one a run of this backend may still be finishing, or the change could not be saved. */
  ok: boolean;
}

/** An email address to find the user's igni server from. */
export interface DiscoverServerArgs {
  /** The user's email address; its domain is looked up for an igni server. */
  email: string;
}

/** How the conversation is shown: the `display` section of igni's settings. */
export interface DisplayConfig {
  /** Color theme: `auto` (follow the terminal or system), `light` or `dark`. */
  color_theme?: string;
  /** Render agent replies as Markdown rather than plain text. */
  markdown?: boolean;
  /** Number of lines of a long message shown before it is truncated. */
  message_truncate_lines?: number;
  /** Show the model's reasoning, when it produces any. */
  show_reasoning?: boolean;
  /** Verbose mode: show which agent handles each step and how work is routed. */
  show_routing?: boolean;
  /** Show the agent's tool calls in the conversation. */
  show_tool_calls?: boolean;
  /** Number of lines of a tool's output shown before it is collapsed. */
  tool_result_preview_lines?: number;
}

/** One element of a card the client could not draw. */
export interface ElementFailureArgs {
  /** Why the client could not draw it, in the client's words. */
  message?: string;
  /** The element's type, e.g. `BarGraph`. */
  type?: string;
}

/**
 * An error message to show the person.
 *
 * On the wire: `error`.
 */
export interface ErrorMessage {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** What went wrong. */
  text?: string;
  /** Always `error`: what kind of message this is. */
  type?: "error";
}

/** Arguments for running a scheduled task's work now. */
export interface ExecuteScheduledTaskArgs {
  /** What the task asks the agent to do (a scheduled task's `description`). */
  description: string;
  /** Id to give the run, so the caller can follow the run's pushes (their `run_id`) as they come; one is made when absent. */
  run_id?: string;
}

/**
 * A small status indicator an extension shows in the client's own
 * interface. The client gets its current value by calling a tool of
 * the extension's every `intervalSeconds`.
 */
export interface ExtensionIndicator {
  /** The indicator's id, a reverse-DNS name. */
  id: string;
  /** How often to call `source`, in seconds. */
  intervalSeconds?: number;
  /** The indicator's name, for a person. */
  label: string;
  /** The `kind` of the extension page to open when the indicator is clicked; empty for an indicator that only reports. */
  opens?: string;
  /** The extension tool to call for the current value; it answers `{label, tone, detail}`. */
  source: string;
}

/** Every installed extension, in a stable order. */
export interface ExtensionListResult {
  /** The installed extensions. */
  extensions?: ExtensionSummary[];
}

/** An entry an extension adds to the tools menu; choosing it runs a slash command. */
export interface ExtensionMenuEntry {
  /** The slash command it runs, e.g. `/review`. */
  command: string;
  /** A one-line description of what it does. */
  desc: string;
  /** The entry's text, for a person. */
  label: string;
}

/** A page an extension contributes to the client. */
export interface ExtensionPage {
  /** The file, relative to the extension's `origin`, the page loads. */
  entry?: string;
  /** The page's kind, a reverse-DNS name unique across extensions, e.g. `com.example.notes`. */
  kind: string;
  /** The page's title, for a person. */
  label: string;
  /** Whether the page is listed in the sidebar. */
  sidebar?: boolean;
}

/** One setting an extension can be configured with. */
export interface ExtensionSetting {
  /** The value used when none is set. */
  default?: JsonValue;
  /** The setting's key in `values`. */
  key: string;
  /** The setting's name, for a person. */
  label: string;
  /** The allowed values when `type` is `enum`; empty otherwise. */
  options?: string[];
  /** The kind of value: `string`, `number`, `boolean` or `enum`. */
  type: string;
}

/** A slash command an installed extension answers. */
export interface ExtensionSlashCommand {
  /** A hint for the arguments it takes; empty when it takes none. */
  argument_hint?: string;
  /** What the command does, in one line. */
  description?: string;
  /** The command's name, without the leading `/`. */
  name: string;
  /** The id of the extension that answers it. */
  owner?: string;
  /** Always `extension`: a command an extension answers. */
  source?: "extension";
}

/**
 * One installed extension: who it is, what state it is in, where its
 * pages are served, and what it contributes.
 */
export interface ExtensionSummary {
  /** The RPC methods its pages were granted. igni checks every call; this copy lets a client refuse early. */
  allow?: string[];
  /** Its prompt edits that have no effect, because another extension replaces that prompt and has no section the edit names. */
  dropped?: ExtensionSwitchedOff[];
  /** Why it is marked faulty (its calls timed out or crashed too often in a row, and igni restarted it); empty while it answers. */
  faulty?: string;
  /** The host permissions it was granted, for display. */
  host?: string[];
  /** The extension's id, a reverse-DNS name. */
  id: string;
  /** Status indicators it contributes. */
  indicators?: ExtensionIndicator[];
  /** Entries it adds to the tools menu. */
  menu?: ExtensionMenuEntry[];
  /** The extension's display name. */
  name: string;
  /** Where its pages are served from; empty when it contributes none. */
  origin?: string;
  /** Pages it contributes. */
  pages?: ExtensionPage[];
  /** Problems that do not stop it working, e.g. a tool reporting other hints than its manifest declares. */
  problems?: string[];
  /** Why it is not `READY`, and what to do; empty when it is. */
  reason?: string;
  /** How its process runs, e.g. `sandboxed (seatbelt)` or `not sandboxed: <why>`; empty when igni starts no process for it. An unsandboxed process has the user's full file and network access. */
  sandbox?: string;
  /** The URL of its own service, as its pages reach it; `null` when it has none a page may reach. */
  service_url?: string | null;
  /** The settings it can be configured with; their current values are in `values`. */
  settings?: ExtensionSetting[];
  /** What the extension is doing: `READY`, `PREPARING`, `DISABLED` or `FAILED`. */
  state: string;
  /** What it does not get because it collides with another extension. Usually empty. */
  switched_off?: ExtensionSwitchedOff[];
  /** The tools it gives the agent. */
  tools?: ExtensionTool[];
  /** The current setting values, by key, with defaults filled in and undeclared keys dropped. They reach its pages as launch parameters. */
  values?: Record<string, JsonValue>;
  /** The installed version, a semantic version. */
  version: string;
  /** Its home on the web, when one is known; `null` otherwise. */
  web_url?: string | null;
}

/** One thing an extension does not get, because it collides with another. */
export interface ExtensionSwitchedOff {
  /** What it claimed, e.g. `prompt:main.workflow`, `command:/review` or `agent:explorer`. */
  claim: string;
  /** Who decided against it, or that nobody has decided yet. */
  reason: string;
}

/** One tool an extension gives the agent, as the panel lists it. */
export interface ExtensionTool {
  /** What the tool says about itself, for a person, e.g. `read-only, local, idempotent`. */
  hints: string;
  /** The tool's name. */
  name: string;
}

/** An extension asked for a link to be opened in the person's browser. */
export interface ExternalOpen {
  /** The id of the extension that asked. */
  source: string;
  /** The link to open. */
  url: string;
  /** The id of the window that should open it; other windows ignore it. */
  window: string;
}

/** Arguments for learning from one finished turn. */
export interface ExtractLearningsArgs {
  /** The assistant's answer in the turn. */
  assistant_msg: string;
  /** The user's message in the turn. */
  user_msg: string;
}

/** Project files matching a partial name, for `@`-mention completion. */
export interface FileCompletion {
  /** Matching file paths, relative to the project folder, best match first; at most the requested limit. */
  matches: string[];
  /** How many files matched in all; more than the length of `matches` when the list was cut at the limit. */
  total: number;
}

/**
 * Channel `file_edited`. The agent has written a file. A client
 * showing that file in an editor can reload it.
 */
export interface FileEditedPayload {
  /** The file that was written. */
  path: string;
}

/** One notification for the person, from igni server or from an extension on this machine. */
export interface FloorNotification {
  /** Who caused it, for display; empty when nobody in particular. */
  actor?: string;
  /** The text under the headline; empty when there is none. */
  body?: string;
  /** When it was created; null when unknown. */
  created_at?: string | null;
  /** The notification's id; use it to mark it read. */
  id: string;
  /** The extension's own name for what kind of notification it is; empty when none. */
  kind?: string;
  /** The organisation it happened in, for one from igni server; empty for a local one. */
  org_id?: string;
  /** That organisation's name, set only when the person belongs to more than one. Show it when it is set. */
  org_name?: string;
  /** Where it came from. */
  origin: NotificationOrigin;
  /** True once it has been marked read. */
  read?: boolean;
  /** The id of the extension it is from. */
  source: string;
  /** The page to open when the person opens it; null when there is none. */
  target?: NotificationTarget | null;
  /** A one-line headline. */
  title?: string;
}

/** One match from searching across every session in the project. */
export interface GlobalChatSearchHit {
  /** When the turn was created, in Unix epoch seconds; `0` if unknown. */
  created_at?: number;
  /** Index of the matching turn in the list returned by `get_chat_history`; use it to jump to that turn. */
  history_index?: number;
  /** End offset (exclusive) of the match within `snippet`. */
  match_end?: number;
  /** Start offset of the match within `snippet` (not the full text). */
  match_start?: number;
  /** Kind of the matching turn, e.g. `user`, `assistant` or `tool`. */
  role?: string;
  /** Id of the agent run the matching turn belongs to. */
  run_id?: string;
  /** Id of the session the match is in; open it to read the turn. */
  session_id?: string;
  /** Name of that session, or empty when it has none. */
  session_name?: string;
  /** Excerpt of the turn's text around the match. */
  snippet?: string;
}

/**
 * The policy pack of the group the current user belongs to on igni
 * server. Every field is empty when the user belongs to no group.
 */
export interface GroupPolicyPackResult {
  /** The model this group's members get when nothing names one; `null` when the group sets none. */
  default_model?: string | null;
  /** How many entries the pack holds. */
  entry_count?: number;
  /** When the pack was last fetched, as an ISO 8601 timestamp; `null` if never. */
  fetched_at?: string | null;
  /** The group's id; `null` when in no group. */
  group_id?: string | null;
  /** The group's name; `null` when in no group. */
  group_name?: string | null;
}

/**
 * One answer inside a `hitl_response_batch`: as `hitl_response`,
 * plus a permission mode to switch to before the run resumes
 * (`set_permission_mode`), so the very next tool call is checked
 * under it.
 *
 * On the wire: `hitl_decision`.
 */
export interface HitlDecision {
  /** `confirm` to run the tool call, `reject` to refuse it. */
  action?: "confirm" | "reject";
  /** How long the answer stands. `once` (or empty): this call only. `always`: save a rule allowing this exact call. `similar`: save a rule allowing calls like it. `deny`: save a rule refusing it. */
  choice?: "" | "once" | "always" | "similar" | "deny";
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The approval request's id, from its `hitl_request`. */
  requirement_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** A permission mode to switch to before the run resumes; empty to keep the current one. */
  set_permission_mode?: "" | "default" | "plan" | "acceptEdits" | "bypassPermissions";
  /** Always `hitl_decision`: what kind of message this is. */
  type?: "hitl_decision";
}

/**
 * A tool call that needs the person's approval before it runs.
 *
 * The run waits until a client answers with `hitl_response` (or
 * `hitl_response_batch`), quoting `requirement_id`.
 *
 * On the wire: `hitl_request`.
 */
export interface Requirement {
  /** The chain of agents that made the call, outermost first. Empty (or one entry) for the main agent; for example `["architect", "reviewer"]` when a reviewer started by an architect asked. */
  agent_path?: string[];
  /** Why approval is being asked, for the person; empty when there is no reason given. */
  details?: string;
  /** True when `details` is still being written; it arrives later in a `requirement_details` message. Show a placeholder until then. */
  details_pending?: boolean;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** A human-readable name for the tool, for display; empty when there is none. */
  friendly_name?: string;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The request's id; quote it in the answer. */
  requirement_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The arguments the tool would be called with. */
  tool_args?: Record<string, JsonValue>;
  /** The tool's name, as the model called it. */
  tool_name?: string;
  /** Always `hitl_request`: what kind of message this is. */
  type?: "hitl_request";
}

/**
 * The person's answer to one approval request (from `run_paused`).
 *
 * On the wire: `hitl_response`.
 */
export interface HitlResponse {
  /** `confirm` to run the tool call, `reject` to refuse it. */
  action?: "confirm" | "reject";
  /** How long the answer stands. `once` (or empty): this call only. `always`: save a rule allowing this exact call. `similar`: save a rule allowing calls like it. `deny`: save a rule refusing it. */
  choice?: "" | "once" | "always" | "similar" | "deny";
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The approval request's id, from its `hitl_request`. */
  requirement_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `hitl_response`: what kind of message this is. */
  type?: "hitl_response";
}

/**
 * The person's answers to every approval request of one pause, sent
 * together: a request left out is taken as rejected.
 *
 * On the wire: `hitl_response_batch`.
 */
export interface HitlResponseBatch {
  /** One answer per approval request. */
  decisions?: HitlDecision[];
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `hitl_response_batch`: what kind of message this is. */
  type?: "hitl_response_batch";
}

/**
 * One configured hook: what it runs, and on which event.
 *
 * Hooks come in several types (a shell command, an HTTP call, an MCP
 * tool call, …). A field that does not apply to a hook's type is
 * empty, e.g. `command` on an HTTP hook or `url` on a command hook.
 */
export interface HookEntryView {
  /** Whether the hook runs without making the agent wait for it. */
  background?: boolean;
  /** The shell command a `command` hook runs. */
  command?: string;
  /** The event the hook runs on. */
  event: string;
  /** The names of the headers an `http` hook sends. Never their values, which may be credentials. */
  header_names?: string[];
  /** Which targets the hook applies to; empty matches every target. */
  matcher?: string;
  /** How long the hook may run, in milliseconds. */
  timeout_ms?: number;
  /** The hook's type, e.g. `command` or `http`. */
  type?: string;
  /** The URL an `http` hook calls, with any credentials removed. */
  url?: string;
}

/** A signal for one extension's pages: pass it to every page of that extension you show. */
export interface HostSignal {
  /** The id of the extension whose pages it is for. */
  extension_id: string;
  /** The signal's name, e.g. `chat.run_completed` or `session.switched`. */
  signal: string;
  /** The signal's value; its shape depends on `signal`. */
  value?: JsonValue;
}

/** A web fetch failed with a temporary error and igni is about to retry it. */
export interface HttpRetryAttemptEventPayload {
  /** Number of the attempt about to be made, counting the first request as 1 (so the first retry is 2). */
  attempt: number;
  /** Seconds igni waits before making this attempt. */
  delay_seconds: number;
}

/** A web fetch succeeded after at least one retry. */
export interface HttpRetrySucceededEventPayload {
  /** Total number of requests made, including the first. */
  attempt_count: number;
  /** Total seconds spent waiting between attempts. */
  delay_seconds: number;
  /** URL that was fetched. */
  url: string;
}

/** The answer to `hydrate`: the window's whole model, its revision, and the fields nobody has set. */
export interface Hydrated {
  /** Always `hydrate`: the request this answers. */
  op?: "hydrate";
  /** The window's revision. */
  rev: number;
  /** Every field of the window's model, as the model holds it. */
  state: WindowModelState;
  /** The fields still at their defaults, never set. */
  unset: string[];
}

/**
 * A short informational message to show the person.
 *
 * On the wire: `info`.
 */
export interface InfoMessage {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The message. */
  text?: string;
  /** Always `info`: what kind of message this is. */
  type?: "info";
}

/** Arguments for installing a plugin. */
export interface InstallPluginArgs {
  /** Branch, tag or commit to check out; when absent, the marketplace's choice or the default branch. */
  install_ref?: string | null;
  /** A git URL, or `@<marketplace>/<plugin>` for a marketplace plugin. */
  ref: string;
}

/**
 * A run that stopped before it finished, and the user message that
 * started it. A client can offer to retry it, discard it, or edit the
 * message and send it again.
 */
export interface InterruptedRun {
  /** That message's text. */
  content: string;
  /** When the run stopped, in seconds since the Unix epoch. */
  interrupted_at: number;
  /** The error, when `reason` is `errored`; `null` otherwise. */
  last_error?: string | null;
  /** The id of the user message that started the run. */
  message_id: string;
  /** Why it stopped: `cancelled` (the user stopped it), `errored` (it failed; see `last_error`) or `abandoned` (it never finished, e.g. igni stopped while it ran). */
  reason: "cancelled" | "errored" | "abandoned";
  /** When igni received the message, in seconds since the Unix epoch. */
  received_at: number;
}

/** Arguments naming one interrupted run of a session. */
export interface InterruptedRunArgs {
  /** Id of the message that started the run, as listed by `get_interrupted_runs`; must not be empty. */
  message_id: string;
  /** Id of the session to act on. */
  session_id: string;
}

/**
 * The session's current plan-mode plan and task list.
 *
 * Read it when opening a plan view and again after the agent submits
 * a plan.
 */
export interface LatestPlanResult {
  /** Earlier plans submitted in this session, oldest first. */
  history?: string[];
  /** The most recent plan text (Markdown); empty if none. */
  latest?: string;
  /** `pending` when a plan is waiting for the user to approve or dismiss it; `""` when no plan has been submitted. */
  state?: "pending" | "approved" | "dismissed" | "";
  /** The session's current task (todo) list. */
  tasks?: TodoItem[];
}

/** Arguments for listing the folders inside a folder. */
export interface ListDirsArgs {
  /** The folder to list; the home folder when absent or empty. */
  path?: string | null;
  /** Include folders whose names start with a dot. */
  show_hidden?: boolean;
}

/**
 * Channel `login_result`. How a sign-in ended. Sent once, after
 * the `login` call has returned and the sign-in has finished.
 */
export interface LoginResultPayload {
  /** The sign-in it ends: the `flow_id` that `login` returned. */
  flow_id?: string;
  /** On success, the signed-in email address; on failure, why it failed. May be empty. */
  result: string;
  /** Whether the user is now signed in. */
  success: boolean;
}

/**
 * Confirms that a sign-in has started. Its progress and outcome
 * arrive later as `login_status` and `login_result` pushes.
 */
export interface LoginStarted {
  /** This sign-in's id, which its `login_status` and `login_result` pushes carry. */
  flow_id?: string;
  /** `true` when the sign-in started. */
  started: boolean;
}

/**
 * Channel `login_status`. Progress of a sign-in that is under way,
 * as text for a person.
 */
export interface LoginStatusPayload {
  /** The sign-in it is about: the `flow_id` that `login` returned. */
  flow_id?: string;
  /** The current status, for a person. */
  text: string;
}

/**
 * What happened when a repeating prompt loop moved to its next iteration.
 *
 * `kind` says which of three outcomes this is; only the fields
 * belonging to that outcome are set, the rest keep their defaults:
 *
 * * `completed` - the loop reached the iteration count the user asked
 *   for and has ended; `total_iterations` holds that count.
 * * `safety_paused` - a loop with no explicit count reached igni's
 *   safety limit and paused instead of ending; `iteration` holds the
 *   count reached.
 * * `step` - a normal next iteration: `prompt`, `display_prompt`,
 *   `iteration`, `remaining` and `cap_explicit` are set.
 */
export interface LoopAdvance {
  /** True on the first iteration after an open-ended loop's safety budget rolled over (it is extended every 30 iterations, up to 200). */
  auto_extended?: boolean;
  /** True when the user gave an explicit iteration count; false for an open-ended loop that runs until stopped or the safety limit. */
  cap_explicit?: boolean;
  /** True when `kind` is `completed`. */
  completed?: boolean;
  /** The user's own prompt text, for showing in the chat. Set only when `kind` is `step`. */
  display_prompt?: string;
  /** 1-based number of the iteration about to run (`step`), or the number reached when the loop paused (`safety_paused`). */
  iteration?: number;
  /** Which outcome this is: `completed` (loop finished its requested count), `safety_paused` (an open-ended loop hit the safety limit and paused) or `step` (a normal next iteration). */
  kind?: "completed" | "safety_paused" | "step";
  /** Full text sent to the agent for this iteration, including igni's loop instructions. Set only when `kind` is `step`. */
  prompt?: string;
  /** Iterations left after this one. Set only when `kind` is `step`. */
  remaining?: number;
  /** True when `kind` is `safety_paused`. */
  safety_cap_paused?: boolean;
  /** Number of iterations the loop ran. Set only when `kind` is `completed`. */
  total_iterations?: number;
}

/**
 * Status of the session's `/loop` (a prompt the agent repeats
 * over several iterations).
 */
export interface LoopStatusSnapshot {
  /** `true` when a loop is running or paused. */
  active: boolean;
  /** Total number of iterations the agent said the loop will take, for progress display (`N / total`); `null` if the agent has not said. */
  announced_total: number | null;
  /** `true` when the user gave the iteration count (`/loop N <prompt>`), so the loop ends at the cap. `false`: the cap is a safety net that extends automatically. */
  cap_explicit: boolean;
  /** Number of iterations started so far (1-based); `0` when idle. */
  iteration_index: number;
  /** Iterations left before the loop's cap is reached; `0` when idle. */
  iterations_remaining: number;
  /** `true` when the loop is paused and waits to be resumed: paused by hand, stopped at the hard iteration cap, or restored paused after igni restarted. */
  paused: boolean;
  /** The prompt being looped; empty when no loop is active. */
  prompt: string;
}

/** One prompt template an MCP server offers. */
export interface McpPrompt {
  /** Names of the arguments the prompt takes. Empty when it takes none. */
  arguments?: string[];
  /** What the prompt is for. Empty when not given. */
  description?: string;
  /** Name of the prompt on its server. */
  name: string;
}

/**
 * One resource an MCP server offers (a file, document or other data it can return).
 *
 * Only `uri` is always set; the other fields are empty when the
 * server does not provide them.
 */
export interface McpResource {
  /** What the resource contains. Empty when not given. */
  description?: string;
  /** MIME type of the resource content, e.g. `text/plain`. Empty when unknown. */
  mime_type?: string;
  /** Human-readable name of the resource. Empty when not given. */
  name?: string;
  /** URI that identifies the resource on its server. */
  uri: string;
}

/**
 * Full details of one configured MCP server: connection state,
 * tools, resources and prompts.
 */
export interface McpServerSnapshot {
  /** `true` when igni is currently connected to the server. */
  connected: boolean;
  /** The last connection error; empty if none. */
  error?: string;
  /** The server's name, as configured. */
  name: string;
  /** `true` when an administrator policy forbids using this server. */
  policy_blocked?: boolean;
  /** Prompts the server offers; empty when it is not connected. */
  prompts?: McpPrompt[];
  /** Resources the server offers; empty when it is not connected. */
  resources?: McpResource[];
  /** Each tool's description, keyed by tool name. */
  tool_descriptions?: Record<string, string>;
  /** Every tool the server offered when it connected, including disabled ones. */
  tool_names?: string[];
  /** Tools the user has turned off; the agent cannot use them. */
  tools_disabled?: string[];
  /** How igni talks to the server, e.g. `stdio` or `sse`; `unknown` if it has no config. */
  transport: string;
}

/**
 * An MCP server's name and whether it is connected.
 *
 * A cheap listing; use the server details call for tools,
 * resources and prompts.
 */
export interface McpServerSummary {
  /** `true` when igni is currently connected to the server. */
  connected: boolean;
  /** The server's name, as configured. */
  name: string;
}

/**
 * Connect or disconnect one of the configured MCP servers.
 *
 * On the wire: `mcp_toggle`.
 */
export interface McpToggle {
  /** True to connect, false to disconnect. */
  connect?: boolean;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The MCP server's name, as configured. */
  server_name?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `mcp_toggle`: what kind of message this is. */
  type?: "mcp_toggle";
}

/**
 * Result of enabling or disabling one tool of an MCP server.
 *
 * Echoes the tool's new state, so no second call is needed to
 * confirm it.
 */
export interface McpToolToggleResult {
  /** The tool's state now: `true` if the agent may use it. */
  enabled: boolean;
  /** Name of the MCP server the tool belongs to. */
  server: string;
  /** Name of the tool. */
  tool: string;
}

/**
 * Arguments for marking notifications read: give `ids`, or
 * `source`, or neither to mark every notification read.
 */
export interface MarkReadArgs {
  /** Ids of the notifications to mark read. */
  ids?: string[] | null;
  /** An extension id: marks all of that extension's notifications read. */
  source?: string | null;
}

/** Arguments for marking a chat as seen. */
export interface MarkSessionSeenArgs {
  /** The chat the person looked at. */
  session_id: string;
}

/** A slash command the user wrote as a Markdown file. */
export interface MarkdownSlashCommand {
  /** A hint for the arguments it takes; empty when it takes none. */
  argument_hint?: string;
  /** What the command does, in one line. */
  description?: string;
  /** The command's name, without the leading `/`. */
  name: string;
  /** Always `markdown`: a command defined in a Markdown file. */
  source?: "markdown";
}

/** A plugin marketplace registered with igni, with its catalog as of the last fetch. */
export interface MarketplaceInfo {
  /** When the catalog was last fetched, as an ISO 8601 UTC timestamp. Empty if never. */
  last_fetched?: string;
  /** Marketplace name. */
  name: string;
  /** Plugins in the catalog. Empty until the catalog has been fetched. */
  plugins?: MarketplacePluginInfo[];
  /** Git URL the marketplace catalog is fetched from. */
  url: string;
}

/** Arguments naming a plugin marketplace. */
export interface MarketplaceNameArgs {
  /** Name of the marketplace. */
  name: string;
}

/** One plugin listed in a marketplace's catalog, available to install. */
export interface MarketplacePluginInfo {
  /** Git branch to install from. Empty for the repository's default branch. */
  branch?: string;
  /** Category the catalog files the plugin under (e.g. `development`, `security`). Empty when the catalog gives none. */
  category?: string;
  /** What the plugin does. Empty when not given. */
  description?: string;
  /** Plugin name; install it as `@<marketplace>/<name>`. */
  name: string;
  /** Where the plugin is fetched from: a git URL, followed by `[<subdirectory>]` when the plugin lives in a subdirectory of that repository. */
  source: string;
  /** Version listed in the catalog. Empty when not given. */
  version?: string;
}

/** Arguments for adding a plugin marketplace. */
export interface MarketplaceUrlArgs {
  /** The marketplace's git URL. */
  url: string;
}

/** Whether a configured MCP server may connect: its first-use approval. */
export interface McpApproval {
  /** `true` when it may connect: approved once, or from the user's own `~/.igni/.mcp.json`. An unapproved one is never connected. */
  approved: boolean;
  /** The server's name, as configured. */
  name: string;
  /** Where it is configured: `user`, `project`, `plugin`, `managed`, ... */
  source: string;
  /** The configuration file it comes from. */
  source_path: string;
}

/** Arguments approving a configured MCP server, or withdrawing its approval. */
export interface McpApprovalArgs {
  /** `true` approves it; `false` withdraws its approval and disconnects it. */
  approved: boolean;
  /** The server's name in the MCP configuration. */
  server_name: string;
}

/** Outcome of connecting the session's configured MCP servers. */
export interface McpInitResult {
  /** Names of the servers that connected, sorted. */
  connected?: string[];
  /** Servers that failed to connect, mapped to the error for each. */
  failed?: Record<string, string>;
  /** True when the session's agents were rebuilt so they can use the newly connected servers' tools. */
  rebuilt?: boolean;
  /** Why no connection attempt was made, or why nothing changed: `already_initialized` (servers were connected earlier in the session), `no_configured_servers` (no MCP servers are configured) or `no_clients_connected` (every server failed, so the agents were not rebuilt). Null when a connection pass ran and at least one server connected. */
  skipped_reason?: "already_initialized" | "no_configured_servers" | "no_clients_connected" | null;
}

/** Arguments naming a configured MCP server. */
export interface McpServerArgs {
  /** The server's name in the MCP configuration. */
  server_name: string;
}

/** Connection state of one configured MCP server. */
export interface McpServerStatus {
  /** True when igni currently has a live connection to the server. */
  connected: boolean;
  /** Name of the MCP server as configured. */
  name: string;
}

/** Arguments for switching one MCP server tool on or off. */
export interface McpToolEnabledArgs {
  /** The tool's new state: `true` lets the agent use it. */
  enabled: boolean;
  /** Name of the MCP server; not checked to exist. */
  server: string;
  /** Name of the server's tool; not checked to exist. */
  tool: string;
}

/**
 * One model call within a run has finished; its token counts are known.
 *
 * On the wire: `model_completed`.
 */
export interface ModelCompleted {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** Tokens sent to the model in this call. */
  input_tokens?: number;
  /** Tokens the model produced in this call. */
  output_tokens?: number;
  /** The id of the run that started this one, for a sub-agent's run; empty for a top-level run. */
  parent_run_id?: string;
  /** The id of the run this event belongs to. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `model_completed`: what kind of message this is. */
  type?: "model_completed";
}

/**
 * One configured model as a client sees it: what it is and how it
 * runs. Its API key is never included, and its URL has any credentials
 * removed.
 */
export interface ModelRegistryEntryView {
  /** The model's context window, in tokens; `null` when not set. */
  context_window?: number | null;
  /** The reasoning effort asked of the model, `low` to `max` (Anthropic models only); `null` when not set. */
  effort?: string | null;
  /** Whether the entry says where its key comes from (a key, an environment variable or a command). Never the key itself. */
  has_api_key: boolean;
  /** Most tokens a reply may hold; `null` for the default. */
  max_tokens?: number | null;
  /** The model's id as the provider knows it. */
  model_id: string;
  /** Whether the system prompt and tool list are sent as cacheable (Anthropic models only). */
  prompt_caching: boolean;
  /** The provider that serves the model, e.g. `anthropic` or `openai_like`. */
  provider: string;
  /** Where the entry came from: `cloud` for igni server's models, empty for the local configuration's own. */
  source?: string;
  /** Sampling temperature; `null` for the provider's default. */
  temperature?: number | null;
  /** The `thinking` object sent to the model unchanged, e.g. `{"type": "adaptive"}` (Anthropic models only); `null` when not set. */
  thinking?: Record<string, JsonValue> | null;
  /** How long a request may take, in seconds. */
  timeout: number;
  /** The endpoint the model is reached at, without credentials; `null` for the provider's default. */
  url?: string | null;
  /** Whether the model accepts images. */
  vision: boolean;
}

/** The models a user can pick from, and which one is the default. */
export interface ModelRegistryResult {
  /** The name of the default model, a key of `registry`; empty means the first entry of `registry` is used. */
  default: string;
  /** The configured overall context-window limit, in tokens; also the size used while no model is configured. */
  max_context_window: number;
  /** Every configured model, keyed by the name used to pick it. */
  registry: Record<string, ModelRegistryEntryView>;
}

/**
 * Switch the session to a different model.
 *
 * On the wire: `model_switch`.
 */
export interface ModelSwitch {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the model to switch to. */
  model_name?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `model_switch`: what kind of message this is. */
  type?: "model_switch";
}

/** What a successful `switch_model` answers. */
export interface ModelSwitched {
  /** Says the model switched, with a note for any part of the choice that could not be saved. */
  text: string;
}

/** The arguments of a call that takes none: `{}`. */
export interface NoArgs {
}

/** How many notifications are unread, in all and per extension — the numbers for badges. */
export interface NotificationCounts {
  /** Unread notifications per extension id; an extension with none is left out. */
  by_source?: Record<string, number>;
  /** Unread notifications in all. */
  unread?: number;
}

/** Where opening a notification goes: one of its extension's pages. */
export interface NotificationTarget {
  /** The id of the extension's page to open. */
  page: string;
  /** The parameters to open the page with. Always strings: a number or a flag is given as its JSON text. */
  params?: Record<string, string>;
}

/** The unread notification counts changed. Refetch the list if you are showing it. */
export interface NotificationsChanged {
  /** What changed them. `server`: igni server's list was fetched again on its own (after signing in, or when the server said something changed). `listed`: a `notifications_list` call fetched it. `marked_read`: a `notifications_mark_read` call. `extension`: an extension on this machine posted a notice. `signed_out`: the person signed out. */
  cause?: "server" | "listed" | "marked_read" | "extension" | "signed_out";
  /** The unread counts now. */
  counts?: NotificationCounts;
}

/** The person's notifications, newest first, with the unread counts. */
export interface NotificationsListResult {
  /** The unread counts. */
  counts?: NotificationCounts;
  /** The notifications, newest first. */
  notifications?: FloorNotification[];
  /** Why igni server could not be asked, when it could not; empty otherwise. The local notifications and the last ones fetched from the server are still returned. */
  server_error?: string;
}

/** The unread counts after marking notifications read. */
export interface NotificationsReadResult {
  /** The unread counts now. */
  counts?: NotificationCounts;
  /** Why igni server could not be told, when it could not; empty otherwise. Notifications from the server may then still count as unread. */
  server_error?: string;
}

/** A sub-agent's progress (a tool call, its start, pause, end or error, a task) or a view the agent or an extension drew, told apart by `type`. */
export interface OrchestrateEventPayload {
}

/**
 * The session's output style changed.
 *
 * Lets a client update whatever shows the active style without
 * polling.
 */
export interface OutputStyleChangedEventPayload {
  /** Name of the output style in effect before the change. */
  previous: string;
  /** Name of the output style now in effect. */
  style: string;
}

/** One output style the agent can answer in. */
export interface OutputStyleInfo {
  /** What the style does, in one line. */
  description: string;
  /** The style's name, as it is chosen. */
  name: string;
}

/** The output styles available, and which one is in use. */
export interface OutputStylesResult {
  /** The name of the style in use. */
  active: string;
  /** Every style that can be chosen. */
  styles: OutputStyleInfo[];
}

/** One level of a window's page stack. */
export interface Page {
  /** What kind of page this is: `plugins`, `extensions`, or an extension's own kind. */
  kind: string;
  /** The name shown for this page. */
  label?: string;
  /** The page's parameters, as text: what the page was opened with. */
  params?: Record<string, string>;
}

/** The panel open over a window's chat. One at a time. */
export interface Panel {
  /** What kind of panel this is: `notifications`, `search`, `login` or `dir-picker`. */
  kind: string;
  /** The panel's own parameters: what the panel shows, in the panel's own shape. */
  params?: Record<string, JsonValue>;
}

/** A user message whose run has started but not yet finished. */
export interface PendingMessage {
  /** The message's text. */
  content: string;
  /** The message's id. */
  message_id: string;
  /** When igni received it, in seconds since the Unix epoch. */
  received_at: number;
  /** Always `user`. */
  role?: "user";
}

/** Arguments naming one pending message of a session. */
export interface PendingMessageArgs {
  /** Id of the pending message, as listed by `get_pending_messages`; must not be empty. */
  message_id: string;
  /** Id of the session to act on. */
  session_id: string;
}

/** The session's permission mode was switched. */
export interface PermissionModeChangedEventPayload {
  /** Always `switched`: the mode was changed directly, as opposed to the agent entering plan mode on its own (reported with kind `plan_mode_entered`). */
  kind?: "switched";
  /** Permission mode now in effect. */
  mode: PermissionMode;
  /** Permission mode in effect before the switch. */
  previous: PermissionMode;
}

/** The session's permission mode changed: the switch itself (`mode` and `previous`), or the plan tool's note that the agent entered plan mode (`mode`, `source`, `reason`). */
export interface PermissionModeChangedPayload {
}

/** Arguments for opening the operating system's folder picker. */
export interface PickDirArgs {
  /** Folder the picker opens in; the session's project folder when absent or empty. */
  start?: string | null;
}

/** The folder the user chose in the operating system's own folder picker. */
export interface PickDirResult {
  /** `true` when the user closed the picker without choosing. */
  cancelled: boolean;
  /** Why the picker could not be shown, e.g. no native dialog is available; empty otherwise. */
  error: string;
  /** The chosen folder; empty when none was chosen. */
  path: string;
}

/**
 * A plan the agent proposed was approved or dismissed.
 *
 * Clients use it to move the plan card from pending to its final
 * state.
 */
export interface PlanDecidedEventPayload {
  /** The decision recorded: `approved` or `dismissed`. */
  decision: PlanDecision;
  /** Run in which the agent submitted the plan. */
  run_id: string;
}

/** Outcome of approving or dismissing a plan the agent proposed. */
export interface PlanDecisionResult {
  /** The decision recorded: `approved` or `dismissed`. */
  decision: PlanDecision;
  /** Why the decision was not recorded. Null when `ok` is true. */
  error?: string | null;
  /** One-line summary of the permission-mode change the decision caused (for example `mode → default` on approval). Empty when the mode did not change. */
  mode_status?: string;
  /** True when the decision was recorded; false when it could not be (for example an unknown run or a storage failure). */
  ok?: boolean;
  /** Run in which the agent submitted the plan; identifies which plan was decided. */
  run_id: string;
}

/**
 * Plan mode was entered, with who entered it and why.
 *
 * Sent on the same channel as a plain permission-mode switch, after
 * it; a client can show it as a short banner explaining the switch.
 */
export interface PlanModeEnteredEventPayload {
  /** Always `plan_mode_entered`: tells this message apart from a plain mode switch (kind `switched`) on the same channel. */
  kind?: "plan_mode_entered";
  /** Permission mode now in effect: `default` (ask before risky actions), `plan` (read-only planning, no edits), `acceptEdits` (file edits approved automatically) or `bypassPermissions` (no approval prompts). */
  mode: "default" | "plan" | "acceptEdits" | "bypassPermissions";
  /** Why plan mode was entered, as given. Empty when none was given. */
  reason?: string;
  /** Who entered plan mode: `agent` (the agent chose to plan first) or `user`. */
  source: "agent" | "user";
}

/**
 * Arguments naming the run that submitted a plan.
 *
 * An empty `run_id` is refused in the answer (`ok: false`) rather
 * than as an invalid argument; a number is taken as its string.
 */
export interface PlanRunArgs {
  /** Id of the run that submitted the plan, as `plan_submitted` carries it. */
  run_id?: string;
}

/**
 * The agent submitted a plan for the user to approve or dismiss.
 *
 * `tasks` is the plan's initial checklist, in the same row shape
 * as the `todos_updated` push; later `todos_updated` pushes
 * update the rows' statuses as work proceeds.
 */
export interface PlanSubmittedEventPayload {
  /** The plan text, in Markdown. */
  plan: string;
  /** Run in which the plan was submitted; pass it back when approving or dismissing the plan. Omitted when not known. */
  run_id?: string | null;
  /** Checklist of the plan's steps, all starting as `pending`. Empty when the plan has no task list. */
  tasks?: TodoItem[];
}

/**
 * A plan the agent proposed in plan mode, shown in place of the
 * `exit_plan_mode` tool call.
 */
export interface PlanTurn {
  /** When the message was created, in Unix epoch seconds; `0` if unknown. */
  created_at?: number;
  /** The plan text (Markdown). */
  plan?: string;
  /** Turn kind; always `plan`. */
  role?: "plan";
  /** Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point. */
  run_id?: string;
  /** Whether the user acted on the plan: `pending` (not yet), `approved`, `dismissed`, or `""` if unknown. */
  state?: "pending" | "approved" | "dismissed" | "";
  /** The task list submitted with the plan. */
  tasks?: JsonValue[];
}

/** An agent the plugin provides. */
export interface PluginAgentInfo {
  /** What the agent does; may be empty. */
  description?: string;
  /** The agent's name. */
  name: string;
}

/**
 * What a plugin contains: its skills, agents, hooks, MCP servers,
 * tools and README.
 *
 * Describes an installed plugin, or one previewed from a marketplace
 * before installing. When `error` is set, the lists are empty.
 */
export interface PluginContents {
  /** Agents the plugin provides. */
  agents?: PluginAgentInfo[];
  /** Why the plugin could not be read (not found, git clone failed, ...); empty on success. */
  error?: string;
  /** Hooks the plugin registers, per event. */
  hooks?: PluginHookInfo[];
  /** MCP servers the plugin provides. */
  mcp_servers?: PluginMcpServerInfo[];
  /** The plugin's name. */
  name?: string;
  /** Where a previewed plugin comes from; `null` for an installed plugin. */
  preview_source?: PluginPreviewSource | null;
  /** The plugin's README (Markdown); empty if it has none. */
  readme?: string;
  /** Folder the plugin was read from. */
  root_path?: string;
  /** Skills the plugin provides. */
  skills?: PluginSkillInfo[];
  /** Custom tools the plugin provides. */
  tools?: PluginToolInfo[];
}

/** Arguments for switching an installed plugin on or off. */
export interface PluginEnabledArgs {
  /** The plugin's new state: `true` to switch it on. */
  enabled: boolean;
  /** Name of the installed plugin. */
  name: string;
}

/** Hooks the plugin registers for one event. */
export interface PluginHookInfo {
  /** Number of hook handlers the plugin registers for the event. */
  count: number;
  /** The hook event, e.g. `PreToolUse` or `Stop`. */
  event: string;
}

/** One installed plugin, with what it bundles and whether it is enabled. */
export interface PluginInfo {
  /** What the plugin does. Empty when not given. */
  description?: string;
  /** True when the plugin is active in this session. */
  enabled?: boolean;
  /** True when the plugin bundles agents. */
  has_agents?: boolean;
  /** True when the plugin bundles hooks. */
  has_hooks?: boolean;
  /** True when the plugin bundles language-server configurations. */
  has_lsp?: boolean;
  /** True when the plugin bundles MCP server configurations. */
  has_mcp?: boolean;
  /** True when the plugin bundles monitors. */
  has_monitors?: boolean;
  /** True when the plugin bundles skills. */
  has_skills?: boolean;
  /** True when the plugin bundles tools. */
  has_tools?: boolean;
  /** True when a system administrator installed the plugin; it is always enabled and cannot be disabled by the user. */
  managed?: boolean;
  /** Plugin name from its manifest. */
  name: string;
  /** Directory the plugin is installed in. */
  path?: string;
  /** Git commit the plugin is pinned to. Empty when it is not pinned. */
  pin?: string;
  /** Where the plugin was found: `user-claude` (~/.claude/plugins), `user-igni` (~/.igni/plugins), `project-claude` (the project's .claude/plugins), `project-igni` (the project's .igni/plugins), `group-policy-igni` (installed by the organization's policy), `managed-claude` or `managed-igni` (installed by a system administrator). */
  source_root?: string;
  /** Version from the plugin's manifest. Empty when not given. */
  version?: string;
}

/** An MCP server the plugin provides. */
export interface PluginMcpServerInfo {
  /** The command that starts the server (or its URL); may be empty. */
  command: string;
  /** The server's name. */
  name: string;
  /** How igni talks to the server, e.g. `stdio` or `sse`. */
  transport: string;
}

/** Arguments naming an installed plugin. */
export interface PluginNameArgs {
  /** Name of the installed plugin. */
  name: string;
}

/**
 * Where a previewed plugin comes from: a git repository and,
 * optionally, a folder inside it.
 *
 * Displayed as `"<url> [<subdir>]"`.
 */
export interface PluginPreviewSource {
  /** Folder inside the repository that holds the plugin; empty for the root. */
  subdir?: string;
  /** The plugin's git repository URL. */
  url: string;
}

/** A skill the plugin provides. */
export interface PluginSkillInfo {
  /** What the skill does; may be empty. */
  description?: string;
  /** The skill's name. */
  name: string;
}

/** A custom tool the plugin provides. */
export interface PluginToolInfo {
  /** The tool's name. */
  name: string;
}

/** The file a window's preview shows. */
export interface Preview {
  /** The path of the file being previewed. */
  path: string;
}

/** Arguments for previewing a plugin from git without installing it. */
export interface PreviewPluginArgs {
  /** Branch, tag or commit to read; the default branch when absent. */
  branch?: string | null;
  /** The plugin's git URL, optionally followed by a folder inside the repository. */
  source: string;
  /** The plugin's folder inside the repository; overrides one given in `source`. */
  subdir?: string | null;
}

/** Arguments naming a background process. */
export interface ProcessArgs {
  /** Operating-system process id of the background process. */
  pid: number;
}

/** Channel `process_exited`. A background process has finished. */
export interface ProcessExitedPayload {
  /** The command it ran; `null` when unknown. */
  cmd: string | null;
  /** How long it ran, in seconds; `null` when unknown. */
  duration_seconds: number | null;
  /** Its exit code; `null` when unknown. */
  exit_code: number | null;
  /** The process's id; `null` when unknown. */
  pid: number | null;
}

/**
 * Channel `process_line`. One line of output from a running
 * background process, sent as it is printed.
 */
export interface ProcessLinePayload {
  /** The line, from stdout or stderr, without its line ending; `null` when there is none. */
  line: string | null;
  /** The process's id; `null` when unknown. */
  pid: number | null;
}

/**
 * A background process the agent started, running or recently
 * finished.
 */
export interface ProcessRow {
  /** The command line that started the process. */
  cmd: string;
  /** How long the process has run (or ran), in seconds. */
  elapsed_seconds: number;
  /** The process's exit code once it has finished; `null` while running. */
  exit_code?: number | null;
  /** `true` while the process is still running. */
  is_running?: boolean;
  /** Operating-system process id. */
  pid: number;
}

/** Channel `process_started`. A background process has started. */
export interface ProcessStartedPayload {
  /** The command it runs; `null` when unknown. */
  cmd: string | null;
  /** The process's id, which its later `process_*` pushes carry; `null` when unknown. */
  pid: number | null;
  /** When it started, in seconds since the Unix epoch; `null` when unknown. */
  started_at: number | null;
}

/** Arguments for reading the latest output of a background process. */
export interface ProcessTailArgs {
  /** Operating-system process id of the background process. */
  pid: number;
  /** How many of the last lines to return (at least 1). */
  tail?: number;
}

/** The latest output of a background process. */
export interface ProcessTailResult {
  /** The exit code once the process has finished; `null` while running or if unknown. */
  exit_code: number | null;
  /** `true` while the process is still running; `false` for an unknown pid. */
  is_running: boolean;
  /** The last lines of the process's combined stdout and stderr; empty for an unknown pid. */
  output: string;
  /** Operating-system process id that was asked for. */
  pid: number;
}

/** Arguments for keeping an agent created during the session. */
export interface PromoteAgentArgs {
  /** Name of the agent created during the session. */
  name: string;
  /** Where to save it: `project` (the project's agents; the default) or `personal` (the user's own agents). */
  target?: string | null;
}

/**
 * The outcome of saving an agent created during a session as a
 * permanent agent file.
 */
export interface PromoteEphemeralResult {
  /** The file it was saved to; empty when `ok` is false. */
  dest?: string;
  /** The agent's name. */
  name: string;
  /** Whether the agent was saved. */
  ok: boolean;
  /** Why it was not saved; empty when `ok` is true. */
  reason?: string;
}

/**
 * A push — the channel, and the payload that channel carries.
 *
 * Something happened that a client may want to show, sent without
 * being asked. Scheduled tasks, login status, permission-mode
 * changes, background processes, file edits and more each have a
 * `channel`; the shape of `payload` depends on it. Ignore a
 * channel you do not know.
 *
 * The `channel` field says which kind of event this is; a client
 * routes on it to render or dispatch. See `PushChannel` for
 * the catalogue of known channels — the producer set is open, so
 * treat anything unlisted as a channel this module simply hasn't
 * catalogued yet, not as invalid.
 *
 * `channel` stays a raw `str` on the wire (not a strict
 * `PushChannel` enum field) so a producer emitting a channel
 * the catalogue does not name yet survives verbatim — a strict enum
 * with `_missing_` → `UNKNOWN` would rewrite the value to
 * `"unknown"` and lose the routing information a client keys on.
 *
 * Producers should build their pushes with the `push_*` factories
 * below rather than by hand: each takes that channel's payload
 * model, so the channel and the payload cannot drift apart.
 *
 * On the wire: `push_notification`.
 */
export interface PushNotification {
  /** What kind of push this is; it decides the shape of `payload`. */
  channel?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The push's data, shaped by `channel`. */
  payload?: Record<string, JsonValue>;
  /** The run whose work sent this push, when igni chose that run's id; empty otherwise. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `push_notification`: what kind of message this is. */
  type?: "push_notification";
}

/**
 * A message the person sends while a run is still going; it is queued for the agent.
 *
 * On the wire: `queue_message`.
 */
export interface QueueMessage {
  /** This client's id, from `welcome`, so it can recognise its own echo. Empty is allowed. */
  client_id?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The message. */
  text?: string;
  /** Always `queue_message`: what kind of message this is. */
  type?: "queue_message";
}

/**
 * A call to one of igni's methods. igni answers with an `rpc_response` carrying the same `id`.
 *
 * On the wire: `rpc_request`.
 */
export interface RpcRequest {
  /** The method's arguments, by name. */
  args?: Record<string, JsonValue>;
  /** The id of the extension whose page is making the call; null for igni's own interface. Methods under `ext.` need it: an extension may reach only its own service. */
  caller?: string | null;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The name of the method to call. */
  method?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `rpc_request`: what kind of message this is. */
  type?: "rpc_request";
}

/**
 * The answer to an `rpc_request`, with the request's `id`.
 *
 * It carries either `result` (the call succeeded) or `error` and
 * `code` (it failed), never both. The two factories build the two
 * shapes; a frame that carries both is refused on the way in.
 *
 * On the wire: `rpc_response`.
 */
export interface RpcResponse {
  /** Why the call failed, for a client to branch on; null on success. */
  code?: RpcErrorCode | null;
  /** What went wrong, as a sentence for a person; null on success. */
  error?: string | null;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** Any JSON value. */
  result?: JsonValue;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `rpc_response`: what kind of message this is. */
  type?: "rpc_response";
}

/** Arguments for reading a file to preview it. */
export interface ReadFileArgs {
  /** The file: relative to the project, absolute, or an `attachment:<id>` reference. */
  path: string;
}

/** Arguments for reading a file's raw bytes to preview an image or PDF. */
export interface ReadFileBytesArgs {
  /** The file: relative to the project, absolute, or an `attachment:<id>` reference. */
  path: string;
}

/**
 * The raw bytes of a file, base64-encoded, for previewing an image
 * or a PDF the text reader cannot show.
 *
 * Same sandbox as `ReadFileResult`; a larger cap, since an image
 * or a PDF is bigger than a source file.
 */
export interface ReadFileBytesResult {
  /** The file's bytes, base64-encoded; empty when `error` is set. */
  data: string;
  /** Why the file could not be read; empty on success. */
  error?: string;
  /** The file's media type guessed from its extension (e.g. `image/png`); empty if unknown or on error. */
  media_type?: string;
  /** The file's path (resolved when the read got that far). */
  path: string;
  /** The file's size in bytes. */
  size: number;
}

/**
 * The contents of a text file, for previewing it.
 *
 * Only files inside the project or igni's data folder can be read,
 * and large files are refused.
 */
export interface ReadFileResult {
  /** The file's text; empty when `error` is set. */
  contents: string;
  /** Why the file could not be read; empty on success. */
  error?: string;
  /** Syntax-highlighting language guessed from the file extension (e.g. `python`); empty if unknown or on error. */
  language?: string;
  /** The file's path (resolved to an absolute path when the read got that far). */
  path: string;
  /** The file's size in bytes. */
  size: number;
}

/**
 * The model has started reasoning ("thinking") before it replies.
 *
 * On the wire: `reasoning_started`.
 */
export interface ReasoningStarted {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the run that started this one, for a sub-agent's run; empty for a top-level run. */
  parent_run_id?: string;
  /** The id of the run this event belongs to. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `reasoning_started`: what kind of message this is. */
  type?: "reasoning_started";
}

/** Arguments for re-reading marketplace catalogues. */
export interface RefreshMarketplacesArgs {
  /** The marketplace to refresh; every marketplace when absent. */
  name?: string | null;
}

/**
 * The reason for an open approval request, sent after the request itself.
 *
 * A request sent with `details_pending` set gets its `details`
 * later in this message; show it in place of the placeholder.
 *
 * On the wire: `requirement_details`.
 */
export interface RequirementDetails {
  /** Why approval is being asked, for the person. */
  details?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the approval request. */
  requirement_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `requirement_details`: what kind of message this is. */
  type?: "requirement_details";
}

/**
 * An approval request was answered, in any client; close its dialog if you show one.
 *
 * On the wire: `requirement_resolved`.
 */
export interface RequirementResolved {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the approval request that was answered. */
  requirement_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `requirement_resolved`: what kind of message this is. */
  type?: "requirement_resolved";
}

/** The answer to `dismiss_toast`: the window's new revision. */
export interface Revised {
  /** Always `dismiss_toast`: the request this answers. */
  op?: "dismiss_toast";
  /** The window's revision after the toast was dismissed. */
  rev: number;
}

/**
 * An agent or team run has finished.
 *
 * On the wire: `run_completed`.
 */
export interface RunCompleted {
  /** How long the run took, in seconds. */
  duration?: number;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** Tokens sent to the model over the whole run. */
  input_tokens?: number;
  /** Tokens the model produced over the whole run, reasoning included. */
  output_tokens?: number;
  /** The id of the run that started this one, for a sub-agent's run; empty for a top-level run. */
  parent_run_id?: string;
  /** The part of `output_tokens` spent on the model's reasoning. The visible reply is `output_tokens - reasoning_tokens`. */
  reasoning_tokens?: number;
  /** The id of the run this event belongs to. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `run_completed`: what kind of message this is. */
  type?: "run_completed";
}

/**
 * The run failed and has stopped.
 *
 * On the wire: `run_error`.
 */
export interface RunError {
  /** What went wrong, as a human-readable message. */
  error?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `run_error`: what kind of message this is. */
  type?: "run_error";
}

/** A sub-agent's run failed. */
export interface RunErrorEvent {
  /** Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level). */
  agent_path: string;
  /** Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card. */
  card_id?: string | null;
  /** Error message describing the failure. */
  error: string;
  /** Always `run_error`: what kind of message this is. */
  type?: "run_error";
}

/**
 * The run is paused until the person approves or rejects one or more tool calls.
 *
 * Answer every request with `hitl_response_batch` (or each one with
 * `hitl_response`) to let the run continue.
 *
 * On the wire: `run_paused`.
 */
export interface RunPaused {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the run that started this one, for a sub-agent's run; empty for a top-level run. */
  parent_run_id?: string;
  /** The tool calls waiting for an answer. */
  requirements?: Requirement[];
  /** The id of the run this event belongs to. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `run_paused`: what kind of message this is. */
  type?: "run_paused";
}

/** Arguments for running a shell command in the project folder. */
export interface RunShellArgs {
  /** The command line to run (without a leading `$`); blank runs nothing. */
  command?: string;
}

/**
 * What a `$` command printed and how it ended — or, when it outlived
 * the wait, that it went on in the background and under which `pid`,
 * the id its `process_*` pushes carry.
 */
export interface RunShellResult {
  /** `true` when the command is still running, in the background. */
  backgrounded?: boolean;
  /** The exit code; `0` for a command still running in the background. */
  exit_code: number;
  /** What the command printed, stdout and stderr together. */
  output: string;
  /** The process's id, once it started; `null` when it could not start. */
  pid?: number | null;
}

/**
 * An agent or team run has begun.
 *
 * On the wire: `run_started`.
 */
export interface RunStarted {
  /** The name of the agent (or team) doing the run. */
  agent_name?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the model the run uses. */
  model?: string;
  /** The id of the run that started this one, for a sub-agent's run; empty for a top-level run. */
  parent_run_id?: string;
  /** The id of the run this event belongs to. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `run_started`: what kind of message this is. */
  type?: "run_started";
}

/** Arguments for saving a permission rule for the project. */
export interface SavePermissionRuleArgs {
  /** What the rule does: `allow`, `ask` or `deny`. */
  level: "allow" | "ask" | "deny";
  /** The permission rule: a tool name, or a tool with an argument pattern such as `Bash(git status)`. */
  rule: string;
}

/**
 * A prompt scheduled to run at a later time, once or repeatedly.
 *
 * When a recurring task completes, igni schedules its next occurrence
 * as a new task.
 */
export interface ScheduledTask {
  /** When the task was scheduled, in the machine's local time. */
  created_at?: string;
  /** What the task does: the prompt igni runs when it is due. */
  description: string;
  /** Error message when the run failed. Empty otherwise. */
  error?: string;
  /** Short identifier of the task (8 hex characters). */
  id: string;
  /** Repeat pattern in the form `every N <minutes|hours|days|weeks>` (e.g. `every 1 days`, `every 7 days`). Empty for a one-time task. */
  recurrence?: string;
  /** Output of the run once it completed. Empty until then. */
  result?: string;
  /** When the task is due to run, in the machine's local time. */
  scheduled_at: string;
  /** Where the task is in its lifecycle. */
  status?: TaskStatus;
}

/** Arguments naming a scheduled task. */
export interface ScheduledTaskArgs {
  /** The task's `id`, as `get_scheduled_tasks` lists it. */
  task_id: string;
}

/** The answer of a scheduled task run, and the run's id. */
export interface ScheduledTaskRunResult {
  /** The agent's answer, as text. */
  result: string;
  /** The run's id: the one asked for, or the one made. */
  run_id: string;
}

/** Arguments for listing scheduled tasks. */
export interface ScheduledTasksArgs {
  /** Also list completed, failed and cancelled tasks. */
  include_done?: boolean;
}

/** Channel `scheduler_completed`. A scheduled task has finished. */
export interface SchedulerCompletedPayload {
  /** What the task does, as it was scheduled. */
  description: string;
  /** The task's outcome, as text. */
  result: string;
  /** The scheduled task's id. */
  task_id: string;
}

/**
 * A scheduled task started or finished.
 *
 * On the wire: `scheduler_event`.
 */
export interface SchedulerEvent {
  /** What the task does, as it was scheduled. */
  description?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** What happened: `started`, `completed`, or `failed` (sometimes sent as `error`). Other values may appear; treat them as unknown. */
  event_type?: string;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The task's output when it finished, or the error when it failed; empty when it started. */
  result?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The scheduled task's id. */
  task_id?: string;
  /** Always `scheduler_event`: what kind of message this is. */
  type?: "scheduler_event";
}

/** Channel `scheduler_started`. A scheduled task has started running. */
export interface SchedulerStartedPayload {
  /** What the task does, as it was scheduled. */
  description: string;
  /** The scheduled task's id. */
  task_id: string;
}

/** Where a window's transcript is scrolled to. */
export interface Scroll {
  /** Whether the transcript is scrolled to its end. */
  at_bottom?: boolean;
  /** The message the transcript is scrolled to; null when it is at the end. */
  message_id?: string | null;
}

/** Arguments for searching across every session in the project. */
export interface SearchAllChatsArgs {
  /** Maximum number of hits to return in total. */
  limit?: number;
  /** Text to find, case-insensitive; blank finds nothing. */
  query: string;
}

/** Arguments for searching a session's conversation. */
export interface SearchChatArgs {
  /** Maximum number of hits to return. */
  limit?: number;
  /** Text to find, case-insensitive; blank finds nothing. */
  query: string;
  /** Id of the session to act on. */
  session_id: string;
}

/**
 * Arguments for finding where a code snippet appears in the project.
 *
 * Unknown keys are refused.
 */
export interface SearchCodeArgs {
  /** The snippet, matched exactly; shorter than 5 characters finds nothing. */
  query: string;
}

/** One place in the project where the searched text occurs. */
export interface SearchCodeMatch {
  /** 1-based line where the match ends (inclusive). */
  end_line: number;
  /** 1-based line where the match starts. */
  line: number;
  /** File path, relative to the project root. */
  path: string;
  /** The first matching line, trimmed of surrounding whitespace. */
  preview: string;
}

/**
 * Where a piece of text (e.g. pasted code) occurs in the project.
 *
 * Text shorter than 5 characters is not searched and gives an empty
 * result.
 */
export interface SearchCodeResult {
  /** Why the search failed, e.g. `search timed out`; empty on success. */
  error?: string;
  /** The matches found, up to the limit. */
  matches?: SearchCodeMatch[];
  /** `true` when the result limit was hit or the search timed out, so there may be more matches. */
  truncated?: boolean;
}

/** What is selected in a window. Each part is independent; `None` for nothing. */
export interface Selection {
  /** The file the selection is in; null when none is. */
  file?: string | null;
  /** The message the selection starts in; null when nothing is selected. */
  message_id?: string | null;
  /** The selected text; null when none is. */
  text?: string | null;
}

/** The igni server now in use, or why the choice was refused. */
export interface ServerChoice {
  /** The server's API URL; empty when refused. */
  api_url?: string;
  /** Why the server was refused; empty on success. */
  error?: string;
  /** Where a person signs in on that server; empty when refused. */
  portal_url?: string;
}

/**
 * Where an email address's organisation runs igni, or, with every
 * URL empty, why nothing usable was found.
 */
export interface ServerFound {
  /** The server's API URL; empty when none was found. */
  api_url?: string;
  /** Where a person signs in; empty when it is derived from `api_url` or nothing was found. */
  portal_url?: string;
  /** Why nothing usable was found; empty when a server was found. A domain with no record is normal, not a fault. */
  reason?: string;
  /** How the server was found: `well-known` (a document published on the domain) or `dns` (a DNS record); empty when nothing was found. */
  source?: string;
}

/**
 * The session's conversation was cleared or compacted (replaced by a summary) to free context.
 *
 * On the wire: `session_cleared`.
 */
export interface SessionCleared {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session's id from now on; it may be the same as before. */
  new_session_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The summary that now stands in for the earlier conversation; empty when there is none. */
  summary?: string;
  /** Always `session_cleared`: what kind of message this is. */
  type?: "session_cleared";
}

/** Arguments naming a session. */
export interface SessionIdArgs {
  /** Id of the session to act on. */
  session_id: string;
}

/**
 * Ask for the saved sessions. igni answers with a `session_list_result`.
 *
 * On the wire: `session_list`.
 */
export interface SessionList {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `session_list`: what kind of message this is. */
  type?: "session_list";
}

/**
 * One saved session, as listed by `session_list`.
 *
 * More fields may be present than those listed here; ignore any you
 * do not know.
 */
export interface SessionListEntry {
  /** The agent the session talks to. */
  agent_name?: string;
  /** When the session was created, in Unix seconds. */
  created_at?: number;
  /** True when this session has a run waiting for the person to answer an approval. */
  has_paused_run?: boolean;
  /** When a message last went into this session or a reply came out, in Unix milliseconds; `0` when igni has not recorded one. The list is newest first by it, or by `updated_at` for a session without one. */
  last_message_at?: number;
  /** The session's name; empty when it has none. */
  name?: string;
  /** How many runs the session holds. */
  run_count?: number;
  /** The session's id. */
  session_id?: string;
  /** A short summary of the conversation; empty when there is none. */
  summary?: string;
  /** True when a run in this session finished after the person last looked at it (`mark_session_seen`). */
  unread?: boolean;
  /** When the session last changed, in Unix seconds. */
  updated_at?: number;
}

/**
 * The answer to `session_list`: the saved sessions.
 *
 * On the wire: `session_list_result`.
 */
export interface SessionListResult {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The saved sessions. */
  sessions?: SessionListEntry[];
  /** Always `session_list_result`: what kind of message this is. */
  type?: "session_list_result";
}

/**
 * Channel `session_named`. igni has given a new session a
 * generated display name.
 */
export interface SessionNamedPayload {
  /** Its new display name. */
  name: string;
  /** The session that was named. */
  session_id: string;
}

/** One chat's state, and whether it is unread. */
export interface SessionState {
  /** When a message last went into the chat or a reply came out, in Unix milliseconds; `0` when igni has not recorded one. The sidebar lists chats by it, newest first. */
  last_message_at?: number;
  /** The chat's session id. */
  session_id: string;
  /** What the chat is doing. `running`: a run is working. `waiting`: a run waits on the person's answer to an approval. `idle`: nothing — also every chat that is not loaded. */
  state?: ActivityState;
  /** True when a run in the chat finished after the person last looked at it (`mark_session_seen`). Read state is the person's, across windows and devices. */
  unread?: boolean;
  /** How many approvals in the chat wait on the person. */
  waiting_approvals?: number;
}

/** Every chat that is doing something or is unread; any other chat is idle and read. */
export interface SessionStates {
  /** Why this was sent. `activity`: a run started, finished, paused or resumed, or the states were asked for. `seen`: a `mark_session_seen` call. */
  cause?: "activity" | "seen";
  /** The chats that are running, waiting or unread, each once. */
  sessions?: SessionState[];
}

/**
 * Switch to a different saved session.
 *
 * On the wire: `session_switch`.
 */
export interface SessionSwitch {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the session to switch to. */
  session_id?: string;
  /** Always `session_switch`: what kind of message this is. */
  type?: "session_switch";
}

/** New setting values for one extension. */
export interface SetExtensionSettingsArgs {
  /** The id of the extension to configure. */
  extension_id: string;
  /** Setting key to new value, merged over the stored values. A key the extension does not declare is refused. */
  values: Record<string, JsonValue>;
}

/** The igni server to use from now on. */
export interface SetServerArgs {
  /** The server's API URL. */
  api_url: string;
  /** Where a person signs in; empty to derive it from `api_url`. */
  portal_url?: string;
}

/**
 * Shut igni down cleanly.
 *
 * On the wire: `shutdown`.
 */
export interface Shutdown {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `shutdown`: what kind of message this is. */
  type?: "shutdown";
}

/** A window's sidebar: open or not, its width and its section. */
export interface Sidebar {
  /** Whether the sidebar is open. */
  open?: boolean;
  /** The section the sidebar shows; null for none. */
  section?: string | null;
  /** The sidebar's width in pixels; null for igni's own sidebar. */
  width?: number | null;
}

/** One skill the agent can use. */
export interface SkillDefinition {
  /** What the skill does, in one line. */
  description: string;
  /** The skill's name, as typed after `/`. */
  name: string;
  /** The skill's instructions; may be empty for a skill that has only a manifest. */
  prompt: string;
}

/** One skill available in the session, as shown in the skills panel. */
export interface SkillInfo {
  /** Agent the skill runs on when `context` is `fork`. Empty otherwise. */
  agent?: string;
  /** Hint shown for the arguments the skill expects. Empty when it takes none. */
  argument_hint?: string;
  /** Full instruction text of the skill (its SKILL.md body). */
  body?: string;
  /** Category the skill is grouped under. */
  category?: string;
  /** How the skill runs: `inline` (on the default skills agent) or `fork` (on the agent named in `agent`). */
  context?: string;
  /** What the skill does. Empty when not given. */
  description?: string;
  /** Skill name, used to invoke it (e.g. `/deploy`). */
  name: string;
  /** Directory the skill was loaded from. Empty when not loaded from disk. */
  source_dir?: string;
  /** True when the user can invoke the skill directly. */
  user_invocable?: boolean;
  /** Version declared by the skill. */
  version?: string;
}

/** A skill the user can run as a slash command. */
export interface SkillSlashCommand {
  /** A hint for the arguments it takes; empty when it takes none. */
  argument_hint?: string;
  /** What the skill does, in one line. */
  description?: string;
  /** The skill's name, without the leading `/`. */
  name: string;
  /** Always `skill`: a skill. */
  source?: "skill";
}

/**
 * Token usage and duration for one agent run, shown at the end of
 * the run. Has no `created_at`.
 */
export interface StatsTurn {
  /** How long the run took, in seconds. */
  duration?: number;
  /** Input (prompt) tokens used by the run. */
  input_tokens?: number;
  /** Output tokens generated by the run. */
  output_tokens?: number;
  /** Reasoning tokens generated by the run; `0` if the model reports none. */
  reasoning_tokens?: number;
  /** Turn kind; always `stats`. */
  role?: "stats";
  /** Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point. */
  run_id?: string;
}

/**
 * The session's current state, for a status bar: token use, model, account and permission mode.
 *
 * On the wire: `status_update`.
 */
export interface StatusUpdate {
  /** True when signed in to igni cloud. */
  cloud_connected?: boolean;
  /** The signed-in account's email address; empty when not signed in. */
  cloud_email?: string;
  /** The signed-in account's display name. Empty until igni has fetched it; show `cloud_email` meanwhile. */
  cloud_name?: string;
  /** The igni cloud organisation signed in to; empty when not signed in. */
  cloud_org?: string;
  /** Tokens the conversation currently takes up in the model's context. */
  context_tokens?: number;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** Tokens sent to the model so far in this session. */
  input_tokens?: number;
  /** The model's context window, in tokens; 0 when unknown. */
  max_context?: number;
  /** The id of the model in use. */
  model?: string;
  /** False when no model is set up, so a run could not reach one. */
  model_configured?: boolean;
  /** Tokens the model has produced so far in this session. */
  output_tokens?: number;
  /** The active permission mode: `default`, `plan`, `acceptEdits`, `bypassPermissions` or `dontAsk`. Other values may appear; treat them as unknown. */
  permission_mode?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Brand colour overrides from the signed-in account's group, keyed by theme token. Null for igni's own palette. */
  theme?: Record<string, JsonValue> | null;
  /** Always `status_update`: what kind of message this is. */
  type?: "status_update";
}

/** Result of stopping a background process. */
export interface StopProcessResult {
  /** `true` when the process was stopped; `false` if it was unknown or had already exited. */
  killed: boolean;
  /** Human-readable explanation of what happened. */
  message: string;
  /** Operating-system process id that was asked for. */
  pid: number;
}

/**
 * Marks the end of a streamed answer, such as a run's events.
 *
 * On the wire: `stream_end`.
 */
export interface StreamEnd {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `stream_end`: what kind of message this is. */
  type?: "stream_end";
}

/**
 * The model's reply is complete, though the run is still wrapping up.
 *
 * igni may spend a few more seconds saving and summarising before
 * `run_completed`. A client can let the person type and send their
 * next message as soon as this arrives: igni starts the next run once
 * the current one has fully finished.
 *
 * On the wire: `streaming_done`.
 */
export interface StreamingDone {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the run that started this one, for a sub-agent's run; empty for a top-level run. */
  parent_run_id?: string;
  /** The id of the run this event belongs to. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `streaming_done`: what kind of message this is. */
  type?: "streaming_done";
}

/** Arguments for switching the session's model. */
export interface SwitchModelArgs {
  /** A model name from the model registry (see `get_model_registry`). */
  model_name: string;
}

/**
 * A team run has created a task for one of its members.
 *
 * On the wire: `task_created`.
 */
export interface TaskCreated {
  /** The name of the member doing it; empty when unassigned. */
  assignee?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The task's status: `pending`, `running`, `completed`, `failed` or `cancelled`. Other values may appear; treat them as unknown. */
  status?: string;
  /** The task's id. */
  task_id?: string;
  /** What the task is, in a few words. */
  title?: string;
  /** Always `task_created`: what kind of message this is. */
  type?: "task_created";
}

/** A task was added to a team's task list. */
export interface TaskCreatedEvent {
  /** Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level). */
  agent_path: string;
  /** Name of the team member assigned the task. Empty when unassigned. */
  assignee?: string;
  /** Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card. */
  card_id?: string | null;
  /** Task title. Empty when not given. */
  title?: string;
  /** Always `task_created`: what kind of message this is. */
  type?: "task_created";
}

/**
 * A team run has started another round of work on its tasks.
 *
 * On the wire: `task_iteration`.
 */
export interface TaskIteration {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The number of the round now under way. */
  iteration?: number;
  /** The most rounds the run will take. */
  max_iterations?: number;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `task_iteration`: what kind of message this is. */
  type?: "task_iteration";
}

/** One task of a team run, as it stands now. */
export interface TaskSnapshot {
  /** The name of the member doing it; empty when unassigned. */
  assignee?: string;
  /** The task's status: `pending`, `running`, `completed`, `failed` or `cancelled`. Other values may appear; treat them as unknown. */
  status?: string;
  /** The task's id. */
  task_id?: string;
  /** What the task is, in a few words. */
  title?: string;
}

/**
 * Every task of a team run, as they stand now.
 *
 * On the wire: `task_state_updated`.
 */
export interface TaskStateUpdated {
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** All the run's tasks; replaces any earlier list. */
  tasks?: TaskSnapshot[];
  /** Always `task_state_updated`: what kind of message this is. */
  type?: "task_state_updated";
}

/**
 * A team run's task changed status or assignee.
 *
 * On the wire: `task_updated`.
 */
export interface TaskUpdated {
  /** The name of the member doing it; empty when unassigned. */
  assignee?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The task's new status: `pending`, `running`, `completed`, `failed` or `cancelled`. Other values may appear; treat them as unknown. */
  status?: string;
  /** The task's id, as in `task_created`. */
  task_id?: string;
  /** Always `task_updated`: what kind of message this is. */
  type?: "task_updated";
}

/** A task in a team's task list changed status. */
export interface TaskUpdatedEvent {
  /** Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level). */
  agent_path: string;
  /** Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card. */
  card_id?: string | null;
  /** New task status, such as `running`, `completed` or `failed`. Empty when unknown. */
  status?: string;
  /** Always `task_updated`: what kind of message this is. */
  type?: "task_updated";
}

/**
 * A sub-agent's or a team's progress card, as it was drawn during a run.
 *
 * `events` are the card's `orchestrate_event` payloads in the order
 * they arrived; feed them to the same reducer as the live push to draw
 * the card. Placed after the `spawn_agent` / `spawn_team` tool turn
 * it came from. Has no `created_at`. Shown only: none of it is in the
 * model's context.
 */
export interface TeamTurn {
  /** The card's id, as the live events carried it. */
  card_id?: string;
  /** The card's `orchestrate_event` payloads, oldest first. */
  events?: Array<Record<string, JsonValue>>;
  /** Turn kind; always `team`. */
  role?: "team";
  /** Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point. */
  run_id?: string;
  /** Position of the card's first event in the session's event log. */
  seq?: number;
  /** Id of the `spawn_agent` / `spawn_team` call the card is for; empty if unknown. */
  tool_call_id?: string;
}

/**
 * The model's reasoning ("thinking") for part of a run.
 *
 * Comes either from the model's separate reasoning output or from an
 * inline `<think>` block in the reply.
 */
export interface ThinkingTurn {
  /** The reasoning text. */
  content?: string;
  /** When the message was created, in Unix epoch seconds; `0` if unknown. */
  created_at?: number;
  /** Turn kind; always `thinking`. */
  role?: "thinking";
  /** Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point. */
  run_id?: string;
}

/** A transient message on screen. */
export interface Toast {
  /** A second line; null when there is none. */
  body?: string | null;
  /** The toast's own id: two writers cannot collide. */
  id?: string;
  /** How it is styled: `info`, `success`, `warning` or `error`. */
  kind: string;
  /** The extension that showed it; null for igni's own. */
  source?: string | null;
  /** Where clicking the toast goes; null when it goes nowhere. */
  target?: Page | null;
  /** The toast's first line. */
  text: string;
  /** Always `toast`: what this is. */
  type?: "toast";
}

/** The answer to `toast`: the toast as shown, with its id, and the window's revision. */
export interface ToastAdded {
  /** Always `toast`: the request this answers. */
  op?: "toast";
  /** The window's revision after showing it. */
  rev: number;
  /** The toast as shown, its `id` included. */
  toast: Toast;
}

/** One item in the agent's todo checklist. */
export interface TodoItem {
  /** Present-tense form shown while the item is in progress, e.g. `Running tests`. Empty when the agent gave none. */
  activeForm?: string;
  /** What the item is, in imperative form, e.g. `Run tests`. */
  content: string;
  /** Progress of the item: `pending` (not started), `in_progress` (being worked on now) or `completed`. */
  status: "pending" | "in_progress" | "completed";
}

/** The agent's todo checklist changed; carries the whole new list. */
export interface TodosUpdatedEventPayload {
  /** The full checklist, in order. Replaces any list received before; empty when the agent cleared it. */
  todos: TodoItem[];
}

/**
 * The arguments of a tool call, as a JSON object.
 *
 * Each tool defines its own keys; any key is accepted and kept. The
 * common ones are named below; leave out the ones the tool does not
 * use.
 */
export interface ToolCallArgs {
  /** Shell command, for shell tools. */
  command?: string;
  /** File path, for file read/write/edit tools. */
  file_path?: string;
  /** Search query, for search tools. */
  query?: string;
  /** URL, for web-fetch tools. */
  url?: string;
}

/**
 * A tool call has finished.
 *
 * On the wire: `tool_completed`.
 */
export interface ToolCompleted {
  /** For a tool that changed a file: the diff to show, as `[text, style]` pairs, one per line. Null when the tool produced no diff. */
  diff_rows?: Array<[string, string]> | null;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** The tool's full output. */
  full_result?: string;
  /** True when `full_result` contains rich-text markup rather than plain text. */
  has_markup?: boolean;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** True when the tool failed: it raised, or returned text starting with `Error:`. */
  is_error?: boolean;
  /** True when the call never ran: the person rejected it when asked for approval, or nobody could be asked. */
  is_rejected?: boolean;
  /** The id of the run that started this one, for a sub-agent's run; empty for a top-level run. */
  parent_run_id?: string;
  /** The id of the run this event belongs to. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** A short, one-line summary of the result. */
  summary?: string;
  /** Always `tool_completed`: what kind of message this is. */
  type?: "tool_completed";
}

/**
 * A sub-agent's tool call finished — or failed, which is what
 * `is_error` says.
 */
export interface ToolCompletedEvent {
  /** Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level). */
  agent_path: string;
  /** Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card. */
  card_id?: string | null;
  /** True when the tool call failed. */
  is_error?: boolean;
  /** Preview of the tool output, or the error message when `is_error` is true; may be truncated. Empty when none. */
  result?: string;
  /** Name of the tool that was called. */
  tool: string;
  /** Identifier of this tool call; matches the earlier `tool_started` event. Null when the model did not supply one. */
  tool_call_id?: string | null;
  /** Always `tool_completed`: what kind of message this is. */
  type?: "tool_completed";
}

/**
 * A tool call failed.
 *
 * On the wire: `tool_error`.
 */
export interface ToolError {
  /** What went wrong, as a human-readable message. */
  error?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the run that started this one, for a sub-agent's run; empty for a top-level run. */
  parent_run_id?: string;
  /** The id of the run this event belongs to. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `tool_error`: what kind of message this is. */
  type?: "tool_error";
}

/**
 * A tool call has begun.
 *
 * On the wire: `tool_started`.
 */
export interface ToolStarted {
  /** A short, human-readable summary of the call's arguments. */
  args_summary?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** A human-readable name for the tool, for display; empty when there is none. */
  friendly_name?: string;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The id of the run that started this one, for a sub-agent's run; empty for a top-level run. */
  parent_run_id?: string;
  /** The id of the run this event belongs to. */
  run_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The tool's name, as the model called it. */
  tool_name?: string;
  /** Always `tool_started`: what kind of message this is. */
  type?: "tool_started";
}

/** A tool call started: a sub-agent began calling a tool. */
export interface ToolStartedEvent {
  /** Dot-joined names of the agent that emitted the event, from the outermost spawning agent down to the emitter (`root` for the top level). */
  agent_path: string;
  /** Preview of the tool arguments as text (usually JSON, may be truncated). Empty when none. */
  args?: string;
  /** Identifier of the team-progress card this event belongs to. All events of one spawn share it. Null when the event is not tied to a card. */
  card_id?: string | null;
  /** Name of the tool being called. */
  tool: string;
  /** Identifier of this tool call; matches the `tool_completed` event for the same call. Null when the model did not supply one. */
  tool_call_id?: string | null;
  /** Always `tool_started`: what kind of message this is. */
  type?: "tool_started";
}

/**
 * One tool call the agent made, with its result.
 *
 * The history equivalent of the live `tool_started` and
 * `tool_completed` events.
 */
export interface ToolTurn {
  /** The call's arguments, as display text. */
  args?: string;
  /** The tool's result text. */
  content?: string;
  /** When the message was created, in Unix epoch seconds; `0` if unknown. */
  created_at?: number;
  /** Human-readable tool name for display. */
  friendly_name?: string;
  /** `true` when the tool call failed. */
  is_error?: boolean;
  /** `true` when the user rejected the call, so it never ran. */
  is_rejected?: boolean;
  /** Turn kind; always `tool`. */
  role?: "tool";
  /** Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point. */
  run_id?: string;
  /** Internal name of the tool that was called. */
  tool_name?: string;
}

/**
 * Arguments for dropping a run, and every later run, from a
 * session's history.
 */
export interface TruncateHistoryArgs {
  /** Id of the first run to drop: a top-level run, as `get_chat_history` carries it. */
  run_id: string;
  /** Id of the session to act on. */
  session_id: string;
}

/** The outcome of cutting a session's history back to before a given run. */
export interface TruncateHistoryResult {
  /** Why nothing was removed; empty on success. */
  error?: string;
  /** How many runs were removed, the given one included; `0` on failure. */
  removed: number;
}

/** The user's answer to "Trust this folder?". */
export interface TrustDecisionArgs {
  /** `trust`: trust the folder and remember it. `once`: trust it until igni exits. `distrust`: do not trust it, and remember that. */
  decision: "trust" | "distrust" | "once";
}

/**
 * What the person is typing in one client, shared with every other client of the session.
 *
 * Each message carries the whole draft, not a change to it. Send it at
 * a modest rate while the person types.
 *
 * On the wire: `typing`.
 */
export interface Typing {
  /** The id of the client the person is typing in. */
  client_id?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The whole draft so far; empty when it was sent or cleared. */
  text?: string;
  /** Always `typing`: what kind of message this is. */
  type?: "typing";
}

/**
 * A newer igni release that can be installed. When no update is
 * available the call returns `null` instead.
 */
export interface UpdateAvailable {
  /** Always `true`: an update is available. */
  available: boolean;
  /** The version running now. */
  current_version: string;
  /** Where the new version can be downloaded. */
  download_url: string;
  /** The newest released version. */
  latest_version: string;
  /** The name of the package to upgrade. */
  pkg_name: string;
}

/** Arguments for moving an installed plugin to another commit. */
export interface UpdatePluginArgs {
  /** Branch, tag or commit to move to; the remote's default branch when absent. */
  install_ref?: string | null;
  /** Name of the installed plugin. */
  name: string;
}

/** Arguments for uploading a file to attach to a message. */
export interface UploadAttachmentArgs {
  /** The file's bytes, base64-encoded. */
  content_base64: string;
  /** The file's name. It is made safe for the disk; a name clash gets a `-N` suffix. */
  filename: string;
}

/** Where an uploaded attachment was saved. */
export interface UploadAttachmentResult {
  /** Why the upload failed, e.g. invalid base64; empty on success. */
  error?: string;
  /** The stored file's path, or an `attachment:<id>` reference when attachments are kept in shared storage; use it to refer to the file in a message. Empty on error. */
  path: string;
  /** Size of the stored file in bytes; `0` on error. */
  size: number;
}

/**
 * The person sends a chat message, starting a run.
 *
 * A run waiting on an approval ends with it, and its approvals are
 * dropped. That refuses them, so it takes what answering takes: from a
 * program without an approver token it is refused while the session
 * waits, with an `error` and the stream's end, and nothing is dropped.
 *
 * On the wire: `user_message`.
 */
export interface UserMessage {
  /** This client's id, from `welcome`. igni echoes the message to every other client attached to the session (`user_message_received`); the sender recognises its own by this id. Empty is allowed. */
  client_id?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Files attached to the message: their contents, keyed by path. */
  file_contents?: Record<string, string>;
  /** True to discard any interrupted or pending runs of the session first, then start afresh with this message; for retrying after an interruption. */
  force?: boolean;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The message. */
  text?: string;
  /** Always `user_message`: what kind of message this is. */
  type?: "user_message";
}

/**
 * A chat message igni accepted, sent to every client of the session so all show it.
 *
 * The client that sent it can recognise it by `client_id` and skip it.
 *
 * On the wire: `user_message_received`.
 */
export interface UserMessageReceived {
  /** The id of the client that sent it; empty when no client did. */
  client_id?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Set when an extension posted the message (`host.chat.post`): show it as that extension's, not the person's. Empty otherwise. */
  extension_id?: string;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** True when it was sent during a run and is queued for the agent. */
  queued?: boolean;
  /** Set when the extension's service sent the message: that service's client id. `extension_id` is set too. Empty otherwise. */
  service_client_id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** The message. */
  text?: string;
  /** Always `user_message_received`: what kind of message this is. */
  type?: "user_message_received";
}

/** A message the user sent. */
export interface UserTurn {
  /** The text the user sent. */
  content?: string;
  /** When the message was created, in Unix epoch seconds; `0` if unknown. */
  created_at?: number;
  /** Turn kind; always `user`. */
  role?: "user";
  /** Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point. */
  run_id?: string;
}

/**
 * Arguments for reporting that the user used a control in a
 * visualization the agent drew.
 */
export interface VisualizationActionArgs {
  /** The control's action name. */
  action?: string;
  /** Values the visualization attached to the action; omit for none. */
  params?: Record<string, JsonValue> | null;
}

/**
 * The `visualization_action_dispatched` broadcast, so log panels
 * and dev tools can observe component interactions.
 */
export interface VisualizationActionDispatchedEventPayload {
  /** Name of the action the user triggered in the visualization. */
  action: string;
  /** Parameters the visualization attached to the action. */
  params: Record<string, JsonValue>;
}

/**
 * Confirmation that a visualization action was dispatched.
 *
 * Echoes the action and its parameters, e.g. to show "you clicked X"
 * in the conversation.
 */
export interface VisualizationActionResult {
  /** Name of the action. */
  action: string;
  /** `true` when the action was dispatched. */
  ok: boolean;
  /** Parameters attached to the action. */
  params?: Record<string, JsonValue>;
}

/**
 * A visualization card recorded in the session's event log.
 *
 * The card's spec arrives as JSON text, possibly in several partial
 * updates sharing one `spec_id`; the update with `final` set holds
 * the complete spec. `title` and `source` are set only for cards
 * an extension added to the chat.
 */
export interface VisualizationDeltaPayload {
  /** Dot-joined names of the agent that produced the card. Empty when not known. */
  agent_path?: string;
  /** The card this delta belongs to; it is not part of the event's wire shape. */
  card_id?: string | null;
  /** True when `json` holds the complete spec; false for an in-progress update. */
  final?: boolean;
  /** The card's visualization spec as JSON text. Partial (possibly incomplete JSON) until `final` is true. */
  json?: string;
  /** Which draw of the card this is. The first draw is 1. The client sends it back with its verdict, so the verdict names the draw it is about. Null on a partial frame, which is not a draw. */
  revision?: number | null;
  /** Id of the extension that added the card. Empty for cards produced by an agent. */
  source?: string;
  /** Identifier of the card; later updates with the same id replace earlier ones. */
  spec_id?: string;
  /** Card title given by the extension that added it. Empty otherwise. */
  title?: string;
  /** Always `visualization_delta`: what kind of message this is. */
  type?: "visualization_delta";
}

/**
 * A visualization card (chart, diagram, extension view) shown in
 * the chat during a run.
 *
 * Has no `created_at`; use the neighbouring turns for display
 * time.
 */
export interface VisualizationTurn {
  /** Id of the extension that appended the card; empty when the built-in visualizer made it. Show the extension's name. */
  extension_id?: string;
  /** Turn kind; always `visualization`. */
  role?: "visualization";
  /** Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point. */
  run_id?: string;
  /** Position of the card in the session's event log, for ordering within a run. */
  seq?: number;
  /** Name of the agent that produced the visualization. */
  source_agent?: string;
  /** The visualization specification to render, as JSON. Not validated by igni. */
  spec?: Record<string, JsonValue>;
  /** Unique id of this visualization. */
  spec_id?: string;
  /** The card's title, as given by the extension that appended it. */
  title?: string;
}

/**
 * Arguments for reporting what the client drew of a card the agent
 * drew.
 */
export interface VisualizationVerdictArgs {
  /** The elements the client could not draw. */
  failed?: ElementFailureArgs[];
  /** What was wrong with the card's shape. */
  issues?: string[];
  /** Which draw of the card this is; the first draw is 1. */
  revision?: number;
  /** The card the verdict is about. */
  spec_id: string;
  /** How many elements the card has. */
  total?: number;
}

/**
 * Confirmation that a card's verdict was recorded.
 *
 * Echoes the card the verdict is about and what the client drew of
 * it, so the client can show that its word was taken.
 */
export interface VisualizationVerdictResult {
  /** How many elements the client drew. */
  drawn: number;
  /** `true` when the verdict was recorded. */
  ok: boolean;
  /** Which draw of the card this is. */
  revision: number;
  /** The card the verdict is about. */
  spec_id: string;
  /** How many elements the card has. */
  total: number;
}

/** The state of a cloud VM's own credential after it signed in. */
export interface VmCredentialState {
  /** What went wrong; empty when nothing did. */
  message?: string;
  /** `ready`: the VM holds a credential and a token from it. `needs_sign_in`: the person must sign in through the gateway again. `needs_reissue`: an app VM's credential is gone and an organisation admin must re-issue it. `unreachable`: igni server could not be reached; the last token holds until it expires. */
  state: "ready" | "needs_sign_in" | "needs_reissue" | "unreachable";
}

/**
 * The first message igni sends a newly attached client.
 *
 * On the wire: `welcome`.
 */
export interface Welcome {
  /** The id igni gave this client. Send it with your messages; messages igni echoes to every client carry it, so you can skip your own. */
  client_id?: string;
  /** The message's place in its stream, counting from 1; a client drops a message whose (id, event_seq) it has seen. 0 on messages sent to igni. */
  event_seq?: number;
  /** Ties messages together: a reply carries its request's id, and the events a request streams carry it too. Empty when nothing is tied. */
  id?: string;
  /** The session the message is for (sent to igni) or from (sent by igni). Empty: the default session, or none in particular. */
  session_id?: string;
  /** Always `welcome`: what kind of message this is. */
  type?: "welcome";
}

/** One change to one window's model, as listeners are told it. */
export interface WindowChange {
  /** The answer given to the dialog, as JSON; null when it was dismissed. */
  answer?: JsonValue | null;
  /** What happened, for the fields that hold a list or a dialog: `toast_shown`, `toast_dismissed`, `dialog_opened` or `dialog_closed`; empty otherwise. */
  event?: string;
  /** Which of the window's fields changed. */
  field: string;
  /** The toast or the dialog the event is about. */
  item?: WindowItem | null;
  /** The window's revision after the change. */
  rev: number;
  /** The writer's own name for the write, echoed so the window that wrote it knows its own write; empty for an extension's. */
  token?: string;
  /** The field's new value, as JSON. */
  value?: JsonValue | null;
  /** The window whose model changed. */
  window: string;
}

/**
 * Arguments for a window reading or writing its own state (its
 * window model).
 */
export interface WindowModelArgs {
  /** The window's connection id, for transports without connections (a terminal socket, an in-process client). Ignored over a WebSocket: the request's own connection is used. */
  connection_id?: string;
  /** The dialog an `answer_dialog` closes. */
  dialog_id?: string;
  /** The model field a `write` sets. */
  field?: string;
  /** What kind of window this is, recorded when it opens. */
  kind?: string;
  /** What to do. `hydrate`: read the whole model, and report the window as open. `write`: set `field` to `value`. `toast`: show the toast `value`. `dismiss_toast`: remove the toast whose id is `value`. `open_dialog`: show igni's own dialog, `value` being its spec. `answer_dialog`: close dialog `dialog_id` with the answer `value` (`null`: dismissed). */
  op: "hydrate" | "write" | "toast" | "dismiss_toast" | "open_dialog" | "answer_dialog";
  /** The writer's own name for this change, echoed on `window_model_changed`. */
  token?: string;
  /** What the op writes, shows or answers with; its shape depends on the op and field. */
  value?: JsonValue;
  /** The window's id, chosen by the window and stable across its reloads. */
  window: string;
}

/** A window's whole model: every field, as a window hydrates from it. */
export interface WindowModelState {
  /** The window's composer. */
  composer?: Composer;
  /** The dialog on screen. */
  dialog?: Dialog | null;
  /** Whether this window has the focus. */
  focused?: boolean;
  /** The panel open over the chat. */
  panel?: Panel | null;
  /** The file being previewed. */
  preview?: Preview | null;
  /** The folder the window shows. */
  project_dir?: string;
  /** The window's page stack. */
  route?: Page[];
  /** Where the transcript is scrolled. */
  scroll?: Scroll;
  /** What is selected. */
  selection?: Selection;
  /** The session the window shows. */
  session?: string;
  /** The window's sidebar. */
  sidebar?: Sidebar;
  /** The toasts on screen. */
  toasts?: Toast[];
}

/** Arguments for cancelling a running workflow. */
export interface WorkflowCancelRequest {
  /** Id of the workflow run to cancel. */
  workflow_run_id: string;
}

/** Result of cancelling a workflow run. */
export interface WorkflowCancelResponse {
  /** `true` when the run was stopped. `false` when no such run is active: it already finished, was already cancelled, or the id is unknown. */
  cancelled: boolean;
  /** Id of the run the request named. */
  workflow_run_id: string;
}

/**
 * One progress event from a running workflow, as pushed on the
 * `workflow_event` channel and kept in the session log.
 */
export interface WorkflowEventRecord {
  /** Name of the workflow. */
  name: string;
  /** Event details; keys depend on `type`. For the final event added by igni: `status` (`completed`, `failed` or `cancelled`), `exit_code` and `synthetic`. */
  payload: Record<string, JsonValue>;
  /** Order of the event within its run, from `0`. `-1` for the final event igni adds itself when the workflow process exits without reporting an end. */
  seq: number;
  /** When the event happened, in Unix epoch milliseconds. */
  ts: number;
  /** Event kind, e.g. `workflow_meta`, `phase_*`, `agent_*`, `parallel_*`, `pipeline_*`, `log`, and the final `workflow_completed` or `workflow_failed`. */
  type: string;
  /** Id of the workflow run the event belongs to. */
  workflow_run_id: string;
}

/** A workflow script available to run in this project. */
export interface WorkflowListItem {
  /** What the workflow does; may be empty. */
  description?: string;
  /** The workflow's name; pass it to run the workflow. */
  name: string;
  /** Where the workflow file is: relative to the project root, or absolute for a workflow outside the project (e.g. in the user's home). */
  path: string;
  /** The workflow's steps, in order. */
  phases: WorkflowPhase[];
  /** When the workflow is the right choice; may be empty. */
  whenToUse?: string;
}

/**
 * `LIST_WORKFLOWS` params: none. Whatever the caller sends
 * (`session_id` and the like) is ignored.
 */
export interface WorkflowListRequest {
}

/** One step of a workflow, as the workflow describes itself. */
export interface WorkflowPhase {
  /** Longer explanation of what the phase does; may be empty. */
  detail?: string;
  /** Short name of the phase. */
  title: string;
}

/** Arguments for starting a workflow. */
export interface WorkflowRunRequest {
  /** The workflow's own input, passed to it unchanged. Each workflow defines the keys it reads; omit for none. */
  args?: Record<string, JsonValue>;
  /** Name of the workflow to run. */
  name: string;
}

/**
 * The workflow run that was started.
 *
 * Returned as soon as the run starts; its progress then arrives as
 * `workflow_event` pushes carrying the same `workflow_run_id`.
 */
export interface WorkflowRunResponse {
  /** Name of the workflow that was started. */
  name: string;
  /** Id of the new run; use it to match events and to cancel the run. */
  workflow_run_id: string;
}

/**
 * A workflow run's card, as it was drawn during the run.
 *
 * `events` are the run's `workflow_event` records in the order
 * they arrived — the very envelopes the `workflow_event` push
 * carried — so the card can be drawn again from the tape, exactly as
 * the live pushes drew it. Placed where the run happened, among the
 * chat turns around it.
 *
 * `run_id` is empty: a workflow's agent calls are kept in their own
 * session, so there is no agent run to point at. Has no
 * `created_at`. Shown only: none of it is in the model's context.
 */
export interface WorkflowTurn {
  /** The run's `workflow_event` records, oldest first. */
  events?: Array<Record<string, JsonValue>>;
  /** Name of the workflow that was run. */
  name?: string;
  /** Turn kind; always `workflow`. */
  role?: "workflow";
  /** Id of the agent run this turn belongs to. Pass it to `truncate_history` to edit or delete from this point. */
  run_id?: string;
  /** Position of the run's first event in the session's event log. */
  seq?: number;
  /** Id of the workflow run the card is for. */
  workflow_run_id?: string;
}

/**
 * Whether the project folder is trusted, and why.
 *
 * Until a folder is trusted, its own tools, hooks, plugins and
 * configuration are not loaded.
 */
export interface WorkspaceTrustStatus {
  /** `false` when the organisation's policy forbids trusting this folder. */
  can_trust: boolean;
  /** Short summary of what an untrusted folder does not get, for showing to the user. */
  gated?: string;
  /** The folder's full canonical path. */
  path: string;
  /** The organisation's trust policy: `ask` (the user decides), `trusted_remotes` (only folders whose git remote is approved) or `never` (no folder is trusted). */
  policy_mode: string;
  /** Human-readable explanation of the current state. */
  reason: string;
  /** The folder's git remote URL, with any credentials removed; `null` if none. */
  remote?: string | null;
  /** How the state was reached: `policy` (organisation policy), `run` (trusted once, until igni exits), `store` (the user's saved answer) or `unset` (no answer yet). */
  source?: string;
  /** `trusted`, `untrusted`, or `ask` when nobody has decided yet (the folder is treated as untrusted meanwhile). */
  state: "trusted" | "untrusted" | "ask";
}

/** The answer to `write`: the window's revision after it, and whether the value changed. */
export interface Written {
  /** False when the field already held the value: nothing changed and no change was sent. */
  changed?: boolean;
  /** Always `write`: the request this answers. */
  op?: "write";
  /** The window's revision after the write. */
  rev: number;
}

/**
 * A background process finished, as the agent is told.
 *
 * On the wire: `push_notification` on the channel `background_process_done`.
 */
export interface BackgroundProcessDonePush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "background_process_done";
  payload: BackgroundProcessDonePayload;
}

/**
 * An edit tool wrote a file.
 *
 * On the wire: `push_notification` on the channel `file_edited`.
 */
export interface FileEditedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "file_edited";
  payload: FileEditedPayload;
}

/**
 * A host-model signal for one extension's pages.
 *
 * On the wire: `push_notification` on the channel `host_signal`.
 */
export interface HostSignalPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "host_signal";
  payload: HostSignal;
}

/**
 * A web fetch is about to be retried.
 *
 * On the wire: `push_notification` on the channel `http_retry_attempt`.
 */
export interface HttpRetryAttemptPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "http_retry_attempt";
  payload: HttpRetryAttemptEventPayload;
}

/**
 * A web fetch succeeded after retrying.
 *
 * On the wire: `push_notification` on the channel `http_retry_succeeded`.
 */
export interface HttpRetrySucceededPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "http_retry_succeeded";
  payload: HttpRetrySucceededEventPayload;
}

/**
 * How a sign-in started by `login` ended.
 *
 * On the wire: `push_notification` on the channel `login_result`.
 */
export interface LoginResultPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "login_result";
  payload: LoginResultPayload;
}

/**
 * What a sign-in started by `login` is doing now.
 *
 * On the wire: `push_notification` on the channel `login_status`.
 */
export interface LoginStatusPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "login_status";
  payload: LoginStatusPayload;
}

/**
 * The person's unread notification counts moved.
 *
 * On the wire: `push_notification` on the channel `notifications_changed`.
 */
export interface NotificationsChangedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "notifications_changed";
  payload: NotificationsChanged;
}

/**
 * An extension asked a window to open a link in the browser.
 *
 * On the wire: `push_notification` on the channel `open_external`.
 */
export interface OpenExternalPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "open_external";
  payload: ExternalOpen;
}

/**
 * A sub-agent's progress (a tool call, its start, pause, end or error, a task) or a view the agent or an extension drew, told apart by `type`.
 *
 * On the wire: `push_notification` on the channel `orchestrate_event`.
 */
export interface OrchestrateEventPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "orchestrate_event";
  payload: OrchestrateEventPayload;
}

/**
 * The session's output style changed.
 *
 * On the wire: `push_notification` on the channel `output_style_changed`.
 */
export interface OutputStyleChangedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "output_style_changed";
  payload: OutputStyleChangedEventPayload;
}

/**
 * The session's permission mode changed: the switch itself (`mode` and `previous`), or the plan tool's note that the agent entered plan mode (`mode`, `source`, `reason`).
 *
 * On the wire: `push_notification` on the channel `permission_mode_changed`.
 */
export interface PermissionModeChangedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "permission_mode_changed";
  payload: PermissionModeChangedPayload;
}

/**
 * A submitted plan was approved or dismissed.
 *
 * On the wire: `push_notification` on the channel `plan_decided`.
 */
export interface PlanDecidedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "plan_decided";
  payload: PlanDecidedEventPayload;
}

/**
 * The agent submitted a plan for the person to decide on.
 *
 * On the wire: `push_notification` on the channel `plan_submitted`.
 */
export interface PlanSubmittedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "plan_submitted";
  payload: PlanSubmittedEventPayload;
}

/**
 * A background process exited.
 *
 * On the wire: `push_notification` on the channel `process_exited`.
 */
export interface ProcessExitedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "process_exited";
  payload: ProcessExitedPayload;
}

/**
 * A background process printed a line.
 *
 * On the wire: `push_notification` on the channel `process_line`.
 */
export interface ProcessLinePush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "process_line";
  payload: ProcessLinePayload;
}

/**
 * A background process started.
 *
 * On the wire: `push_notification` on the channel `process_started`.
 */
export interface ProcessStartedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "process_started";
  payload: ProcessStartedPayload;
}

/**
 * A scheduled task finished: its result, or why it failed.
 *
 * On the wire: `push_notification` on the channel `scheduler_completed`.
 */
export interface SchedulerCompletedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "scheduler_completed";
  payload: SchedulerCompletedPayload;
}

/**
 * A scheduled task started running.
 *
 * On the wire: `push_notification` on the channel `scheduler_started`.
 */
export interface SchedulerStartedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "scheduler_started";
  payload: SchedulerStartedPayload;
}

/**
 * A session was given a name.
 *
 * On the wire: `push_notification` on the channel `session_named`.
 */
export interface SessionNamedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "session_named";
  payload: SessionNamedPayload;
}

/**
 * Which chats are running, waiting on the person, or finished unseen moved.
 *
 * On the wire: `push_notification` on the channel `session_states_changed`.
 */
export interface SessionStatesChangedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "session_states_changed";
  payload: SessionStates;
}

/**
 * The agent's to-do list, whole, after it changed.
 *
 * On the wire: `push_notification` on the channel `todos_updated`.
 */
export interface TodosUpdatedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "todos_updated";
  payload: TodosUpdatedEventPayload;
}

/**
 * The person used a control in a view.
 *
 * On the wire: `push_notification` on the channel `visualization_action_dispatched`.
 */
export interface VisualizationActionDispatchedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "visualization_action_dispatched";
  payload: VisualizationActionDispatchedEventPayload;
}

/**
 * A cloud VM's own credential changed state; a client that connects later is sent the state last pushed, to it alone.
 *
 * On the wire: `push_notification` on the channel `vm_credential`.
 */
export interface VmCredentialPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "vm_credential";
  payload: VmCredentialState;
}

/**
 * A window's model changed; the window it names applies it.
 *
 * On the wire: `push_notification` on the channel `window_model_changed`.
 */
export interface WindowModelChangedPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "window_model_changed";
  payload: WindowChange;
}

/**
 * One step of a running workflow, keyed by its run id.
 *
 * On the wire: `push_notification` on the channel `workflow_event`.
 */
export interface WorkflowEventPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "workflow_event";
  payload: WorkflowEventRecord;
}

/**
 * A folder's trust status: windows showing the trust dialog for it close it, or open it while `state` is `ask`.
 *
 * On the wire: `push_notification` on the channel `workspace_trust_required`.
 */
export interface WorkspaceTrustRequiredPush extends Omit<PushNotification, "channel" | "payload"> {
  channel: "workspace_trust_required";
  payload: WorkspaceTrustStatus;
}

/** One of 9 kinds, told apart by `role`. */
export type ChatTurn = UserTurn | AssistantTurn | ThinkingTurn | ToolTurn | PlanTurn | StatsTurn | VisualizationTurn | TeamTurn | WorkflowTurn;

/** One of 4 kinds, told apart by `source`. */
export type SlashCommand = BuiltinSlashCommand | MarkdownSlashCommand | SkillSlashCommand | ExtensionSlashCommand;

/** One of 2 kinds, told apart by `type`. */
export type WindowItem = Toast | Dialog;

/** One of 6 kinds, told apart by `op`. */
export type WindowModelResult = Hydrated | Written | ToastAdded | Revised | DialogShown | DialogAnswered;

/** Every message igni may send, by its `type` discriminant. */
export type ServerEvent = CommandResult | ContentDelta | ErrorMessage | InfoMessage | ModelCompleted | PushNotification | ReasoningStarted | Requirement | RequirementDetails | RequirementResolved | RpcResponse | RunCompleted | RunError | RunPaused | RunStarted | SchedulerEvent | SessionCleared | SessionListResult | StatusUpdate | StreamEnd | StreamingDone | TaskCreated | TaskIteration | TaskStateUpdated | TaskUpdated | ToolCompleted | ToolError | ToolStarted | Typing | UserMessageReceived | Welcome;

/** Every wire `type` igni sends that this client knows. */
export const EVENT_TYPES: ReadonlySet<string> = new Set([
  "command_result",
  "content_delta",
  "error",
  "hitl_request",
  "info",
  "model_completed",
  "push_notification",
  "reasoning_started",
  "requirement_details",
  "requirement_resolved",
  "rpc_response",
  "run_completed",
  "run_error",
  "run_paused",
  "run_started",
  "scheduler_event",
  "session_cleared",
  "session_list_result",
  "status_update",
  "stream_end",
  "streaming_done",
  "task_created",
  "task_iteration",
  "task_state_updated",
  "task_updated",
  "tool_completed",
  "tool_error",
  "tool_started",
  "typing",
  "user_message_received",
  "welcome",
]);

/** Every wire `type` a client sends. */
export const FRAME_TYPES: ReadonlySet<string> = new Set([
  "cancel",
  "cancel_login",
  "command",
  "hitl_decision",
  "hitl_response",
  "hitl_response_batch",
  "mcp_toggle",
  "model_switch",
  "queue_message",
  "rpc_request",
  "session_list",
  "session_switch",
  "shutdown",
  "typing",
  "user_message",
]);

/** Every push channel the contract types. */
export const PUSH_CHANNELS: ReadonlySet<string> = new Set([
  "background_process_done",
  "file_edited",
  "host_signal",
  "http_retry_attempt",
  "http_retry_succeeded",
  "login_result",
  "login_status",
  "notifications_changed",
  "open_external",
  "orchestrate_event",
  "output_style_changed",
  "permission_mode_changed",
  "plan_decided",
  "plan_submitted",
  "process_exited",
  "process_line",
  "process_started",
  "scheduler_completed",
  "scheduler_started",
  "session_named",
  "session_states_changed",
  "todos_updated",
  "visualization_action_dispatched",
  "vm_credential",
  "window_model_changed",
  "workflow_event",
  "workspace_trust_required",
]);

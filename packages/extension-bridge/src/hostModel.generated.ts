// GENERATED from the igni host schema 1.13.0 by igni-sdk's tools/host_codegen.py — do not edit. Run `make host-sdks` after refreshing contracts/host-schema.json.
//
// `bridge.host` as an extension's page sees it. Read
// `docs/HOST_OBJECT_MODEL.md` in igni for what each object is.

import { HostObject, Property, Signal, type HostLink, type JsonValue } from "./hostModel.js";

/**
 * The version of igni's host schema this file was generated from.
 *
 * It moves when igni's host model moves. The bridge carries it on the
 * wire, so a host and a page can say which model they are speaking.
 */
export const SCHEMA_VERSION = "1.13.0";

/** One change anywhere in the model, as `host.changed` reports it. */
export interface Change {
  /** The member that changed, `object.member`. */
  path: string;
  /** Its new value. */
  value: JsonValue;
  /** The window, for a per-window member. */
  window?: string | null;
}

/** How igni presents the conversation. */
export interface Display {
  /** Whether routing detail is shown. */
  verbose: boolean;
  /** The active output style; empty for none. */
  output_style: string;
  /** The styles that can be chosen. */
  output_styles: string[];
  /** `auto`, `light` or `dark`. */
  color_theme: string;
  show_reasoning: boolean;
  show_tool_calls: boolean;
}

/** Whether igni can reach a model and its server. */
export interface Connection {
  cloud_connected: boolean;
  /** False when runs would reach no model. */
  model_configured: boolean;
}

/** A newer igni than the one running. */
export interface UpdateInfo {
  current_version: string;
  latest_version: string;
  download_url: string;
}

/** One key of an extension's own state. */
export interface StateChange {
  key: string;
  /** `None` when the key was deleted. */
  value?: string | null;
}

/** One igni window: a desktop window or a browser tab. */
export interface WindowInfo {
  /** Stable across reloads of the same window. */
  id: string;
  /** `tauri` or `web`. */
  kind: string;
  connected: boolean;
  /** Whether the person is using this window: it has focus. */
  focused: boolean;
  /** The session it shows. */
  session_id?: string | null;
  project_dir?: string | null;
}

/** One level of a window's page stack. */
export interface Page {
  /** `plugins`, `extensions`, an extension's page kind, … */
  kind: string;
  label: string;
  params?: Record<string, string>;
}

/** Where a window is: its page stack, empty for the chat. */
export interface Route {
  window: string;
  pages: Page[];
}

/** The panel open over a window's chat: `notifications`, `search` (find in the conversation), `login` or `dir-picker`. One at a time. */
export interface Panel {
  kind: string;
  params?: Record<string, JsonValue>;
}

/** A window's panel opened or closed. */
export interface PanelChange {
  window: string;
  panel?: Panel | null;
}

/** A window's sidebar. */
export interface Sidebar {
  open: boolean;
  /** Its width in pixels; `None` for igni's own. */
  width?: number | null;
  /** The part of it in view: `links` (the destinations) or `sessions`. */
  section?: string | null;
}

/** A window's sidebar changed. */
export interface SidebarChange {
  window: string;
  sidebar: Sidebar;
}

/** The file previewed in a window. */
export interface Preview {
  path: string;
}

/** A window's preview changed. */
export interface PreviewChange {
  window: string;
  preview?: Preview | null;
}

/** What is selected in a window. Each part is independent; `None` for nothing. */
export interface SelectionState {
  /** The highlighted message, by the run it belongs to (`run_id` in `chat.messages` and the run signals). */
  message_id?: string | null;
  /** Text selected in the transcript. */
  text?: string | null;
  /** The file last picked: a file pill, a reference. */
  file?: string | null;
}

/** A window's selection changed. */
export interface SelectionChange {
  window: string;
  selection: SelectionState;
}

/** A window's composer. */
export interface Composer {
  /** The draft, without the mode's `/` or `$`. */
  text: string;
  /** The files the draft refers to (`@path`), in order. */
  attachments?: string[];
  /** `chat`, `command` (a slash command) or `shell` (a `$` line). */
  mode?: string | null;
}

/** A window's draft changed. */
export interface ComposerChange {
  window: string;
  composer: Composer;
}

/** A transient message on screen. */
export interface Toast {
  /** Always `toast`: what this is. */
  type: string;
  id: string;
  /** Its first line. */
  text: string;
  /** `info`, `success`, `warning` or `error`. */
  kind: string;
  /** A second line. */
  body?: string | null;
  /** Where clicking it goes. */
  target?: Page | null;
  /** The extension that showed it; `None` for igni. */
  source?: string | null;
}

/** A toast appeared or went away. */
export interface ToastChange {
  window: string;
  toast: Toast;
}

/** A dialog on screen: igni's own (`spec.kind` is `update`) or an extension's (`show_dialog`). One at a time; a new one replaces the last, which closes unanswered. */
export interface Dialog {
  /** Always `dialog`: what this is. */
  type: string;
  id: string;
  spec: JsonValue;
  /** The extension that asked; `None` for igni. */
  source?: string | null;
}

/** A dialog opened or closed. */
export interface DialogChange {
  window: string;
  dialog: Dialog;
  /** What the person answered, when it closed: `{button, value}`; `None` when it was dismissed or replaced. */
  answer?: JsonValue;
}

/** Where a window's transcript is scrolled to. */
export interface Scroll {
  /** The message at the top of the view, by its run; `None` for none. */
  message_id?: string | null;
  /** Following the newest message. */
  at_bottom: boolean;
  /** The window, in a signal. */
  window?: string | null;
}

/** One session, as the session list shows it. */
export interface SessionInfo {
  session_id: string;
  name: string;
  created_at: number;
  updated_at: number;
  run_count: number;
  summary: string;
  agent_name: string;
}

/** A window moved to another session. */
export interface SessionChange {
  session_id: string;
  window?: string | null;
}

/** The session list, as it was just read. */
export interface SessionList {
  sessions: SessionInfo[];
}

/** `/clear`: a session carries on under a new id. */
export interface SessionCleared {
  session_id: string;
  new_session_id: string;
  summary: string;
}

/** A session was given its name. */
export interface SessionNamed {
  session_id: string;
  name: string;
}

/** A session bound, and the folder it works in. */
export interface SessionAttached {
  session_id: string;
  project_dir: string;
}

/** A message posted in a chat. */
export interface ChatMessage {
  session_id: string;
  text: string;
  /** For the next turn rather than now. */
  queued: boolean;
  /** The extension that posted it, or whose service sent it; `None` for the person. */
  from_extension?: string | null;
  /** The client id of the service that sent it, when the extension's service did (a message item, posted as sent); `None` for a post an extension made itself and for the person's. */
  from_service?: string | null;
}

/** Turns were removed from a session's history. */
export interface HistoryChange {
  session_id: string;
  /** `truncated` or `discarded`. */
  what: string;
  /** The run removed from, or the message discarded. */
  run_id: string;
}

/** A piece of the agent's answer as it streams. */
export interface ContentDelta {
  session_id: string;
  text: string;
  thinking: boolean;
}

/** Which run. */
export interface RunRef {
  session_id: string;
  run_id: string;
  /** Set for a sub-agent's run. */
  parent_run_id: string;
}

/** A run started. */
export interface RunStart {
  session_id: string;
  run_id: string;
  parent_run_id: string;
  agent_name: string;
  model: string;
}

/** A finished run. */
export interface Run {
  session_id: string;
  run_id: string;
  parent_run_id: string;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  /** Seconds. */
  duration: number;
  /** Files the run edited, relative to the project — only those within the extension's workspace grant, and none without one. */
  changed_files: string[];
}

/** A run stopped with an error. */
export interface RunFailure {
  session_id: string;
  error: string;
}

/** The agent asking to act. */
export interface Approval {
  requirement_id: string;
  session_id: string;
  tool_name: string;
  friendly_name: string;
  tool_args: JsonValue;
  details: string;
  /** Which sub-agent is asking, outermost first. */
  agent_path: string[];
}

/** A run waiting on approvals. */
export interface RunPause {
  session_id: string;
  run_id: string;
  requirements: Approval[];
}

/** An approval was answered, by anyone. */
export interface ApprovalResolved {
  session_id: string;
  requirement_id: string;
}

/** An approval began or stopped waiting on a person — however it ended: answered in a window or through the API, after a restart, or dropped with its run. */
export interface ApprovalChange {
  session_id: string;
  requirement_id: string;
  run_id: string;
  /** `waiting` or `resolved`. */
  state: string;
  /** `main` (the main agent) or `sub_agent`. */
  origin: string;
  /** The tool asked about; empty when resolved. */
  tool_name: string;
}

/** One session's share of `Activity`. */
export interface SessionActivity {
  session_id: string;
  /** `idle`, `waiting` or `running`. */
  state: string;
  waiting_approvals: number;
}

/** Whether igni is doing anything. A run waiting only on a person — on an approval, its own or a sub-agent's — is `waiting`, not `running`: nothing happens until the decision, so the process may be suspended and the decision wakes it. */
export interface Activity {
  /** `idle`, `waiting` or `running`. */
  state: string;
  /** Nothing is running and nothing is busy. */
  suspendable: boolean;
  waiting_approvals: number;
  sessions: SessionActivity[];
  /** What holds igni busy outside a run's turn: calls out, scheduled tasks, processes, extensions that said they are working (`self.busy`). */
  busy: BusyLease[];
  /** When something is next due while nothing runs (ISO 8601, UTC): when a suspended igni should be woken. */
  wake_at: string | null;
}

/** One thing igni is busy with. A lease with `expires_at` stops counting then, whether or not it was let go. */
export interface BusyLease {
  id: string;
  /** `post_run`, `model_call`, `http_call`, `mcp_call`, `extension_call`, `scheduled_task`, `process`, `monitor`, `extension` or `background`. */
  kind: string;
  /** Who holds it: an extension id, a server, a task. */
  holder: string;
  reason: string;
  /** ISO 8601. */
  since: string;
  /** ISO 8601; `None` until let go. */
  expires_at: string | null;
}

/** The reason for an approval, arriving after it. */
export interface ApprovalDetails {
  session_id: string;
  requirement_id: string;
  details: string;
}

/** One answer to one approval. */
export interface ApprovalAnswer {
  requirement_id: string;
  /** `confirm` or `reject`. */
  action: string;
  /** `once`, `always` or `similar`; empty with `reject`. */
  choice?: string;
}

/** The agent started calling a tool. */
export interface ToolCall {
  session_id: string;
  run_id: string;
  parent_run_id: string;
  tool_name: string;
  friendly_name: string;
  args_summary: string;
}

/** A tool call finished. */
export interface ToolResult {
  session_id: string;
  run_id: string;
  parent_run_id: string;
  summary: string;
  is_error: boolean;
  is_rejected: boolean;
}

/** A tool call failed. */
export interface ToolFailure {
  session_id: string;
  run_id: string;
  parent_run_id: string;
  error: string;
}

/** One model call's tokens. */
export interface ModelUsage {
  session_id: string;
  run_id: string;
  parent_run_id: string;
  input_tokens: number;
  output_tokens: number;
}

/** Someone's draft in a session, live. */
export interface Typing {
  session_id: string;
  text: string;
  window?: string | null;
}

/** A session's status line. */
export interface Status {
  session_id: string;
  model: string;
  model_configured: boolean;
  permission_mode: string;
  input_tokens: number;
  output_tokens: number;
  context_tokens: number;
  max_context: number;
}

/** An info or error line in a session. */
export interface Notice {
  session_id: string;
  text: string;
}

/** How full the context is, and with what. */
export interface ContextUsage {
  tokens: number;
  max: number;
  breakdown: JsonValue;
}

/** The agent wrote a file. */
export interface FileEdited {
  session_id: string;
  /** Relative to the project; only within the workspace grant. */
  path: string;
}

/** Progress of a sub-agent or a team, as the transcript shows it. */
export interface AgentEvent {
  session_id: string;
  kind: string;
  payload: JsonValue;
}

/** A network call being retried, and whether it recovered. */
export interface Retry {
  session_id: string;
  /** `attempt` or `succeeded`. */
  kind: string;
  payload: JsonValue;
}

/** A json-render block in the transcript. */
export interface View {
  view_id: string;
  session_id: string;
  title: string;
  /** A json-render spec: `{root, elements}`. */
  spec: JsonValue;
  /** `visualizer`, or the extension that appended it. */
  source: string;
}

/** The person used a control inside a view. */
export interface ViewAction {
  session_id: string;
  action: string;
  params: JsonValue;
}

/** The plan the agent proposed in plan mode. */
export interface Plan {
  latest: string;
  history: string[];
  /** The todo list the plan carries. */
  tasks: TodoItem[];
  /** `pending`, or empty when there is none. */
  state: string;
}

/** A plan was submitted or decided. */
export interface PlanChange {
  session_id: string;
  /** `submitted` or `decided`. */
  kind: string;
  payload: JsonValue;
}

/** A sub-agent task created or updated. */
export interface TaskEvent {
  session_id: string;
  task_id: string;
  title: string;
  assignee: string;
  status: string;
}

/** A task loop's iteration count. */
export interface TaskIteration {
  session_id: string;
  iteration: number;
  max_iterations: number;
}

/** Every task, as it now stands. */
export interface TaskSnapshot {
  session_id: string;
  tasks: JsonValue[];
}

/** The agent's todo list. */
export interface Todos {
  session_id: string;
  todos: TodoItem[];
}

/** `/loop`, as it stands. */
export interface LoopStatus {
  active: boolean;
  paused: boolean;
  prompt: string;
  iteration_index: number;
  iterations_remaining: number;
  cap_explicit: boolean;
  /** How many iterations were announced, when it is known. */
  announced_total: number | null;
}

/** What a slash command answered. */
export interface CommandOutcome {
  kind: string;
  content: string;
  display_content: string;
}

/** Something in a collection changed; read it again. */
export interface CollectionChange {
  /** What happened: `connected`, `installed`, `event`, … */
  what: string;
  /** Which item, when there is one. */
  name?: string | null;
  /** The host's report of it. */
  payload?: JsonValue;
}

/** A workflow started. */
export interface WorkflowRun {
  workflow_run_id: string;
  name: string;
}

/** A scheduled task started, finished or changed. */
export interface SchedulerEvent {
  kind: string;
  task_id: string;
  description: string;
  result: string;
}

/** A background shell started, printed, or exited. */
export interface ProcessEvent {
  /** `started`, `line`, `exited` or `done`. */
  kind: string;
  payload: JsonValue;
}

/** The project's git HEAD. */
export interface Head {
  commit_sha: string;
  branch: string;
}

/** Files git sees as changed, within the extension's workspace grant. */
export interface FilesChanged {
  paths: string[];
  /** The list was capped: rescan rather than trust it. */
  truncated: boolean;
}

/** The model in use changed. */
export interface ModelChange {
  current: string;
}

/** An installed extension. */
export interface ExtensionInfo {
  id: string;
  name: string;
  version: string;
  /** `PREPARING`, `READY`, `FAILED` or `DISABLED`. */
  state: string;
  /** Why it is not READY, and what to do. */
  reason: string;
  /** Its home on the web — its service's URL, which is the service's `client_uri` — when one is known. */
  web_url?: string | null;
  /** What it does not get: a collision with an extension higher in the super admin's priority order (the reason begins `lower priority than <extension>`), or an override whose text lacks the sections its manifest declares. */
  switched_off: Withheld[];
  /** Its prompt edits that land nowhere: another extension overrides that prompt, and its override has no section the edit names. */
  dropped: Withheld[];
  /** Why it is faulty — its calls timed out or crashed three times in a row, so igni restarted it and does not wait on its hooks — or empty while it answers. The first answer after the restart clears it. */
  faulty: string;
}

/** One thing an extension declared and does not get, and why. */
export interface Withheld {
  /** `prompt:main`, `prompt:main#workflow`, `prompt:agent:explorer+notes`, `command:/review`, `anchor:NAME`. */
  claim: string;
  reason: string;
}

/** An extension's health moved. */
export interface ExtensionStateChange {
  extension_id: string;
  state: string;
  reason: string;
}

/** The session's permission mode changed. */
export interface PermissionModeChange {
  mode: string;
  /** The mode before this one; `None` when the push named none. */
  previous?: string | null;
}

/** Who is signed in to igni, without any credential. */
export interface Account {
  signed_in: boolean;
  email: string;
  name: string;
  org: string;
}

/** Where opening a notification goes: one of an extension's pages. */
export interface NotificationTarget {
  page: string;
  params?: Record<string, string>;
}

/** One notification, from igni server or from an extension on this machine. */
export interface NotificationEntry {
  id: string;
  /** `server` or `local`. */
  origin: string;
  /** The extension it belongs to. */
  source: string;
  kind: string;
  title: string;
  body: string;
  actor: string;
  target?: NotificationTarget | null;
  /** ISO 8601. */
  created_at?: string | null;
  read: boolean;
}

/** Unread notifications, in all and per extension. */
export interface NotificationCounts {
  unread: number;
  by_source: Record<string, number>;
}

/** Something to tell the person at this machine. It never leaves it. */
export interface LocalNotification {
  /** The extension's word for what happened. */
  kind: string;
  title: string;
  /** One line. */
  body?: string;
  /** One of this extension's pages. */
  target: NotificationTarget;
  /** The same event is shown once, however often it is sent. */
  event_key: string;
}

/** An extension's settings, as now configured. */
export interface SettingsChange {
  values: Record<string, JsonValue>;
}

/** One typed question about a context. It quotes the context's fields by name in backticks, as in: Is `diff` only a refactor? */
export interface DecisionQuestion {
  /** Its name in the answers: a lowercase name. */
  id: string;
  /** `choice` (one of `options`), `score` (one of `levels`, lowest first) or `noul` (yes or no — Laya's name for it). */
  kind: string;
  /** The question, up to 500 characters. */
  question: string;
  /** `choice` only: 2–20 labels, each to what it means (empty when the label says it). */
  options?: Record<string, string> | null;
  /** `score` only: 2–10 level labels, lowest first. */
  levels?: string[] | null;
}

/** One question's answer, with the probabilities it came from. */
export interface DecisionAnswer {
  kind: string;
  /** The option chosen, the level reached, or `yes` / `no`. */
  answer: string;
  /** The probability of that answer. */
  confidence: number;
  /** Every option's, level's, or `yes` and `no`'s probability. */
  probabilities: Record<string, number>;
  /** `score` only: the expected level, 0 the lowest. */
  score?: number | null;
}

/** Every question's answer about one context. */
export interface Decision {
  /** By question id. */
  answers: Record<string, DecisionAnswer>;
  /** The Laya checkpoint that answered: `english` or `multilingual`. */
  model: string;
}

/** Every model igni knows: the default, the ceiling, and the rows. */
export interface ModelRegistry {
  /** The model used unless another is chosen. */
  default: string;
  /** The largest context window any model has. */
  max_context_window: number;
  /** The rows, by model id. */
  registry: Record<string, ModelEntry>;
}

/** One model in the registry — and never its credential: only whether it has a key. */
export interface ModelEntry {
  model_id: string;
  provider: string;
  /** The endpoint, when the provider names one. */
  url: string | null;
  /** Whether the entry says where its key comes from. Never the key, never the environment variable, never the command. */
  has_api_key: boolean;
  temperature: number | null;
  max_tokens: number | null;
  /** Seconds before a request to it is given up on. */
  timeout: number;
  /** Whether it reads images. */
  vision: boolean;
  context_window: number | null;
  /** How it is asked to think. */
  thinking: Record<string, JsonValue> | null;
  effort: string | null;
  prompt_caching: boolean;
  /** Where the entry came from: `cloud` or the local configuration. */
  source: string;
}

/** One MCP server: its name, and whether it is connected. */
export interface McpServer {
  name: string;
  connected: boolean;
}

/** One MCP server and what it carries. */
export interface McpServerDetails {
  name: string;
  connected: boolean;
  transport: string;
  /** The tools it offers. */
  tool_names: string[];
  /** What each tool says it does. */
  tool_descriptions: Record<string, string>;
  /** The tools withheld from the agent. */
  tools_disabled: string[];
  /** The resources it offers. */
  resources: McpResource[];
  /** The prompts it offers. */
  prompts: McpPrompt[];
  /** Why it is not working, when it is not. */
  error: string;
  /** Whether the group's policy forbade it. */
  policy_blocked: boolean;
}

/** One resource an MCP server offers. */
export interface McpResource {
  uri: string;
  name: string;
  description: string;
  mime_type: string;
}

/** One prompt an MCP server offers. */
export interface McpPrompt {
  name: string;
  description: string;
  /** The arguments it takes. */
  arguments: string[];
}

/** What starting the MCP servers did. */
export interface McpInit {
  /** The servers that are now connected. */
  connected: string[];
  /** The servers that did not, and why. */
  failed: Record<string, string>;
  /** Whether the clients were rebuilt. */
  rebuilt: boolean;
  /** Why nothing was started, when nothing was: `already_initialized`, `no_configured_servers` or `no_clients_connected`. */
  skipped_reason: string | null;
}

/** One tool of one server, offered or withheld. */
export interface McpToolToggle {
  server: string;
  tool: string;
  enabled: boolean;
}

/** One installed plugin. */
export interface PluginInfo {
  name: string;
  version: string;
  description: string;
  /** Where it was installed from. */
  source_root: string;
  /** Where it lives on this machine. */
  path: string;
  enabled: boolean;
  has_skills: boolean;
  has_agents: boolean;
  has_hooks: boolean;
  has_mcp: boolean;
  has_tools: boolean;
  has_lsp: boolean;
  has_monitors: boolean;
  /** Whether igni keeps it up to date itself. */
  managed: boolean;
  /** The version it is pinned to, when it is. */
  pin: string;
}

/** One marketplace of plugins. */
export interface Marketplace {
  name: string;
  url: string;
  /** When it was last read. */
  last_fetched: string;
  /** The plugins it offers. */
  plugins: MarketplacePlugin[];
}

/** One plugin a marketplace offers. */
export interface MarketplacePlugin {
  name: string;
  source: string;
  description: string;
  version: string;
  branch: string;
}

/** What a plugin carries. */
export interface PluginContents {
  name: string;
  /** Where it lives on this machine. */
  root_path: string;
  skills: PluginSkill[];
  agents: PluginAgent[];
  hooks: PluginHook[];
  mcp_servers: PluginMcpServer[];
  tools: PluginTool[];
  readme: string;
  /** Why it could not be read, when it could not. */
  error: string;
  /** Where it would come from. */
  preview_source: PluginPreviewSource | null;
}

/** One skill a plugin carries. */
export interface PluginSkill {
  name: string;
  description: string;
}

/** One agent a plugin carries. */
export interface PluginAgent {
  name: string;
  description: string;
}

/** One hook a plugin carries: the event, and how many it registers. */
export interface PluginHook {
  event: string;
  count: number;
}

/** One MCP server a plugin carries. */
export interface PluginMcpServer {
  name: string;
  transport: string;
  command: string;
}

/** One tool a plugin carries. */
export interface PluginTool {
  name: string;
}

/** Where a plugin would come from. */
export interface PluginPreviewSource {
  url: string;
  subdir: string;
}

/** One hook igni has. */
export interface HookEntry {
  event: string;
  /** How it runs: `command`, `url` or another. */
  type: string;
  command: string;
  url: string;
  /** What it matches, when it matches something. */
  matcher: string;
  timeout_ms: number;
  background: boolean;
  /** The names of the headers an `http` hook sends. Never their values, which may be credentials. */
  header_names: string[];
}

/** The group's policy pack. */
export interface PolicyPack {
  group_id: string | null;
  group_name: string | null;
  fetched_at: string | null;
  /** How many rules it holds. */
  entry_count: number;
  /** The model it points every group at. */
  default_model: string | null;
}

/** What was decided about a plan. */
export interface PlanDecision {
  /** The run the plan belonged to. */
  run_id: string;
  /** `approved` or `dismissed`. */
  decision: string;
  /** What the plan mode says now. */
  mode_status: string;
  ok: boolean;
  /** Why it went wrong, when it did. */
  error: string | null;
}

/** One item of the agent's todo list. */
export interface TodoItem {
  /** What is to be done, as an imperative. */
  content: string;
  /** `pending`, `in_progress` or `completed`. */
  status: string;
  /** What is shown while it is in progress — the gerund, e.g. `Running tests`. */
  activeForm: string;
}

/** One iteration of a loop, taken. */
export interface LoopAdvance {
  /** `completed`, `safety_paused` or `step`. */
  kind: string;
  completed: boolean;
  total_iterations: number;
  safety_cap_paused: boolean;
  prompt: string;
  display_prompt: string;
  iteration: number;
  remaining: number;
  /** Whether the cap was asked for. */
  cap_explicit: boolean;
  /** Whether the cap was extended by itself. */
  auto_extended: boolean;
}

/** One slash command. */
export interface SlashCommand {
  /** `builtin`, `markdown`, `skill` or `extension`. */
  source: string;
  /** With its slash: `/ctx`. */
  name: string;
  description: string;
  /** What it takes, as a hint. */
  argument_hint: string;
  /** The extension that answers it, when an extension does. */
  owner?: string | null;
}

/** One skill, as the agent is given it. */
export interface SkillDefinition {
  name: string;
  description: string;
  /** Its body: what the agent is told to do. */
  prompt: string;
}

/** One skill, as the person sees it. */
export interface SkillDetails {
  name: string;
  description: string;
  version: string;
  category: string;
  argument_hint: string;
  context: string;
  agent: string;
  /** Whether the person may invoke it as `/name`. */
  user_invocable: boolean;
  body: string;
  /** Where it lives on this machine. */
  source_dir: string;
}

/** One agent. */
export interface AgentInfo {
  name: string;
  description: string;
  /** The tools it may use. */
  tools: string[];
  model: string;
  color: string;
  /** Whether it may run other agents. */
  can_orchestrate: boolean;
  /** The MCP servers it is given. */
  mcp_servers: string[];
  tags: string[];
  system_prompt: string;
  /** Where it lives on this machine. */
  source_path: string;
  /** Whether it was made for one task only. */
  is_ephemeral: boolean;
  /** The tools it names that do not exist. */
  unknown_tools: string[];
}

/** What became of an agent made for one task. */
export interface PromoteResult {
  ok: boolean;
  name: string;
  /** Where it was kept, when it was. */
  dest: string;
  /** Why it was not, when it was not. */
  reason: string;
}

/** What became of an agent made for one task, dropped. */
export interface DiscardResult {
  ok: boolean;
  name: string;
  /** Why it was not, when it was not. */
  reason: string;
}

/** One workflow. */
export interface Workflow {
  name: string;
  description: string;
  /** When the agent should reach for it. */
  whenToUse: string;
  /** The phases it runs through. */
  phases: WorkflowPhase[];
  /** Where it lives on this machine. */
  path: string;
}

/** One phase of a workflow. */
export interface WorkflowPhase {
  title: string;
  detail: string;
}

/** One scheduled task. */
export interface ScheduledTask {
  id: string;
  /** What the agent is asked to do. */
  description: string;
  /** ISO 8601, when it is next due. */
  scheduled_at: string;
  /** ISO 8601, when it was made. */
  created_at: string;
  /** `pending`, `running`, `completed`, `failed` or `cancelled`. */
  status: string;
  /** What it left behind, when it has run. */
  result: string;
  /** Why it failed, when it did. */
  error: string;
  /** How it repeats, when it does. */
  recurrence: string;
}

/** One background shell. */
export interface ProcessRow {
  pid: number;
  cmd: string;
  elapsed_seconds: number;
  is_running: boolean;
  /** How it ended, when it has. */
  exit_code: number | null;
}

/** A background shell's last lines. */
export interface ProcessTail {
  pid: number;
  output: string;
  is_running: boolean;
  /** How it ended, when it has. */
  exit_code: number | null;
}

/** What stopping a background shell did. */
export interface ProcessStop {
  pid: number;
  killed: boolean;
  message: string;
}

/** What a command in the project printed. */
export interface ShellResult {
  output: string;
  exit_code: number;
  /** The process's id, once it started; `null` when it could not. */
  pid: number | null;
  /** `true` when the command is still running, in the background. */
  backgrounded: boolean;
}

/** Key–value state of the extension's own, kept by the host across restarts. An extension sees only its own keys. */
export class HostAppState extends HostObject {
  static readonly PATH = "app.state";
  /** Every key and value. */
  readonly values: Property<Record<string, string>>;
  /** A key was set or deleted. */
  readonly changed: Signal<StateChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "app.state", window, session);
    this.values = new Property(this, "values", false);
    this.changed = new Signal("app.state.changed");
  }

  /** One value, or `None`. */
  get(key: string): Promise<string | null> {
    return this.call<string | null>("get", { key });
  }

  /** Store one value. */
  set(key: string, value: string): Promise<void> {
    return this.call<void>("set", { key, value });
  }

  /** Remove one key. */
  delete(key: string): Promise<void> {
    return this.call<void>("delete", { key });
  }
}

/** The agent asking to act, and the answers. Through `host.sessions.chat(id)` `waiting` reads that session; an approval is answered only in the session on screen. */
export class HostChatApprovals extends HostObject {
  static readonly PATH = "chat.approvals";
  /** Requests not yet answered. */
  readonly waiting: Property<Approval[]>;
  /** The agent asked. */
  readonly requested: Signal<Approval>;
  /** Somebody answered. */
  readonly resolved: Signal<ApprovalResolved>;
  /** The reason arrived. */
  readonly details: Signal<ApprovalDetails>;
  /** An approval appeared or went away, whoever answered and whenever — including after a restart. For an app following approvals through the API. */
  readonly changed: Signal<ApprovalChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "chat.approvals", window, session);
    this.waiting = new Property(this, "waiting", false);
    this.requested = new Signal("chat.approvals.requested");
    this.resolved = new Signal("chat.approvals.resolved");
    this.details = new Signal("chat.approvals.details");
    this.changed = new Signal("chat.approvals.changed");
  }

  /** Answer one request, as the person's dialog does. */
  answer(requirement_id: string, action: string, choice?: string): Promise<void> {
    return this.call<void>("answer", { requirement_id, action, choice });
  }

  /** Answer every request of a pause at once. */
  answer_all(answers: ApprovalAnswer[]): Promise<void> {
    return this.call<void>("answer_all", { answers });
  }
}

/** json-render blocks in the transcript — the visualizer's and extensions'. Through `host.sessions.chat(id)` `list` reads that session; `dispatch` acts only in the session on screen. */
export class HostChatViews extends HostObject {
  static readonly PATH = "chat.views";
  /** The views in the current session. */
  readonly list: Property<View[]>;
  /** A view appeared or was replaced. */
  readonly shown: Signal<View>;
  /** The person used a control in a view. */
  readonly action: Signal<ViewAction>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "chat.views", window, session);
    this.list = new Property(this, "list", false);
    this.shown = new Signal("chat.views.shown");
    this.action = new Signal("chat.views.action");
  }

  /** Act on a view as if the person had. */
  dispatch(view_id: string, action: string, params?: Record<string, JsonValue>): Promise<JsonValue> {
    return this.call<JsonValue>("dispatch", { view_id, action, params });
  }
}

/** igni itself: how it presents things, which version, whether it is connected. */
export class HostApp extends HostObject {
  static readonly PATH = "app";
  /** `host.app.state`. Key–value state of the extension's own, kept by the host across restarts. An extension sees only its own keys. */
  readonly state: HostAppState;
  /** Theme, verbosity, output style. */
  readonly display: Property<Display>;
  /** The igni version running. */
  readonly version: Property<string>;
  /** A newer igni, as last checked; `None` when there is none or it was not checked yet. */
  readonly update_available: Property<UpdateInfo | null>;
  /** Model and server reachability. */
  readonly connection: Property<Connection>;
  /** Running, waiting on a person, or idle — what decides whether igni's process may be suspended. */
  readonly activity: Property<Activity>;
  /** Verbosity or output style changed. */
  readonly display_changed: Signal<Display>;
  /** The connection changed. */
  readonly connection_changed: Signal<Connection>;
  /** An update check answered. */
  readonly update_changed: Signal<UpdateInfo | null>;
  /** igni started or stopped doing something. */
  readonly activity_changed: Signal<Activity>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "app", window, session);
    this.state = new HostAppState(link, window, session);
    this.display = new Property(this, "display", false);
    this.version = new Property(this, "version", false);
    this.update_available = new Property(this, "update_available", false);
    this.connection = new Property(this, "connection", false);
    this.activity = new Property(this, "activity", false);
    this.display_changed = new Signal("app.display_changed");
    this.connection_changed = new Signal("app.connection_changed");
    this.update_changed = new Signal("app.update_changed");
    this.activity_changed = new Signal("app.activity_changed");
  }

  /** Show or hide routing detail. */
  set_verbose(on: boolean): Promise<Display> {
    return this.call<Display>("set_verbose", { on });
  }

  /** Switch the output style, as `/output-style <name>` does. */
  set_output_style(name: string): Promise<Display> {
    return this.call<Display>("set_output_style", { name });
  }

  /** Ask whether a newer igni exists: `None` when none does. A check that could not reach an answer (offline, an HTTP error, an unreadable reply) is refused (`refused`) rather than answered `None`. */
  check_for_update(): Promise<UpdateInfo | null> {
    return this.call<UpdateInfo | null>("check_for_update", {});
  }

  /** Open an https link in the person's browser, the way igni opens every link outside it. The window asked about opens it: a page's own, else the active one. Anything but an absolute `https://` URL with a host and no credentials in it is refused (`invalid`). */
  open_external(url: string): Promise<void> {
    return this.call<void>("open_external", { url });
  }
}

/** Every open igni window. Address one window's UI with `host.windows.ui(id)`. */
export class HostWindows extends HostObject {
  static readonly PATH = "windows";
  /** Every window connected now. */
  readonly list: Property<WindowInfo[]>;
  /** The window the person is using — the one with focus; `None` when igni is in the background. */
  readonly focused: Property<string | null>;
  /** A window connected. */
  readonly opened: Signal<WindowInfo>;
  /** A window went away. */
  readonly closed: Signal<WindowInfo>;
  /** A window took focus or lost it; `focused` says which. */
  readonly focus_changed: Signal<WindowInfo>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "windows", window, session);
    this.list = new Property(this, "list", false);
    this.focused = new Property(this, "focused", false);
    this.opened = new Signal("windows.opened");
    this.closed = new Signal("windows.closed");
    this.focus_changed = new Signal("windows.focus_changed");
  }

  /** `host.ui` of one window, by its id. */
  ui(windowId: string): HostUi {
    return new HostUi(this.link, windowId);
  }
}

/** What a window shows — the model its views bind to. `host.ui` is the active window, the one the person last used; `host.windows.ui(id)` any window. igni's own views write here too, by the same path, so every change below is a signal whoever made it. */
export class HostUi extends HostObject {
  static readonly PATH = "ui";
  /** The page stack; empty when the chat is showing. Writable: setting it navigates. */
  readonly route: Property<Page[]>;
  /** The panel open over the chat. Writable: setting it opens one, `None` closes it. */
  readonly panel: Property<Panel | null>;
  /** The sidebar. Writable. */
  readonly sidebar: Property<Sidebar>;
  /** The file previewed. Writable: `None` closes it. */
  readonly preview: Property<Preview | null>;
  /** What is selected. Writable. */
  readonly selection: Property<SelectionState>;
  /** The composer: draft, the files it refers to, its mode. Writable. */
  readonly composer: Property<Composer>;
  /** Toasts on screen, oldest first. */
  readonly toasts: Property<Toast[]>;
  /** The open dialog. */
  readonly dialog: Property<Dialog | null>;
  /** Where the transcript is. */
  readonly scroll: Property<Scroll>;
  /** The page stack changed. */
  readonly navigated: Signal<Route>;
  /** A panel opened or closed. */
  readonly panel_changed: Signal<PanelChange>;
  /** The sidebar changed. */
  readonly sidebar_changed: Signal<SidebarChange>;
  /** The preview opened, changed or closed. */
  readonly preview_changed: Signal<PreviewChange>;
  /** The selection changed. */
  readonly selection_changed: Signal<SelectionChange>;
  /** The draft changed. */
  readonly composer_changed: Signal<ComposerChange>;
  /** A toast appeared. */
  readonly toast_shown: Signal<ToastChange>;
  /** A toast went away. */
  readonly toast_dismissed: Signal<ToastChange>;
  /** A dialog opened. */
  readonly dialog_opened: Signal<DialogChange>;
  /** A dialog closed, with the answer. */
  readonly dialog_closed: Signal<DialogChange>;
  /** The transcript came to rest somewhere else, or started or stopped following the newest message. */
  readonly scrolled: Signal<Scroll>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "ui", window, session);
    this.route = new Property(this, "route", true);
    this.panel = new Property(this, "panel", true);
    this.sidebar = new Property(this, "sidebar", true);
    this.preview = new Property(this, "preview", true);
    this.selection = new Property(this, "selection", true);
    this.composer = new Property(this, "composer", true);
    this.toasts = new Property(this, "toasts", false);
    this.dialog = new Property(this, "dialog", false);
    this.scroll = new Property(this, "scroll", false);
    this.navigated = new Signal("ui.navigated");
    this.panel_changed = new Signal("ui.panel_changed");
    this.sidebar_changed = new Signal("ui.sidebar_changed");
    this.preview_changed = new Signal("ui.preview_changed");
    this.selection_changed = new Signal("ui.selection_changed");
    this.composer_changed = new Signal("ui.composer_changed");
    this.toast_shown = new Signal("ui.toast_shown");
    this.toast_dismissed = new Signal("ui.toast_dismissed");
    this.dialog_opened = new Signal("ui.dialog_opened");
    this.dialog_closed = new Signal("ui.dialog_closed");
    this.scrolled = new Signal("ui.scrolled");
  }

  /** Open a page at the top of the stack, as a header link does. */
  navigate(page: string, params?: Record<string, string>): Promise<Page[]> {
    return this.call<Page[]>("navigate", { page, params });
  }

  /** Go back one level; at the root, back to the chat. */
  back(): Promise<Page[]> {
    return this.call<Page[]>("back", {});
  }

  /** Open a panel over the chat, closing the one that was open. */
  open_panel(kind: string, params?: Record<string, JsonValue>): Promise<Panel> {
    return this.call<Panel>("open_panel", { kind, params });
  }

  /** Close the panel. */
  close_panel(): Promise<void> {
    return this.call<void>("close_panel", {});
  }

  /** Open or close the sidebar, and size it or bring a section into view. */
  set_sidebar(open: boolean, width?: number, section?: string): Promise<Sidebar> {
    return this.call<Sidebar>("set_sidebar", { open, width, section });
  }

  /** Preview a file of the project. (`preview` is the property.) */
  open_preview(path: string): Promise<Preview> {
    return this.call<Preview>("open_preview", { path });
  }

  /** Close the preview. */
  close_preview(): Promise<void> {
    return this.call<void>("close_preview", {});
  }

  /** Select a message, text or file. The parts left out are cleared. */
  select(selection: SelectionState): Promise<SelectionState> {
    return this.call<SelectionState>("select", { selection });
  }

  /** Replace the draft. */
  set_composer(text: string, attachments?: string[], mode?: string): Promise<Composer> {
    return this.call<Composer>("set_composer", { text, attachments, mode });
  }

  /** Show a transient message, labelled as this extension's. */
  toast(text: string, kind?: string, body?: string, target?: Page): Promise<Toast> {
    return this.call<Toast>("toast", { text, kind, body, target });
  }

  /** Take one of this extension's toasts away. */
  dismiss_toast(toast_id: string): Promise<void> {
    return this.call<void>("dismiss_toast", { toast_id });
  }

  /** Show a dialog and wait for the person's answer. `spec` is `{title, body, buttons: [{id, label, primary}], input: {label, placeholder, value}}` — `buttons` defaults to one OK, `input` is optional. Answers `{button, value}`, or `None` when the dialog was dismissed, or replaced by another. (`dialog` is the property.) */
  show_dialog(spec: JsonValue): Promise<JsonValue> {
    return this.call<JsonValue>("show_dialog", { spec });
  }

  /** Scroll the transcript to a message, by its run; `bottom` for the newest. */
  scroll_to(message_id: string): Promise<Scroll> {
    return this.call<Scroll>("scroll_to", { message_id });
  }
}

/** The sessions of this project, and which one the active window shows. Reach any session's chat, without showing it, with `host.sessions.chat(id)`. */
export class HostSessions extends HostObject {
  static readonly PATH = "sessions";
  /** Every session, newest first. */
  readonly list: Property<SessionInfo[]>;
  /** The session the active window shows. Writable: setting it switches, and is refused where the person's switch would be. */
  readonly current: Property<string>;
  /** A window moved to another session. */
  readonly current_changed: Signal<SessionChange>;
  /** The session list was read. */
  readonly listed: Signal<SessionList>;
  /** `/clear` renewed a session. */
  readonly cleared: Signal<SessionCleared>;
  /** A session got its name. */
  readonly named: Signal<SessionNamed>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "sessions", window, session);
    this.list = new Property(this, "list", false);
    this.current = new Property(this, "current", true);
    this.current_changed = new Signal("session.switched");
    this.listed = new Signal("sessions.listed");
    this.cleared = new Signal("sessions.cleared");
    this.named = new Signal("sessions.named");
  }

  /** Show a session in the active window. */
  open(session_id: string): Promise<SessionChange> {
    return this.call<SessionChange>("open", { session_id });
  }

  /** Start a new session, in a folder or in this project. It moves no window unless `focus` is true: reach it with `host.sessions.chat(session_id)`. A `title` names it at once, kept as a service's chat title is, so no auto-name replaces it. */
  create(project_dir?: string, title?: string, focus?: boolean): Promise<SessionAttached> {
    return this.call<SessionAttached>("create", { project_dir, title, focus });
  }

  /** Make sure a session is live, without showing it. */
  attach(session_id: string, project_dir?: string): Promise<SessionAttached> {
    return this.call<SessionAttached>("attach", { session_id, project_dir });
  }

  /** `host.chat` of any session of this project, by its id, without showing it. The session on screen's id is `host.chat` itself. */
  chat(sessionId: string): HostChat {
    return new HostChat(this.link, null, sessionId);
  }
}

/** The conversation in the current session. Signals carry the session they happened in, and arrive for every live session. `host.sessions.chat(id)` is the same object for any session of this project, without showing it: its properties read that session, and `post`, `queue`, `append` and `replace` write there (with `sessions.post` as well). A message posted there starts a run, or waits for the run already going there — never answering an approval. Its other methods act only on the session on screen. */
export class HostChat extends HostObject {
  static readonly PATH = "chat";
  /** `host.chat.approvals`. The agent asking to act, and the answers. Through `host.sessions.chat(id)` `waiting` reads that session; an approval is answered only in the session on screen. */
  readonly approvals: HostChatApprovals;
  /** `host.chat.views`. json-render blocks in the transcript — the visualizer's and extensions'. Through `host.sessions.chat(id)` `list` reads that session; `dispatch` acts only in the session on screen. */
  readonly views: HostChatViews;
  /** The current session. */
  readonly session_id: Property<string>;
  /** The transcript, turn by turn. */
  readonly messages: Property<JsonValue[]>;
  /** Messages waiting for a turn. */
  readonly pending: Property<JsonValue[]>;
  /** Whether a run is going. */
  readonly processing: Property<boolean>;
  /** The status line. */
  readonly status: Property<Status>;
  /** Seconds a run may take. */
  readonly timeout: Property<number>;
  /** Runs that stopped part-way. */
  readonly interrupted_runs: Property<JsonValue[]>;
  /** Token counts and what fills them. */
  readonly context: Property<ContextUsage>;
  /** A message was posted — by the person, an extension, or an extension's service (`from_service`). */
  readonly message_added: Signal<ChatMessage>;
  /** The agent's answer, streaming. */
  readonly content_delta: Signal<ContentDelta>;
  /** The agent started thinking. */
  readonly reasoning_started: Signal<RunRef>;
  /** A run started. */
  readonly run_started: Signal<RunStart>;
  /** A run finished, with the files it changed. */
  readonly run_completed: Signal<Run>;
  /** A run stopped with an error. */
  readonly run_error: Signal<RunFailure>;
  /** A run is waiting for approvals. */
  readonly run_paused: Signal<RunPause>;
  /** The answer finished streaming. */
  readonly streaming_done: Signal<RunRef>;
  /** Somebody's draft, live. */
  readonly typing: Signal<Typing>;
  /** The status line changed. */
  readonly status_changed: Signal<Status>;
  /** An info line. */
  readonly info: Signal<Notice>;
  /** An error line. */
  readonly error: Signal<Notice>;
  /** The agent called a tool. */
  readonly tool_started: Signal<ToolCall>;
  /** A tool call finished. */
  readonly tool_completed: Signal<ToolResult>;
  /** A tool call failed. */
  readonly tool_error: Signal<ToolFailure>;
  /** A model call finished. */
  readonly model_completed: Signal<ModelUsage>;
  /** The agent wrote a file. */
  readonly file_edited: Signal<FileEdited>;
  /** A sub-agent or team moved on. */
  readonly agent_event: Signal<AgentEvent>;
  /** A network call is being retried. */
  readonly retry: Signal<Retry>;
  /** Turns were truncated or discarded. */
  readonly history_changed: Signal<HistoryChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "chat", window, session);
    this.approvals = new HostChatApprovals(link, window, session);
    this.views = new HostChatViews(link, window, session);
    this.session_id = new Property(this, "session_id", false);
    this.messages = new Property(this, "messages", false);
    this.pending = new Property(this, "pending", false);
    this.processing = new Property(this, "processing", false);
    this.status = new Property(this, "status", false);
    this.timeout = new Property(this, "timeout", false);
    this.interrupted_runs = new Property(this, "interrupted_runs", false);
    this.context = new Property(this, "context", false);
    this.message_added = new Signal("chat.message_added");
    this.content_delta = new Signal("chat.content_delta");
    this.reasoning_started = new Signal("chat.reasoning_started");
    this.run_started = new Signal("chat.run_started");
    this.run_completed = new Signal("chat.run_completed");
    this.run_error = new Signal("chat.run_error");
    this.run_paused = new Signal("chat.run_paused");
    this.streaming_done = new Signal("chat.streaming_done");
    this.typing = new Signal("chat.typing");
    this.status_changed = new Signal("chat.status_changed");
    this.info = new Signal("chat.info");
    this.error = new Signal("chat.error");
    this.tool_started = new Signal("chat.tool_started");
    this.tool_completed = new Signal("chat.tool_completed");
    this.tool_error = new Signal("chat.tool_error");
    this.model_completed = new Signal("chat.model_completed");
    this.file_edited = new Signal("chat.file_edited");
    this.agent_event = new Signal("chat.agent_event");
    this.retry = new Signal("chat.retry");
    this.history_changed = new Signal("chat.history_changed");
  }

  /** Post a message in the chat, labelled as this extension. The agent sees it and answers in the chat as usual. In a session that is not on screen it starts a run, or is queued for the run going there (working or waiting on an approval) — then without attachments. */
  post(text: string, attachments?: Record<string, string>): Promise<void> {
    return this.call<void>("post", { text, attachments });
  }

  /** Post a message for the next turn, labelled as this extension. */
  queue(text: string): Promise<void> {
    return this.call<void>("queue", { text });
  }

  /** Show a json-render block in the transcript. Shown to the person, never sent to the model. Returns its id. */
  append(view: JsonValue, title?: string): Promise<string> {
    return this.call<string>("append", { view, title });
  }

  /** Replace a block this extension appended. */
  replace(view_id: string, view: JsonValue, title?: string): Promise<void> {
    return this.call<void>("replace", { view_id, view, title });
  }

  /** Search the transcript. */
  search(query: string, limit?: number): Promise<JsonValue[]> {
    return this.call<JsonValue[]>("search", { query, limit });
  }

  /** Stop the run. */
  cancel(): Promise<void> {
    return this.call<void>("cancel", {});
  }

  /** Stop one sub-agent's run. */
  cancel_agent(run_id: string): Promise<void> {
    return this.call<void>("cancel_agent", { run_id });
  }

  /** Remove a run and everything after it. */
  truncate(run_id: string): Promise<JsonValue> {
    return this.call<JsonValue>("truncate", { run_id });
  }

  /** Compact the conversation if it needs it, as igni does after a run. */
  compact(): Promise<SessionCleared | null> {
    return this.call<SessionCleared | null>("compact", {});
  }

  /** Have the agent note what a turn taught it. */
  extract_learnings(user_msg: string, assistant_msg: string): Promise<void> {
    return this.call<void>("extract_learnings", { user_msg, assistant_msg });
  }

  /** Forget an interrupted run. */
  discard_interrupted(message_id: string): Promise<JsonValue> {
    return this.call<JsonValue>("discard_interrupted", { message_id });
  }

  /** Upload an attachment for a later `post`. */
  upload(filename: string, content_base64: string): Promise<JsonValue> {
    return this.call<JsonValue>("upload", { filename, content_base64 });
  }
}

/** Plan mode: the plan the agent proposed. */
export class HostPlan extends HostObject {
  static readonly PATH = "plan";
  /** The latest plan. */
  readonly latest: Property<Plan>;
  /** A plan was submitted or decided. */
  readonly changed: Signal<PlanChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "plan", window, session);
    this.latest = new Property(this, "latest", false);
    this.changed = new Signal("plan.changed");
  }

  /** Approve the plan. */
  approve(run_id?: string): Promise<PlanDecision> {
    return this.call<PlanDecision>("approve", { run_id });
  }

  /** Send the plan back. */
  dismiss(run_id?: string): Promise<PlanDecision> {
    return this.call<PlanDecision>("dismiss", { run_id });
  }
}

/** The agent's todo list and its sub-agent tasks. */
export class HostTasks extends HostObject {
  static readonly PATH = "tasks";
  /** The todo list. */
  readonly todos: Property<TodoItem[]>;
  /** A task was created. */
  readonly created: Signal<TaskEvent>;
  /** A task changed. */
  readonly updated: Signal<TaskEvent>;
  /** A task loop moved on. */
  readonly iteration: Signal<TaskIteration>;
  /** Every task, as it now stands. */
  readonly snapshot: Signal<TaskSnapshot>;
  /** The todo list changed. */
  readonly todos_changed: Signal<Todos>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "tasks", window, session);
    this.todos = new Property(this, "todos", false);
    this.created = new Signal("tasks.created");
    this.updated = new Signal("tasks.updated");
    this.iteration = new Signal("tasks.iteration");
    this.snapshot = new Signal("tasks.snapshot");
    this.todos_changed = new Signal("tasks.todos_changed");
  }
}

/** `/loop`: a prompt repeated until done. */
export class HostLoop extends HostObject {
  static readonly PATH = "loop";
  /** Where it is. */
  readonly status: Property<LoopStatus>;
  /** It paused, resumed, advanced or stopped. */
  readonly changed: Signal<LoopStatus>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "loop", window, session);
    this.status = new Property(this, "status", false);
    this.changed = new Signal("loop.changed");
  }

  /** Pause after this iteration. */
  pause(): Promise<boolean> {
    return this.call<boolean>("pause", {});
  }

  /** Carry on. */
  resume(): Promise<string> {
    return this.call<string>("resume", {});
  }

  /** Stop the loop. */
  cancel_pending(): Promise<boolean> {
    return this.call<boolean>("cancel_pending", {});
  }

  /** Take the next iteration. */
  pop_pending(): Promise<LoopAdvance | null> {
    return this.call<LoopAdvance | null>("pop_pending", {});
  }
}

/** Slash commands and skills. */
export class HostCommands extends HostObject {
  static readonly PATH = "commands";
  /** Every slash command. */
  readonly list: Property<SlashCommand[]>;
  /** Skill names. */
  readonly skills: Property<string[]>;
  /** Each skill's description and prompt. */
  readonly skill_definitions: Property<SkillDefinition[]>;
  /** Each skill's details. */
  readonly skill_details: Property<SkillDetails[]>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "commands", window, session);
    this.list = new Property(this, "list", false);
    this.skills = new Property(this, "skills", false);
    this.skill_definitions = new Property(this, "skill_definitions", false);
    this.skill_details = new Property(this, "skill_details", false);
  }

  /** Run a slash command, as the extension. The answer comes back here. */
  run(command: string): Promise<CommandOutcome> {
    return this.call<CommandOutcome>("run", { command });
  }
}

/** Agent definitions. */
export class HostAgents extends HostObject {
  static readonly PATH = "agents";
  /** Every agent. */
  readonly details: Property<AgentInfo[]>;
  /** An agent was promoted or discarded. */
  readonly changed: Signal<CollectionChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "agents", window, session);
    this.details = new Property(this, "details", false);
    this.changed = new Signal("agents.changed");
  }

  /** Keep an agent made for one task, as `/agents promote` does. */
  promote_ephemeral(name: string, target?: string): Promise<PromoteResult> {
    return this.call<PromoteResult>("promote_ephemeral", { name, target });
  }

  /** Drop an agent made for one task. */
  discard_ephemeral(name: string): Promise<DiscardResult> {
    return this.call<DiscardResult>("discard_ephemeral", { name });
  }
}

/** Workflows: scripted runs. */
export class HostWorkflows extends HostObject {
  static readonly PATH = "workflows";
  /** Every workflow. */
  readonly list: Property<Workflow[]>;
  /** A workflow run moved on. */
  readonly changed: Signal<CollectionChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "workflows", window, session);
    this.list = new Property(this, "list", false);
    this.changed = new Signal("workflows.changed");
  }

  /** Start a workflow. */
  run(name: string, input?: Record<string, JsonValue>): Promise<WorkflowRun> {
    return this.call<WorkflowRun>("run", { name, input });
  }

  /** Stop a workflow run. */
  cancel(workflow_run_id: string): Promise<boolean> {
    return this.call<boolean>("cancel", { workflow_run_id });
  }
}

/** Scheduled tasks. */
export class HostScheduler extends HostObject {
  static readonly PATH = "scheduler";
  /** Every scheduled task. */
  readonly tasks: Property<ScheduledTask[]>;
  /** A task started, finished or changed. */
  readonly event: Signal<SchedulerEvent>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "scheduler", window, session);
    this.tasks = new Property(this, "tasks", false);
    this.event = new Signal("scheduler.event");
  }

  /** Start the scheduler. */
  start(): Promise<void> {
    return this.call<void>("start", {});
  }

  /** Run a scheduled task now. */
  run_now(task_id: string): Promise<string> {
    return this.call<string>("run_now", { task_id });
  }

  /** Cancel a scheduled task. */
  cancel(task_id: string): Promise<void> {
    return this.call<void>("cancel", { task_id });
  }
}

/** Background shells. */
export class HostProcesses extends HostObject {
  static readonly PATH = "processes";
  /** Every background shell. */
  readonly list: Property<ProcessRow[]>;
  /** A shell started, printed or exited. */
  readonly changed: Signal<ProcessEvent>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "processes", window, session);
    this.list = new Property(this, "list", false);
    this.changed = new Signal("processes.changed");
  }

  /** A shell's last lines. */
  tail(pid: number, lines?: number): Promise<ProcessTail> {
    return this.call<ProcessTail>("tail", { pid, lines });
  }

  /** Stop a shell. */
  stop(pid: number): Promise<ProcessStop> {
    return this.call<ProcessStop>("stop", { pid });
  }

  /** Run a command in the project and wait for it. */
  run(command: string): Promise<ShellResult> {
    return this.call<ShellResult>("run", { command });
  }
}

/** The project, as far as the extension's workspace grant reaches. */
export class HostWorkspace extends HostObject {
  static readonly PATH = "workspace";
  /** The project directory. */
  readonly root: Property<string>;
  /** Git HEAD; `None` outside a repository. */
  readonly head: Property<Head | null>;
  /** HEAD moved. */
  readonly head_changed: Signal<Head>;
  /** Files changed, as git sees them, within the grant. */
  readonly files_changed: Signal<FilesChanged>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "workspace", window, session);
    this.root = new Property(this, "root", false);
    this.head = new Property(this, "head", false);
    this.head_changed = new Signal("workspace.head-changed");
    this.files_changed = new Signal("workspace.files-changed");
  }

  /** Read a file in the project. */
  read(path: string): Promise<JsonValue> {
    return this.call<JsonValue>("read", { path });
  }

  /** List a directory in the project. */
  list(dir?: string): Promise<JsonValue> {
    return this.call<JsonValue>("list", { dir });
  }

  /** Complete a path, as `@` does. */
  complete(prefix: string): Promise<JsonValue> {
    return this.call<JsonValue>("complete", { prefix });
  }

  /** Search the code. */
  search(query: string): Promise<JsonValue> {
    return this.call<JsonValue>("search", { query });
  }

  /** Ask the person to pick a folder. */
  pick_dir(): Promise<JsonValue> {
    return this.call<JsonValue>("pick_dir", {});
  }

  /** Open a file in the project with the application this machine opens it with — what an extension whose process is sandboxed cannot do itself. Only a file the workspace grant reaches (`refused` outside the project, `not_granted` outside `workspacePaths`), and only a document: `.csv`, `.gif`, `.htm`, `.html`, `.jpeg`, `.jpg`, `.md`, `.pdf`, `.png`, `.svg`, `.txt`, `.webp` (`invalid` otherwise, and for an executable file). `failed` when nothing here opened it. */
  open(path: string): Promise<void> {
    return this.call<void>("open", { path });
  }
}

/** Models. */
export class HostModels extends HostObject {
  static readonly PATH = "models";
  /** Every model igni knows. */
  readonly registry: Property<ModelRegistry>;
  /** The model in use. Writable: setting it switches. */
  readonly current: Property<string>;
  /** The model in use changed. */
  readonly changed: Signal<ModelChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "models", window, session);
    this.registry = new Property(this, "registry", false);
    this.current = new Property(this, "current", true);
    this.changed = new Signal("models.changed");
  }
}

/** MCP servers. */
export class HostMcp extends HostObject {
  static readonly PATH = "mcp";
  /** Every server. */
  readonly servers: Property<McpServer[]>;
  /** Each server's status. */
  readonly status: Property<McpServer[]>;
  /** Each server's tools and details. */
  readonly details: Property<McpServerDetails[]>;
  /** A server connected, disconnected or changed tools. */
  readonly changed: Signal<CollectionChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "mcp", window, session);
    this.servers = new Property(this, "servers", false);
    this.status = new Property(this, "status", false);
    this.details = new Property(this, "details", false);
    this.changed = new Signal("mcp.changed");
  }

  /** Connect a server. */
  connect(name: string): Promise<void> {
    return this.call<void>("connect", { name });
  }

  /** Disconnect a server. */
  disconnect(name: string): Promise<void> {
    return this.call<void>("disconnect", { name });
  }

  /** Start the servers that should be running. */
  ensure(): Promise<McpInit> {
    return this.call<McpInit>("ensure", {});
  }

  /** Offer or withhold one tool. */
  set_tool_enabled(server: string, tool: string, on: boolean): Promise<McpToolToggle> {
    return this.call<McpToolToggle>("set_tool_enabled", { server, tool, on });
  }
}

/** Plugins and marketplaces. */
export class HostPlugins extends HostObject {
  static readonly PATH = "plugins";
  /** Every installed plugin. */
  readonly installed: Property<PluginInfo[]>;
  /** Every marketplace. */
  readonly marketplaces: Property<Marketplace[]>;
  /** A plugin or marketplace changed. */
  readonly changed: Signal<CollectionChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "plugins", window, session);
    this.installed = new Property(this, "installed", false);
    this.marketplaces = new Property(this, "marketplaces", false);
    this.changed = new Signal("plugins.changed");
  }

  /** What a plugin carries. */
  contents(name: string): Promise<PluginContents> {
    return this.call<PluginContents>("contents", { name });
  }

  /** What a plugin would install. */
  preview(source: string, branch?: string, subdir?: string): Promise<PluginContents> {
    return this.call<PluginContents>("preview", { source, branch, subdir });
  }

  /** Install a plugin. */
  install(ref: string, install_ref?: string): Promise<void> {
    return this.call<void>("install", { ref, install_ref });
  }

  /** Update a plugin. */
  update(name: string, install_ref?: string): Promise<void> {
    return this.call<void>("update", { name, install_ref });
  }

  /** Remove a plugin. */
  remove(name: string): Promise<void> {
    return this.call<void>("remove", { name });
  }

  /** Enable or disable a plugin. */
  set_enabled(name: string, on: boolean): Promise<void> {
    return this.call<void>("set_enabled", { name, on });
  }

  /** Add a marketplace. */
  add_marketplace(url: string): Promise<void> {
    return this.call<void>("add_marketplace", { url });
  }

  /** Remove a marketplace. */
  remove_marketplace(name: string): Promise<void> {
    return this.call<void>("remove_marketplace", { name });
  }

  /** Refresh marketplaces. */
  refresh_marketplaces(name?: string): Promise<void> {
    return this.call<void>("refresh_marketplaces", { name });
  }
}

/** Installed extensions. Read-only, apart from this extension's own settings. */
export class HostExtensions extends HostObject {
  static readonly PATH = "extensions";
  /** Every installed extension. */
  readonly installed: Property<ExtensionInfo[]>;
  /** An extension's health moved. */
  readonly state_changed: Signal<ExtensionStateChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "extensions", window, session);
    this.installed = new Property(this, "installed", false);
    this.state_changed = new Signal("extension.state-changed");
  }

  /** Change this extension's own settings. */
  set_settings(values: Record<string, JsonValue>): Promise<SettingsChange> {
    return this.call<SettingsChange>("set_settings", { values });
  }
}

/** Hooks. */
export class HostHooks extends HostObject {
  static readonly PATH = "hooks";
  /** Every hook. */
  readonly details: Property<HookEntry[]>;
  /** Hooks were reloaded. */
  readonly changed: Signal<CollectionChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "hooks", window, session);
    this.details = new Property(this, "details", false);
    this.changed = new Signal("hooks.changed");
  }

  /** Reload hooks. */
  reload(): Promise<void> {
    return this.call<void>("reload", {});
  }

  /** Run the session-start hooks. */
  fire_session_start(): Promise<void> {
    return this.call<void>("fire_session_start", {});
  }
}

/** What the agent may do without asking. */
export class HostPermissions extends HostObject {
  static readonly PATH = "permissions";
  /** `default`, `plan`, `acceptEdits` or `bypassPermissions`. */
  readonly mode: Property<string>;
  /** The mode changed. */
  readonly mode_changed: Signal<PermissionModeChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "permissions", window, session);
    this.mode = new Property(this, "mode", false);
    this.mode_changed = new Signal("permissions.mode_changed");
  }

  /** Would this tool call be allowed, asked or denied? One of `allow`, `ask` or `deny`. */
  check(tool_name: string, func_name: string, tool_args?: Record<string, JsonValue>): Promise<string> {
    return this.call<string>("check", { tool_name, func_name, tool_args });
  }

  /** Save a permission rule. */
  save_rule(rule: string, level: string): Promise<void> {
    return this.call<void>("save_rule", { rule, level });
  }
}

/** The group policy in force. */
export class HostPolicy extends HostObject {
  static readonly PATH = "policy";
  /** The group's policy pack. */
  readonly pack: Property<PolicyPack>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "policy", window, session);
    this.pack = new Property(this, "pack", false);
  }
}

/** Whether the person is signed in to igni. Never their session or a credential. */
export class HostAccount extends HostObject {
  static readonly PATH = "account";
  /** Who is signed in. */
  readonly status: Property<Account>;
  /** Someone signed in or out. */
  readonly changed: Signal<Account>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "account", window, session);
    this.status = new Property(this, "status", false);
    this.changed = new Signal("account.changed");
  }

  /** Start the person's own sign-in. Its result is theirs. */
  sign_in(): Promise<void> {
    return this.call<void>("sign_in", {});
  }

  /** Sign the person out. */
  sign_out(): Promise<Account> {
    return this.call<Account>("sign_out", {});
  }
}

/** The floor's notifications. Its own always; everyone's with `notifications`. */
export class HostNotifications extends HostObject {
  static readonly PATH = "notifications";
  /** Newest first. */
  readonly list: Property<NotificationEntry[]>;
  /** Unread counts. */
  readonly unread: Property<NotificationCounts>;
  /** The counts moved. */
  readonly changed: Signal<NotificationCounts>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "notifications", window, session);
    this.list = new Property(this, "list", false);
    this.unread = new Property(this, "unread", false);
    this.changed = new Signal("notifications.changed");
  }

  /** Tell the person at this machine something. It never leaves the machine. */
  notify(notification: LocalNotification): Promise<void> {
    return this.call<void>("notify", { notification });
  }

  /** Mark notifications read: these ids, one source, or all of them. */
  mark_read(ids?: string[], source?: string): Promise<NotificationCounts> {
    return this.call<NotificationCounts>("mark_read", { ids, source });
  }
}

/** This extension, as the host sees it. */
export class HostSelf extends HostObject {
  static readonly PATH = "self";
  /** Its manifest id. */
  readonly id: Property<string>;
  /** Its settings. Writable. */
  readonly settings: Property<Record<string, JsonValue>>;
  /** Its own entry. */
  readonly state: Property<ExtensionInfo>;
  /** Its home on the web: its service's URL, when it has one. */
  readonly web_url: Property<string | null>;
  /** Its settings changed. */
  readonly settings_changed: Signal<SettingsChange>;
  /** Its health moved. */
  readonly state_changed: Signal<ExtensionStateChange>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "self", window, session);
    this.id = new Property(this, "id", false);
    this.settings = new Property(this, "settings", true);
    this.state = new Property(this, "state", false);
    this.web_url = new Property(this, "web_url", false);
    this.settings_changed = new Signal("self.settings_changed");
    this.state_changed = new Signal("self.state_changed");
  }

  /** Say this extension is working inside igni's process, so the process is not suspended under it (in the cloud, its VM). A lease for `reason`: it expires after `ttl_seconds` (default and at most 600) unless renewed by calling again with the same reason, so an extension that stops answering cannot keep igni awake. Shown in `app.activity`'s `busy`. */
  busy(reason: string, ttl_seconds?: number): Promise<BusyLease> {
    return this.call<BusyLease>("busy", { reason, ttl_seconds });
  }

  /** Let go of the lease `busy` took for `reason`. Nothing happens if there is none. */
  done(reason: string): Promise<void> {
    return this.call<void>("done", { reason });
  }
}

/** The root. `changed` reports every change anywhere in the model, for an extension that wants to see all of it; each delivery needs the grant of the member that changed. */
export class Host extends HostObject {
  static readonly PATH = "";
  /** `host.app`. igni itself: how it presents things, which version, whether it is connected. */
  readonly app: HostApp;
  /** `host.windows`. Every open igni window. Address one window's UI with `host.windows.ui(id)`. */
  readonly windows: HostWindows;
  /** `host.ui`. What a window shows — the model its views bind to. `host.ui` is the active window, the one the person last used; `host.windows.ui(id)` any window. igni's own views write here too, by the same path, so every change below is a signal whoever made it. */
  readonly ui: HostUi;
  /** `host.sessions`. The sessions of this project, and which one the active window shows. Reach any session's chat, without showing it, with `host.sessions.chat(id)`. */
  readonly sessions: HostSessions;
  /** `host.chat`. The conversation in the current session. Signals carry the session they happened in, and arrive for every live session. `host.sessions.chat(id)` is the same object for any session of this project, without showing it: its properties read that session, and `post`, `queue`, `append` and `replace` write there (with `sessions.post` as well). A message posted there starts a run, or waits for the run already going there — never answering an approval. Its other methods act only on the session on screen. */
  readonly chat: HostChat;
  /** `host.plan`. Plan mode: the plan the agent proposed. */
  readonly plan: HostPlan;
  /** `host.tasks`. The agent's todo list and its sub-agent tasks. */
  readonly tasks: HostTasks;
  /** `host.loop`. `/loop`: a prompt repeated until done. */
  readonly loop: HostLoop;
  /** `host.commands`. Slash commands and skills. */
  readonly commands: HostCommands;
  /** `host.agents`. Agent definitions. */
  readonly agents: HostAgents;
  /** `host.workflows`. Workflows: scripted runs. */
  readonly workflows: HostWorkflows;
  /** `host.scheduler`. Scheduled tasks. */
  readonly scheduler: HostScheduler;
  /** `host.processes`. Background shells. */
  readonly processes: HostProcesses;
  /** `host.workspace`. The project, as far as the extension's workspace grant reaches. */
  readonly workspace: HostWorkspace;
  /** `host.models`. Models. */
  readonly models: HostModels;
  /** `host.mcp`. MCP servers. */
  readonly mcp: HostMcp;
  /** `host.plugins`. Plugins and marketplaces. */
  readonly plugins: HostPlugins;
  /** `host.extensions`. Installed extensions. Read-only, apart from this extension's own settings. */
  readonly extensions: HostExtensions;
  /** `host.hooks`. Hooks. */
  readonly hooks: HostHooks;
  /** `host.permissions`. What the agent may do without asking. */
  readonly permissions: HostPermissions;
  /** `host.policy`. The group policy in force. */
  readonly policy: HostPolicy;
  /** `host.account`. Whether the person is signed in to igni. Never their session or a credential. */
  readonly account: HostAccount;
  /** `host.notifications`. The floor's notifications. Its own always; everyone's with `notifications`. */
  readonly notifications: HostNotifications;
  /** `host.self`. This extension, as the host sees it. */
  readonly self: HostSelf;
  /** Anything changed. Carries the member's path and its new value. */
  readonly changed: Signal<Change>;

  /**
   * The object igni hands a page, bound to a host and to the window
   * or session it was reached through.
   *
   * A page never builds one of these: `bridge.host` is already the
   * right one, and a second would be a second conversation.
   */
  constructor(
    link: HostLink,
    window: string | null = null,
    session: string | null = null,
  ) {
    super(link, "", window, session);
    this.app = new HostApp(link, window, session);
    this.windows = new HostWindows(link, window, session);
    this.ui = new HostUi(link, window, session);
    this.sessions = new HostSessions(link, window, session);
    this.chat = new HostChat(link, window, session);
    this.plan = new HostPlan(link, window, session);
    this.tasks = new HostTasks(link, window, session);
    this.loop = new HostLoop(link, window, session);
    this.commands = new HostCommands(link, window, session);
    this.agents = new HostAgents(link, window, session);
    this.workflows = new HostWorkflows(link, window, session);
    this.scheduler = new HostScheduler(link, window, session);
    this.processes = new HostProcesses(link, window, session);
    this.workspace = new HostWorkspace(link, window, session);
    this.models = new HostModels(link, window, session);
    this.mcp = new HostMcp(link, window, session);
    this.plugins = new HostPlugins(link, window, session);
    this.extensions = new HostExtensions(link, window, session);
    this.hooks = new HostHooks(link, window, session);
    this.permissions = new HostPermissions(link, window, session);
    this.policy = new HostPolicy(link, window, session);
    this.account = new HostAccount(link, window, session);
    this.notifications = new HostNotifications(link, window, session);
    this.self = new HostSelf(link, window, session);
    this.changed = new Signal("changed");
  }

  /** Ask igni's local decision model (Laya) typed questions about a context, in one pass on this machine. `context` is named text fields — at most 8, 6,000 characters in all — that the questions quote in backticks; `questions` are 1–16 `DecisionQuestion`s. A context the model would have to cut is refused (`invalid`), never answered from part of it; a model that cannot be loaded answers `unavailable`. Zero-shot accuracy is modest: measure it on your own data before acting on an answer, and use the probabilities, not just the answer. */
  decide(context: Record<string, string>, questions: DecisionQuestion[]): Promise<Decision> {
    return this.call<Decision>("decide", { context, questions });
  }

  /** `decide` for up to 16 contexts at once, sharing forward passes. One decision per context, in order. */
  decide_batch(contexts: (Record<string, string>)[], questions: DecisionQuestion[]): Promise<Decision[]> {
    return this.call<Decision[]>("decide_batch", { contexts, questions });
  }
}


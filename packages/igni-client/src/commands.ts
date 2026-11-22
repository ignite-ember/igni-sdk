// Commands in a VM: run a shell command in a producer's microVM and stream its output.
//
// This goes through Fleet's gateway (POST /v1/commands), not through igni: the
// gateway wakes the VM and its node runs the command, streaming stdout and stderr
// back as NDJSON. igni server decides who may run what and keeps an audit record.

import {
  AuthError,
  GROUP_LOCAL_ONLY,
  GroupIsLocalOnly,
  IgniClientError,
  NotAllowed,
  Unavailable,
  reasonToken,
} from "./errors.js";
import type { Fleet } from "./targets.js";

const PRODUCER_KINDS = ["person", "app", "space"];
const MAX_COMMAND_BYTES = 16 * 1024;

/** The producer's VM as the gateway sees it right now. Reading it never wakes the VM. */
export interface VmState {
  state: string;
  signed_in: boolean;
}

/** Who the gateway says this client is, and the state of its VM. */
export interface Me {
  producer: string;
  org: string;
  group: string | null;
  expires_at: number;
  vm: VmState | null;
}

/** A piece of a command's output, as it was written. */
export interface CommandOutput {
  stream: "stdout" | "stderr";
  data: Buffer;
  text: string;
}

/** How a command ended. */
export interface CommandFinished {
  exit_code: number | null;
  signal: number | null;
  timed_out: boolean;
  killed: boolean;
  duration_ms: number | null;
  error: string | null;
  streamed: boolean;
  ok: boolean;
}

function finished(raw: Record<string, unknown>): CommandFinished {
  const exitCode = typeof raw.exit_code === "number" ? raw.exit_code : null;
  const error = typeof raw.error === "string" ? raw.error : null;
  return {
    exit_code: exitCode,
    signal: typeof raw.signal === "number" ? raw.signal : null,
    timed_out: raw.timed_out === true,
    killed: raw.killed === true,
    duration_ms: typeof raw.duration_ms === "number" ? raw.duration_ms : null,
    error,
    streamed: raw.streamed !== false,
    ok: exitCode === 0 && !error,
  };
}

interface CommandRequest {
  producer: { kind: string; id: string };
  command: string;
  timeout_s: number;
}

function parseProducer(producer: string): { kind: string; id: string } {
  const [kind, id] = [producer.slice(0, producer.indexOf(":")), producer.slice(producer.indexOf(":") + 1)];
  if (!PRODUCER_KINDS.includes(kind) || !id) {
    throw new Error("a producer is 'person:<id>', 'app:<id>' or 'space:<id>'");
  }
  return { kind, id };
}

function checkCommand(command: string, timeoutS: number): void {
  if (!command || Buffer.byteLength(command) > MAX_COMMAND_BYTES) {
    throw new Error("a command is 1 byte to 16 KiB");
  }
  if (!(timeoutS >= 1 && timeoutS <= 3600)) {
    throw new Error("timeoutS is 1 to 3600");
  }
}

/** A non-2xx answer from the gateway, and the error it means for the caller. */
export async function gatewayError(response: Response): Promise<IgniClientError> {
  const text = (await response.text()).trim();
  let detail = text;
  let code = "";
  try {
    const body = JSON.parse(text) as { detail?: unknown; error_description?: unknown; error?: unknown };
    detail = String(body.detail ?? body.error_description ?? body.error ?? text);
    code = typeof body.error === "string" ? body.error : "";
  } catch {
    // not JSON: the text is the reason
  }
  if (response.status === 401) {
    return new AuthError(`the gateway refused the credential: ${detail}`);
  }
  if (response.status === 403 && [reasonToken(code), reasonToken(detail)].includes(GROUP_LOCAL_ONLY)) {
    return new GroupIsLocalOnly(
      `the gateway refused: the person's group runs igni only on their own computer (${detail}); use the local igni`,
    );
  }
  if ([400, 403, 404, 422].includes(response.status)) {
    return new NotAllowed(`the gateway refused: ${detail}`);
  }
  return new Unavailable(`the gateway answered ${response.status}: ${detail}`);
}

/** A command being run. Iterate it for its output; `finished` says how it ended. */
export class CommandRun implements AsyncIterable<CommandOutput> {
  finished: CommandFinished | null = null;
  stdout = "";
  stderr = "";
  private started = false;

  constructor(
    private readonly fleet: Fleet,
    private readonly request: CommandRequest,
    private readonly token: string,
  ) {}

  [Symbol.asyncIterator](): AsyncIterator<CommandOutput> {
    return this.lines();
  }

  /** Run it to the end, keeping its output in `stdout` and `stderr`. */
  async wait(): Promise<CommandFinished> {
    for await (const _ of this) {
      void _;
    }
    return this.finished!;
  }

  private async *lines(): AsyncGenerator<CommandOutput> {
    if (this.started) {
      throw new Error("a command's output can be read once");
    }
    this.started = true;
    let response: Response;
    try {
      response = await this.fleet.stream("POST", "/v1/commands", this.token, { body: this.request });
    } catch (error) {
      throw new Unavailable(`the gateway did not answer: ${String(error)}`);
    }
    if (response.status !== 200) {
      throw await gatewayError(response);
    }
    for await (const line of ndjson(response)) {
      const output = this.take(line);
      if (output) {
        yield output;
      }
    }
    if (this.finished === null) {
      this.finished = finished({ error: "the gateway ended the output without a result" });
    }
  }

  private take(value: Record<string, unknown>): CommandOutput | null {
    if (value.done) {
      const { done: _done, ...rest } = value;
      void _done;
      this.finished = finished(rest);
      return null;
    }
    if (value.stream === "stdout" || value.stream === "stderr") {
      const data = Buffer.from(String(value.data_b64 ?? ""), "base64");
      const output: CommandOutput = { stream: value.stream, data, text: data.toString("utf-8") };
      if (output.stream === "stdout") {
        this.stdout += output.text;
      } else {
        this.stderr += output.text;
      }
      return output;
    }
    // command / woken / unknown lines carry no output
    return null;
  }
}

async function* ndjson(response: Response): AsyncGenerator<Record<string, unknown>> {
  const body = response.body;
  if (!body) {
    return;
  }
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let newline = buffer.indexOf("\n");
    while (newline >= 0) {
      const text = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      newline = buffer.indexOf("\n");
      if (text) {
        yield parseLine(text);
      }
    }
  }
  const rest = buffer.trim();
  if (rest) {
    yield parseLine(rest);
  }
}

function parseLine(text: string): Record<string, unknown> {
  try {
    const value = JSON.parse(text) as unknown;
    return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

/** Run commands in VMs through Fleet's gateway. */
export class Commands {
  private cachedMe: Me | null = null;

  constructor(private readonly fleet: Fleet) {}

  /** Who this client is to the gateway. */
  async me(): Promise<Me> {
    const response = await this.fleet.request("GET", "/v1/me");
    if (response.status !== 200) {
      throw await gatewayError(response);
    }
    const raw = (await response.json()) as Record<string, unknown>;
    this.cachedMe = {
      producer: String(raw.producer ?? ""),
      org: typeof raw.org === "string" ? raw.org : "",
      group: typeof raw.group === "string" ? raw.group : null,
      expires_at: typeof raw.expires_at === "number" ? raw.expires_at : 0,
      vm: isVm(raw.vm) ? (raw.vm as unknown as VmState) : null,
    };
    return this.cachedMe;
  }

  /** Start `command` in a VM — this producer's own unless `producer` (`kind:id`) names another. */
  async run(command: string, opts: { timeoutS?: number; producer?: string } = {}): Promise<CommandRun> {
    const timeoutS = opts.timeoutS ?? 600;
    checkCommand(command, timeoutS);
    const producer = opts.producer ?? (this.cachedMe ?? (await this.me())).producer;
    const request: CommandRequest = { producer: parseProducer(producer), command, timeout_s: timeoutS };
    return new CommandRun(this.fleet, request, await this.fleet.auth.token());
  }
}

function isVm(value: unknown): boolean {
  return Boolean(value) && typeof value === "object" && typeof (value as { state?: unknown }).state === "string";
}

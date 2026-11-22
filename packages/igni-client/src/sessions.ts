// Sessions: igni's conversations, each with its own history, model and project.

import { IgniSessions, SessionApi } from "./api.generated.js";
import { ApprovalRequested, type Policy } from "./approvals.js";
import { Caller } from "./calls.js";
import type { Connection } from "./connection.js";
import type { Event } from "./events.js";
import type { RunPaused, SessionListEntry } from "./models.generated.js";
import { Reply } from "./replies.js";
import { Approver } from "./approvals.js";
import { Run, answerElsewhere, type RunItem } from "./runs.js";

/** One of igni's sessions, attached to this client. */
export class Session extends SessionApi {
  /** The folder this session works in, as igni bound it. */
  projectDir: string;

  constructor(
    private readonly conn: Connection,
    sessionId: string,
    projectDir = "",
  ) {
    super(new Caller(conn, sessionId));
    this.projectDir = projectDir;
  }

  get id(): string {
    return this.caller.sessionId;
  }

  /** Send a prompt and follow the run it starts, event by event. */
  send(
    text: string,
    opts: { files?: Record<string, string>; force?: boolean } = {},
  ): AsyncGenerator<RunItem> {
    const frame = {
      type: "user_message",
      id: this.conn.router.newId("run"),
      session_id: this.id,
      text,
      file_contents: opts.files ?? {},
      client_id: this.conn.clientId,
      force: opts.force ?? false,
    };
    return new Run(this.conn, this.id).stream(frame);
  }

  /** Send a prompt and return the whole answer once the run ends. */
  async ask(
    text: string,
    opts: { files?: Record<string, string>; approve?: Policy } = {},
  ): Promise<Reply> {
    return Reply.collect(
      this.send(text, { files: opts.files }),
      new Approver(opts.approve),
      () => this.conn.vmCredential,
      this.conn.target.describe(),
    );
  }

  /** Add a prompt for after the run that is going; it starts nothing now. */
  async queue(text: string): Promise<void> {
    await this.conn.send({
      type: "queue_message",
      session_id: this.id,
      text,
      client_id: this.conn.clientId,
    });
  }

  /** Every message igni sends about this session from now on, from every client's runs. */
  async *events(): AsyncGenerator<Event | ApprovalRequested> {
    const queue = this.conn.router.listen();
    try {
      for (;;) {
        const event = await queue.get();
        if (event.session_id !== this.id) {
          continue;
        }
        if (event.type === "run_paused") {
          yield new ApprovalRequested(event as unknown as RunPaused, answerElsewhere(this.conn, this.id));
          continue;
        }
        yield event as unknown as Event;
      }
    } finally {
      this.conn.router.unlisten(queue);
    }
  }

  toString(): string {
    return `Session(${this.id})`;
  }
}

/** Create, open and list sessions; `attach()` is igni's own call underneath. */
export class Sessions extends IgniSessions {
  private readonly attached = new Map<string, Session>();

  constructor(private readonly conn: Connection) {
    super(new Caller(conn));
  }

  /** A new session, working in `projectDir` (igni's own project when left out). */
  async create(projectDir?: string): Promise<Session> {
    return this.attachInternal(undefined, projectDir);
  }

  /** An existing session. Approvals it was waiting for are shown again (Session.events()). */
  async open(sessionId: string, projectDir?: string): Promise<Session> {
    return this.attachInternal(sessionId, projectDir);
  }

  /** The session igni opened at start. */
  async default(): Promise<Session> {
    const sessionId = await new SessionApi(new Caller(this.conn)).current_id();
    return this.attachInternal(sessionId || undefined, undefined);
  }

  /** Every session kept in igni's own project, newest first. */
  async list(): Promise<SessionListEntry[]> {
    const listed = await new SessionApi(new Caller(this.conn)).list_sessions();
    return listed.sessions ?? [];
  }

  /** Attach every session again — after igni moved, or the socket was opened again. */
  async reattach(): Promise<void> {
    for (const session of [...this.attached.values()]) {
      await this.attachInternal(session.id, session.projectDir || undefined);
    }
  }

  private async attachInternal(sessionId?: string, projectDir?: string): Promise<Session> {
    const attached = await this.attach(projectDir ?? "", sessionId ?? "");
    const session = this.attached.get(attached.session_id ?? "") ?? new Session(this.conn, attached.session_id ?? "");
    session.projectDir = attached.project_dir ?? "";
    this.attached.set(attached.session_id ?? "", session);
    return session;
  }
}

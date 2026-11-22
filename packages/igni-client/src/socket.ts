// The one transport the core depends on, and the `ws`-backed factory for Node.
//
// The core (connection, calls, sessions) is transport-agnostic behind `Socket`
// and `SocketFactory`; a browser build can inject a native-WebSocket factory
// without touching anything above. Only Node's factory ships in 0.1.0.

import WebSocket from "ws";

/** One open socket to igni. */
export interface Socket {
  send(data: string): void;
  close(code?: number, reason?: string): Promise<void>;
  onMessage(cb: (data: string) => void): void;
  onClose(cb: (code: number, reason: string) => void): void;
  /** The negotiated subprotocol. */
  readonly protocol: string;
  /** The close code, once the socket has closed. */
  readonly closeCode: number | undefined;
  /** The close reason, once the socket has closed. */
  readonly closeReason: string;
}

/** How a `Socket` is opened. */
export interface SocketFactory {
  open(url: string, subprotocols: string[], headers?: Record<string, string>): Promise<Socket>;
}

/** A handshake igni refused with an HTTP status before the socket opened. */
export class HandshakeError extends Error {
  constructor(
    readonly status: number,
    readonly body: string,
  ) {
    super(`handshake refused with ${status}`);
    this.name = "HandshakeError";
  }
}

const MAX_FRAME = 64 * 1024 * 1024;
const OPEN_TIMEOUT_MS = 30_000;

class WsSocket implements Socket {
  closeCode: number | undefined;
  closeReason = "";
  private buffered: string[] = [];
  private onMessageCb: ((data: string) => void) | null = null;
  private onCloseCb: ((code: number, reason: string) => void) | null = null;

  constructor(private readonly ws: WebSocket) {
    ws.on("message", (data: WebSocket.RawData) => {
      const text = typeof data === "string" ? data : data.toString();
      if (this.onMessageCb) {
        this.onMessageCb(text);
      } else {
        this.buffered.push(text);
      }
    });
    ws.on("close", (code: number, reason: Buffer) => {
      this.closeCode = code;
      this.closeReason = reason.toString();
      this.onCloseCb?.(code, this.closeReason);
    });
    // After the handshake, an error is just a closed line.
    ws.on("error", () => undefined);
  }

  get protocol(): string {
    return this.ws.protocol;
  }

  send(data: string): void {
    this.ws.send(data);
  }

  onMessage(cb: (data: string) => void): void {
    this.onMessageCb = cb;
    const held = this.buffered;
    this.buffered = [];
    for (const text of held) {
      cb(text);
    }
  }

  onClose(cb: (code: number, reason: string) => void): void {
    this.onCloseCb = cb;
    if (this.closeCode !== undefined) {
      cb(this.closeCode, this.closeReason);
    }
  }

  close(code?: number, reason?: string): Promise<void> {
    return new Promise((resolve) => {
      if (this.ws.readyState === WebSocket.CLOSED) {
        resolve();
        return;
      }
      this.ws.once("close", () => resolve());
      try {
        this.ws.close(code, reason);
      } catch {
        resolve();
      }
    });
  }
}

/** The `ws`-backed factory used on Node: it can set headers (Fleet's bearer). */
export const nodeSocketFactory: SocketFactory = {
  open(url, subprotocols, headers) {
    return new Promise<Socket>((resolve, reject) => {
      const ws = new WebSocket(url, subprotocols, {
        headers,
        maxPayload: MAX_FRAME,
        perMessageDeflate: false,
        handshakeTimeout: OPEN_TIMEOUT_MS,
      });
      ws.once("open", () => {
        ws.removeAllListeners("unexpected-response");
        resolve(new WsSocket(ws));
      });
      ws.once("unexpected-response", (_req, res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk: Buffer) => chunks.push(chunk));
        res.on("end", () =>
          reject(new HandshakeError(res.statusCode ?? 0, Buffer.concat(chunks).toString())),
        );
        res.on("error", () => reject(new HandshakeError(res.statusCode ?? 0, "")));
      });
      ws.once("error", (error: Error) => reject(error));
    });
  },
};

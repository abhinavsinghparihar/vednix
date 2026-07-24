/**
 * Vednix WebSocket client — mirrors backend/docs API.md protocol exactly.
 * Auto-reconnect with backoff; frames are strictly typed (mirrors api/schemas.py).
 */

export type CoreStateName =
  | "IDLE" | "LISTENING" | "THINKING" | "SPEAKING"
  | "EXECUTING" | "SEARCHING" | "LEARNING" | "UPDATING";

export type Language = "auto" | "hi" | "hinglish" | "en";

export type ServerFrame =
  | { type: "state_changed"; state: CoreStateName }
  | { type: "message_started"; message_id: string; conversation_id: string }
  | { type: "token"; message_id: string; content: string }
  | { type: "message_done"; message_id: string; conversation_id: string; plugins: string[]; cancelled: boolean }
  | { type: "conversation_created"; conversation_id: string; title: string }
  | { type: "title_updated"; conversation_id: string; title: string }
  | { type: "error"; code: string; message: string }
  | { type: "pong" };

export interface OutgoingUserMessage {
  type: "user_message";
  content: string;
  conversation_id: string | null;
  model?: string | null;
  language?: Language | null;
  temperature?: number | null;
}

export type WSStatus = "connecting" | "open" | "closed";

type FrameHandler = (frame: ServerFrame) => void;
type StatusHandler = (status: WSStatus) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private retries = 0;
  private closedByUser = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private url: string,
    private onFrame: FrameHandler,
    private onStatus: StatusHandler,
  ) {}

  connect(): void {
    this.closedByUser = false;
    this.onStatus("connecting");
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws.onopen = () => {
      this.retries = 0;
      this.onStatus("open");
    };
    this.ws.onmessage = (event) => {
      try {
        this.onFrame(JSON.parse(event.data as string) as ServerFrame);
      } catch {
        // malformed frames are ignored — server never sends them
      }
    };
    this.ws.onclose = () => {
      this.onStatus("closed");
      if (!this.closedByUser) this.scheduleReconnect();
    };
    this.ws.onerror = () => this.ws?.close();
  }

  private scheduleReconnect(): void {
    if (this.closedByUser || this.retries >= 8) return;
    const delay = Math.min(8000, 400 * 2 ** this.retries++);
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  get isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  send(payload: OutgoingUserMessage | { type: "cancel" } | { type: "ping" }): boolean {
    if (!this.isOpen) return false;
    this.ws!.send(JSON.stringify(payload));
    return true;
  }

  close(): void {
    this.closedByUser = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}

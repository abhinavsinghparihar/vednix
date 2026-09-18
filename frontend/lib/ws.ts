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
  | { type: "message_done"; message_id: string; conversation_id: string; plugins: string[]; kb_sources?: string[]; sources?: { title: string; url: string }[]; steps?: { step: string; detail: string }[]; cancelled: boolean }
  | { type: "agent_step"; step: string; detail: string }
  | { type: "conversation_created"; conversation_id: string; title: string }
  | { type: "title_updated"; conversation_id: string; title: string }
  | { type: "error"; code: string; message: string }
  | { type: "pong" };

export interface OutgoingUserMessage {
  type: "user_message";
  content: string;
  conversation_id: string | null;
  model?: string | null;
  provider?: string | null;
  language?: Language | null;
  temperature?: number | null;
  attachments?: string[];
  internet?: boolean; // Phase 5: web research before the LLM turn
  multi_agent?: boolean; // Phase 6: planner/researcher/critic agent loop
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
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) return;
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
    this.ws.onclose = (ev) => {
      this.onStatus("closed");
      // 4401/4403 = the session gate rejected us (locked API, no/expired
      // session). Retrying forever would just spin — stop; the auth store
      // reroutes the shell and a fresh WSClient is built after sign-in.
      if (ev.code === 4401 || ev.code === 4403) {
        this.closedByUser = true;
        return;
      }
      if (!this.closedByUser) this.scheduleReconnect();
    };
    this.ws.onerror = () => this.ws?.close();
  }

  private scheduleReconnect(): void {
    if (this.closedByUser || this.retries >= 8 || this.reconnectTimer) return;
    const delay = Math.min(8000, 400 * 2 ** this.retries++);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
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

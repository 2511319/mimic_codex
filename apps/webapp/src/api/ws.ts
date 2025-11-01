export type SyncMessage = {
  eventType: string;
  payload: unknown;
  traceId?: string | null;
  senderId?: string | null;
};

export type PartyWs = {
  connect: () => void;
  disconnect: () => void;
  send: (msg: SyncMessage) => void;
  onMessage: (cb: (msg: SyncMessage) => void) => void;
  onStatus: (cb: (status: "connected" | "disconnected" | "error") => void) => void;
};

export function buildWsUrl(baseUrl: string | undefined, campaignId: string): string {
  const base = baseUrl ?? (window.location.origin ?? "");
  const url = new URL(base);
  url.pathname = `/ws/campaign/${encodeURIComponent(campaignId)}`;
  url.search = "";
  url.hash = "";
  if (url.protocol === "http:") url.protocol = "ws:";
  if (url.protocol === "https:") url.protocol = "wss:";
  return url.toString();
}

function getEnvVar(name: string): string | undefined {
  const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env;
  return env?.[name];
}

export function createPartyWs(campaignId: string): PartyWs {
  const WS_BASE = getEnvVar("VITE_PARTY_WS_URL");
  const url = buildWsUrl(WS_BASE ?? getEnvVar("VITE_API_BASE_URL"), campaignId);

  let ws: WebSocket | null = null;
  const messageHandlers = new Set<(m: SyncMessage) => void>();
  const statusHandlers = new Set<(s: "connected" | "disconnected" | "error") => void>();

  function notifyStatus(s: "connected" | "disconnected" | "error"): void {
    for (const cb of statusHandlers) cb(s);
  }

  function connect(): void {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    ws = new WebSocket(url);
    ws.onopen = () => notifyStatus("connected");
    ws.onclose = () => notifyStatus("disconnected");
    ws.onerror = () => notifyStatus("error");
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data as string) as SyncMessage;
        for (const cb of messageHandlers) cb(data);
      } catch {
        // ignore invalid JSON
      }
    };
  }

  function disconnect(): void {
    if (ws) {
      try { ws.close(); } catch { /* ignore */ }
      ws = null;
    }
  }

  function send(msg: SyncMessage): void {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try { ws.send(JSON.stringify(msg)); } catch { /* ignore */ }
  }

  return {
    connect,
    disconnect,
    send,
    onMessage(cb) { messageHandlers.add(cb); },
    onStatus(cb) { statusHandlers.add(cb); }
  };
}

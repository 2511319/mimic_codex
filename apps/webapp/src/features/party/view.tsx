import type { JSX } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { createPartyWs, type SyncMessage } from "../../api/ws";
import { validateEventEnvelope } from "../../lib/validation";

export default function PartyFeature(): JSX.Element {
  const [campaignId, setCampaignId] = useState<string>("cmp1");
  const [status, setStatus] = useState<"connected" | "disconnected" | "error">("disconnected");
  const [eventType, setEventType] = useState<string>("ping");
  const [payload, setPayload] = useState<string>("{\n  \"hello\": \"world\"\n}");
  const [log, setLog] = useState<SyncMessage[]>([]);
  const wsRef = useRef<ReturnType<typeof createPartyWs> | null>(null);

  const ws = useMemo(() => createPartyWs(campaignId), [campaignId]);

  useEffect(() => {
    wsRef.current = ws;
    ws.onMessage((m) => setLog((prev) => [m, ...prev].slice(0, 50)));
    ws.onStatus((s) => setStatus(s));
    return () => {
      ws.disconnect();
    };
  }, [ws]);

  const connect = (): void => wsRef.current?.connect();
  const disconnect = (): void => wsRef.current?.disconnect();
  const send = (): void => {
    try {
      const parsed = JSON.parse(payload) as unknown;
      const candidate: SyncMessage = { eventType, payload: parsed };
      const result = validateEventEnvelope(candidate);
      if (!result.valid) {
        alert("Сообщение не соответствует схеме envelope"); // eslint-disable-line no-alert
        return;
      }
      wsRef.current?.send(candidate);
    } catch {
      // простая защита от невалидного JSON
      alert("Payload должен быть валидным JSON"); // eslint-disable-line no-alert
    }
  };

  return (
    <section>
      <h3>Party</h3>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <label>
          Кампания:
          <input value={campaignId} onChange={(e) => setCampaignId(e.target.value)} />
        </label>
        <button type="button" onClick={connect}>Подключиться</button>
        <button type="button" onClick={disconnect}>Отключиться</button>
        <span>Статус: {status}</span>
      </div>
      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <label>
            Событие:
            <input value={eventType} onChange={(e) => setEventType(e.target.value)} />
          </label>
          <label style={{ display: "block", marginTop: 8 }}>
            Payload (JSON):
            <textarea rows={8} value={payload} onChange={(e) => setPayload(e.target.value)} />
          </label>
          <button type="button" onClick={send}>Отправить</button>
        </div>
        <div>
          <strong>Лента событий</strong>
          <ul>
            {log.map((m, idx) => {
              const v = validateEventEnvelope(m);
              const ok = v.valid;
              return (
                <li key={`${m.eventType}-${idx}-${typeof m.payload}`}>
                  <code>{m.eventType}</code>
                  {" — "}
                  {JSON.stringify(m.payload)}
                  {!ok ? <em style={{ color: "crimson" }}> (invalid)</em> : null}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </section>
  );
}

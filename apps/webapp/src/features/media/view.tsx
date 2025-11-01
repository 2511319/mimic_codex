import type { Dispatch, JSX, SetStateAction } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { createMediaJob, readMediaJob, type MediaJobResponse, type MediaJobType } from "../../api/media";

type JobUI = {
  jobId: string;
  status: MediaJobResponse["status"];
  result?: Record<string, unknown> | null;
  error?: string | null;
};

type CacheEntry = {
  jobId: string;
  status: MediaJobResponse["status"];
  result?: Record<string, unknown> | null;
  error?: string | null;
  updatedAt: string;
};

type CacheMap = Record<string, CacheEntry>;

const CACHE_KEY = "rpgbot.media.cache";

export default function MediaFeature(): JSX.Element {
  const [type, setType] = useState<MediaJobType>("image");
  const [clientToken, setClientToken] = useState<string>("");
  const [payload, setPayload] = useState<string>(() => JSON.stringify({ prompt: "Ancient ruins" }, null, 2));
  const [job, setJob] = useState<JobUI | null>(null);
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [cache, setCache] = useState<CacheMap>(() => loadCache());

  const defaultPayload = useMemo(() => {
    return type === "tts" ? { text: "Hello" } : { prompt: "Ancient ruins" };
  }, [type]);

  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
      }
    };
  }, []);

  const startPolling = useCallback((jobId: string, token?: string) => {
    if (pollingRef.current) {
      clearTimeout(pollingRef.current);
      pollingRef.current = null;
    }

    let delay = 200; // backoff
    const tick = async (): Promise<void> => {
      try {
        const resp = await readMediaJob(jobId);
        setJob({ jobId: resp.jobId, status: resp.status, result: resp.result ?? undefined, error: resp.error ?? undefined });
        if (token) {
          updateCache(token, {
            jobId: resp.jobId,
            status: resp.status,
            result: resp.result ?? undefined,
            error: resp.error ?? undefined,
            updatedAt: resp.updatedAt
          }, setCache);
        }
        if (resp.status === "succeeded" || resp.status === "failed") {
          pollingRef.current = null;
          return;
        }
        delay = Math.min(delay * 2, 2000);
        pollingRef.current = setTimeout(() => void tick(), delay);
      } catch {
        // остановить поллинг на ошибке сети
        pollingRef.current = null;
      }
    };
    pollingRef.current = setTimeout(() => void tick(), delay);
  }, []);

  const loadFromToken = useCallback(
    async (token: string) => {
      const cached = cache[token];
      if (!cached) {
        alert("Нет данных в кэше для указанного clientToken"); // eslint-disable-line no-alert
        return;
      }
      try {
        const resp = await readMediaJob(cached.jobId);
        setJob({ jobId: resp.jobId, status: resp.status, result: resp.result ?? undefined, error: resp.error ?? undefined });
        updateCache(token, {
          jobId: resp.jobId,
          status: resp.status,
          result: resp.result ?? undefined,
          error: resp.error ?? undefined,
          updatedAt: resp.updatedAt
        }, setCache);
        if (resp.status !== "succeeded" && resp.status !== "failed") {
          startPolling(resp.jobId, token);
        }
      } catch {
        alert("Не удалось получить задачу по clientToken"); // eslint-disable-line no-alert
      }
    },
    [cache, startPolling]
  );

  const submit = async (): Promise<void> => {
    try {
      const data = JSON.parse(payload) as Record<string, unknown>;
      const body = {
        jobType: type,
        payload: data,
        clientToken: clientToken || undefined
      };
      if (clientToken && cache[clientToken]) {
        await loadFromToken(clientToken);
        return;
      }
      const created = await createMediaJob(body);
      setJob({ jobId: created.jobId, status: created.status });
      if (created.clientToken) {
        updateCache(created.clientToken, {
          jobId: created.jobId,
          status: created.status,
          result: created.result ?? undefined,
          error: created.error ?? undefined,
          updatedAt: created.updatedAt
        }, setCache);
      }
      startPolling(created.jobId, created.clientToken ?? (clientToken || undefined));
    } catch {
      alert("Payload должен быть валидным JSON"); // eslint-disable-line no-alert
    }
  };

  return (
    <section>
      <h3>Media</h3>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <label>
          Тип:
          <select value={type} onChange={(e) => setType(e.target.value as MediaJobType)}>
            <option value="image">image</option>
            <option value="tts">tts</option>
          </select>
        </label>
        <label>
          clientToken:
          <input placeholder="опционально" value={clientToken} onChange={(e) => setClientToken(e.target.value)} />
        </label>
        <button type="button" onClick={() => setPayload(JSON.stringify(defaultPayload, null, 2))}>Заполнить пример</button>
        <button type="button" onClick={() => clientToken && void loadFromToken(clientToken)} disabled={!clientToken}>
          Получить по clientToken
        </button>
      </div>
      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <label>
            Payload (JSON):
            <textarea rows={10} value={payload} onChange={(e) => setPayload(e.target.value)} />
          </label>
          <button type="button" onClick={submit}>Отправить</button>
        </div>
        <div>
          <strong>Статус</strong>
          {job ? (
            <div>
              <div>jobId: <code>{job.jobId}</code></div>
              <div>status: <strong>{job.status}</strong></div>
              {job.result ? (
                <details>
                  <summary>Результат</summary>
                  <pre>{JSON.stringify(job.result, null, 2)}</pre>
                </details>
              ) : null}
              {job.error ? <div style={{ color: "crimson" }}>Ошибка: {job.error}</div> : null}
              {clientToken && cache[clientToken] ? (
                <div style={{ marginTop: 8, fontSize: "0.875rem", color: "#4b5563" }}>
                  Кэш обновлён: {new Date(cache[clientToken].updatedAt).toLocaleString()}
                </div>
              ) : null}
            </div>
          ) : (
            <div>Задача не создана</div>
          )}
        </div>
      </div>
    </section>
  );
}

function loadCache(): CacheMap {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as CacheMap;
    return parsed;
  } catch {
    return {};
  }
}

function persistCache(map: CacheMap): void {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(map));
  } catch {
    // ignore
  }
}

function updateCache(token: string, entry: CacheEntry, setCache: Dispatch<SetStateAction<CacheMap>>): void {
  if (!token) return;
  setCache((prev) => {
    const next: CacheMap = { ...prev, [token]: entry };
    persistCache(next);
    return next;
  });
}

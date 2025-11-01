import type { JSX } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createGeneration,
  fetchGenerationProfileDetail,
  fetchGenerationProfiles,
  type GenerationProfileDetail,
  type GenerationResult
} from "../../api/generation";

type RequestState =
  | { status: "idle" }
  | { status: "pending" }
  | { status: "success"; data: GenerationResult }
  | { status: "error"; message: string };

type ProfilesState = "loading" | "ready" | "error";
type DetailState = "idle" | "loading" | "ready" | "error";

export default function GenerationView(): JSX.Element {
  const [profiles, setProfiles] = useState<string[]>([]);
  const [profile, setProfile] = useState<string>("");
  const [profilesState, setProfilesState] = useState<ProfilesState>("loading");
  const [detailState, setDetailState] = useState<DetailState>("idle");
  const [profileDetail, setProfileDetail] = useState<GenerationProfileDetail | null>(null);
  const [prompt, setPrompt] = useState<string>("Describe a mysterious tavern encounter.");
  const [state, setState] = useState<RequestState>({ status: "idle" });

  useEffect(() => {
    let cancelled = false;
    const loadProfiles = async (): Promise<void> => {
      setProfilesState("loading");
      try {
        const list = await fetchGenerationProfiles();
        if (cancelled) return;
        setProfiles(list);
        const initial = list[0] ?? "";
        setProfile(initial);
        setProfilesState("ready");
      } catch {
        if (cancelled) return;
        setProfiles([]);
        setProfile("");
        setProfilesState("error");
      }
    };
    void loadProfiles();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!profile) {
      setProfileDetail(null);
      setDetailState("idle");
      return;
    }
    let cancelled = false;
    const loadDetail = async (): Promise<void> => {
      setDetailState("loading");
      try {
        const detail = await fetchGenerationProfileDetail(profile);
        if (cancelled) return;
        setProfileDetail(detail);
        setDetailState("ready");
      } catch {
        if (cancelled) return;
        setProfileDetail(null);
        setDetailState("error");
      }
    };
    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [profile]);

  const prettyJson = useMemo(() => {
    if (state.status !== "success") {
      return "";
    }
    return JSON.stringify(state.data.result, null, 2);
  }, [state]);

  const runGeneration = useCallback(async () => {
    if (!prompt.trim()) {
      setState({ status: "error", message: "Промпт не может быть пустым." });
      return;
    }
    if (!profile) {
      setState({ status: "error", message: "Нет доступных профилей." });
      return;
    }
    setState({ status: "pending" });
    try {
      const data = await createGeneration(profile, { prompt });
      setState({ status: "success", data });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Не удалось выполнить генерацию.";
      setState({ status: "error", message });
    }
  }, [profile, prompt]);

  return (
    <section>
      <h3>Generation</h3>
      <p>Запрашивает структурированный ответ от OpenAI через Gateway API.</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 640 }}>
        <label>
          Профиль:
          <select value={profile} disabled={profilesState !== "ready"} onChange={(event) => setProfile(event.target.value)}>
            {profiles.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        {profilesState === "error" ? (
          <p style={{ color: "crimson" }}>Не удалось загрузить список профилей. Проверьте конфигурацию Gateway.</p>
        ) : null}
        {detailState === "ready" && profileDetail ? (
          <div style={{ fontSize: "0.9rem", color: "#374151" }}>
            <p>
              Температура: <strong>{profileDetail.temperature}</strong>, max tokens: <strong>{profileDetail.maxOutputTokens}</strong>
            </p>
            <details>
              <summary>JSON Schema ответа</summary>
              <pre style={{ overflowX: "auto" }}>{JSON.stringify(profileDetail.responseSchema, null, 2)}</pre>
            </details>
          </div>
        ) : null}
        {detailState === "error" ? (
          <p style={{ color: "crimson" }}>Не удалось получить схему профиля. Попробуйте позже.</p>
        ) : null}
        <label>
          Промпт:
          <textarea rows={4} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
        </label>
        <button
          type="button"
          onClick={() => void runGeneration()}
          disabled={state.status === "pending" || profilesState !== "ready" || detailState === "loading"}
        >
          {state.status === "pending" ? "Генерация…" : "Сгенерировать"}
        </button>
        {state.status === "error" ? <p style={{ color: "crimson" }}>{state.message}</p> : null}
        {state.status === "success" ? (
          <div>
            <p>
              Профиль: <code>{state.data.profile}</code>
            </p>
            <details open>
              <summary>Результат</summary>
              <pre style={{ overflowX: "auto" }}>{prettyJson}</pre>
            </details>
          </div>
        ) : null}
      </div>
    </section>
  );
}

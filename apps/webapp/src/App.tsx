import { Suspense, useEffect, useMemo, useState } from "react";

import { fetchConfig, fetchHealth } from "./api/client";
import { AuthGate, AuthProvider, useAuth } from "./auth/AuthContext";
import { registry } from "./feature/registry";

type HealthState = {
  status: "loading" | "ready" | "error";
  message?: string;
};

function App(): JSX.Element {
  const initData = useMemo(() => new URLSearchParams(window.location.search).get("initData"), []);

  return (
    <AuthProvider initData={initData}>
      <Shell />
    </AuthProvider>
  );
}

export default App;

function Shell(): JSX.Element {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchConfig()
      .then((cfg) => {
        if (cancelled) return;
        const trace = cfg.traceId ? ` (trace ${cfg.traceId.slice(0, 8)})` : "";
        setHealth({ status: "ready", message: `API ${cfg.apiVersion}${trace}` });
      })
      .catch(() => {
        // ignore; fallback to /health already handled
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    fetchHealth()
      .then((payload) => {
        setHealth({ status: "ready", message: `API ${payload.apiVersion}` });
      })
      .catch(() => {
        setHealth({ status: "error", message: "API недоступен" });
      });
  }, []);

  return (
    <main className="app">
      <Header health={health} />
      <AuthSection />
      <hr />
      <section>
        <h2>Функции</h2>
        <AuthGate>
          <FeatureHost />
        </AuthGate>
      </section>
    </main>
  );
}

function Header({ health }: { health: HealthState }): JSX.Element {
  return (
    <header>
      <h1>RPG-Bot Mini App</h1>
      <p>
        Состояние сервиса: <strong>{health.status}</strong>
      </p>
      {health.message ? <p>{health.message}</p> : null}
      <ConfigTrace />
      <hr />
    </header>
  );
}

function AuthSection(): JSX.Element {
  const { state } = useAuth();

  let content: JSX.Element;
  if (state.status === "authenticated") {
    const profile = state.profile;
    const suffix = profile?.username ? `: @${profile.username}` : profile ? `: ${profile.firstName}` : "";
    content = <p>Вход выполнен{suffix}</p>;
  } else if (state.status === "checking") {
    content = <p>Выполняется вход…</p>;
  } else if (state.reason === "exchange_failed") {
    content = <p>Не удалось обменять initData. Попробуйте снова из Telegram.</p>;
  } else {
    content = <p>Не авторизован. Откройте Mini App из Telegram.</p>;
  }

  return (
    <section>
      <h2>Авторизация</h2>
      {content}
    </section>
  );
}

function ConfigTrace(): JSX.Element | null {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchConfig()
      .then((cfg) => {
        if (cancelled) return;
        if (cfg.traceId) {
          setText(`trace ${cfg.traceId.slice(0, 8)}`);
        }
      })
      .catch(() => {
        // ignore
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return text ? <p>{text}</p> : null;
}

function FeatureHost(): JSX.Element {
  const features = registry.list();
  const [activeId, setActiveId] = useState<string | null>(() => features[0]?.id ?? null);

  useEffect(() => {
    const current = registry.list();
    if (!current.some((f) => f.id === activeId)) {
      setActiveId(current[0]?.id ?? null);
    }
  }, [activeId]);

  const active = features.find((f) => f.id === activeId) ?? features[0] ?? null;

  if (!active) {
    return <p>Нет подключённых модулей</p>;
  }

  return (
    <div>
      <FeatureTabs features={features} activeId={active.id} onSelect={setActiveId} />
      <div style={{ marginTop: 12 }}>
        <Suspense fallback={<p>Загрузка модуля…</p>}>
          <active.Component />
        </Suspense>
      </div>
    </div>
  );
}

type FeatureTabsProps = {
  features: ReturnType<typeof registry.list>;
  activeId: string;
  onSelect: (id: string) => void;
};

function FeatureTabs({ features, activeId, onSelect }: FeatureTabsProps): JSX.Element {
  return (
    <nav style={{ display: "flex", gap: 8 }}>
      {features.map((feature) => (
        <button
          key={feature.id}
          type="button"
          onClick={() => onSelect(feature.id)}
          style={{
            padding: "6px 12px",
            borderRadius: 6,
            border: feature.id === activeId ? "2px solid #4f46e5" : "1px solid #ccc",
            background: feature.id === activeId ? "#eef2ff" : "#fff"
          }}
        >
          {feature.title}
        </button>
      ))}
    </nav>
  );
}

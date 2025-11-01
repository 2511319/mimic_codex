import { createContext, useContext, useEffect, useMemo, useState, useCallback, type ReactNode } from "react";

import {
  exchangeInitData,
  persistToken,
  readPersistedToken,
  setupAuthInterceptor,
  type PersistedAuth
} from "../api/client";

type AuthState =
  | { status: "checking" }
  | { status: "authenticated"; tokenType: string; accessToken: string; profile?: AuthProfile }
  | { status: "unauthenticated"; reason: "missing_init_data" | "exchange_failed" };

type AuthProfile = {
  id: number;
  firstName: string;
  lastName?: string | null;
  username?: string | null;
};

type AuthContextValue = {
  state: AuthState;
  logout: () => void;
  retry: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

type AuthProviderProps = {
  initData: string | null;
  children: ReactNode;
};

export function AuthProvider({ initData, children }: AuthProviderProps): JSX.Element {
  const [state, setState] = useState<AuthState>({ status: "checking" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setupAuthInterceptor();
  }, []);

  useEffect(() => {
    let cancelled = false;

    const fromPersisted = (auth: PersistedAuth): void => {
      if (cancelled) return;
      setState({
        status: "authenticated",
        tokenType: auth.tokenType,
        accessToken: auth.accessToken,
        profile: auth.user
          ? {
              id: auth.user.id,
              firstName: auth.user.first_name,
              lastName: auth.user.last_name ?? null,
              username: auth.user.username ?? null
            }
          : undefined
      });
    };

    const persisted = readPersistedToken();
    if (persisted) {
      fromPersisted(persisted);
      return () => {
        cancelled = true;
      };
    }

    if (!initData) {
      setState({ status: "unauthenticated", reason: "missing_init_data" });
      return () => {
        cancelled = true;
      };
    }

    setState({ status: "checking" });

    const run = async (): Promise<void> => {
      try {
        const resp = await exchangeInitData(initData);
        if (cancelled) return;
        persistToken(resp);
        stripInitDataFromUrl();
        const auth: PersistedAuth = {
          accessToken: resp.accessToken,
          tokenType: resp.tokenType,
          user: resp.user,
          chat: resp.chat
        };
        fromPersisted(auth);
      } catch (error) {
        if (cancelled) return;
        setState({ status: "unauthenticated", reason: "exchange_failed" });
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [initData, attempt]);

  const logout = useCallback((): void => {
    localStorage.removeItem("rpgbot.auth");
    setState({ status: "unauthenticated", reason: "missing_init_data" });
  }, []);

  const retry = useCallback((): void => {
    setAttempt((x) => x + 1);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({ state, logout, retry }), [state, logout, retry]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function stripInitDataFromUrl(): void {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("initData")) return;
    url.searchParams.delete("initData");
    window.history.replaceState({}, "", url.toString());
  } catch {
    // ignore
  }
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

type AuthGateProps = {
  children: ReactNode;
};

export function AuthGate({ children }: AuthGateProps): JSX.Element {
  const { state, retry } = useAuth();

  if (state.status === "checking") {
    return <p>Авторизация…</p>;
  }

  if (state.status === "unauthenticated") {
    if (state.reason === "missing_init_data") {
      return <p>Не удалось найти initData. Откройте Mini App из Telegram.</p>;
    }
    return (
      <div>
        <p>Не удалось обменять initData на токен.</p>
        <button type="button" onClick={retry}>
          Попробовать ещё раз
        </button>
      </div>
    );
  }

  return <>{children}</>;
}

import axios from "axios";

export type HealthResponse = {
  status: string;
  apiVersion: string;
};

export type ConfigResponse = {
  apiVersion: string;
  knowledge?: string;
  generation?: string;
  traceId?: string;
};

export type TelegramUser = {
  id: number;
  is_bot: boolean;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  allows_write_to_pm?: boolean;
};

export type TelegramChat = {
  id: number;
  type: string;
  title?: string;
  username?: string;
} | null;

export type AccessTokenResponse = {
  accessToken: string;
  tokenType: string; // always "Bearer"
  expiresIn: number;
  issuedAt: string; // ISO datetime
  user: TelegramUser;
  chat: TelegramChat;
};

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/"
});

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>("/health");
  return data;
}

export async function fetchConfig(): Promise<ConfigResponse> {
  const { data } = await api.get<ConfigResponse>("/config");
  return data;
}

export async function exchangeInitData(initData: string): Promise<AccessTokenResponse> {
  const { data } = await api.post<AccessTokenResponse>("/v1/auth/telegram", { initData });
  return data;
}

export function persistToken(resp: AccessTokenResponse): void {
  try {
    const payload = JSON.stringify({
      accessToken: resp.accessToken,
      tokenType: resp.tokenType,
      expiresAt: new Date(Date.parse(resp.issuedAt) + resp.expiresIn * 1000).toISOString(),
      user: resp.user,
      chat: resp.chat
    });
    localStorage.setItem("rpgbot.auth", payload);
  } catch {
    // ignore storage errors
  }
}

export type PersistedAuth = {
  accessToken: string;
  tokenType: string;
  user?: TelegramUser;
  chat?: TelegramChat | null;
};

export function readPersistedToken(): PersistedAuth | null {
  try {
    const raw = localStorage.getItem("rpgbot.auth");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as {
      accessToken: string;
      tokenType: string;
      expiresAt: string;
      user?: TelegramUser;
      chat?: TelegramChat | null;
    };
    if (Date.now() >= Date.parse(parsed.expiresAt)) {
      localStorage.removeItem("rpgbot.auth");
      return null;
    }
    return {
      accessToken: parsed.accessToken,
      tokenType: parsed.tokenType,
      user: parsed.user,
      chat: parsed.chat ?? null
    };
  } catch {
    return null;
  }
}

let interceptorInstalled = false;

export function setupAuthInterceptor(): void {
  if (interceptorInstalled) return;
  api.interceptors.request.use((config) => {
    const token = readPersistedToken();
    if (token) {
      // eslint-disable-next-line no-param-reassign
      config.headers = {
        ...(config.headers ?? {}),
        Authorization: `${token.tokenType} ${token.accessToken}`
      } as typeof config.headers;
    }
    return config;
  });
  interceptorInstalled = true;
}

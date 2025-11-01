import axios from "axios";

import { validateMediaJobResponse } from "../lib/validation";

import { readPersistedToken } from "./client";

export type MediaJobType = "tts" | "stt" | "image" | "avatar";
export type MediaJobStatus = "queued" | "processing" | "succeeded" | "failed";

export type MediaJobRequest = {
  jobType: MediaJobType;
  payload: Record<string, unknown>;
  clientToken?: string;
};

export type MediaJobResponse = {
  jobId: string;
  jobType: MediaJobType;
  status: MediaJobStatus;
  result?: Record<string, unknown> | null;
  error?: string | null;
  createdAt: string;
  updatedAt: string;
  clientToken?: string | null;
};

function getEnvVar(name: string): string | undefined {
  const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env;
  return env?.[name];
}

const MEDIA_BASE_URL = getEnvVar("VITE_MEDIA_BASE_URL") ?? getEnvVar("VITE_API_BASE_URL") ?? "/";
const mediaApi = axios.create({ baseURL: MEDIA_BASE_URL });

export async function createMediaJob(body: MediaJobRequest): Promise<MediaJobResponse> {
  const token = readPersistedToken();
  const { data } = await mediaApi.post<MediaJobResponse>("/v1/media/jobs", body, {
    headers: token ? { Authorization: `${token.tokenType} ${token.accessToken}` } : undefined
  });
  return ensureValid(data);
}

export async function readMediaJob(jobId: string): Promise<MediaJobResponse> {
  const token = readPersistedToken();
  const { data } = await mediaApi.get<MediaJobResponse>(`/v1/media/jobs/${encodeURIComponent(jobId)}`, {
    headers: token ? { Authorization: `${token.tokenType} ${token.accessToken}` } : undefined
  });
  return ensureValid(data);
}

function ensureValid(payload: MediaJobResponse): MediaJobResponse {
  const result = validateMediaJobResponse(payload);
  if (!result.valid) {
    throw new Error("MediaJobResponse validation failed");
  }
  return payload;
}

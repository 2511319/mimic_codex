import { api } from "./client";

export type GenerationRequestPayload = {
  prompt: string;
};

export type GenerationResult = {
  profile: string;
  result: Record<string, unknown>;
};

export type GenerationProfileDetail = {
  profile: string;
  temperature: number;
  maxOutputTokens: number;
  responseSchema: Record<string, unknown>;
};

export async function fetchGenerationProfiles(): Promise<string[]> {
  const { data } = await api.get<{ profiles: string[] }>("/v1/generation/profiles");
  return data.profiles;
}

export async function fetchGenerationProfileDetail(profile: string): Promise<GenerationProfileDetail> {
  const { data } = await api.get<GenerationProfileDetail>(`/v1/generation/profiles/${encodeURIComponent(profile)}`);
  return data;
}

export async function createGeneration(profile: string, payload: GenerationRequestPayload): Promise<GenerationResult> {
  const { data } = await api.post<GenerationResult>(`/v1/generation/${encodeURIComponent(profile)}`, payload);
  return data;
}

import axios from "axios";

export type HealthResponse = {
  status: string;
  apiVersion: string;
};

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/"
});

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>("/health");
  return data;
}

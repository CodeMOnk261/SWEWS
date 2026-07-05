const trimTrailingSlash = (value: string) => value.replace(/\/+$/, "");

const browserOrigin =
  typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:5173";

export const API_BASE = trimTrailingSlash(
  import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000"
);

export const WS_BASE = API_BASE.replace(/^http/i, "ws");

export const APP_BASE = trimTrailingSlash(browserOrigin);

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

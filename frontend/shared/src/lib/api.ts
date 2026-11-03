/**
 * Small helpers to talk to the FastAPI backend: getJson / postJson (fetch + error handling), useApi (a React
 * hook that loads data when a page opens), wsUrl (the WebSocket address) and APP_URLS (links between the two
 * apps). Paths start with /api: in development the Vite server forwards them to http://127.0.0.1:8000 (see
 * vite.config.ts), so the browser talks to one origin.
 */
import { useCallback, useEffect, useState } from "react";

/** JSON row returned by the API (records of a pandas DataFrame). */
export type Row = Record<string, any>;

/**
 * Turn an HTTP error into a readable Error (FastAPI puts its message in `detail`).
 */
async function failure(response: Response): Promise<Error> {
  let detail = await response.text();
  try {
    detail = JSON.parse(detail).detail ?? detail;
  } catch {
    /* plain-text error */
  }
  return new Error(`${response.status} ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
}

/**
 * GET a URL and parse the JSON answer (throws on an HTTP error).
 */
export async function getJson<T = any>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw await failure(response);
  return response.json();
}

/**
 * POST a JSON body and parse the JSON answer.
 */
export async function postJson<T = any>(path: string, body: unknown = {}): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await failure(response);
  return response.json();
}

/** Fetch on mount (and when `path` changes); `reload` refetches. */
export function useApi<T = any>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(() => {
    // No path yet (e.g. nothing selected): do nothing.
    if (!path) return;
    // `alive` ignores an answer that arrives after the page changed (no update of a closed page).
    let alive = true;
    setLoading(true);
    setError(null);
    getJson<T>(path)
      .then((value) => alive && setData(value))
      .catch((e) => alive && setError(String(e.message ?? e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [path]);
  // Load when the page opens, and again whenever the path changes.
  useEffect(load, [load]);
  return { data, error, loading, reload: load };
}

/**
 * ws:// in development, wss:// when the site is served over https.
 */
export function wsUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}${path}`;
}

/** URL of the other app (front office <-> back office), overridable at build time. */
export const APP_URLS = {
  front: (import.meta as any).env?.VITE_FRONT_OFFICE_URL ?? "http://localhost:5173",
  back: (import.meta as any).env?.VITE_BACK_OFFICE_URL ?? "http://localhost:5174",
};

import { useCallback, useEffect, useState } from "react";

/** JSON row returned by the API (records of a pandas DataFrame). */
export type Row = Record<string, any>;

async function failure(response: Response): Promise<Error> {
  let detail = await response.text();
  try {
    detail = JSON.parse(detail).detail ?? detail;
  } catch {
    /* plain-text error */
  }
  return new Error(`${response.status} ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
}

export async function getJson<T = any>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw await failure(response);
  return response.json();
}

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
    if (!path) return;
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
  useEffect(load, [load]);
  return { data, error, loading, reload: load };
}

export function wsUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}${path}`;
}

/** URL of the other app (front office <-> back office), overridable at build time. */
export const APP_URLS = {
  front: (import.meta as any).env?.VITE_FRONT_OFFICE_URL ?? "http://localhost:5173",
  back: (import.meta as any).env?.VITE_BACK_OFFICE_URL ?? "http://localhost:5174",
};

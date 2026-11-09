"use client";

import { useCallback, useEffect, useState } from "react";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Calls the API with the session cookie (HttpOnly: this code never sees it). The CSRF header
 * proves the request comes from this app; a cross-site form can't set it. */
export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Tenet-CSRF", "1");
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, body, credentials: "include" });
  if (response.status === 401 && typeof window !== "undefined") {
    const here = window.location.pathname;
    if (!here.startsWith("/login") && !here.startsWith("/invite")) {
      window.location.href = `/login?next=${encodeURIComponent(here + window.location.search)}`;
    }
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, detail);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

/** Where the browser goes to sign in with a provider (a full-page redirect, not fetch). */
export function signInUrl(provider: string, next = "/", invite?: string): string {
  const params = new URLSearchParams({ next });
  if (invite) params.set("invite", invite);
  return `${API_URL}/auth/${provider}/start?${params}`;
}

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));

  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

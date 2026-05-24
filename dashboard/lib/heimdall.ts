import "server-only";

import type {
  AlertsPage,
  AlertsQuery,
  AlertsStats,
} from "@/lib/types";

const BASE = process.env.HEIMDALL_API_URL ?? "http://127.0.0.1:8000";
const TOKEN = process.env.HEIMDALL_API_TOKEN ?? "";

function authHeaders(): HeadersInit {
  return TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};
}

async function get<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init.headers ?? {}) },
    // Always fresh — this is a security console, stale numbers mislead.
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Heimdall ${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function getAlerts(query: AlertsQuery = {}): Promise<AlertsPage> {
  const params = new URLSearchParams();
  if (query.limit != null) params.set("limit", String(query.limit));
  if (query.offset != null) params.set("offset", String(query.offset));
  if (query.layer) params.set("layer", query.layer);
  if (query.category) params.set("category", query.category);
  const qs = params.toString();
  return get<AlertsPage>(`/api/alerts${qs ? `?${qs}` : ""}`);
}

export async function getStats(): Promise<AlertsStats> {
  return get<AlertsStats>(`/api/alerts/stats`);
}

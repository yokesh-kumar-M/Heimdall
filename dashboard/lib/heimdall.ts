import "server-only";

import { auth } from "@clerk/nextjs/server";

import type {
  AlertsPage,
  AlertsQuery,
  AlertsStats,
} from "@/lib/types";

const BASE = process.env.HEIMDALL_API_URL ?? "http://127.0.0.1:8000";
const STATIC_TOKEN = process.env.HEIMDALL_API_TOKEN ?? "";
const CLERK_OFF =
  process.env.CLERK_DISABLED === "true" ||
  !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

/**
 * Build the Authorization header for an outbound call to the FastAPI
 * backend. Order of preference:
 *   1. Clerk session JWT (when the user is signed in and Clerk is on).
 *   2. Static service token (single-user self-host or for cron jobs).
 */
async function authHeaders(): Promise<HeadersInit> {
  if (!CLERK_OFF) {
    try {
      const { getToken } = await auth();
      const token = await getToken();
      if (token) return { Authorization: `Bearer ${token}` };
    } catch {
      /* swallow — fall through to static token */
    }
  }
  return STATIC_TOKEN ? { Authorization: `Bearer ${STATIC_TOKEN}` } : {};
}

export async function backendGet<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = { ...(await authHeaders()), ...(init.headers ?? {}) };
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Heimdall ${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function backendForward(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = { ...(await authHeaders()), ...(init.headers ?? {}) };
  return fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
}

// ----- Typed helpers used by server components -----
export async function getAlerts(query: AlertsQuery = {}): Promise<AlertsPage> {
  const params = new URLSearchParams();
  if (query.limit != null) params.set("limit", String(query.limit));
  if (query.offset != null) params.set("offset", String(query.offset));
  if (query.layer) params.set("layer", query.layer);
  if (query.category) params.set("category", query.category);
  const qs = params.toString();
  return backendGet<AlertsPage>(`/api/alerts${qs ? `?${qs}` : ""}`);
}

export async function getStats(): Promise<AlertsStats> {
  return backendGet<AlertsStats>(`/api/alerts/stats`);
}

export interface BillingSummary {
  tenant_id: string;
  budget: {
    monthly_limit_usd: number;
    warn_at_pct: number;
    hard_cap_usd: number | null;
  } | null;
  month_to_date_usd: number;
  month_to_date_pct: number | null;
  projected_month_end_usd: number | null;
  top_models: Array<{ model: string; cost_usd: number; tokens: number; requests: number }>;
  daily_series: Array<{ day: string; cost_usd: number; tokens: number; requests: number }>;
}

export async function getBilling(): Promise<BillingSummary> {
  return backendGet<BillingSummary>(`/api/billing/summary`);
}

export interface ApiKeyRow {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export async function getApiKeys(): Promise<{ keys: ApiKeyRow[] }> {
  return backendGet<{ keys: ApiKeyRow[] }>(`/api/keys`);
}

export interface ProviderRow {
  id: number;
  slug: string;
  display_name: string;
  base_url: string;
  has_key: boolean;
  secret_ref: string | null;
  priority: number;
  enabled: boolean;
  health_status: string;
  consecutive_failures: number;
  routing_strategy: string;
}

export async function getProviders(): Promise<{ providers: ProviderRow[] }> {
  return backendGet<{ providers: ProviderRow[] }>(`/api/providers`);
}

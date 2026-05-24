export type Layer = "deterministic" | "semantic";

export interface Alert {
  id: number;
  timestamp: string;
  incident_id: string | null;
  masked_ip: string;
  country_code: string | null;
  triggered_layer: Layer;
  owasp_category: string;
  rule: string;
  detail: string | null;
  snippet: string | null;
  model: string | null;
  model_params: Record<string, unknown> | null;
  user_agent: string | null;
  blocked_prompt: string;
  original_prompt: string | null;
  sanitized_prompt: string | null;
  extra: Record<string, unknown> | null;
}

export interface FeedbackRow {
  id: number;
  alert_id: number;
  incident_id: string | null;
  feedback_type: "false_positive" | "confirmed" | "note";
  note: string | null;
  created_at: string;
}

export interface Incident {
  incident_id: string | null;
  primary_id: number;
  violations: Alert[];
  feedback: FeedbackRow[];
}

export interface AlertsPage {
  count: number;
  limit: number;
  offset: number;
  alerts: Alert[];
}

export interface AlertsStats {
  total: number;
  by_layer: Record<string, number>;
  by_category: Record<string, number>;
}

export interface AlertsQuery {
  limit?: number;
  offset?: number;
  layer?: Layer | null;
  category?: string | null;
}

export interface PolicyRow {
  rule: string;
  enabled: boolean;
  suppress_after_n_fp: number | null;
  note: string | null;
  auto_suppressed: boolean;
  updated_at: string;
  hits: number;
  fp_count: number;
}

export interface PoliciesResponse {
  count: number;
  default_fp_threshold: number | null;
  policies: PolicyRow[];
}

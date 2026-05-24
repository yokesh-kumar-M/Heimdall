export interface InvisibleHit {
  start: number;
  end: number;
  codepoint: string;
  name: string;
}

export type DetKind = "jailbreak" | "secret" | "pii";

export interface DetMatch {
  rule: string;
  category: string;
  detail: string;
  kind: DetKind;
  start: number;
  end: number;
  snippet: string;
}

export interface SemanticPayload {
  enabled: boolean;
  ran: boolean;
  ms: number;
  verdict: "safe" | "unsafe" | "skipped" | "degraded" | null;
  codes: string[];
  taxonomy: Array<{ code: string; label: string }>;
  raw_output: string | null;
  error: string | null;
}

export interface SandboxResult {
  input: string;
  sanitized: string;
  would_block: boolean;
  blocked_by: "deterministic" | "semantic" | null;
  phases: {
    unicode: {
      ms: number;
      invisible_chars: InvisibleHit[];
      char_count_in: number;
      char_count_out: number;
    };
    deterministic: {
      ms: number;
      matches: DetMatch[];
      verdict: "blocked" | "safe";
    };
    semantic: SemanticPayload;
  };
  totals: { ms: number; l1_ms: number; l2_ms: number };
}

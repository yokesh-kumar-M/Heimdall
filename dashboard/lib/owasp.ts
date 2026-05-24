export const OWASP_LLM_TOP_10 = [
  "LLM01: Prompt Injection",
  "LLM02: Sensitive Information Disclosure",
  "LLM03: Supply Chain",
  "LLM04: Data and Model Poisoning",
  "LLM05: Improper Output Handling",
  "LLM06: Excessive Agency",
  "LLM07: System Prompt Leakage",
  "LLM08: Vector and Embedding Weaknesses",
  "LLM09: Misinformation",
  "LLM10: Unbounded Consumption",
] as const;

export type OwaspCategory = (typeof OWASP_LLM_TOP_10)[number];

const SHORT: Record<string, string> = {
  "LLM01: Prompt Injection": "LLM01",
  "LLM02: Sensitive Information Disclosure": "LLM02",
  "LLM03: Supply Chain": "LLM03",
  "LLM04: Data and Model Poisoning": "LLM04",
  "LLM05: Improper Output Handling": "LLM05",
  "LLM06: Excessive Agency": "LLM06",
  "LLM07: System Prompt Leakage": "LLM07",
  "LLM08: Vector and Embedding Weaknesses": "LLM08",
  "LLM09: Misinformation": "LLM09",
  "LLM10: Unbounded Consumption": "LLM10",
};

export function owaspShort(full: string): string {
  return SHORT[full] ?? full.split(":")[0] ?? full;
}

// Severity color palette — tuned for dark backgrounds.
const COLORS: Record<string, string> = {
  "LLM01: Prompt Injection": "bg-rose-500/15 text-rose-300 border-rose-500/30",
  "LLM02: Sensitive Information Disclosure":
    "bg-amber-500/15 text-amber-300 border-amber-500/30",
  "LLM03: Supply Chain": "bg-violet-500/15 text-violet-300 border-violet-500/30",
  "LLM04: Data and Model Poisoning":
    "bg-orange-500/15 text-orange-300 border-orange-500/30",
  "LLM05: Improper Output Handling":
    "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  "LLM06: Excessive Agency": "bg-pink-500/15 text-pink-300 border-pink-500/30",
  "LLM07: System Prompt Leakage":
    "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30",
  "LLM08: Vector and Embedding Weaknesses":
    "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  "LLM09: Misinformation":
    "bg-yellow-500/15 text-yellow-300 border-yellow-500/30",
  "LLM10: Unbounded Consumption":
    "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
};

export function owaspBadgeClass(category: string): string {
  return (
    COLORS[category] ?? "bg-zinc-500/15 text-zinc-300 border-zinc-500/30"
  );
}

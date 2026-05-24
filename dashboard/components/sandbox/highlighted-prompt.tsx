"use client";

import { useMemo } from "react";

import type { DetKind, DetMatch, InvisibleHit } from "@/lib/sandbox-types";

type Span =
  | { kind: "text"; text: string }
  | { kind: "invisible"; hit: InvisibleHit }
  | { kind: "match"; match: DetMatch };

const KIND_STYLE: Record<DetKind, string> = {
  jailbreak:
    "bg-violet-500/25 text-violet-100 border-b-2 border-violet-400/80 decoration-violet-400",
  secret:
    "bg-amber-500/25 text-amber-100 border-b-2 border-amber-400/80 decoration-amber-400",
  pii:
    "bg-orange-500/25 text-orange-100 border-b-2 border-orange-400/80 decoration-orange-400",
};

function buildSpans(
  text: string,
  invisible: InvisibleHit[],
  matches: DetMatch[]
): Span[] {
  // Merge events sorted by start. We don't expect overlapping matches in practice
  // (regexes are designed not to). If they do overlap, the earlier match wins.
  const events = [
    ...invisible.map((h) => ({ kind: "invisible" as const, start: h.start, end: h.end, payload: h })),
    ...matches.map((m) => ({ kind: "match" as const, start: m.start, end: m.end, payload: m })),
  ].sort((a, b) => a.start - b.start);

  const spans: Span[] = [];
  let cursor = 0;
  for (const e of events) {
    if (e.start < cursor) continue;
    if (e.start > cursor) {
      spans.push({ kind: "text", text: text.slice(cursor, e.start) });
    }
    if (e.kind === "invisible") {
      spans.push({ kind: "invisible", hit: e.payload });
    } else {
      spans.push({ kind: "match", match: e.payload });
    }
    cursor = e.end;
  }
  if (cursor < text.length) {
    spans.push({ kind: "text", text: text.slice(cursor) });
  }
  return spans;
}

export function HighlightedPrompt({
  text,
  invisible,
  matches,
}: {
  text: string;
  invisible: InvisibleHit[];
  matches: DetMatch[];
}) {
  const spans = useMemo(
    () => buildSpans(text, invisible, matches),
    [text, invisible, matches]
  );

  if (!text) {
    return (
      <p className="text-sm text-muted-foreground italic">
        Type a prompt and press Evaluate to see the security pipeline at work.
      </p>
    );
  }

  return (
    <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed">
      {spans.map((s, i) => {
        if (s.kind === "text") return <span key={i}>{s.text}</span>;
        if (s.kind === "invisible") {
          return (
            <span
              key={i}
              title={`${s.hit.codepoint} · ${s.hit.name} (stripped before forward)`}
              className="inline-block align-middle mx-px px-1 py-0 rounded text-[10px] font-medium uppercase tracking-wider bg-rose-500/30 text-rose-100 border border-rose-400/60"
            >
              {s.hit.codepoint}
            </span>
          );
        }
        return (
          <span
            key={i}
            title={`${s.match.rule} — ${s.match.detail}`}
            className={`px-0.5 rounded-sm ${KIND_STYLE[s.match.kind]}`}
          >
            {text.slice(s.match.start, s.match.end)}
          </span>
        );
      })}
    </pre>
  );
}

export function HighlightLegend() {
  return (
    <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
      <LegendDot color="rose" label="Invisible Unicode" />
      <LegendDot color="violet" label="Jailbreak phrase" />
      <LegendDot color="amber" label="Credential / API key" />
      <LegendDot color="orange" label="PII (cards, SSN)" />
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  const map: Record<string, string> = {
    rose: "bg-rose-400",
    violet: "bg-violet-400",
    amber: "bg-amber-400",
    orange: "bg-orange-400",
  };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2 w-2 rounded-full ${map[color]}`} />
      {label}
    </span>
  );
}

"use client";

import { useMemo } from "react";

import { diffChars } from "@/lib/diff";

// Invisible / steganographic Unicode ranges. Using \u escapes so the source
// file is itself readable and to avoid parser issues with literal invisibles.
const INVISIBLE_RE =
  /[​-‏‪-‮⁠-⁯﻿᠎]|[\uDB40][\uDC20-\uDC7F]/g;

function visibleChar(s: string): string {
  return s.replace(INVISIBLE_RE, (ch) => {
    const cp = ch.codePointAt(0) ?? 0;
    return `[U+${cp.toString(16).toUpperCase().padStart(4, "0")}]`;
  });
}

/**
 * Renders an inline character-level diff. Deletions (chars removed by the
 * sanitizer) are shown in red strikethrough; insertions (chars added by
 * NFKC normalization) in emerald.
 */
export function DiffView({
  original,
  sanitized,
}: {
  original: string;
  sanitized: string;
}) {
  const spans = useMemo(() => diffChars(original, sanitized), [original, sanitized]);

  if (!original && !sanitized) {
    return (
      <p className="text-xs text-muted-foreground italic">
        No prompt content recorded for this incident.
      </p>
    );
  }

  return (
    <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed">
      {spans.map((s, i) => {
        if (s.op === "equal") return <span key={i}>{s.text}</span>;
        if (s.op === "delete") {
          return (
            <span
              key={i}
              className="bg-rose-500/25 text-rose-100 line-through decoration-rose-300/80 rounded-sm px-0.5"
              title="Removed by sanitizer before forwarding to upstream LLM"
            >
              {visibleChar(s.text)}
            </span>
          );
        }
        return (
          <span
            key={i}
            className="bg-emerald-500/20 text-emerald-100 rounded-sm px-0.5"
            title="Added by NFKC normalization"
          >
            {s.text}
          </span>
        );
      })}
    </pre>
  );
}

export function DiffLegend() {
  return (
    <div className="flex gap-3 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block w-3 h-2 rounded bg-rose-500/40" />
        Removed
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block w-3 h-2 rounded bg-emerald-500/40" />
        Added (normalization)
      </span>
    </div>
  );
}

"use client";

import { useState, useMemo } from "react";
import type { InvisibleHit } from "@/lib/sandbox-types";
import { cn } from "@/lib/utils";

interface CharCodePoint {
  char: string;
  start: number;
  end: number;
  codePoint: number;
  hex: string;
  name: string;
  type: "whitespace" | "control" | "ascii" | "unicode" | "invisible" | "emoji";
  invisibleHit?: InvisibleHit;
}

function parseCharacters(text: string, invisibleHits: InvisibleHit[]): CharCodePoint[] {
  const result: CharCodePoint[] = [];
  let index = 0;
  // Iterate codepoints safely to prevent surrogate pair split issues
  for (const char of Array.from(text)) {
    const cp = char.codePointAt(0) ?? 0;
    const len = char.length;
    const start = index;
    const end = index + len;

    // Check if this character matches any invisible hits
    const hit = invisibleHits.find((h) => h.start === start);

    let type: "whitespace" | "control" | "ascii" | "unicode" | "invisible" | "emoji" = "ascii";

    if (hit) {
      type = "invisible";
    } else if (cp === 32 || cp === 9 || cp === 10 || cp === 13) {
      type = "whitespace";
    } else if (cp < 32 || (cp >= 127 && cp < 160)) {
      type = "control";
    } else if (cp >= 0x1f300 && cp <= 0x1f9ff) {
      type = "emoji";
    } else if (cp >= 128) {
      type = "unicode";
    }

    let customName = "";
    if (cp === 32) customName = "SPACE (U+0020)";
    else if (cp === 10) customName = "LINE FEED (NEWLINE U+000A)";
    else if (cp === 13) customName = "CARRIAGE RETURN (U+000D)";
    else if (cp === 9) customName = "CHARACTER TABULATION (TAB U+0009)";

    result.push({
      char,
      start,
      end,
      codePoint: cp,
      hex: `U+${cp.toString(16).toUpperCase().padStart(4, "0")}`,
      name: hit?.name || customName || `Unicode codepoint (U+${cp.toString(16).toUpperCase()})`,
      type,
      invisibleHit: hit,
    });

    index += len;
  }
  return result;
}

export function UnicodeInspector({
  text,
  invisible,
}: {
  text: string;
  invisible: InvisibleHit[];
}) {
  const chars = useMemo(() => parseCharacters(text, invisible), [text, invisible]);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const hoveredChar = hoveredIndex !== null ? chars[hoveredIndex] : null;

  const getCharStyles = (type: string) => {
    switch (type) {
      case "invisible":
        return "bg-rose-500/20 text-rose-300 border-rose-500/40 hover:bg-rose-500/35 shadow-[0_0_8px_rgba(244,63,94,0.3)] animate-pulse";
      case "whitespace":
        return "bg-white/[0.02] text-muted-foreground/60 border-white/[0.04] hover:bg-white/[0.06]";
      case "control":
        return "bg-amber-500/10 text-amber-300 border-amber-500/35 hover:bg-amber-500/20";
      case "emoji":
        return "bg-indigo-500/10 text-indigo-200 border-indigo-500/30 hover:bg-indigo-500/20";
      case "unicode":
        return "bg-violet-500/10 text-violet-200 border-violet-500/30 hover:bg-violet-500/20";
      default:
        return "bg-black/30 text-foreground border-white/[0.06] hover:bg-white/[0.04]";
    }
  };

  const getLabel = (c: CharCodePoint) => {
    if (c.type === "invisible") return "∅";
    if (c.codePoint === 32) return "␣";
    if (c.codePoint === 10) return "↵";
    if (c.codePoint === 9) return "⇥";
    return c.char;
  };

  if (!text) {
    return (
      <p className="text-xs text-muted-foreground italic">
        Evaluate a prompt to inspect its character matrices.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-[1fr_220px] gap-4">
      {/* Grid of character boxes */}
      <div className="border border-white/[0.04] bg-black/20 rounded-xl p-3 flex flex-wrap gap-1.5 max-h-[300px] overflow-y-auto content-start">
        {chars.map((c, i) => (
          <div
            key={i}
            onMouseEnter={() => setHoveredIndex(i)}
            onMouseLeave={() => setHoveredIndex(null)}
            className={cn(
              "h-8 w-8 rounded border flex items-center justify-center font-mono text-sm cursor-pointer transition-all duration-150 select-none",
              getCharStyles(c.type),
              hoveredIndex === i ? "scale-110 z-10 border-violet-400" : ""
            )}
          >
            {getLabel(c)}
          </div>
        ))}
      </div>

      {/* Forensic detail panel */}
      <div className="border border-white/[0.06] bg-white/[0.02] rounded-xl p-3 flex flex-col justify-between min-h-[140px] text-xs">
        {hoveredChar ? (
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  "h-12 w-12 rounded border flex items-center justify-center font-mono text-xl",
                  getCharStyles(hoveredChar.type)
                )}
              >
                {getLabel(hoveredChar)}
              </div>
              <div>
                <div className="font-semibold text-foreground font-mono">
                  {hoveredChar.hex}
                </div>
                <div className="text-[10px] text-muted-foreground uppercase font-semibold">
                  Offset: {hoveredChar.start}
                </div>
              </div>
            </div>

            <div className="space-y-1 pt-1.5 border-t border-white/[0.04]">
              <div className="text-[10px] text-muted-foreground font-mono uppercase">
                Descriptor
              </div>
              <div className="text-foreground font-medium leading-relaxed uppercase break-words">
                {hoveredChar.name}
              </div>
            </div>

            <div className="space-y-1">
              <div className="text-[10px] text-muted-foreground font-mono uppercase">
                Gateway Decision
              </div>
              <div>
                {hoveredChar.type === "invisible" ? (
                  <span className="px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-300 border border-rose-500/30 text-[10px] font-bold">
                    STRIPPED
                  </span>
                ) : hoveredChar.type === "control" ? (
                  <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30 text-[10px] font-bold">
                    NORMALIZED
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 text-[10px]">
                    PASSED
                  </span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center flex-1 text-center py-6 text-muted-foreground">
            <span className="text-2xl mb-1">⌕</span>
            <span>Hover any character card to inspect codepoint metadata.</span>
          </div>
        )}
      </div>
    </div>
  );
}

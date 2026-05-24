"use client";

import { Check, X, Shield, FileText, Activity, AlertTriangle, ArrowRight } from "lucide-react";
import type { SandboxResult } from "@/lib/sandbox-types";
import { cn } from "@/lib/utils";

interface PipelineVisualizerProps {
  result: SandboxResult;
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export function PipelineVisualizer({
  result,
  activeTab,
  setActiveTab,
}: PipelineVisualizerProps) {
  const { phases, would_block, blocked_by } = result;

  // Compute node statuses
  // 1. Input Node
  const inputStatus = "good";

  // 2. Unicode Normalizer
  const unicodeNormStatus =
    phases.unicode.char_count_in > phases.unicode.char_count_out ? "warning" : "good";

  // 3. Unicode Scan
  const unicodeScanStatus =
    phases.unicode.invisible_chars.length > 0 ? "warning" : "good";

  // 4. Deterministic Regex
  const detStatus =
    phases.deterministic.matches.length > 0 ? "danger" : "good";

  // 5. Llama Guard 3
  const semStatus =
    phases.semantic.verdict === "unsafe"
      ? "danger"
      : phases.semantic.verdict === "degraded"
        ? "warning"
        : phases.semantic.verdict === "safe"
          ? "good"
          : "muted"; // skipped / null

  // 6. Upstream Gateway
  const gatewayStatus = would_block ? "danger" : "good";

  const nodes = [
    {
      id: "input",
      title: "Input Prompt",
      subtitle: `${phases.unicode.char_count_in} chars`,
      icon: FileText,
      status: inputStatus,
      tab: "annotated",
      description: "Original input payload",
    },
    {
      id: "normalize",
      title: "NFKC Normalizer",
      subtitle: `${phases.unicode.char_count_out} chars`,
      icon: Activity,
      status: unicodeNormStatus,
      tab: "sanitized",
      description: unicodeNormStatus === "warning" ? "Unicode normalized & stripped" : "No modifications needed",
    },
    {
      id: "unicode",
      title: "L1: Unicode Scan",
      subtitle: `${phases.unicode.ms.toFixed(2)} ms`,
      icon: AlertTriangle,
      status: unicodeScanStatus,
      tab: "trace",
      description: unicodeScanStatus === "warning" ? `${phases.unicode.invisible_chars.length} hidden chars found` : "Zero-width/BIDI clean",
    },
    {
      id: "regex",
      title: "L1: Regex Check",
      subtitle: `${phases.deterministic.ms.toFixed(2)} ms`,
      icon: Shield,
      status: detStatus,
      tab: "trace",
      description: detStatus === "danger" ? `${phases.deterministic.matches.length} triggers blocked` : "Patterns clean",
    },
    {
      id: "llama",
      title: "L2: Llama Guard",
      subtitle: phases.semantic.verdict === "skipped" || phases.semantic.verdict === null
        ? "Skipped"
        : `${phases.semantic.ms.toFixed(2)} ms`,
      icon: Shield,
      status: semStatus,
      tab: "trace",
      description: 
        semStatus === "danger" 
          ? "Flagged unsafe" 
          : semStatus === "warning"
            ? "Scanner unreachable"
            : semStatus === "muted"
              ? "Not enabled"
              : "Semantic safe",
    },
    {
      id: "upstream",
      title: "Upstream Gateway",
      subtitle: would_block ? "Blocked" : "Forwarded",
      icon: Check,
      status: gatewayStatus,
      tab: would_block ? "raw" : "sanitized",
      description: would_block ? `Blocked by L${blocked_by === "semantic" ? "2" : "1"}` : "Dispatched upstream",
    },
  ];

  const getStatusStyles = (status: string) => {
    switch (status) {
      case "good":
        return {
          bg: "bg-emerald-500/10 border-emerald-400/35 hover:border-emerald-400/60 shadow-[0_0_15px_-3px_rgba(16,185,129,0.1)]",
          glow: "rgba(16,185,129,0.3)",
          text: "text-emerald-400",
          iconBg: "bg-emerald-500/20 text-emerald-300",
        };
      case "warning":
        return {
          bg: "bg-amber-500/10 border-amber-400/35 hover:border-amber-400/60 shadow-[0_0_15px_-3px_rgba(245,158,11,0.1)]",
          glow: "rgba(245,158,11,0.3)",
          text: "text-amber-400",
          iconBg: "bg-amber-500/20 text-amber-300",
        };
      case "danger":
        return {
          bg: "bg-rose-500/10 border-rose-400/35 hover:border-rose-400/60 shadow-[0_0_15px_-3px_rgba(239,68,68,0.15)]",
          glow: "rgba(239,68,68,0.3)",
          text: "text-rose-400",
          iconBg: "bg-rose-500/20 text-rose-300",
        };
      default:
        return {
          bg: "bg-white/[0.02] border-white/[0.06] hover:border-white/20",
          glow: "rgba(255,255,255,0.05)",
          text: "text-muted-foreground",
          iconBg: "bg-white/[0.04] text-muted-foreground",
        };
    }
  };

  return (
    <div className="w-full space-y-4">
      <div className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground/80">
        Interactive Inspection Pipeline
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        {nodes.map((node, index) => {
          const styles = getStatusStyles(node.status);
          const Icon = node.icon;
          const isSelected = activeTab === node.tab;

          return (
            <div
              key={node.id}
              onClick={() => setActiveTab(node.tab)}
              className={cn(
                "relative rounded-xl border p-3 flex flex-col justify-between cursor-pointer transition-all duration-200 select-none",
                styles.bg,
                isSelected ? "ring-1 ring-violet-400/40 border-violet-400/50" : ""
              )}
              style={{
                boxShadow: isSelected ? `0 0 20px -2px ${styles.glow}` : "",
              }}
            >
              {/* Connection Arrow (only on desktop and not for the last node) */}
              {index < nodes.length - 1 && (
                <div className="hidden lg:flex absolute top-1/2 -translate-y-1/2 -right-2 z-10 items-center justify-center h-4 w-4 rounded-full bg-border border border-white/[0.06] text-muted-foreground/80">
                  <ArrowRight className="h-2.5 w-2.5" />
                </div>
              )}

              {/* Top Node Row */}
              <div className="flex items-start justify-between gap-2">
                <div className={cn("p-1.5 rounded-lg shrink-0", styles.iconBg)}>
                  {node.status === "danger" && node.id === "upstream" ? (
                    <X className="h-4 w-4" />
                  ) : node.status === "good" && node.id === "upstream" ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Icon className="h-4 w-4" />
                  )}
                </div>
                <span className="text-[10px] font-mono tabular-nums text-muted-foreground font-semibold">
                  {node.subtitle}
                </span>
              </div>

              {/* Title & Info */}
              <div className="mt-4 space-y-1">
                <div className={cn("text-xs font-semibold tracking-tight", styles.text)}>
                  {node.title}
                </div>
                <p className="text-[10px] text-muted-foreground leading-snug line-clamp-2">
                  {node.description}
                </p>
              </div>

              {/* Selected overlay border line */}
              {isSelected && (
                <div className="absolute inset-x-0 bottom-0 h-[3px] rounded-b-xl bg-violet-400" />
              )}
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-muted-foreground italic text-center">
        Tip: Click any node block to automatically switch the panel below to focus on its detailed logs.
      </p>
    </div>
  );
}

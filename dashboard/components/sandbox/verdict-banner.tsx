import { cn } from "@/lib/utils";

export function VerdictBanner({
  blocked,
  blockedBy,
}: {
  blocked: boolean;
  blockedBy: "deterministic" | "semantic" | null;
}) {
  if (blocked) {
    return (
      <div
        className={cn(
          "rounded-xl px-4 py-3 flex items-center justify-between gap-4",
          "border border-rose-400/40",
          "bg-gradient-to-r from-rose-500/15 via-rose-500/10 to-transparent"
        )}
      >
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center justify-center h-7 w-7 rounded-full grad-danger text-white text-xs font-bold shadow-[0_0_20px_-4px_rgba(244,63,94,0.7)]">
            ✕
          </span>
          <div>
            <div className="text-sm font-medium">
              BLOCKED by{" "}
              <span className="text-rose-300">
                {blockedBy === "semantic" ? "L2 · Llama Guard 3" : "L1 · Deterministic"}
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              This request would not reach the upstream LLM.
            </div>
          </div>
        </div>
        <code className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-full bg-rose-500/15 text-rose-300 border border-rose-400/30">
          403 Forbidden
        </code>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-xl px-4 py-3 flex items-center justify-between gap-4",
        "border border-emerald-400/40",
        "bg-gradient-to-r from-emerald-500/15 via-emerald-500/10 to-transparent"
      )}
    >
      <div className="flex items-center gap-3">
        <span className="inline-flex items-center justify-center h-7 w-7 rounded-full grad-good text-white text-xs font-bold shadow-[0_0_20px_-4px_rgba(45,212,191,0.6)]">
          ✓
        </span>
        <div>
          <div className="text-sm font-medium">
            CLEAN — would forward to upstream
          </div>
          <div className="text-xs text-muted-foreground">
            Passed all active security layers.
          </div>
        </div>
      </div>
      <code className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-400/30">
        200 OK
      </code>
    </div>
  );
}

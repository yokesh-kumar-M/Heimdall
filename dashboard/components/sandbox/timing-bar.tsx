export function TimingBar({
  unicodeMs,
  detMs,
  semMs,
}: {
  unicodeMs: number;
  detMs: number;
  semMs: number;
}) {
  const total = Math.max(0.001, unicodeMs + detMs + semMs);
  const pct = (v: number) => (v / total) * 100;

  return (
    <div className="space-y-3">
      <div className="h-2 w-full rounded-full overflow-hidden flex bg-white/[0.04] ring-1 ring-white/10">
        <div
          className="h-full grad-info transition-all"
          style={{ width: `${pct(unicodeMs)}%` }}
          title={`Unicode normalize: ${unicodeMs.toFixed(2)}ms`}
        />
        <div
          className="h-full grad-warning transition-all"
          style={{ width: `${pct(detMs)}%` }}
          title={`Deterministic: ${detMs.toFixed(2)}ms`}
        />
        <div
          className="h-full grad-good transition-all"
          style={{ width: `${pct(semMs)}%` }}
          title={`Semantic: ${semMs.toFixed(2)}ms`}
        />
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs font-mono">
        <PhaseRow label="Unicode" ms={unicodeMs} accent="grad-info" />
        <PhaseRow label="Deterministic" ms={detMs} accent="grad-warning" />
        <PhaseRow label="Semantic" ms={semMs} accent="grad-good" />
      </div>
      <div className="text-[11px] text-muted-foreground">
        Total pipeline latency:{" "}
        <span className="tabular-nums text-foreground">
          {total.toFixed(2)} ms
        </span>
      </div>
    </div>
  );
}

function PhaseRow({
  label,
  ms,
  accent,
}: {
  label: string;
  ms: number;
  accent: string;
}) {
  return (
    <div className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5">
      <div className="flex items-center gap-2">
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${accent}`} />
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
      </div>
      <div className="text-sm tabular-nums mt-0.5">{ms.toFixed(2)} ms</div>
    </div>
  );
}

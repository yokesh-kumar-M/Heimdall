"use client";

import { useEffect, useState } from "react";

export function StatusIndicator() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [ping, setPing] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const t0 = performance.now();
      try {
        const r = await fetch("/api/health", { cache: "no-store" });
        if (!alive) return;
        setOnline(r.ok);
        setPing(Math.round(performance.now() - t0));
      } catch {
        if (!alive) return;
        setOnline(false);
        setPing(null);
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const colorClass =
    online === null
      ? "text-zinc-500"
      : online
        ? "text-emerald-400"
        : "text-rose-400";
  const label =
    online === null
      ? "Connecting…"
      : online
        ? "Operational"
        : "Gateway unreachable";

  return (
    <div className="flex items-center gap-2 text-xs">
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full status-dot ${colorClass}`}
        style={{ background: "currentColor" }}
      />
      <div className="flex flex-col leading-tight">
        <span className="text-foreground/90">System Status: {label}</span>
        <span className="text-[10px] text-muted-foreground">
          {ping != null ? `Listening for threats · ${ping}ms` : "—"}
        </span>
      </div>
    </div>
  );
}

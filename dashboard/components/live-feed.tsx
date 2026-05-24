"use client";

import { Pause, Play, Trash2, Wifi, WifiOff } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { owaspShort } from "@/lib/owasp";

type FeedEvent =
  | {
      kind: "block";
      id: number;
      ts: number;
      status: number;
      layer: string | null;
      model: string | null;
      masked_ip: string;
      country_code: string | null;
      rules: string[];
      primary_category: string | null;
    }
  | {
      kind: "pass";
      id: number;
      ts: number;
      status: number;
      model: string | null;
      masked_ip: string;
      country_code: string | null;
      char_count: number;
    };

type ConnState = "connecting" | "open" | "closed";

const MAX_ROWS = 250;

export function LiveFeed() {
  const [rows, setRows] = useState<FeedEvent[]>([]);
  const [paused, setPaused] = useState(false);
  const [conn, setConn] = useState<ConnState>("connecting");
  const [autoScroll, setAutoScroll] = useState(true);

  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const idRef = useRef(0);
  const bufferRef = useRef<FeedEvent[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // -------- subscribe to SSE
  useEffect(() => {
    const es = new EventSource("/api/alerts/stream");
    esRef.current = es;
    setConn("connecting");

    es.addEventListener("hello", () => setConn("open"));
    es.addEventListener("open", () => setConn("open"));
    es.onopen = () => setConn("open");
    es.onerror = () => setConn("closed");

    es.addEventListener("alert", (raw) => {
      try {
        const data = JSON.parse((raw as MessageEvent).data) as Record<string, unknown>;
        const id = ++idRef.current;
        const ts = Date.now();
        const event: FeedEvent =
          data.type === "block"
            ? {
                kind: "block",
                id,
                ts,
                status: Number(data.status ?? 403),
                layer: (data.layer as string | null) ?? null,
                model: (data.model as string | null) ?? null,
                masked_ip: String(data.masked_ip ?? "—"),
                country_code: (data.country_code as string | null) ?? null,
                rules: Array.isArray(data.rules) ? (data.rules as string[]) : [],
                primary_category:
                  (data.primary_category as string | null) ?? null,
              }
            : {
                kind: "pass",
                id,
                ts,
                status: Number(data.status ?? 200),
                model: (data.model as string | null) ?? null,
                masked_ip: String(data.masked_ip ?? "—"),
                country_code: (data.country_code as string | null) ?? null,
                char_count: Number(data.char_count ?? 0),
              };

        // Buffer while paused so we don't drop events; flush on resume.
        if (pausedRef.current) {
          bufferRef.current.push(event);
          if (bufferRef.current.length > MAX_ROWS) {
            bufferRef.current.splice(0, bufferRef.current.length - MAX_ROWS);
          }
          return;
        }
        setRows((prev) => {
          const next = [...prev, event];
          return next.length > MAX_ROWS ? next.slice(-MAX_ROWS) : next;
        });
      } catch {
        // Malformed frame — ignore.
      }
    });

    return () => {
      es.close();
      esRef.current = null;
    };
  }, []);

  // -------- flush buffered rows when un-pausing
  useEffect(() => {
    if (paused) return;
    if (bufferRef.current.length === 0) return;
    const drained = bufferRef.current;
    bufferRef.current = [];
    setRows((prev) => {
      const next = [...prev, ...drained];
      return next.length > MAX_ROWS ? next.slice(-MAX_ROWS) : next;
    });
  }, [paused]);

  // -------- autoscroll: pin to bottom unless user scrolled up
  useEffect(() => {
    if (!autoScroll) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [rows, autoScroll]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 32;
    setAutoScroll(nearBottom);
  }, []);

  const clear = () => {
    setRows([]);
    bufferRef.current = [];
  };

  const blockCount = rows.filter((r) => r.kind === "block").length;
  const passCount = rows.length - blockCount;

  return (
    <div className="rounded-xl border border-white/[0.06] bg-black/40 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 px-3 py-2 border-b border-white/[0.06] bg-white/[0.02]">
        <div className="flex items-center gap-2">
          <ConnDot state={conn} />
          <span className="text-xs uppercase tracking-wider text-muted-foreground">
            Live feed
          </span>
          <span className="text-[11px] text-muted-foreground tabular-nums">
            · {rows.length} rows · {blockCount} block · {passCount} pass
          </span>
          {paused && bufferRef.current.length > 0 ? (
            <span className="text-[10px] uppercase tracking-wider text-amber-300">
              · {bufferRef.current.length} buffered
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setPaused((p) => !p)}
            className="h-7 px-2 text-xs"
            title={paused ? "Resume" : "Pause"}
          >
            {paused ? (
              <>
                <Play className="h-3 w-3 mr-1" /> Resume
              </>
            ) : (
              <>
                <Pause className="h-3 w-3 mr-1" /> Pause
              </>
            )}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={clear}
            className="h-7 px-2 text-xs"
            title="Clear"
          >
            <Trash2 className="h-3 w-3 mr-1" /> Clear
          </Button>
        </div>
      </div>

      {/* Terminal */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="h-[280px] overflow-y-auto font-mono text-[11.5px] leading-relaxed bg-[oklch(0.13_0.018_260)]"
      >
        {rows.length === 0 ? (
          <div className="p-6 text-muted-foreground text-xs">
            {conn === "open"
              ? "Waiting for proxy traffic… fire a request to /v1/chat/completions to see events."
              : conn === "connecting"
                ? "Connecting to stream…"
                : "Stream closed. Check the backend at /api/alerts/stream."}
          </div>
        ) : (
          <ul className="px-2 py-1.5">
            {rows.map((r) => (
              <FeedRow key={r.id} r={r} />
            ))}
          </ul>
        )}
      </div>

      {/* Auto-scroll indicator */}
      {!autoScroll && rows.length > 0 ? (
        <button
          onClick={() => {
            setAutoScroll(true);
            const el = scrollRef.current;
            if (el) el.scrollTop = el.scrollHeight;
          }}
          className="w-full text-[11px] py-1.5 bg-amber-500/10 text-amber-200 border-t border-amber-500/30 hover:bg-amber-500/15"
        >
          ↓ Jump to live · auto-scroll paused
        </button>
      ) : null}
    </div>
  );
}

function FeedRow({ r }: { r: FeedEvent }) {
  const time = new Date(r.ts).toLocaleTimeString(undefined, {
    hour12: false,
  });
  if (r.kind === "block") {
    return (
      <li className="flex items-baseline gap-2 py-0.5 px-1 hover:bg-rose-500/5 border-l-2 border-transparent hover:border-rose-400/40">
        <span className="text-muted-foreground tabular-nums">{time}</span>
        <span className="text-rose-300 font-bold">[BLOCK]</span>
        <span className="text-rose-200/80">{r.status}</span>
        <span className="text-rose-200/70">
          L{r.layer === "semantic" ? "2" : "1"}:{r.rules[0] ?? "?"}
        </span>
        {r.primary_category ? (
          <span className="text-rose-200/60">
            ({owaspShort(r.primary_category)})
          </span>
        ) : null}
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">{r.model ?? "—"}</span>
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">
          {r.masked_ip}
          {r.country_code ? ` (${r.country_code})` : ""}
        </span>
      </li>
    );
  }
  return (
    <li className="flex items-baseline gap-2 py-0.5 px-1 hover:bg-emerald-500/5 border-l-2 border-transparent hover:border-emerald-400/40">
      <span className="text-muted-foreground tabular-nums">{time}</span>
      <span className="text-emerald-300 font-bold">[PASS]</span>
      <span className="text-emerald-200/80">{r.status}</span>
      <span className="text-muted-foreground">{r.model ?? "—"}</span>
      <span className="text-muted-foreground">·</span>
      <span className="text-muted-foreground">
        {r.masked_ip}
        {r.country_code ? ` (${r.country_code})` : ""}
      </span>
      <span className="text-muted-foreground">·</span>
      <span className="text-muted-foreground tabular-nums">
        {r.char_count} chars
      </span>
    </li>
  );
}

function ConnDot({ state }: { state: ConnState }) {
  if (state === "open") {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-300">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 status-pulse" />
        <Wifi className="h-3 w-3" />
      </span>
    );
  }
  if (state === "connecting") {
    return (
      <span className="inline-flex items-center gap-1 text-amber-300">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 status-pulse" />
        <Wifi className="h-3 w-3" />
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-rose-300">
      <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
      <WifiOff className="h-3 w-3" />
    </span>
  );
}

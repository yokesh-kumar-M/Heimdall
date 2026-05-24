"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

const useIsoLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

export interface BlocksPoint {
  bucket: string;
  deterministic: number;
  semantic: number;
}

const HEIGHT = 260;
const PAD_LEFT = 36;
const PAD_RIGHT = 12;
const PAD_TOP = 16;
const PAD_BOTTOM = 28;

function smoothPath(points: Array<[number, number]>): string {
  if (points.length === 0) return "";
  if (points.length === 1) {
    const [x, y] = points[0];
    return `M ${x} ${y}`;
  }
  let d = `M ${points[0][0]} ${points[0][1]}`;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const mx = (x0 + x1) / 2;
    d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
  }
  return d;
}

export function BlocksChart({ data }: { data: BlocksPoint[] }) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(1200);
  const [hover, setHover] = useState<number | null>(null);

  useIsoLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const update = () => {
      const w = el.getBoundingClientRect().width || el.clientWidth;
      if (w > 0) setWidth(Math.max(Math.floor(w), 320));
    };
    update();
    // Second measurement after first paint to catch any late layout.
    const raf = requestAnimationFrame(update);
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  const innerW = Math.max(width - PAD_LEFT - PAD_RIGHT, 1);
  const innerH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const maxY = Math.max(
    1,
    ...data.map((p) => p.deterministic + p.semantic)
  );
  const stepX = data.length > 1 ? innerW / (data.length - 1) : innerW;
  const y = (v: number) => PAD_TOP + innerH - (v / maxY) * innerH;
  const x = (i: number) => PAD_LEFT + i * stepX;

  const detPts = data.map((p, i) => [x(i), y(p.deterministic)] as [number, number]);
  const stackPts = data.map(
    (p, i) => [x(i), y(p.deterministic + p.semantic)] as [number, number]
  );

  // Area paths (close back along the baseline).
  const baselineY = PAD_TOP + innerH;
  const detPath =
    smoothPath(detPts) +
    ` L ${x(data.length - 1)} ${baselineY} L ${x(0)} ${baselineY} Z`;
  const semPath =
    smoothPath(stackPts) +
    ` L ${x(data.length - 1)} ${y(data[data.length - 1]?.deterministic ?? 0)}` +
    " " +
    smoothPath([...detPts].reverse()).replace(/^M/, "L") +
    " Z";

  // Y ticks
  const yTicks = Array.from({ length: 4 }, (_, i) => {
    const v = Math.round((maxY * (i + 1)) / 4);
    return { v, y: y(v) };
  });

  return (
    <div ref={wrapRef} className="w-full select-none" style={{ height: HEIGHT }}>
      <svg
        width="100%"
        height={HEIGHT}
        viewBox={`0 0 ${width} ${HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        className="overflow-visible"
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="det-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.5} />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="sem-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-3)" stopOpacity={0.5} />
            <stop offset="100%" stopColor="var(--chart-3)" stopOpacity={0} />
          </linearGradient>
        </defs>

        {/* Y grid + labels */}
        {yTicks.map((t) => (
          <g key={t.v}>
            <line
              x1={PAD_LEFT}
              x2={width - PAD_RIGHT}
              y1={t.y}
              y2={t.y}
              stroke="var(--border)"
              strokeOpacity={0.4}
              strokeDasharray="3 3"
            />
            <text
              x={PAD_LEFT - 6}
              y={t.y}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={10}
              fill="var(--muted-foreground)"
              fontFamily="var(--font-mono)"
            >
              {t.v}
            </text>
          </g>
        ))}

        {/* Stacked semantic band (top) */}
        <path d={semPath} fill="url(#sem-grad)" stroke="none" />
        {/* Deterministic band (bottom) */}
        <path d={detPath} fill="url(#det-grad)" stroke="none" />
        {/* Top edges */}
        <path
          d={smoothPath(detPts)}
          fill="none"
          stroke="var(--chart-1)"
          strokeWidth={2}
        />
        <path
          d={smoothPath(stackPts)}
          fill="none"
          stroke="var(--chart-3)"
          strokeWidth={2}
        />

        {/* X labels — every 4th hour */}
        {data.map((p, i) =>
          i % 4 === 0 || i === data.length - 1 ? (
            <text
              key={p.bucket}
              x={x(i)}
              y={HEIGHT - 8}
              textAnchor="middle"
              fontSize={10}
              fill="var(--muted-foreground)"
              fontFamily="var(--font-mono)"
            >
              {p.bucket.slice(11, 16)}
            </text>
          ) : null
        )}

        {/* Hover crosshair + invisible hit targets */}
        {hover != null && data[hover] ? (
          <>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={PAD_TOP}
              y2={baselineY}
              stroke="var(--foreground)"
              strokeOpacity={0.3}
            />
            <circle
              cx={x(hover)}
              cy={y(data[hover].deterministic)}
              r={3}
              fill="var(--chart-1)"
            />
            <circle
              cx={x(hover)}
              cy={y(data[hover].deterministic + data[hover].semantic)}
              r={3}
              fill="var(--chart-3)"
            />
          </>
        ) : null}
        {data.map((_, i) => (
          <rect
            key={i}
            x={x(i) - stepX / 2}
            y={PAD_TOP}
            width={stepX}
            height={innerH}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>

      <div className="flex justify-between mt-2 text-[11px]">
        <div className="flex gap-4">
          <span className="inline-flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: "var(--chart-1)" }}
            />
            <span className="text-muted-foreground">Deterministic</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: "var(--chart-3)" }}
            />
            <span className="text-muted-foreground">Semantic</span>
          </span>
        </div>
        {hover != null && data[hover] ? (
          <span className="font-mono text-muted-foreground">
            {data[hover].bucket.slice(11, 16)} —{" "}
            <span className="text-foreground">
              det {data[hover].deterministic} · sem {data[hover].semantic}
            </span>
          </span>
        ) : (
          <span className="text-muted-foreground">peak {maxY}</span>
        )}
      </div>
    </div>
  );
}

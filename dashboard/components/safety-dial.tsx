"use client";

import { useEffect, useState, useRef } from "react";
import { cn } from "@/lib/utils";

export function SafetyDial({
  blocks24h,
  totalBlocks,
  ratio = "—",
  topCategory = "—",
}: {
  blocks24h: number;
  totalBlocks: number;
  ratio?: string;
  topCategory?: string;
}) {
  const penalty = Math.min(100, Math.round(40 * Math.log10(1 + blocks24h)));
  const targetScore = Math.max(0, 100 - penalty);

  const [score, setScore] = useState(0);
  const [isHovered, setIsHovered] = useState(false);
  const prevScoreRef = useRef(0);

  useEffect(() => {
    let startTimestamp: number | null = null;
    const duration = 1200; // 1.2s count up
    const startScore = prevScoreRef.current;
    const diff = targetScore - startScore;

    const step = (timestamp: number) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      const easeProgress = 1 - Math.pow(1 - progress, 4); // easeOutQuart
      
      const current = Math.round(startScore + easeProgress * diff);
      setScore(current);

      if (progress < 1) {
        window.requestAnimationFrame(step);
      } else {
        prevScoreRef.current = targetScore;
      }
    };

    window.requestAnimationFrame(step);
  }, [targetScore]);

  // Arc geometry — 240° sweep, centered at top
  const SIZE = 200;
  const cx = SIZE / 2;
  const cy = SIZE / 2 + 8;
  const r = 78;
  const sweep = 240; // degrees
  const startAngle = -210; // top-left
  const endAngle = startAngle + sweep;
  const angle = startAngle + (sweep * score) / 100;

  const polar = (deg: number, radius: number) => {
    const rad = (deg * Math.PI) / 180;
    return [cx + Math.cos(rad) * radius, cy + Math.sin(rad) * radius] as const;
  };

  const arc = (from: number, to: number, radius = r) => {
    const [x1, y1] = polar(from, radius);
    const [x2, y2] = polar(to, radius);
    const large = Math.abs(to - from) > 180 ? 1 : 0;
    const sweepFlag = to > from ? 1 : 0;
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${large} ${sweepFlag} ${x2} ${y2}`;
  };

  const trackPath = arc(startAngle, endAngle);
  const valuePath = arc(startAngle, angle);

  // Color band by score
  const stops =
    score >= 85
      ? ["oklch(0.72 0.16 165)", "oklch(0.65 0.14 200)"]
      : score >= 60
        ? ["oklch(0.78 0.18 70)", "oklch(0.68 0.18 40)"]
        : ["oklch(0.65 0.22 18)", "oklch(0.55 0.20 8)"];

  const label =
    score >= 85 ? "Healthy" : score >= 60 ? "Elevated" : "Under attack";

  const glowColor =
    score >= 85
      ? "rgba(45, 212, 191, 0.4)"
      : score >= 60
        ? "rgba(245, 158, 11, 0.4)"
        : "rgba(244, 63, 94, 0.5)";

  return (
    <div className="flex flex-col sm:flex-row items-center gap-6 justify-center lg:justify-start">
      <div 
        className="relative shrink-0 cursor-pointer group"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <svg width={SIZE} height={SIZE} className="shrink-0 transition-transform duration-300 group-hover:scale-102">
          <defs>
            <linearGradient id="safety-grad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={stops[0]} />
              <stop offset="100%" stopColor={stops[1]} />
            </linearGradient>
            <filter id="safety-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="8" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Dotted outer background ring */}
          <circle
            cx={cx}
            cy={cy}
            r={r + 12}
            fill="none"
            stroke="oklch(0.30 0.015 260 / 0.15)"
            strokeWidth={1}
            strokeDasharray="4 8"
            className="animate-[spin_120s_linear_infinite]"
          />

          {/* Track */}
          <path
            d={trackPath}
            fill="none"
            stroke="oklch(0.30 0.015 260 / 0.4)"
            strokeWidth={8}
            strokeLinecap="round"
          />

          {/* Value arc with glow */}
          <path
            d={valuePath}
            fill="none"
            stroke="url(#safety-grad)"
            strokeWidth={10}
            strokeLinecap="round"
            filter="url(#safety-glow)"
            className="transition-all duration-300"
          />

          {/* Dynamic center content */}
          {!isHovered ? (
            <>
              {/* Score Display */}
              <text
                x={cx}
                y={cy - 2}
                textAnchor="middle"
                fontSize={48}
                fontWeight={700}
                fill="oklch(0.97 0.005 250)"
                fontFamily="var(--font-mono)"
                style={{ 
                  letterSpacing: "-0.04em",
                  filter: `drop-shadow(0 0 12px ${glowColor})`
                }}
                className="transition-all duration-500"
              >
                {score}
              </text>
              <text
                x={cx}
                y={cy + 22}
                textAnchor="middle"
                fontSize={10}
                fill="oklch(0.66 0.015 255)"
                letterSpacing="0.18em"
                className="font-medium"
              >
                SAFETY INDEX
              </text>
            </>
          ) : (
            <>
              {/* Stats Hover Display */}
              <text
                x={cx}
                y={cy - 24}
                textAnchor="middle"
                fontSize={10}
                fill="oklch(0.66 0.015 255)"
                letterSpacing="0.1em"
                fontWeight={500}
              >
                GATE RATIO L1/L2
              </text>
              <text
                x={cx}
                y={cy - 4}
                textAnchor="middle"
                fontSize={16}
                fontWeight={600}
                fill="oklch(0.97 0.005 250)"
                fontFamily="var(--font-mono)"
              >
                {ratio}
              </text>
              <text
                x={cx}
                y={cy + 16}
                textAnchor="middle"
                fontSize={10}
                fill="oklch(0.66 0.015 255)"
                letterSpacing="0.1em"
                fontWeight={500}
              >
                TOP PAYLOAD
              </text>
              <text
                x={cx}
                y={cy + 32}
                textAnchor="middle"
                fontSize={11}
                fontWeight={600}
                fill="oklch(0.97 0.005 250)"
                className="truncate max-w-[120px]"
              >
                {topCategory}
              </text>
            </>
          )}
        </svg>

        {/* Small pulsing tag at center bottom of dial */}
        <div 
          className={cn(
            "absolute bottom-4 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border transition-all duration-300",
            score >= 85
              ? "bg-emerald-500/10 text-emerald-300 border-emerald-400/30"
              : score >= 60
                ? "bg-amber-500/10 text-amber-300 border-amber-400/30"
                : "bg-rose-500/10 text-rose-300 border-rose-400/30"
          )}
          style={{ boxShadow: `0 0 10px ${glowColor}` }}
        >
          {label}
        </div>
      </div>

      <div className="space-y-3 flex-1">
        <div className="text-xl font-semibold flex items-center gap-2">
          <span
            className={cn(
              "transition-colors duration-300",
              score >= 85
                ? "text-grad-good"
                : score >= 60
                  ? "text-grad-warning"
                  : "text-grad-danger"
            )}
          >
            {label}
          </span>
          <span 
            className={cn(
              "h-2 w-2 rounded-full status-pulse shrink-0",
              score >= 85 ? "bg-emerald-400 text-emerald-400" : score >= 60 ? "bg-amber-400 text-amber-400" : "bg-rose-400 text-rose-400"
            )} 
          />
        </div>
        <ul className="text-xs text-muted-foreground space-y-1.5 border-l border-white/[0.06] pl-4">
          <li className="flex justify-between items-center max-w-[200px]">
            <span>Last 24 hours:</span>
            <span className="tabular-nums font-mono text-foreground font-semibold">{blocks24h}</span>
          </li>
          <li className="flex justify-between items-center max-w-[200px]">
            <span>All-time blocks:</span>
            <span className="tabular-nums font-mono text-foreground font-semibold">{totalBlocks.toLocaleString()}</span>
          </li>
          <li className="pt-1.5 leading-relaxed text-[11px]">
            Index drops as blocking incidents increase. Hover dial to inspect target gateway telemetry splits.
          </li>
        </ul>
      </div>
    </div>
  );
}

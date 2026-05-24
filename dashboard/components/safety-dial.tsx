/**
 * Heimdall Safety Index — overall cleanliness ratio of traffic.
 *
 * The score is 100 when no blocks have happened in the window, dropping as
 * blocks accumulate. We use a log-scaled penalty so the dial is sensitive in
 * the 0–20 range (where most healthy gateways live) and saturates above 100
 * blocks/hour.
 *
 * This is intentionally a pure SVG component — no client deps, renders on the
 * server with the same output, no recharts headache.
 */
export function SafetyDial({
  blocks24h,
  totalBlocks,
}: {
  blocks24h: number;
  totalBlocks: number;
}) {
  const penalty = Math.min(100, Math.round(40 * Math.log10(1 + blocks24h)));
  const score = Math.max(0, 100 - penalty);

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

  return (
    <div className="flex items-center gap-6">
      <svg width={SIZE} height={SIZE} className="shrink-0">
        <defs>
          <linearGradient id="safety-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={stops[0]} />
            <stop offset="100%" stopColor={stops[1]} />
          </linearGradient>
          <filter id="safety-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Track */}
        <path
          d={trackPath}
          fill="none"
          stroke="oklch(0.30 0.015 260 / 0.5)"
          strokeWidth={10}
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
        />

        {/* Center text */}
        <text
          x={cx}
          y={cy - 6}
          textAnchor="middle"
          fontSize={42}
          fontWeight={600}
          fill="oklch(0.97 0.005 250)"
          fontFamily="var(--font-mono)"
          style={{ letterSpacing: "-0.04em" }}
        >
          {score}
        </text>
        <text
          x={cx}
          y={cy + 18}
          textAnchor="middle"
          fontSize={10}
          fill="oklch(0.66 0.015 255)"
          letterSpacing="0.18em"
        >
          SAFETY INDEX
        </text>
      </svg>

      <div className="space-y-2">
        <div className="text-xl font-semibold">
          <span
            className={
              score >= 85
                ? "text-grad-good"
                : score >= 60
                  ? "text-grad-warning"
                  : "text-grad-danger"
            }
          >
            {label}
          </span>
        </div>
        <ul className="text-xs text-muted-foreground space-y-1">
          <li>
            <span className="tabular-nums text-foreground">{blocks24h}</span>{" "}
            blocks in last 24h
          </li>
          <li>
            <span className="tabular-nums text-foreground">
              {totalBlocks.toLocaleString()}
            </span>{" "}
            blocks all-time
          </li>
          <li className="pt-2 leading-relaxed">
            Score reflects current incident pressure. Healthy ≥ 85, Elevated
            ≥ 60.
          </li>
        </ul>
      </div>
    </div>
  );
}

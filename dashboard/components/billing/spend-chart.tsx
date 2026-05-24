"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Point {
  day: string;
  cost_usd: number;
  tokens: number;
  requests: number;
}

export function SpendChart({ data }: { data: Point[] }) {
  if (!data.length) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No spend data yet.
      </p>
    );
  }
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="spend" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="oklch(0.68 0.18 245)" stopOpacity={0.6} />
              <stop offset="95%" stopColor="oklch(0.68 0.18 245)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.3 0 0 / 0.4)" />
          <XAxis dataKey="day" fontSize={10} stroke="oklch(0.66 0 0)" tickFormatter={(v) => v.slice(5)} />
          <YAxis fontSize={10} stroke="oklch(0.66 0 0)" tickFormatter={(v) => `$${v.toFixed(2)}`} />
          <Tooltip
            contentStyle={{ background: "oklch(0.2 0.018 258)", border: "1px solid oklch(0.32 0 0)", borderRadius: 8 }}
            formatter={(v: number) => [`$${v.toFixed(4)}`, "cost"]}
          />
          <Area type="monotone" dataKey="cost_usd" stroke="oklch(0.68 0.18 245)" fill="url(#spend)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

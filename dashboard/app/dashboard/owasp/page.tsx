import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getAlerts, getStats } from "@/lib/heimdall";
import { OWASP_LLM_TOP_10, owaspBadgeClass, owaspShort } from "@/lib/owasp";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Alert } from "@/lib/types";

function lastSeen(alerts: Alert[], category: string): string | null {
  for (const a of alerts) {
    if (a.owasp_category === category) return a.timestamp;
  }
  return null;
}

export const dynamic = "force-dynamic";

export default async function OwaspPage() {
  const [stats, recent] = await Promise.all([
    getStats(),
    getAlerts({ limit: 500 }),
  ]);

  const cards = OWASP_LLM_TOP_10.map((category) => {
    const count = stats.by_category[category] ?? 0;
    return {
      category,
      count,
      lastSeen: lastSeen(recent.alerts, category),
      pct: stats.total > 0 ? Math.round((count / stats.total) * 100) : 0,
    };
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          OWASP LLM Top 10
        </h1>
        <p className="text-sm text-muted-foreground">
          Compliance view — one card per 2025 category, showing block counts
          observed by Heimdall.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {cards.map((c) => (
          <Card key={c.category} className={c.count > 0 ? "border-foreground/20" : "opacity-80"}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium">
                  {c.category.split(": ")[1] ?? c.category}
                </CardTitle>
                <span
                  className={cn(
                    "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold",
                    owaspBadgeClass(c.category)
                  )}
                >
                  {owaspShort(c.category)}
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-semibold tabular-nums">
                  {c.count.toLocaleString()}
                </span>
                <span className="text-xs text-muted-foreground">
                  {c.pct}% of total
                </span>
              </div>
              <div className="text-xs text-muted-foreground">
                {c.lastSeen ? (
                  <>Last seen {relativeTime(c.lastSeen)}</>
                ) : (
                  <>Never triggered</>
                )}
              </div>
              {c.count > 0 ? (
                <Link
                  href={`/dashboard/alerts?category=${encodeURIComponent(c.category)}`}
                  className="text-xs underline-offset-4 hover:underline"
                >
                  View incidents →
                </Link>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

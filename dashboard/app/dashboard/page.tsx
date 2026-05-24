import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BlocksChart, type BlocksPoint } from "@/components/blocks-chart";
import { CategoryBar } from "@/components/category-bar";
import { KpiCard } from "@/components/kpi-card";
import { LiveFeed } from "@/components/live-feed";
import { SafetyDial } from "@/components/safety-dial";
import { ThreatMap } from "@/components/threat-map";
import { getAlerts, getStats } from "@/lib/heimdall";
import { owaspShort } from "@/lib/owasp";
import type { Alert } from "@/lib/types";

function buildHourlySeries(alerts: Alert[]): BlocksPoint[] {
  const now = new Date();
  const buckets: Record<string, BlocksPoint> = {};
  for (let i = 23; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 60 * 60 * 1000);
    d.setMinutes(0, 0, 0);
    const key = d.toISOString();
    buckets[key] = { bucket: key, deterministic: 0, semantic: 0 };
  }
  for (const a of alerts) {
    const t = new Date(a.timestamp);
    t.setMinutes(0, 0, 0);
    const key = t.toISOString();
    if (buckets[key]) {
      if (a.triggered_layer === "semantic") buckets[key].semantic += 1;
      else buckets[key].deterministic += 1;
    }
  }
  return Object.values(buckets);
}

function topRules(alerts: Alert[], n = 8): Array<{ rule: string; count: number }> {
  const counts = new Map<string, number>();
  for (const a of alerts) counts.set(a.rule, (counts.get(a.rule) ?? 0) + 1);
  return [...counts.entries()]
    .map(([rule, count]) => ({ rule, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, n);
}

function topAttackerSubnets(alerts: Alert[], n = 5): Array<{ subnet: string; count: number }> {
  const counts = new Map<string, number>();
  for (const a of alerts) {
    const parts = a.masked_ip.split(".");
    const subnet =
      parts.length >= 2 ? `${parts[0]}.${parts[1]}.*.*` : a.masked_ip;
    counts.set(subnet, (counts.get(subnet) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([subnet, count]) => ({ subnet, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, n);
}

export const dynamic = "force-dynamic";

export default async function Overview() {
  const [stats, recent] = await Promise.all([
    getStats(),
    getAlerts({ limit: 1000 }),
  ]);

  const series = buildHourlySeries(recent.alerts);
  const last24h = series.reduce(
    (acc, p) => acc + p.deterministic + p.semantic,
    0
  );
  const topCategories = Object.entries(stats.by_category)
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count);
  const topCategory = topCategories[0];
  const layerDet = stats.by_layer.deterministic ?? 0;
  const layerSem = stats.by_layer.semantic ?? 0;
  const ratio =
    layerDet + layerSem === 0
      ? "—"
      : `${Math.round((layerDet / (layerDet + layerSem)) * 100)}% / ${Math.round(
          (layerSem / (layerDet + layerSem)) * 100
        )}%`;
  const subnets = topAttackerSubnets(recent.alerts);
  const rules = topRules(recent.alerts);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="text-sm text-muted-foreground">
          Live view of blocked requests across both defense layers.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-4">
        <Card className="lg:row-span-2">
          <CardHeader>
            <CardTitle className="text-base">Heimdall Safety Index</CardTitle>
          </CardHeader>
          <CardContent className="pt-2 pb-4">
            <SafetyDial
              blocks24h={last24h}
              totalBlocks={stats.total}
              ratio={ratio}
              topCategory={topCategory ? owaspShort(topCategory.category) : "—"}
            />
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard
            label="Total blocks"
            value={stats.total.toLocaleString()}
            hint="All time"
            accent="info"
          />
          <KpiCard
            label="Last 24h"
            value={last24h.toLocaleString()}
            hint={`${series.length} hour windows`}
            accent={last24h > 0 ? "warning" : "good"}
          />
          <KpiCard
            label="Top category"
            value={topCategory ? owaspShort(topCategory.category) : "—"}
            hint={topCategory ? `${topCategory.count} hits` : "no blocks yet"}
            accent="danger"
          />
          <KpiCard
            label="L1 / L2 split"
            value={ratio}
            hint="deterministic / semantic"
            accent="info"
          />
          <KpiCard
            label="Unique attackers"
            value={subnets.length.toLocaleString()}
            hint="distinct /16 subnets (recent)"
            accent="warning"
          />
          <KpiCard
            label="Rules fired"
            value={rules.length.toLocaleString()}
            hint="distinct rules (recent)"
            accent="info"
          />
        </div>

        <Card className="lg:col-start-2">
          <CardHeader>
            <CardTitle className="text-base">Blocks per hour (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            <BlocksChart data={series} />
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Live activity stream</CardTitle>
          </CardHeader>
          <CardContent>
            <LiveFeed />
          </CardContent>
        </Card>
        <ThreatMap />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">OWASP categories</CardTitle>
          </CardHeader>
          <CardContent>
            <CategoryBar items={topCategories} total={stats.total} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top rules fired</CardTitle>
          </CardHeader>
          <CardContent>
            {rules.length === 0 ? (
              <p className="text-sm text-muted-foreground">No rule hits yet.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {rules.map((r) => (
                  <li key={r.rule} className="flex justify-between font-mono">
                    <span className="text-foreground">{r.rule}</span>
                    <span className="text-muted-foreground tabular-nums">
                      {r.count}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Top attacker subnets</CardTitle>
        </CardHeader>
        <CardContent>
          {subnets.length === 0 ? (
            <p className="text-sm text-muted-foreground">Quiet so far.</p>
          ) : (
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm font-mono">
              {subnets.map((s) => (
                <li
                  key={s.subnet}
                  className="flex justify-between border border-border/60 rounded px-3 py-1.5"
                >
                  <span>{s.subnet}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {s.count}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

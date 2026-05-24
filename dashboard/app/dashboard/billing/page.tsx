import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { KpiCard } from "@/components/kpi-card";
import { BudgetForm } from "@/components/billing/budget-form";
import { SpendChart } from "@/components/billing/spend-chart";
import { getBilling } from "@/lib/heimdall";

export const dynamic = "force-dynamic";

export default async function BillingPage() {
  const data = await getBilling();
  const limit = data.budget?.monthly_limit_usd ?? 0;
  const pct = data.month_to_date_pct ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Spending &amp; budget</h1>
        <p className="text-sm text-muted-foreground">
          Token usage and cost across every proxied request, this month.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Month to date"
          value={`$${data.month_to_date_usd.toFixed(2)}`}
          hint={limit > 0 ? `${pct.toFixed(1)}% of $${limit.toFixed(0)}` : "no budget set"}
          accent={pct >= 80 ? "danger" : "info"}
        />
        <KpiCard
          label="Projected end of month"
          value={
            data.projected_month_end_usd != null
              ? `$${data.projected_month_end_usd.toFixed(2)}`
              : "—"
          }
          hint="7-day rolling avg × days remaining"
          accent="warning"
        />
        <KpiCard
          label="Top model"
          value={data.top_models[0]?.model ?? "—"}
          hint={data.top_models[0] ? `$${data.top_models[0].cost_usd.toFixed(2)}` : "no usage yet"}
          accent="info"
        />
        <KpiCard
          label="Requests this month"
          value={data.daily_series
            .reduce((a, d) => a + d.requests, 0)
            .toLocaleString()}
          hint={`${data.daily_series.length} days of data`}
          accent="good"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Daily cost (30d)</CardTitle>
          </CardHeader>
          <CardContent>
            <SpendChart data={data.daily_series} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Monthly budget</CardTitle>
          </CardHeader>
          <CardContent>
            <BudgetForm budget={data.budget} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Top models</CardTitle>
        </CardHeader>
        <CardContent>
          {data.top_models.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No usage yet — make a request through Heimdall to see costs here.
            </p>
          ) : (
            <ul className="space-y-2 text-sm font-mono">
              {data.top_models.map((m) => (
                <li
                  key={m.model}
                  className="flex justify-between border border-border/60 rounded px-3 py-2"
                >
                  <span>{m.model}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {m.tokens.toLocaleString()} tok · ${m.cost_usd.toFixed(4)} ·{" "}
                    {m.requests.toLocaleString()} req
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

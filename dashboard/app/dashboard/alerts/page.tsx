import Link from "next/link";

import { AlertsTableBody } from "@/components/alerts-table-body";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getAlerts } from "@/lib/heimdall";
import { OWASP_LLM_TOP_10 } from "@/lib/owasp";
import type { Layer } from "@/lib/types";

const LAYERS: Layer[] = ["deterministic", "semantic"];

interface SearchParams {
  layer?: string;
  category?: string;
  limit?: string;
  offset?: string;
}

export const dynamic = "force-dynamic";

export default async function AlertsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const limit = Math.min(Math.max(parseInt(sp.limit ?? "50", 10) || 50, 1), 500);
  const offset = Math.max(parseInt(sp.offset ?? "0", 10) || 0, 0);
  const layer = (LAYERS as string[]).includes(sp.layer ?? "")
    ? (sp.layer as Layer)
    : null;
  const category = (OWASP_LLM_TOP_10 as readonly string[]).includes(
    sp.category ?? ""
  )
    ? (sp.category as string)
    : null;

  const data = await getAlerts({ limit, offset, layer, category });

  const buildHref = (patch: Partial<SearchParams>) => {
    const params = new URLSearchParams();
    const next = { ...sp, ...patch };
    if (next.layer) params.set("layer", next.layer);
    if (next.category) params.set("category", next.category);
    if (next.limit) params.set("limit", next.limit);
    if (next.offset && next.offset !== "0") params.set("offset", next.offset);
    const qs = params.toString();
    return `/dashboard/alerts${qs ? `?${qs}` : ""}`;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Alerts</h1>
          <p className="text-sm text-muted-foreground">
            Every blocked request, freshest first. Click a row for the full prompt.
          </p>
        </div>
        <div className="text-xs text-muted-foreground">
          showing {data.count} · offset {offset}
        </div>
      </div>

      {/* Filter row */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground mr-1">Layer:</span>
          <FilterChip active={!layer} href={buildHref({ layer: undefined, offset: "0" })}>
            all
          </FilterChip>
          {LAYERS.map((l) => (
            <FilterChip
              key={l}
              active={layer === l}
              href={buildHref({ layer: l, offset: "0" })}
            >
              {l}
            </FilterChip>
          ))}
          <span className="mx-3 h-4 w-px bg-border" />
          <span className="text-muted-foreground mr-1">Category:</span>
          <FilterChip
            active={!category}
            href={buildHref({ category: undefined, offset: "0" })}
          >
            all
          </FilterChip>
          {OWASP_LLM_TOP_10.map((c) => (
            <FilterChip
              key={c}
              active={category === c}
              href={buildHref({ category: c, offset: "0" })}
            >
              {c.split(":")[0]}
            </FilterChip>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[160px]">Timestamp</TableHead>
                <TableHead className="w-[140px]">Source</TableHead>
                <TableHead className="w-[140px]">Layer</TableHead>
                <TableHead className="w-[90px]">OWASP</TableHead>
                <TableHead className="w-[220px]">Rule</TableHead>
                <TableHead>Blocked prompt</TableHead>
              </TableRow>
            </TableHeader>
            <AlertsTableBody alerts={data.alerts} />
          </Table>
        </CardContent>
      </Card>
      <p className="text-[11px] text-muted-foreground -mt-3">
        Tip — click any row to open the audit drawer with diff, violations,
        request context, and feedback actions.
      </p>

      <div className="flex justify-between text-sm">
        <Link
          href={buildHref({ offset: String(Math.max(offset - limit, 0)) })}
          aria-disabled={offset === 0}
          className={`underline-offset-4 hover:underline ${
            offset === 0 ? "pointer-events-none text-muted-foreground/40" : ""
          }`}
        >
          ← Newer
        </Link>
        <Link
          href={buildHref({ offset: String(offset + limit) })}
          aria-disabled={data.alerts.length < limit}
          className={`underline-offset-4 hover:underline ${
            data.alerts.length < limit
              ? "pointer-events-none text-muted-foreground/40"
              : ""
          }`}
        >
          Older →
        </Link>
      </div>
    </div>
  );
}

function FilterChip({
  active,
  href,
  children,
}: {
  active: boolean;
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs transition-colors ${
        active
          ? "border-foreground/60 bg-foreground text-background"
          : "border-border/60 hover:bg-secondary/60"
      }`}
    >
      {children}
    </Link>
  );
}

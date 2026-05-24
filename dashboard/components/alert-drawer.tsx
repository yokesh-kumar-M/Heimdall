"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { CategoryBadge } from "@/components/category-badge";
import { LayerBadge } from "@/components/layer-badge";
import { DiffLegend, DiffView } from "@/components/sandbox/diff-view";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { absoluteTime, relativeTime, truncate } from "@/lib/format";
import type { Incident, Alert } from "@/lib/types";

interface Props {
  alertId: number | null;
  onOpenChange: (open: boolean) => void;
}

const COUNTRY_LABEL: Record<string, string> = {
  LO: "Loopback",
  LAN: "Private network",
};

export function AlertDrawer({ alertId, onOpenChange }: Props) {
  const [data, setData] = useState<Incident | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);

  useEffect(() => {
    if (alertId == null) return;
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset + fetch when the selected alert changes
    setLoading(true);
    setError(null);
    setData(null);
    fetch(`/api/alerts/${alertId}`, { cache: "no-store" })
      .then(async (r) => {
        if (!alive) return;
        if (!r.ok) throw new Error(`Failed to load alert (${r.status})`);
        setData((await r.json()) as Incident);
      })
      .catch((e) => {
        if (alive) setError((e as Error).message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [alertId]);

  const primary = data?.violations.find((v) => v.id === data.primary_id) ?? data?.violations[0];

  const flagFP = async () => {
    if (!primary) return;
    setPosting(true);
    try {
      const r = await fetch(`/api/alerts/${primary.id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feedback_type: "false_positive",
          note: "Flagged from drawer",
        }),
      });
      if (!r.ok) throw new Error(`feedback failed (${r.status})`);
      toast.success("Flagged as false positive", {
        description: "Recorded — analysts can audit feedback under Phase 3 policy.",
      });
      // Refresh
      const fresh = await fetch(`/api/alerts/${primary.id}`, { cache: "no-store" });
      if (fresh.ok) setData((await fresh.json()) as Incident);
    } catch (e) {
      toast.error("Could not flag", { description: (e as Error).message });
    } finally {
      setPosting(false);
    }
  };

  const open = alertId != null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="!max-w-2xl w-full overflow-y-auto sm:max-w-2xl">
        {loading ? (
          <DrawerSkeleton />
        ) : error ? (
          <div className="p-6 text-sm text-rose-300">{error}</div>
        ) : primary && data ? (
          <>
            <SheetHeader className="border-b border-white/[0.06]">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <SheetTitle className="text-base">Incident detail</SheetTitle>
                  <SheetDescription className="text-xs">
                    {relativeTime(primary.timestamp)} ·{" "}
                    <span className="font-mono">{absoluteTime(primary.timestamp)}</span>
                  </SheetDescription>
                </div>
                <div className="flex flex-col items-end gap-1 text-xs">
                  <LayerBadge layer={primary.triggered_layer} />
                  <span className="font-mono text-muted-foreground">
                    {primary.masked_ip}
                    {primary.country_code
                      ? ` · ${COUNTRY_LABEL[primary.country_code] ?? primary.country_code}`
                      : ""}
                  </span>
                  {data.violations.length > 1 ? (
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      {data.violations.length} violations · incident{" "}
                      <code>{data.incident_id?.slice(0, 8)}</code>
                    </span>
                  ) : null}
                </div>
              </div>
            </SheetHeader>

            <div className="px-4 pb-4 pt-3 space-y-4">
              {/* Verdict + quick rules */}
              <div className="rounded-lg border border-rose-400/30 bg-gradient-to-r from-rose-500/15 via-rose-500/10 to-transparent px-3 py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <span className="inline-flex items-center justify-center h-5 w-5 rounded-full grad-danger text-white text-[10px] font-bold">
                    ✕
                  </span>
                  Blocked — would not reach upstream LLM
                </div>
                <code className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-full bg-rose-500/15 text-rose-300 border border-rose-400/30">
                  403 Forbidden
                </code>
              </div>

              {/* Tabs */}
              <Tabs defaultValue="diff" className="w-full">
                <TabsList>
                  <TabsTrigger value="diff">Diff</TabsTrigger>
                  <TabsTrigger value="violations">
                    Violations · {data.violations.length}
                  </TabsTrigger>
                  <TabsTrigger value="request">Request</TabsTrigger>
                  <TabsTrigger value="raw">Raw JSON</TabsTrigger>
                </TabsList>

                <TabsContent value="diff" className="mt-3 space-y-3">
                  <DiffLegend />
                  <div className="rounded-lg border border-white/[0.06] bg-black/40 p-3">
                    <DiffView
                      original={primary.original_prompt ?? primary.blocked_prompt}
                      sanitized={primary.sanitized_prompt ?? primary.blocked_prompt}
                    />
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    The right-hand stream is what would have been forwarded if
                    no rule had fired. Heimdall blocked before either path was
                    chosen.
                  </p>
                </TabsContent>

                <TabsContent value="violations" className="mt-3 space-y-2">
                  {data.violations.map((v) => (
                    <ViolationRow key={v.id} v={v} />
                  ))}
                </TabsContent>

                <TabsContent value="request" className="mt-3">
                  <RequestDetails primary={primary} />
                </TabsContent>

                <TabsContent value="raw" className="mt-3">
                  <pre className="rounded-lg border border-white/[0.06] bg-black/40 p-3 overflow-auto max-h-[460px] font-mono text-[11px] leading-relaxed text-muted-foreground">
                    {JSON.stringify(data, null, 2)}
                  </pre>
                </TabsContent>
              </Tabs>

              {/* Feedback area */}
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-3 space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium">Threat actions</div>
                    <p className="text-[11px] text-muted-foreground">
                      Feedback is recorded for Phase 3 rule tuning. It does not
                      currently disable scanners.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={flagFP}
                    disabled={posting}
                  >
                    {posting ? "Flagging…" : "Flag false positive"}
                  </Button>
                </div>
                {data.feedback.length > 0 ? (
                  <ul className="text-xs text-muted-foreground border-t border-white/[0.06] pt-2 space-y-1">
                    {data.feedback.map((f) => (
                      <li key={f.id} className="font-mono">
                        <span className="text-amber-300">[{f.feedback_type}]</span>{" "}
                        {f.note ?? "—"}{" "}
                        <span className="text-[10px]">
                          {relativeTime(f.created_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function DrawerSkeleton() {
  return (
    <div className="p-6 space-y-3">
      <div className="shimmer h-5 w-1/3 rounded" />
      <div className="shimmer h-3 w-2/3 rounded" />
      <div className="shimmer h-32 w-full rounded mt-4" />
      <div className="shimmer h-32 w-full rounded" />
    </div>
  );
}

function ViolationRow({ v }: { v: Alert }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
      <CategoryBadge category={v.owasp_category} />
      <div className="flex-1 space-y-0.5">
        <code className="text-sm text-foreground">{v.rule}</code>
        <p className="text-xs text-muted-foreground leading-relaxed">{v.detail}</p>
        {v.snippet ? (
          <p className="text-[11px] text-muted-foreground font-mono">
            snippet: {truncate(v.snippet, 100)}
          </p>
        ) : null}
      </div>
      <span className="text-[10px] text-muted-foreground font-mono">
        #{v.id}
      </span>
    </div>
  );
}

function RequestDetails({ primary }: { primary: Alert }) {
  const rows: Array<[string, React.ReactNode]> = [
    ["Model", primary.model ?? "—"],
    ["Layer", <LayerBadge key="l" layer={primary.triggered_layer} />],
    ["IP (masked)", <code key="ip">{primary.masked_ip}</code>],
    [
      "Geo",
      primary.country_code
        ? `${COUNTRY_LABEL[primary.country_code] ?? primary.country_code}`
        : "—",
    ],
    ["User-Agent", primary.user_agent ?? "—"],
    ["Timestamp", <code key="t">{absoluteTime(primary.timestamp)}</code>],
    [
      "Incident",
      primary.incident_id ? (
        <code key="i" className="text-xs">
          {primary.incident_id}
        </code>
      ) : (
        "—"
      ),
    ],
  ];

  return (
    <div className="space-y-3">
      <table className="w-full text-xs">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-b border-white/[0.04] last:border-0">
              <td className="py-1.5 pr-3 text-muted-foreground w-[120px] uppercase tracking-wider text-[10px]">
                {k}
              </td>
              <td className="py-1.5">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Model params
        </div>
        <pre className="rounded-lg border border-white/[0.06] bg-black/40 p-2 font-mono text-[11px] text-muted-foreground overflow-auto max-h-[160px]">
          {JSON.stringify(primary.model_params ?? {}, null, 2)}
        </pre>
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Extra (L2 / scanner internal state)
        </div>
        <pre className="rounded-lg border border-white/[0.06] bg-black/40 p-2 font-mono text-[11px] text-muted-foreground overflow-auto max-h-[160px]">
          {JSON.stringify(primary.extra ?? {}, null, 2)}
        </pre>
      </div>
    </div>
  );
}

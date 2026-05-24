"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { relativeTime } from "@/lib/format";
import type { PoliciesResponse, PolicyRow } from "@/lib/policy-types";
import { cn } from "@/lib/utils";

export default function PoliciesPage() {
  const [data, setData] = useState<PoliciesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/policies", { cache: "no-store" });
      if (!r.ok) throw new Error(`Failed (${r.status})`);
      setData((await r.json()) as PoliciesResponse);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const update = async (
    rule: string,
    patch: Partial<Pick<PolicyRow, "enabled" | "suppress_after_n_fp" | "note">>
  ) => {
    setWorking(rule);
    try {
      const r = await fetch(`/api/policies/${encodeURIComponent(rule)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!r.ok) throw new Error(`Update failed (${r.status})`);
      toast.success(`Updated ${rule}`);
      await refresh();
    } catch (e) {
      toast.error("Update failed", { description: (e as Error).message });
    } finally {
      setWorking(null);
    }
  };

  const reset = async (rule: string) => {
    setWorking(rule);
    try {
      const r = await fetch(`/api/policies/${encodeURIComponent(rule)}`, {
        method: "DELETE",
      });
      if (!r.ok) throw new Error(`Reset failed (${r.status})`);
      toast.success(`Reset ${rule} to default`);
      await refresh();
    } catch (e) {
      toast.error("Reset failed", { description: (e as Error).message });
    } finally {
      setWorking(null);
    }
  };

  if (error) {
    return <div className="text-sm text-rose-300">{error}</div>;
  }

  if (!data) {
    return <div className="text-sm text-muted-foreground">Loading policies…</div>;
  }

  const disabled = data.policies.filter((p) => !p.enabled);
  const flagged = data.policies.filter(
    (p) => p.enabled && p.fp_count >= Math.ceil((data.default_fp_threshold ?? 5) / 2)
  );

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Rule Policies
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Tune scanner behaviour per rule. Disabled rules are still scanned
            (so the audit trail stays complete) but their findings are
            shadowed — they no longer gate the request.
          </p>
        </div>
        <div className="text-xs text-muted-foreground font-mono">
          default FP threshold {data.default_fp_threshold ?? "—"} ·{" "}
          {disabled.length} suppressed
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Rule</TableHead>
                <TableHead className="w-[100px] text-right">Hits</TableHead>
                <TableHead className="w-[100px] text-right">FP feedback</TableHead>
                <TableHead className="w-[120px]">Threshold</TableHead>
                <TableHead className="w-[120px]">State</TableHead>
                <TableHead className="w-[200px]">Note</TableHead>
                <TableHead className="w-[180px] text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.policies.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-8">
                    No rules have fired yet. Policies appear here once
                    scanners record their first hit.
                  </TableCell>
                </TableRow>
              ) : (
                data.policies.map((p) => (
                  <PolicyRowView
                    key={p.rule}
                    row={p}
                    busy={working === p.rule}
                    onSubmit={update}
                    onReset={reset}
                  />
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {flagged.length > 0 ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-amber-300">
              Rules approaching auto-suppress
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-xs font-mono">
              {flagged.map((p) => (
                <li
                  key={p.rule}
                  className="flex items-center justify-between border-b border-white/[0.04] py-1.5 last:border-0"
                >
                  <span>{p.rule}</span>
                  <span className="text-muted-foreground">
                    {p.fp_count} FP / threshold {p.suppress_after_n_fp ?? "—"}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function PolicyRowView({
  row,
  busy,
  onSubmit,
  onReset,
}: {
  row: PolicyRow;
  busy: boolean;
  onSubmit: (
    rule: string,
    patch: Partial<Pick<PolicyRow, "enabled" | "suppress_after_n_fp" | "note">>
  ) => Promise<void>;
  onReset: (rule: string) => Promise<void>;
}) {
  const [threshold, setThreshold] = useState<string>(
    row.suppress_after_n_fp == null ? "" : String(row.suppress_after_n_fp)
  );
  const [note, setNote] = useState<string>(row.note ?? "");

  useEffect(() => {
    setThreshold(
      row.suppress_after_n_fp == null ? "" : String(row.suppress_after_n_fp)
    );
    setNote(row.note ?? "");
  }, [row.suppress_after_n_fp, row.note]);

  return (
    <TableRow className={cn(!row.enabled && "opacity-70")}>
      <TableCell className="font-mono text-xs">{row.rule}</TableCell>
      <TableCell className="text-right tabular-nums text-xs">
        {row.hits.toLocaleString()}
      </TableCell>
      <TableCell className="text-right tabular-nums text-xs">
        {row.fp_count > 0 ? (
          <span className="text-amber-300">{row.fp_count}</span>
        ) : (
          <span className="text-muted-foreground">0</span>
        )}
      </TableCell>
      <TableCell>
        <Input
          value={threshold}
          onChange={(e) => setThreshold(e.target.value.replace(/[^\d]/g, ""))}
          placeholder="default"
          className="h-7 text-xs font-mono"
          inputMode="numeric"
        />
      </TableCell>
      <TableCell>
        {row.enabled ? (
          <Badge className="bg-emerald-500/15 text-emerald-200 border border-emerald-400/30 text-[10px]">
            ENABLED
          </Badge>
        ) : row.auto_suppressed ? (
          <Badge className="bg-amber-500/15 text-amber-200 border border-amber-400/30 text-[10px]">
            AUTO-SUPPRESSED
          </Badge>
        ) : (
          <Badge className="bg-rose-500/15 text-rose-200 border border-rose-400/30 text-[10px]">
            SUPPRESSED
          </Badge>
        )}
        <div className="text-[10px] text-muted-foreground mt-1">
          {relativeTime(row.updated_at)}
        </div>
      </TableCell>
      <TableCell>
        <Input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="reason…"
          className="h-7 text-xs"
        />
      </TableCell>
      <TableCell className="text-right space-x-1">
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() =>
            onSubmit(row.rule, {
              enabled: !row.enabled,
              note: note || null,
              suppress_after_n_fp:
                threshold === "" ? null : Number.parseInt(threshold, 10),
            })
          }
          className="h-7 text-[11px]"
        >
          {row.enabled ? "Suppress" : "Enable"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => onReset(row.rule)}
          className="h-7 text-[11px] text-muted-foreground"
        >
          Reset
        </Button>
      </TableCell>
    </TableRow>
  );
}

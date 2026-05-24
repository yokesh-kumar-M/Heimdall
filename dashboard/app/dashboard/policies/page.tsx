"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import { toast } from "sonner";
import { Search, ShieldAlert, RotateCcw } from "lucide-react";

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

  // Search and Filter States
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedLayer, setSelectedLayer] = useState<"all" | "L1" | "L2">("all");
  const [selectedStatus, setSelectedStatus] = useState<"all" | "enabled" | "suppressed" | "auto-suppressed">("all");

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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- data fetch on mount; setState fires after the await
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

  // Filter Logic
  const filteredPolicies = data.policies.filter((p) => {
    const matchesSearch =
      p.rule.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (p.note && p.note.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesLayer =
      selectedLayer === "all" ||
      (selectedLayer === "L1" && p.rule.toLowerCase().startsWith("l1_")) ||
      (selectedLayer === "L2" && p.rule.toLowerCase().startsWith("l2_"));

    const matchesStatus =
      selectedStatus === "all" ||
      (selectedStatus === "enabled" && p.enabled) ||
      (selectedStatus === "suppressed" && !p.enabled && !p.auto_suppressed) ||
      (selectedStatus === "auto-suppressed" && p.auto_suppressed);

    return matchesSearch && matchesLayer && matchesStatus;
  });

  const disabled = data.policies.filter((p) => !p.enabled);
  const flagged = data.policies.filter(
    (p) => p.enabled && p.fp_count >= Math.ceil((data.default_fp_threshold ?? 5) / 2)
  );

  const maxHits = Math.max(1, ...data.policies.map((p) => p.hits));

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

      {/* Advanced Filter Panel */}
      <Card className="border-white/[0.06] bg-black/40">
        <CardContent className="p-4 flex flex-col md:flex-row items-center gap-4 text-sm justify-between">
          <div className="relative w-full md:max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search rules or notes..."
              className="h-9 pl-9 pr-8 text-xs"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs font-mono"
              >
                ✕
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-4 w-full md:w-auto">
            {/* Layer Filter */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">Layer:</span>
              <div className="flex rounded-lg bg-white/[0.04] p-0.5 border border-white/[0.06] text-xs">
                {(["all", "L1", "L2"] as const).map((l) => (
                  <button
                    key={l}
                    onClick={() => setSelectedLayer(l)}
                    className={cn(
                      "px-2.5 py-0.5 rounded-md transition-all cursor-pointer font-mono text-[10px]",
                      selectedLayer === l
                        ? "bg-white/[0.08] text-foreground font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </div>

            {/* Status Filter */}
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">Status:</span>
              <div className="flex rounded-lg bg-white/[0.04] p-0.5 border border-white/[0.06] text-xs">
                {(["all", "enabled", "suppressed", "auto-suppressed"] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => setSelectedStatus(s)}
                    className={cn(
                      "px-2.5 py-0.5 rounded-md transition-all cursor-pointer font-mono text-[10px]",
                      selectedStatus === s
                        ? "bg-white/[0.08] text-foreground font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {s.replace("-", " ")}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="overflow-hidden border-white/[0.06] bg-black/40">
        <CardContent className="p-0">
          <Table>
            <TableHeader className="bg-white/[0.02]">
              <TableRow>
                <TableHead>Rule</TableHead>
                <TableHead className="w-[120px] text-right">Hits</TableHead>
                <TableHead className="w-[100px] text-right">FP feedback</TableHead>
                <TableHead className="w-[130px]">Threshold</TableHead>
                <TableHead className="w-[150px]">State</TableHead>
                <TableHead className="w-[220px]">Note</TableHead>
                <TableHead className="w-[150px] text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredPolicies.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-12">
                    No rules match the current search or filters.
                  </TableCell>
                </TableRow>
              ) : (
                filteredPolicies.map((p) => (
                  <PolicyRowView
                    key={p.rule}
                    row={p}
                    maxHits={maxHits}
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
        <Card className="border-amber-500/20 bg-amber-500/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wider text-amber-300 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4" />
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
                  <span className="text-muted-foreground">{p.rule}</span>
                  <span className="text-amber-200">
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
  maxHits,
  busy,
  onSubmit,
  onReset,
}: {
  row: PolicyRow;
  maxHits: number;
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
  const [justSaved, setJustSaved] = useState(false);
  const prevBusy = useRef(busy);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing external row updates into editable local draft
    setThreshold(
      row.suppress_after_n_fp == null ? "" : String(row.suppress_after_n_fp)
    );
    setNote(row.note ?? "");
  }, [row.suppress_after_n_fp, row.note]);

  // Handle auto-save checkmarks on blur
  useEffect(() => {
    if (prevBusy.current && !busy) {
      setJustSaved(true);
      const t = setTimeout(() => setJustSaved(false), 2000);
      return () => clearTimeout(t);
    }
    prevBusy.current = busy;
  }, [busy]);

  const handleThresholdBlur = () => {
    const val = threshold === "" ? null : Number.parseInt(threshold, 10);
    if (val !== row.suppress_after_n_fp) {
      void onSubmit(row.rule, { suppress_after_n_fp: val });
    }
  };

  const handleNoteBlur = () => {
    const val = note.trim() === "" ? null : note.trim();
    if (val !== row.note) {
      void onSubmit(row.rule, { note: val });
    }
  };

  return (
    <TableRow className={cn("transition-colors hover:bg-white/[0.01]", !row.enabled && "opacity-60")}>
      <TableCell className="font-mono text-xs font-semibold">{row.rule}</TableCell>
      
      {/* Hits with Sparkbar */}
      <TableCell className="relative text-right tabular-nums text-xs pr-4 min-w-[110px] h-11 align-middle">
        <div
          className="absolute right-0 bottom-1/2 translate-y-1/2 h-2.5 rounded-l bg-violet-500/10 border-r-2 border-violet-400/40 transition-all duration-500"
          style={{ width: `${(row.hits / maxHits) * 100}%` }}
        />
        <span className="relative z-10 font-mono font-medium">
          {row.hits.toLocaleString()}
        </span>
      </TableCell>

      <TableCell className="text-right tabular-nums text-xs">
        {row.fp_count > 0 ? (
          <span className="text-amber-300 font-semibold">{row.fp_count}</span>
        ) : (
          <span className="text-muted-foreground/60">0</span>
        )}
      </TableCell>

      {/* Auto-save suppress threshold */}
      <TableCell className="relative">
        <Input
          value={threshold}
          onChange={(e) => setThreshold(e.target.value.replace(/[^\d]/g, ""))}
          onBlur={handleThresholdBlur}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          placeholder="default"
          className="h-7 text-xs font-mono pr-6 border-white/10 bg-black/20 focus:border-violet-500/40 focus:ring-1 focus:ring-violet-500/30"
          inputMode="numeric"
          disabled={busy}
        />
        {busy && (
          <span className="absolute right-3.5 top-1/2 -translate-y-1/2 h-3 w-3 animate-spin rounded-full border border-solid border-violet-400 border-t-transparent" />
        )}
        {justSaved && !busy && (
          <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-emerald-400 text-[10px] font-bold">✓</span>
        )}
      </TableCell>

      {/* State Badge */}
      <TableCell>
        {row.enabled ? (
          <Badge className="bg-emerald-500/10 text-emerald-300 border-emerald-400/20 text-[9px] font-semibold tracking-wider">
            ENABLED
          </Badge>
        ) : row.auto_suppressed ? (
          <Badge className="bg-amber-500/10 text-amber-300 border-amber-400/20 text-[9px] font-semibold tracking-wider">
            AUTO-MUTED
          </Badge>
        ) : (
          <Badge className="bg-rose-500/10 text-rose-300 border-rose-400/20 text-[9px] font-semibold tracking-wider">
            MUTED
          </Badge>
        )}
        <div className="text-[9px] text-muted-foreground/70 mt-1 font-mono">
          {relativeTime(row.updated_at)}
        </div>
      </TableCell>

      {/* Auto-save Audit Note */}
      <TableCell className="relative">
        <Input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={handleNoteBlur}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          placeholder="reason…"
          className="h-7 text-xs pr-6 border-white/10 bg-black/20 focus:border-violet-500/40 focus:ring-1 focus:ring-violet-500/30"
          disabled={busy}
        />
        {busy && (
          <span className="absolute right-3.5 top-1/2 -translate-y-1/2 h-3 w-3 animate-spin rounded-full border border-solid border-violet-400 border-t-transparent" />
        )}
        {justSaved && !busy && (
          <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-emerald-400 text-[10px] font-bold">✓</span>
        )}
      </TableCell>

      {/* Actions */}
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-2.5">
          {/* Animated Custom Slide Switch */}
          <button
            role="switch"
            aria-checked={row.enabled}
            disabled={busy}
            title={row.enabled ? "Suppress scanner rule" : "Enable scanner rule"}
            onClick={() =>
              onSubmit(row.rule, {
                enabled: !row.enabled,
                note: note || null,
                suppress_after_n_fp: threshold === "" ? null : Number.parseInt(threshold, 10),
              })
            }
            className={cn(
              "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border border-white/10 transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-50",
              row.enabled ? "bg-emerald-500/90 hover:bg-emerald-500" : "bg-white/[0.08]"
            )}
          >
            <span
              className={cn(
                "pointer-events-none inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out mt-0.5",
                row.enabled ? "translate-x-4.5" : "translate-x-0.5"
              )}
            />
          </button>

          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => onReset(row.rule)}
            className="h-7 w-7 p-0 text-muted-foreground hover:text-rose-400 transition-colors hover:bg-rose-500/5 rounded-md"
            title="Reset to defaults"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

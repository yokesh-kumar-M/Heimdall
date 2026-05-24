"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Budget {
  monthly_limit_usd: number;
  warn_at_pct: number;
  hard_cap_usd: number | null;
}

export function BudgetForm({ budget }: { budget: Budget | null }) {
  const [limit, setLimit] = useState(budget?.monthly_limit_usd?.toString() ?? "");
  const [warn, setWarn] = useState(budget?.warn_at_pct?.toString() ?? "80");
  const [hard, setHard] = useState(budget?.hard_cap_usd?.toString() ?? "");
  const [pending, start] = useTransition();

  async function save() {
    start(async () => {
      const res = await fetch("/api/billing/budget", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          monthly_limit_usd: limit ? Number(limit) : 0,
          warn_at_pct: warn ? Number(warn) : 80,
          hard_cap_usd: hard ? Number(hard) : null,
        }),
      });
      if (res.ok) {
        toast.success("Budget saved");
      } else {
        toast.error(`Failed: ${res.status} ${res.statusText}`);
      }
    });
  }

  return (
    <div className="space-y-3">
      <label className="block text-xs text-muted-foreground">
        Monthly limit (USD)
        <Input
          type="number"
          step="0.01"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
          placeholder="50.00"
          className="mt-1"
        />
      </label>
      <label className="block text-xs text-muted-foreground">
        Warn at (% of limit)
        <Input
          type="number"
          min="1"
          max="100"
          value={warn}
          onChange={(e) => setWarn(e.target.value)}
          className="mt-1"
        />
      </label>
      <label className="block text-xs text-muted-foreground">
        Hard cap (USD) — blocks requests above this
        <Input
          type="number"
          step="0.01"
          value={hard}
          onChange={(e) => setHard(e.target.value)}
          placeholder="(optional)"
          className="mt-1"
        />
      </label>
      <Button onClick={save} disabled={pending} className="w-full">
        {pending ? "Saving…" : "Save budget"}
      </Button>
    </div>
  );
}

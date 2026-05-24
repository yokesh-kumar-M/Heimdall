"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Trash2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Provider {
  id: number;
  slug: string;
  display_name: string;
  base_url: string;
  has_key: boolean;
  secret_ref: string | null;
  priority: number;
  enabled: boolean;
  health_status: string;
  consecutive_failures: number;
  routing_strategy: string;
}

const PRESETS = [
  { slug: "openai", display_name: "OpenAI", base_url: "https://api.openai.com/v1", secret_ref: "OPENAI_API_KEY" },
  { slug: "anthropic", display_name: "Anthropic (OAI-compat)", base_url: "https://api.anthropic.com/v1", secret_ref: "ANTHROPIC_API_KEY" },
  { slug: "openrouter", display_name: "OpenRouter", base_url: "https://openrouter.ai/api/v1", secret_ref: "OPENROUTER_API_KEY" },
  { slug: "groq", display_name: "Groq", base_url: "https://api.groq.com/openai/v1", secret_ref: "GROQ_API_KEY" },
];

export function ProvidersClient({ initial }: { initial: Provider[] }) {
  const [items, setItems] = useState(initial);
  const [pending, start] = useTransition();
  const [form, setForm] = useState({
    slug: "", display_name: "", base_url: "", secret_ref: "",
    priority: 100, enabled: true, routing_strategy: "primary_failover",
  });

  function applyPreset(slug: string) {
    const p = PRESETS.find((p) => p.slug === slug);
    if (p) setForm((f) => ({ ...f, ...p }));
  }

  async function save() {
    if (!form.slug || !form.display_name || !form.base_url) {
      toast.error("slug, name, and base_url required");
      return;
    }
    start(async () => {
      const res = await fetch("/api/providers", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        toast.error(`Failed: ${res.status}`);
        return;
      }
      const updated = await res.json();
      setItems((cur) => {
        const existing = cur.findIndex((p) => p.id === updated.id);
        return existing >= 0
          ? cur.map((p, i) => (i === existing ? updated : p))
          : [...cur, updated].sort((a, b) => a.priority - b.priority);
      });
      toast.success("Provider saved");
    });
  }

  async function remove(id: number) {
    if (!confirm("Delete this provider?")) return;
    const res = await fetch(`/api/providers/${id}`, { method: "DELETE" });
    if (!res.ok) {
      toast.error(`Failed: ${res.status}`);
      return;
    }
    setItems((cur) => cur.filter((p) => p.id !== id));
  }

  return (
    <div className="space-y-6">
      {/* form */}
      <div className="rounded-xl border border-white/[0.06] p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Quick add:</span>
          {PRESETS.map((p) => (
            <Button
              key={p.slug}
              size="sm"
              variant="ghost"
              onClick={() => applyPreset(p.slug)}
            >
              {p.display_name}
            </Button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Input
            placeholder="slug (openai)"
            value={form.slug}
            onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
          />
          <Input
            placeholder="display name"
            value={form.display_name}
            onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
          />
          <Input
            placeholder="https://…/v1"
            className="col-span-2"
            value={form.base_url}
            onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
          />
          <Input
            placeholder="env var holding API key (e.g. OPENAI_API_KEY)"
            value={form.secret_ref}
            onChange={(e) => setForm((f) => ({ ...f, secret_ref: e.target.value }))}
          />
          <Input
            type="number"
            placeholder="priority"
            value={form.priority}
            onChange={(e) => setForm((f) => ({ ...f, priority: Number(e.target.value) }))}
          />
        </div>
        <Button onClick={save} disabled={pending}>
          <Plus className="h-4 w-4" /> {pending ? "Saving…" : "Add / update provider"}
        </Button>
      </div>

      {/* list */}
      <ul className="divide-y divide-white/[0.06] border border-white/[0.06] rounded-lg overflow-hidden">
        {items.length === 0 && (
          <li className="px-4 py-6 text-sm text-muted-foreground">
            No providers yet. Heimdall will use the global UPSTREAM_BASE_URL
            fallback until you add one.
          </li>
        )}
        {items.map((p) => (
          <li key={p.id} className="flex items-center justify-between px-4 py-3 gap-4">
            <div className="min-w-0">
              <p className="font-medium truncate flex items-center gap-2">
                {p.display_name}
                <span
                  className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${
                    p.health_status === "up"
                      ? "bg-emerald-500/10 text-emerald-300"
                      : p.health_status === "degraded"
                      ? "bg-rose-500/10 text-rose-300"
                      : "bg-white/[0.06] text-muted-foreground"
                  }`}
                >
                  {p.health_status}
                </span>
              </p>
              <p className="text-xs text-muted-foreground font-mono truncate">
                {p.slug} · priority {p.priority} · {p.base_url}
                {p.secret_ref && ` · key=${p.secret_ref}`}
              </p>
            </div>
            <Button size="sm" variant="ghost" onClick={() => remove(p.id)}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

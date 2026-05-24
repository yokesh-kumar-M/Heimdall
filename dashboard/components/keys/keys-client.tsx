"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Trash2, Copy, KeyRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface KeyRow {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export function KeysClient({ initialKeys }: { initialKeys: KeyRow[] }) {
  const [keys, setKeys] = useState(initialKeys);
  const [name, setName] = useState("");
  const [reveal, setReveal] = useState<string | null>(null);
  const [pending, start] = useTransition();

  async function create() {
    if (!name.trim()) {
      toast.error("Name required");
      return;
    }
    start(async () => {
      const res = await fetch("/api/keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        toast.error(`Failed: ${res.status}`);
        return;
      }
      const { plain, key } = await res.json();
      setKeys((k) => [key, ...k]);
      setReveal(plain);
      setName("");
    });
  }

  async function revoke(id: number) {
    if (!confirm("Revoke this key? Calls using it will start failing immediately.")) return;
    const res = await fetch(`/api/keys/${id}`, { method: "DELETE" });
    if (!res.ok) {
      toast.error(`Failed: ${res.status}`);
      return;
    }
    setKeys((k) =>
      k.map((row) =>
        row.id === id ? { ...row, revoked_at: new Date().toISOString() } : row,
      ),
    );
    toast.success("Key revoked");
  }

  return (
    <div className="space-y-4">
      {reveal && (
        <div className="rounded-xl border border-amber-400/40 bg-amber-400/[0.06] p-4">
          <p className="text-sm font-medium">Copy this now — it won&apos;t be shown again.</p>
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 font-mono text-sm break-all">{reveal}</code>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                navigator.clipboard.writeText(reveal);
                toast.success("Copied");
              }}
            >
              <Copy className="h-4 w-4" />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setReveal(null)}>
              dismiss
            </Button>
          </div>
        </div>
      )}

      <div className="flex items-end gap-2">
        <label className="flex-1 text-xs text-muted-foreground">
          Name (e.g. &quot;my-laptop&quot;, &quot;ci&quot;)
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="laptop"
            className="mt-1"
          />
        </label>
        <Button onClick={create} disabled={pending}>
          <KeyRound className="h-4 w-4" /> {pending ? "Minting…" : "Create key"}
        </Button>
      </div>

      <ul className="divide-y divide-white/[0.06] border border-white/[0.06] rounded-lg overflow-hidden">
        {keys.length === 0 && (
          <li className="px-4 py-6 text-sm text-muted-foreground">
            No keys yet. Create your first one above.
          </li>
        )}
        {keys.map((k) => (
          <li key={k.id} className="flex items-center justify-between px-4 py-3">
            <div className="min-w-0">
              <p className="font-medium truncate">{k.name}</p>
              <p className="text-xs text-muted-foreground font-mono">
                {k.prefix}… · created {new Date(k.created_at).toLocaleDateString()}
                {k.last_used_at && ` · last used ${new Date(k.last_used_at).toLocaleDateString()}`}
                {k.revoked_at && " · REVOKED"}
              </p>
            </div>
            {!k.revoked_at && (
              <Button size="sm" variant="ghost" onClick={() => revoke(k.id)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

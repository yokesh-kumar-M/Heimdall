import { owaspBadgeClass, owaspShort } from "@/lib/owasp";
import { cn } from "@/lib/utils";

export function CategoryBar({
  items,
  total,
}: {
  items: Array<{ category: string; count: number }>;
  total: number;
}) {
  if (!items.length) {
    return (
      <p className="text-sm text-muted-foreground">No blocks yet — your gateway is quiet.</p>
    );
  }
  return (
    <ol className="space-y-3">
      {items.map((it) => {
        const pct = total > 0 ? Math.round((it.count / total) * 100) : 0;
        return (
          <li key={it.category} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium",
                    owaspBadgeClass(it.category)
                  )}
                >
                  {owaspShort(it.category)}
                </span>
                <span className="text-foreground">{it.category.split(": ")[1] ?? it.category}</span>
              </div>
              <span className="tabular-nums text-muted-foreground">
                {it.count} · {pct}%
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-secondary overflow-hidden">
              <div
                className="h-full bg-foreground/70"
                style={{ width: `${pct}%` }}
              />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

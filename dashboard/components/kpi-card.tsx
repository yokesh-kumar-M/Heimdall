import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Accent = "default" | "danger" | "warning" | "good" | "info";

const ACCENT_TEXT: Record<Accent, string> = {
  default: "text-foreground",
  danger: "text-grad-danger",
  warning: "text-grad-warning",
  good: "text-grad-good",
  info: "text-grad-info",
};

const ACCENT_GLOW: Record<Accent, string> = {
  default: "",
  danger: "before:bg-[var(--grad-danger)]",
  warning: "before:bg-[var(--grad-warning)]",
  good: "before:bg-[var(--grad-good)]",
  info: "before:bg-[var(--grad-info)]",
};

export function KpiCard({
  label,
  value,
  hint,
  accent = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  accent?: Accent;
}) {
  return (
    <Card
      className={cn(
        "relative overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:ring-1 hover:ring-white/15",
        // Top accent bar via ::before
        "before:absolute before:inset-x-0 before:top-0 before:h-[2px] before:opacity-90",
        ACCENT_GLOW[accent]
      )}
    >
      <CardHeader className="pb-1">
        <CardTitle className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            "text-3xl font-semibold tabular-nums leading-none",
            ACCENT_TEXT[accent]
          )}
        >
          {value}
        </div>
        {hint ? (
          <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

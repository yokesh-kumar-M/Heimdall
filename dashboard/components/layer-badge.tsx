import { cn } from "@/lib/utils";

export function LayerBadge({ layer }: { layer: string }) {
  const styles =
    layer === "semantic"
      ? "bg-violet-500/15 text-violet-300 border-violet-500/30"
      : "bg-sky-500/15 text-sky-300 border-sky-500/30";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        styles
      )}
    >
      {layer === "semantic" ? "L2 · semantic" : "L1 · deterministic"}
    </span>
  );
}

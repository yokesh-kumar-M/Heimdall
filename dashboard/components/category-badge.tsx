import { owaspBadgeClass, owaspShort } from "@/lib/owasp";
import { cn } from "@/lib/utils";

export function CategoryBadge({ category }: { category: string }) {
  return (
    <span
      title={category}
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium",
        owaspBadgeClass(category)
      )}
    >
      {owaspShort(category)}
    </span>
  );
}

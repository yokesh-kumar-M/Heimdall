import { cn } from "@/lib/utils";

export function Shimmer({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("shimmer rounded-md", className)}
      {...props}
    />
  );
}

export function ShimmerCard({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-1">
      <Shimmer className="h-4 w-1/3" />
      {Array.from({ length: rows }).map((_, i) => (
        <Shimmer key={i} className="h-3 w-full" />
      ))}
    </div>
  );
}

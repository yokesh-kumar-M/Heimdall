"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/alerts", label: "Alerts" },
  { href: "/dashboard/owasp", label: "OWASP" },
  { href: "/dashboard/policies", label: "Policies" },
  { href: "/dashboard/sandbox", label: "Sandbox" },
];

export function SiteNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 text-sm rounded-full p-1 bg-white/[0.04] border border-white/10 backdrop-blur-md">
      {LINKS.map((l) => {
        const active =
          l.href === "/dashboard"
            ? pathname === "/dashboard"
            : pathname.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            className={cn(
              "relative px-3.5 py-1.5 rounded-full transition-all duration-200",
              active
                ? "text-white shadow-[0_0_24px_-8px_rgba(180,140,255,0.6)] bg-gradient-to-br from-indigo-500/30 via-violet-500/25 to-rose-500/20 ring-1 ring-white/15"
                : "text-muted-foreground hover:text-foreground hover:bg-white/[0.04]"
            )}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}

import Link from "next/link";

import { UserMenu } from "@/components/user-menu";
import { RefreshButton } from "@/components/refresh-button";
import { SiteNav } from "@/components/site-nav";
import { StatusIndicator } from "@/components/status-indicator";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col min-h-screen">
      <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-background/40 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-6 px-6 py-3">
          <Link href="/dashboard" className="flex items-center gap-2.5 group">
            <div className="relative h-8 w-8 rounded-lg overflow-hidden">
              <div className="absolute inset-0 grad-info opacity-90" />
              <div className="absolute inset-0 bg-gradient-to-br from-rose-500/40 via-transparent to-violet-500/50 mix-blend-screen" />
              <div className="relative h-full w-full flex items-center justify-center text-sm font-bold text-white drop-shadow">
                H
              </div>
            </div>
            <div className="flex flex-col leading-tight">
              <span className="font-semibold tracking-tight">Heimdall</span>
              <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                Security Console
              </span>
            </div>
          </Link>
          <SiteNav />
          <div className="flex items-center gap-3">
            <StatusIndicator />
            <RefreshButton />
            <UserMenu />
          </div>
        </div>
      </header>
      <main className="flex-1">
        <div className="max-w-7xl mx-auto px-6 py-6 fade-in-up">{children}</div>
      </main>
      <footer className="border-t border-white/[0.06] px-6 py-3 text-xs text-muted-foreground">
        <div className="max-w-7xl mx-auto flex justify-between">
          <span>
            Heimdall v0.2.0 · <span className="text-grad-info font-medium">L1 deterministic</span>{" "}
            · <span className="text-grad-good font-medium">L2 Llama Guard 3</span>
            {" "}· <span className="text-grad-warning font-medium">AI triage</span>
          </span>
          <span>OWASP LLM Top 10 (2025)</span>
        </div>
      </footer>
    </div>
  );
}

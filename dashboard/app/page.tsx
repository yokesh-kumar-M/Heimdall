import Link from "next/link";
import { Shield, Zap, BarChart3, Layers, Globe, Sparkles } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";

const CLERK_OFF =
  process.env.CLERK_DISABLED === "true" ||
  !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

const FEATURES = [
  {
    icon: Shield,
    title: "Layered defense",
    body: "Sub-millisecond deterministic scanners catch invisible Unicode, jailbreaks, and 9 classes of secrets/PII. Llama Guard 3 backs them up.",
  },
  {
    icon: Sparkles,
    title: "AI triage",
    body: "Click an alert, get a plain-English explanation from Claude Haiku — severity, why, what to do next, with auto-clustering of similar incidents.",
  },
  {
    icon: BarChart3,
    title: "Budgets that bite",
    body: "Set a monthly cap per workspace. Soft thresholds warn, hard caps block. Token usage is priced for every request.",
  },
  {
    icon: Layers,
    title: "Multi-provider routing",
    body: "Configure OpenAI, Anthropic, OpenRouter, Groq, or self-hosted in one place. Heimdall picks by priority / cost / latency, with auto-failover.",
  },
  {
    icon: Zap,
    title: "Drop-in compatible",
    body: "Point any OpenAI SDK at https://your-heimdall/v1 and ship. Nothing else changes.",
  },
  {
    icon: Globe,
    title: "OWASP LLM Top 10",
    body: "Every block is mapped to a 2025 OWASP LLM category. The compliance view is real, not theatre.",
  },
];

export default function Marketing() {
  return (
    <main className="flex-1">
      <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-background/40 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-6 px-6 py-3">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="relative h-8 w-8 rounded-lg overflow-hidden">
              <div className="absolute inset-0 grad-info opacity-90" />
              <div className="absolute inset-0 bg-gradient-to-br from-rose-500/40 via-transparent to-violet-500/50 mix-blend-screen" />
              <div className="relative h-full w-full flex items-center justify-center text-sm font-bold text-white">
                H
              </div>
            </div>
            <span className="font-semibold tracking-tight">Heimdall</span>
          </Link>
          <nav className="flex items-center gap-3 text-sm">
            <Link href="#features" className="text-muted-foreground hover:text-foreground">
              Features
            </Link>
            <Link
              href="https://github.com/your-org/heimdall"
              className="text-muted-foreground hover:text-foreground"
            >
              GitHub
            </Link>
            {CLERK_OFF ? (
              <Link href="/dashboard" className={buttonVariants({ size: "sm" })}>
                Open dashboard
              </Link>
            ) : (
              <>
                <Link href="/sign-in" className={buttonVariants({ size: "sm", variant: "ghost" })}>
                  Sign in
                </Link>
                <Link href="/sign-up" className={buttonVariants({ size: "sm" })}>
                  Get started
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <section className="relative px-6 pt-24 pb-16 text-center">
        <div className="max-w-3xl mx-auto fade-in-up">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full grad-good" />
            Open source · self-hostable · v0.2
          </span>
          <h1 className="mt-6 text-5xl sm:text-6xl font-bold tracking-tight">
            A security gateway for{" "}
            <span className="text-grad-info">every LLM call</span>
            <br />
            you make.
          </h1>
          <p className="mt-6 text-lg text-muted-foreground max-w-2xl mx-auto">
            Heimdall sits between your code and OpenAI / Anthropic / your own vLLM.
            Every prompt runs through layered scanners, every cost is tracked,
            every block is explained.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            {CLERK_OFF ? (
              <Link href="/dashboard" className={buttonVariants({ size: "lg" })}>
                Open dashboard →
              </Link>
            ) : (
              <>
                <Link href="/sign-up" className={buttonVariants({ size: "lg" })}>
                  Start free →
                </Link>
                <Link
                  href="https://github.com/your-org/heimdall"
                  className={buttonVariants({ size: "lg", variant: "ghost" })}
                >
                  Self-host
                </Link>
              </>
            )}
          </div>
          <pre className="mt-10 mx-auto max-w-xl rounded-xl glass-card p-4 text-left text-sm overflow-x-auto">
{`from openai import OpenAI
client = OpenAI(
  base_url="https://your-heimdall.fly.dev/v1",
  api_key="sk_hd_..."   # ← your Heimdall key
)
client.chat.completions.create(model="gpt-4o-mini", messages=[...])`}
          </pre>
        </div>
      </section>

      <section id="features" className="px-6 py-20">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-semibold tracking-tight text-center">
            Six layers of common sense
          </h2>
          <p className="mt-2 text-center text-muted-foreground">
            Each one defaults on. Each one stays out of your way.
          </p>
          <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {FEATURES.map((f) => (
              <div key={f.title} className="glass-card rounded-xl p-5 fade-in-up">
                <f.icon className="h-6 w-6 text-grad-info" />
                <h3 className="mt-3 font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                  {f.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-white/[0.06] px-6 py-6 text-xs text-muted-foreground">
        <div className="max-w-6xl mx-auto flex justify-between">
          <span>Heimdall — built for the OWASP LLM Top 10 (2025).</span>
          <span>
            <Link href="https://github.com/your-org/heimdall" className="hover:text-foreground">
              github
            </Link>
            {" · "}
            <Link href="/dashboard" className="hover:text-foreground">
              dashboard
            </Link>
          </span>
        </div>
      </footer>
    </main>
  );
}

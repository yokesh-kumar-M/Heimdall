import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { ClerkProvider } from "@clerk/nextjs";

import { Toaster } from "@/components/ui/sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const CLERK_OFF =
  process.env.CLERK_DISABLED === "true" ||
  !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export const metadata: Metadata = {
  title: "Heimdall — Security gateway for AI",
  description:
    "An OpenAI-compatible reverse proxy that guards every LLM call. Block prompt injection, data leaks, jailbreaks, and runaway spend — in one drop-in URL.",
  openGraph: {
    title: "Heimdall — Security gateway for AI",
    description:
      "Drop-in security for any OpenAI-compatible API. Layered scanners, AI triage, multi-provider failover, per-user budgets.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const tree = (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        {children}
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
  return CLERK_OFF ? tree : <ClerkProvider>{tree}</ClerkProvider>;
}

/**
 * UserMenu — shows the Clerk UserButton if Clerk is configured; otherwise
 * a "self-host" badge. Either way the component never crashes if the
 * Clerk provider isn't mounted.
 */
"use client";

import dynamic from "next/dynamic";

const CLERK_OFF =
  process.env.NEXT_PUBLIC_CLERK_DISABLED === "true" ||
  !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

const UserButton = dynamic(
  () => import("@clerk/nextjs").then((m) => m.UserButton),
  { ssr: false },
);

export function UserMenu() {
  if (CLERK_OFF) {
    return (
      <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        Self-host
      </span>
    );
  }
  return (
    <UserButton
      afterSignOutUrl="/"
      appearance={{
        elements: { userButtonAvatarBox: "h-8 w-8 ring-1 ring-white/20" },
      }}
    />
  );
}

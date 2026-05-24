/**
 * Clerk auth middleware.
 *
 * When `CLERK_DISABLED=true`, runs in pass-through mode (single-user
 * self-host). When Clerk is configured, /dashboard/* requires sign-in and
 * the marketing pages stay public.
 */
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtectedRoute = createRouteMatcher([
  "/dashboard(.*)",
  "/api/dashboard(.*)",
]);

const clerkOff =
  process.env.CLERK_DISABLED === "true" ||
  !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export default clerkOff
  ? (() => undefined as unknown as ReturnType<typeof clerkMiddleware>)
  : clerkMiddleware(async (auth, req) => {
      if (isProtectedRoute(req)) {
        await auth.protect();
      }
    });

export const config = {
  matcher: [
    // Skip Next internals + static assets, run on everything else
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};

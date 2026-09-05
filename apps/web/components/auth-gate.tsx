"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Nav } from "@/components/nav";

// Routes reachable without a token. Everything else is gated.
const PUBLIC_PATHS = ["/login", "/signup"];

// Routes that render full-bleed (no Nav sidebar/chrome) even once
// authenticated — the Issue #123 signup/onboarding wizard is a dedicated
// full-screen flow in the design mockup, not a page inside the app shell.
// Superset of PUBLIC_PATHS: /signup/brand and /onboarding/interview still
// require a token (the redirect effect below still applies to them), they
// just don't get the Nav wrapper once one is present.
const CHROMELESS_PATHS = ["/login", "/signup", "/signup/brand", "/onboarding/interview"];

/**
 * Wraps the whole app (mounted from app/layout.tsx). Redirects
 * unauthenticated visitors to /login on every protected route, and renders
 * the shell nav once a session is present (except on the chromeless
 * signup/onboarding wizard routes, which render full-bleed).
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { token, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublicPath = PUBLIC_PATHS.includes(pathname);
  const isChromeless = CHROMELESS_PATHS.includes(pathname);

  useEffect(() => {
    if (isLoading || isPublicPath) return;
    if (!token) {
      const target = `/login?from=${encodeURIComponent(pathname)}`;
      router.replace(target);
    }
  }, [token, isLoading, isPublicPath, pathname, router]);

  if (isPublicPath) {
    return <>{children}</>;
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink-400" role="status">
        Loading…
      </div>
    );
  }

  if (!token) {
    // Redirect kicked off above; render nothing while it lands.
    return null;
  }

  if (isChromeless) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen bg-canvas">
      <Nav />
      <main className="min-w-0 flex-1 px-6 py-8 lg:px-10">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}

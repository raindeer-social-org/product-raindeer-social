"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Nav } from "@/components/nav";

// Routes reachable without a token. Everything else is gated.
const PUBLIC_PATHS = ["/login"];

/**
 * Wraps the whole app (mounted from app/layout.tsx). Redirects
 * unauthenticated visitors to /login on every protected route, and renders
 * the shell nav once a session is present.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { token, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublicPath = PUBLIC_PATHS.includes(pathname);

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
      <div className="auth-gate-status" role="status">
        Loading…
      </div>
    );
  }

  if (!token) {
    // Redirect kicked off above; render nothing while it lands.
    return null;
  }

  return (
    <div className="app-shell">
      <Nav />
      <main className="app-main">{children}</main>
    </div>
  );
}

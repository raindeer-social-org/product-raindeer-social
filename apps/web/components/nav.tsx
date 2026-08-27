"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { BrandSwitcher } from "@/components/brand-switcher";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/components/ui/cn";

function IconDashboard() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm10 0h6V11h-6v9Zm0-16v5h6V4h-6Z" fill="currentColor" />
    </svg>
  );
}
function IconCalendar() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3 9h18M8 3v4M16 3v4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function IconReview() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9 11l2 2 4-4M7 4h10a2 2 0 012 2v13l-4-2H7a2 2 0 01-2-2V6a2 2 0 012-2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
function IconBrand() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 20V6a2 2 0 012-2h8l6 6v10a2 2 0 01-2 2H6a2 2 0 01-2-2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M14 4v5a1 1 0 001 1h5" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}
function IconOnboarding() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M5 20c0-3.6 3.1-6.5 7-6.5s7 2.9 7 6.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function IconSocial() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="6" cy="12" r="2.4" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="18" cy="6" r="2.4" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="18" cy="18" r="2.4" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8.2 10.8l7.6-3.6M8.2 13.2l7.6 3.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function IconAnalytics() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 20V10M12 20V4M20 20v-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function IconReport() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7 3h7l4 4v13a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M9 12h6M9 16h6M9 8h2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

const NAV_LINKS: { href: string; label: string; icon: () => ReactNode }[] = [
  { href: "/", label: "Dashboard", icon: IconDashboard },
  { href: "/calendar", label: "Calendar", icon: IconCalendar },
  { href: "/review-queue", label: "Review Queue", icon: IconReview },
  { href: "/brands", label: "Brands", icon: IconBrand },
  { href: "/onboarding", label: "Onboarding", icon: IconOnboarding },
  { href: "/social-accounts", label: "Connections", icon: IconSocial },
  { href: "/analytics", label: "Analytics", icon: IconAnalytics },
  { href: "/reports", label: "Reports", icon: IconReport },
];

export function Nav() {
  const pathname = usePathname();
  const { logout } = useAuth();

  return (
    <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col border-r border-ink-800 bg-ink-950 bg-gradient-to-b from-ink-900 via-ink-950 to-ink-950 shadow-chrome">
      <div className="flex h-16 items-center gap-2.5 border-b border-ink-800 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-500 text-sm font-bold text-ink-950">
          R
        </div>
        <Link href="/" className="text-[15px] font-semibold tracking-tight text-ink-100">
          Raindeer Social
        </Link>
      </div>

      <div className="border-b border-ink-800 px-4 py-3.5">
        <p className="mb-2 px-0.5 font-mono text-[10px] font-medium uppercase tracking-widest text-ink-500">
          Brand
        </p>
        <BrandSwitcher />
      </div>

      <nav aria-label="Main navigation" className="flex-1 overflow-y-auto scrollbar-thin px-3 py-4">
        <p className="mb-2 px-3 font-mono text-[10px] font-medium uppercase tracking-widest text-ink-500">
          Workspace
        </p>
        <ul className="space-y-0.5">
          {NAV_LINKS.map((link) => {
            const isActive = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            const Icon = link.icon;
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-lg border-l-2 px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "border-accent-500 bg-ink-800/70 text-accent-400"
                      : "border-transparent text-ink-300 hover:border-ink-600 hover:bg-ink-800/50 hover:text-ink-50",
                  )}
                >
                  <Icon />
                  <span className="flex-1">{link.label}</span>
                  {isActive ? (
                    <span
                      aria-hidden="true"
                      className="h-1.5 w-1.5 shrink-0 animate-pulse-dot rounded-full bg-accent-500"
                    />
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-ink-800 p-3">
        <p className="mb-2 px-3 font-mono text-[10px] font-medium uppercase tracking-widest text-ink-500">
          Session
        </p>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-ink-300 transition-colors hover:bg-ink-800/70 hover:text-ink-50"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M15 17l5-5-5-5M20 12H9M12 19H6a2 2 0 01-2-2V7a2 2 0 012-2h6"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Log out
        </button>
      </div>
    </aside>
  );
}

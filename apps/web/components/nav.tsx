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
function IconArena() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="6" cy="6" r="2.2" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="18" cy="6" r="2.2" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="18" r="2.2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M7.7 7.4L11 16M16.3 7.4L13 16M8.2 6h7.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
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
function IconSettings() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M19.4 13.5a1.7 1.7 0 000-3l1.2-1.6-1.7-1.7-1.7 1.1a1.7 1.7 0 00-3-1.2L14 4.6h-2.4l-.2 1.9a1.7 1.7 0 00-3 1.2L6.7 6.6 5 8.3l1.1 1.6a1.7 1.7 0 000 3L5 14.5l1.7 1.7 1.6-1.1a1.7 1.7 0 003 1.2l.2 1.9H14l.2-1.9a1.7 1.7 0 003-1.2l1.6 1.1 1.7-1.7-1.1-1.6Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// Every route here already exists as a real page. Screens still landing
// from the mockup migration (Research, Creative, Create Post, Content AI,
// Settings) add their own nav entry in their own PR once the page itself
// exists — keeps this list from linking to 404s in the meantime. Arena
// (Issue #124) is the first of those to land.
const NAV_LINKS: { href: string; label: string; icon: () => ReactNode }[] = [
  { href: "/", label: "Dashboard", icon: IconDashboard },
  { href: "/calendar", label: "Calendar", icon: IconCalendar },
  { href: "/arena", label: "Content Arena", icon: IconArena },
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
    <aside className="sticky top-0 flex h-screen w-[236px] shrink-0 flex-col gap-3.5 border-r border-line-soft bg-white px-3.5 py-4">
      <Link href="/" className="flex items-center gap-2.5 px-1.5">
        <div className="flex h-[29px] w-[29px] items-center justify-center rounded-[9px] bg-gradient-to-br from-brand-600 to-brand-300 text-[13px] font-extrabold text-white">
          R
        </div>
        <span className="text-[15px] font-bold tracking-tight text-ink-950">
          raindeer<span className="text-brand-600">.</span>
        </span>
      </Link>

      <BrandSwitcher />

      <nav aria-label="Main navigation" className="flex-1 overflow-y-auto scrollbar-thin">
        <ul className="flex flex-col gap-0.5">
          {NAV_LINKS.map((link) => {
            const isActive = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            const Icon = link.icon;
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2.5 rounded-[10px] px-2.5 py-[9px] text-[13.5px] transition-colors",
                    isActive ? "bg-brand-50 font-bold text-ink-950" : "font-medium text-ink-500 hover:bg-canvas hover:text-ink-950",
                  )}
                >
                  <span className="w-[18px] text-center">
                    <Icon />
                  </span>
                  {link.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="mt-auto flex flex-col gap-2.5">
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-[13.5px] font-medium text-ink-500 hover:bg-canvas hover:text-ink-950"
        >
          <span className="w-[18px] text-center">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M15 17l5-5-5-5M20 12H9M12 19H6a2 2 0 01-2-2V7a2 2 0 012-2h6"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          Log out
        </button>
      </div>
    </aside>
  );
}

// Exported so future pages (Settings) can reuse the exact same icon without
// redefining it.
export { IconSettings };

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandSwitcher } from "@/components/brand-switcher";
import { useAuth } from "@/lib/auth-context";

// Stub routes for the feature areas this shell wires together. Each of
// these pages is a placeholder ("coming soon") until its own issue lands.
const NAV_LINKS = [
  { href: "/calendar", label: "Calendar" },
  { href: "/review-queue", label: "Review Queue" },
  { href: "/onboarding", label: "Onboarding" },
  { href: "/analytics", label: "Analytics" },
];

export function Nav() {
  const pathname = usePathname();
  const { logout } = useAuth();

  return (
    <header className="nav">
      <div className="nav-primary">
        <Link href="/" className="nav-logo">
          Raindeer Social
        </Link>
        <nav aria-label="Main navigation">
          <ul className="nav-links">
            {NAV_LINKS.map((link) => {
              const isActive = pathname === link.href;
              return (
                <li key={link.href}>
                  <Link href={link.href} aria-current={isActive ? "page" : undefined}>
                    {link.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
      <div className="nav-secondary">
        <BrandSwitcher />
        <button type="button" className="nav-logout" onClick={logout}>
          Log out
        </button>
      </div>
    </header>
  );
}

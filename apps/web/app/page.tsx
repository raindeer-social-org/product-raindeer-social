"use client";

import Link from "next/link";
import { useBrand } from "@/lib/brand-context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";

const SECTIONS = [
  {
    href: "/calendar",
    label: "Calendar",
    description: "Plan and schedule posts across every platform.",
  },
  {
    href: "/review-queue",
    label: "Review Queue",
    description: "Approve, edit, or reject AI-drafted posts awaiting sign-off.",
  },
  {
    href: "/brands",
    label: "Brands",
    description: "Manage the brands your organization runs content for.",
  },
  {
    href: "/onboarding",
    label: "Onboarding",
    description: "Teach the AI your brand's voice, audience, and goals.",
  },
  {
    href: "/social-accounts",
    label: "Connections",
    description: "Connect LinkedIn, X, and other platforms for publishing.",
  },
  {
    href: "/analytics",
    label: "Analytics",
    description: "Track engagement across every published post.",
  },
  {
    href: "/reports",
    label: "Reports",
    description: "Read the AI-generated weekly performance summary.",
  },
];

export default function DashboardHomePage() {
  const { selectedBrand } = useBrand();

  return (
    <div>
      <PageHeader
        title={`Welcome back${selectedBrand ? `, ${selectedBrand.name}` : ""}`}
        description="Here's everything you can do from one place."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SECTIONS.map((section) => (
          <Link key={section.href} href={section.href} className="group block">
            <Card className="h-full p-5 transition-shadow group-hover:shadow-card-hover">
              <h3 className="text-sm font-semibold text-slate-900 group-hover:text-brand-700">
                {section.label}
              </h3>
              <p className="mt-1.5 text-sm text-slate-500">{section.description}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

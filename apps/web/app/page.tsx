"use client";

import Link from "next/link";
import { useBrand } from "@/lib/brand-context";

export default function DashboardHomePage() {
  const { selectedBrand } = useBrand();

  return (
    <section className="stub-page">
      <h1>Dashboard</h1>
      <p>
        Signed in{selectedBrand ? ` — scoped to ${selectedBrand.name}` : ""}. Pick a section from
        the nav above.
      </p>
      <ul>
        <li>
          <Link href="/calendar">Calendar</Link>
        </li>
        <li>
          <Link href="/review-queue">Review Queue</Link>
        </li>
        <li>
          <Link href="/onboarding">Onboarding</Link>
        </li>
        <li>
          <Link href="/analytics">Analytics</Link>
        </li>
      </ul>
    </section>
  );
}

"use client";

import { useBrand } from "@/lib/brand-context";

// Stub for #34 / #35 — replace with the real analytics dashboards.
export default function AnalyticsPage() {
  const { selectedBrand } = useBrand();

  return (
    <section className="stub-page">
      <h1>Analytics</h1>
      <p>Coming soon.</p>
      <p className="scoped-brand">
        Showing data for: <strong>{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
      </p>
    </section>
  );
}

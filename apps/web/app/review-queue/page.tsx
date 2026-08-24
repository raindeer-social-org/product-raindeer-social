"use client";

import { useBrand } from "@/lib/brand-context";

// Stub for #25 — replace with the real review queue view.
export default function ReviewQueuePage() {
  const { selectedBrand } = useBrand();

  return (
    <section className="stub-page">
      <h1>Review Queue</h1>
      <p>Coming soon.</p>
      <p className="scoped-brand">
        Showing data for: <strong>{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
      </p>
    </section>
  );
}

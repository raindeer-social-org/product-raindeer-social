"use client";

import { useBrand } from "@/lib/brand-context";

// Stub for #27 — replace with the real calendar view.
export default function CalendarPage() {
  const { selectedBrand } = useBrand();

  return (
    <section className="stub-page">
      <h1>Calendar</h1>
      <p>Coming soon.</p>
      <p className="scoped-brand">
        Showing data for: <strong>{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
      </p>
    </section>
  );
}

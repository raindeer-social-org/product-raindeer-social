"use client";

import { useBrand } from "@/lib/brand-context";

// Stub for #13 — replace with the real onboarding flow.
export default function OnboardingPage() {
  const { selectedBrand } = useBrand();

  return (
    <section className="stub-page">
      <h1>Onboarding</h1>
      <p>Coming soon.</p>
      <p className="scoped-brand">
        Showing data for: <strong>{selectedBrand ? selectedBrand.name : "no brand selected"}</strong>
      </p>
    </section>
  );
}

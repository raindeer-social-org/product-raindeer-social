"use client";

import { useBrand } from "@/lib/brand-context";

/**
 * Lets the signed-in user pick which brand the rest of the app is scoped
 * to. Every brand-aware page reads the selection back out of BrandContext
 * (useBrand().selectedBrand) rather than fetching brand-agnostic data, so
 * switching here re-scopes every page without those pages needing their
 * own brand-picking UI.
 */
export function BrandSwitcher() {
  const { brands, selectedBrandId, setSelectedBrandId, isLoading, error } = useBrand();

  if (isLoading) {
    return (
      <span className="brand-switcher-status" role="status">
        Loading brands…
      </span>
    );
  }

  if (error) {
    return (
      <span className="brand-switcher-status brand-switcher-error" role="alert">
        {error}
      </span>
    );
  }

  if (brands.length === 0) {
    return <span className="brand-switcher-status">No brands yet</span>;
  }

  return (
    <label className="brand-switcher">
      <span className="brand-switcher-label">Brand</span>
      <select
        aria-label="Select brand"
        value={selectedBrandId ?? ""}
        onChange={(event) => setSelectedBrandId(event.target.value)}
      >
        {brands.map((brand) => (
          <option key={brand.id} value={brand.id}>
            {brand.name}
          </option>
        ))}
      </select>
    </label>
  );
}

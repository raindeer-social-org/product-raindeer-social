"use client";

import { useBrand } from "@/lib/brand-context";
import { Avatar } from "@/components/ui/Avatar";
import { Skeleton } from "@/components/ui/Skeleton";

/**
 * Lets the signed-in user pick which brand the rest of the app is scoped
 * to. Every brand-aware page reads the selection back out of BrandContext
 * (useBrand().selectedBrand) rather than fetching brand-agnostic data, so
 * switching here re-scopes every page without those pages needing their
 * own brand-picking UI.
 */
export function BrandSwitcher() {
  const { brands, selectedBrand, selectedBrandId, setSelectedBrandId, isLoading, error } = useBrand();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-1 py-1" role="status">
        <Skeleton className="h-8 w-8 rounded-full" />
        <Skeleton className="h-4 w-24" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="px-1 text-xs font-medium text-red-400" role="alert">
        {error}
      </p>
    );
  }

  if (brands.length === 0) {
    return <p className="px-1 text-xs text-ink-400">No brands yet</p>;
  }

  return (
    <div className="relative">
      <div className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center">
        <Avatar name={selectedBrand?.name ?? "?"} src={selectedBrand?.logo_url} size="sm" />
      </div>
      <select
        aria-label="Select brand"
        value={selectedBrandId ?? ""}
        onChange={(event) => setSelectedBrandId(event.target.value)}
        className="w-full appearance-none rounded-lg border border-ink-700 bg-ink-800/60 py-2 pl-10 pr-8 text-sm font-medium text-ink-100 transition-colors hover:bg-ink-800 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
      >
        {brands.map((brand) => (
          <option key={brand.id} value={brand.id} className="bg-ink-900 text-ink-100">
            {brand.name}
          </option>
        ))}
      </select>
      <div className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-ink-400">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </div>
  );
}

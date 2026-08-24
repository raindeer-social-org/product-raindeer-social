"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { type Brand, fetchBrands } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const SELECTED_BRAND_STORAGE_KEY = "raindeer.selectedBrandId";

interface BrandContextValue {
  brands: Brand[];
  selectedBrandId: string | null;
  /** The full Brand record for selectedBrandId, or null if none is selected/loaded. */
  selectedBrand: Brand | null;
  setSelectedBrandId: (id: string) => void;
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

const BrandContext = createContext<BrandContextValue | undefined>(undefined);

export function BrandProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [brands, setBrands] = useState<Brand[]>([]);
  const [selectedBrandId, setSelectedBrandIdState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) {
      setBrands([]);
      setSelectedBrandIdState(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchBrands(token);
      setBrands(result);
      setSelectedBrandIdState((current) => {
        // Keep the current selection if it's still valid, otherwise fall
        // back to whatever was last persisted, otherwise the first brand.
        if (current && result.some((brand) => brand.id === current)) {
          return current;
        }
        const stored = window.localStorage.getItem(SELECTED_BRAND_STORAGE_KEY);
        if (stored && result.some((brand) => brand.id === stored)) {
          return stored;
        }
        return result[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load brands");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const setSelectedBrandId = useCallback((id: string) => {
    setSelectedBrandIdState(id);
    window.localStorage.setItem(SELECTED_BRAND_STORAGE_KEY, id);
  }, []);

  const selectedBrand = useMemo(
    () => brands.find((brand) => brand.id === selectedBrandId) ?? null,
    [brands, selectedBrandId]
  );

  const value = useMemo<BrandContextValue>(
    () => ({
      brands,
      selectedBrandId,
      selectedBrand,
      setSelectedBrandId,
      isLoading,
      error,
      refresh: load,
    }),
    [brands, selectedBrandId, selectedBrand, setSelectedBrandId, isLoading, error, load]
  );

  return <BrandContext.Provider value={value}>{children}</BrandContext.Provider>;
}

export function useBrand(): BrandContextValue {
  const ctx = useContext(BrandContext);
  if (!ctx) {
    throw new Error("useBrand must be used within a BrandProvider");
  }
  return ctx;
}

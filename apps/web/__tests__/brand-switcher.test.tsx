import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrandSwitcher } from "@/components/brand-switcher";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider, useBrand } from "@/lib/brand-context";

const fetchBrandsMock = vi.fn();

vi.mock("@/lib/api", () => ({
  fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
}));

const BRANDS = [
  { id: "brand-1", organization_id: "org-1", name: "Acme Co", industry: null, logo_url: null, target_audience: null, colors: null, tone_descriptors: null, product_catalog: null, brand_report: null, created_at: "2026-01-01", updated_at: "2026-01-01" },
  { id: "brand-2", organization_id: "org-1", name: "Beta Inc", industry: null, logo_url: null, target_audience: null, colors: null, tone_descriptors: null, product_catalog: null, brand_report: null, created_at: "2026-01-01", updated_at: "2026-01-01" },
];

// Consumer used to prove that switching brands here re-scopes what a page
// reading useBrand() sees — the same hook every real feature page will use.
function SelectedBrandLabel() {
  const { selectedBrand } = useBrand();
  return <div data-testid="selected-brand">{selectedBrand?.name ?? "none"}</div>;
}

function renderSwitcher() {
  return render(
    <AuthProvider>
      <BrandProvider>
        <BrandSwitcher />
        <SelectedBrandLabel />
      </BrandProvider>
    </AuthProvider>
  );
}

describe("BrandSwitcher", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");
  });

  it("shows a loading state before brands resolve", async () => {
    fetchBrandsMock.mockReturnValue(new Promise(() => {}));

    renderSwitcher();

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("lists every brand and defaults the selection to the first one", async () => {
    fetchBrandsMock.mockResolvedValue(BRANDS);

    renderSwitcher();

    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Select brand" })).toBeInTheDocument();
    });

    expect(screen.getByRole("option", { name: "Acme Co" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Beta Inc" })).toBeInTheDocument();
    expect(screen.getByTestId("selected-brand")).toHaveTextContent("Acme Co");
  });

  it("scopes the rest of the page to the newly selected brand", async () => {
    fetchBrandsMock.mockResolvedValue(BRANDS);
    const user = userEvent.setup();

    renderSwitcher();

    const select = await screen.findByRole("combobox", { name: "Select brand" });
    await act(async () => {
      await user.selectOptions(select, "brand-2");
    });

    expect(screen.getByTestId("selected-brand")).toHaveTextContent("Beta Inc");
  });

  it("persists the selection across a provider remount", async () => {
    fetchBrandsMock.mockResolvedValue(BRANDS);
    const user = userEvent.setup();

    const { unmount } = renderSwitcher();
    const select = await screen.findByRole("combobox", { name: "Select brand" });
    await act(async () => {
      await user.selectOptions(select, "brand-2");
    });
    unmount();

    renderSwitcher();

    await waitFor(() => {
      expect(screen.getByTestId("selected-brand")).toHaveTextContent("Beta Inc");
    });
  });

  it("shows an error state when the brands request fails", async () => {
    fetchBrandsMock.mockRejectedValue(new Error("Failed to load brands"));

    renderSwitcher();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Failed to load brands");
    });
  });

  it("shows an empty state when the org has no brands yet", async () => {
    fetchBrandsMock.mockResolvedValue([]);

    renderSwitcher();

    await waitFor(() => {
      expect(screen.getByText("No brands yet")).toBeInTheDocument();
    });
  });
});

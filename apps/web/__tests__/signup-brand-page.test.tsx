import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SignupBrandPage from "@/app/signup/brand/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ApiError } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const fetchBrandsMock = vi.fn();
const createBrandMock = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    createBrand: (...args: unknown[]) => createBrandMock(...args),
  };
});

function renderPage() {
  return render(
    <AuthProvider>
      <BrandProvider>
        <SignupBrandPage />
      </BrandProvider>
    </AuthProvider>
  );
}

describe("SignupBrandPage", () => {
  beforeEach(() => {
    push.mockClear();
    fetchBrandsMock.mockReset();
    createBrandMock.mockReset();
    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");
    fetchBrandsMock.mockResolvedValue([]);
  });

  it("creates the brand with category/sector/website/one-liner folded into product_catalog", async () => {
    createBrandMock.mockResolvedValue({
      id: "brand-1",
      organization_id: "org-1",
      name: "LexStart",
      industry: "Legal tech",
      logo_url: null,
      target_audience: null,
      colors: null,
      tone_descriptors: null,
      product_catalog: { founded: "2024", sector: "B2B SaaS", website: "https://lexstart.in", one_liner: "Compliance automation" },
      brand_report: null,
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
    });
    const user = userEvent.setup();

    renderPage();

    await user.type(screen.getByLabelText("Brand name"), "LexStart");
    await user.type(screen.getByLabelText("Founded"), "2024");
    await user.type(screen.getByLabelText("Website"), "https://lexstart.in");
    await user.type(screen.getByLabelText("One line about what you do"), "Compliance automation");
    await user.click(screen.getByRole("button", { name: "Meet Aarav" }));

    await vi.waitFor(() => {
      expect(createBrandMock).toHaveBeenCalledWith("test-token", {
        name: "LexStart",
        industry: "Legal tech",
        product_catalog: {
          founded: "2024",
          sector: "B2B SaaS",
          website: "https://lexstart.in",
          one_liner: "Compliance automation",
        },
      });
    });

    await vi.waitFor(() => {
      expect(push).toHaveBeenCalledWith("/onboarding/interview");
    });
  });

  it("shows an error and does not navigate when brand creation fails", async () => {
    createBrandMock.mockRejectedValue(new ApiError("Failed to create brand", 500));
    const user = userEvent.setup();

    renderPage();

    await user.type(screen.getByLabelText("Brand name"), "LexStart");
    await user.click(screen.getByRole("button", { name: "Meet Aarav" }));

    expect(await screen.findByText("Failed to create brand")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("requires a brand name before submitting", async () => {
    const user = userEvent.setup();

    renderPage();

    await user.click(screen.getByRole("button", { name: "Meet Aarav" }));

    expect(await screen.findByText("Brand name is required.")).toBeInTheDocument();
    expect(createBrandMock).not.toHaveBeenCalled();
  });
});

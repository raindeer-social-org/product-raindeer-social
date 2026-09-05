import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ContentAIPage from "@/app/content-ai/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";
import type { ContentAIVariant } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const generateContentAIImagesMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    generateContentAIImages: (...args: unknown[]) => generateContentAIImagesMock(...args),
  };
});

const BRANDS = [
  {
    id: "brand-1",
    organization_id: "org-1",
    name: "Acme Co",
    industry: null,
    logo_url: null,
    target_audience: null,
    colors: null,
    tone_descriptors: null,
    product_catalog: null,
    brand_report: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  },
];

function makeVariants(): ContentAIVariant[] {
  return [
    { status: "generated", url: "https://storage.example/1.png" },
    { status: "generated", url: "https://storage.example/2.png" },
    { status: "failed", url: null },
    { status: "generated", url: "https://storage.example/4.png" },
  ];
}

function renderPage() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <ContentAIPage />
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("ContentAIPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    generateContentAIImagesMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
  });

  it("generates variants with the chosen aspect ratio, style, and brand lock", async () => {
    generateContentAIImagesMock.mockResolvedValue(makeVariants());
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(fetchBrandsMock).toHaveBeenCalled());
    await screen.findByLabelText("Describe the image");

    await user.click(screen.getByRole("button", { name: "Portrait 4:5" }));
    await user.click(screen.getByRole("button", { name: "Bold" }));

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /Generate 4 variants/ }));
    });

    await waitFor(() =>
      expect(generateContentAIImagesMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        expect.objectContaining({
          aspect_ratio: "4:5",
          style: "bold",
          lock_brand_colors: true,
          count: 4,
        })
      )
    );

    const images = await screen.findAllByRole("img");
    expect(images).toHaveLength(3);
    expect(screen.getByText("Generation failed")).toBeInTheDocument();
  });

  it("unchecks brand lock and passes it through", async () => {
    generateContentAIImagesMock.mockResolvedValue(makeVariants());
    const user = userEvent.setup();

    renderPage();
    await screen.findByLabelText("Describe the image");

    await user.click(screen.getByLabelText("Lock to brand colours and logo"));
    await act(async () => {
      await user.click(screen.getByRole("button", { name: /Generate 4 variants/ }));
    });

    await waitFor(() =>
      expect(generateContentAIImagesMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        expect.objectContaining({ lock_brand_colors: false })
      )
    );
  });
});

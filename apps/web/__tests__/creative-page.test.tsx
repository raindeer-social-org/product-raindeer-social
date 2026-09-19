import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CreativePage from "@/app/creative/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";
import type { CreativeAngle } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const generateCreativeAnglesMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    generateCreativeAngles: (...args: unknown[]) => generateCreativeAnglesMock(...args),
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

function makeAngles(count = 6): CreativeAngle[] {
  return Array.from({ length: count }, (_, i) => ({
    format: `Format ${i}`,
    angle: `Angle ${i}`,
    hook: `Hook number ${i}`,
    why: `Why this works ${i}`,
    cta: `CTA ${i}`,
    score: 90 - i,
  }));
}

function renderPage() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <CreativePage />
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("CreativePage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    generateCreativeAnglesMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
  });

  it("generates and renders 6 angle cards from the brief", async () => {
    generateCreativeAnglesMock.mockResolvedValue(makeAngles());
    const user = userEvent.setup();

    renderPage();

    await waitFor(() => expect(fetchBrandsMock).toHaveBeenCalled());
    await screen.findByLabelText("Creative brief");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Generate all 6 →" }));
    });

    await waitFor(() =>
      expect(generateCreativeAnglesMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        expect.any(String)
      )
    );

    expect(await screen.findByText("Hook number 0")).toBeInTheDocument();
    expect(screen.getByText("Hook number 5")).toBeInTheDocument();
    expect(screen.getAllByText(/Why this works/).length).toBe(6);
  });

  it("shows an error and no cards when generation fails", async () => {
    generateCreativeAnglesMock.mockRejectedValue(new Error("LLM unreachable"));
    const user = userEvent.setup();

    renderPage();
    await screen.findByLabelText("Creative brief");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Generate all 6 →" }));
    });

    expect(await screen.findByText("LLM unreachable")).toBeInTheDocument();
    expect(screen.queryByText(/Hook number/)).not.toBeInTheDocument();
  });
});

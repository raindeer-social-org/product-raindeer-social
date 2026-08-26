import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import OnboardingPage from "@/app/onboarding/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";
import type { Brand, OnboardingResponseData } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchOnboardingMock = vi.fn();
const upsertOnboardingMock = vi.fn();
const completeOnboardingMock = vi.fn();
const runOnboardingAgentMock = vi.fn();
const exportBrandReportMock = vi.fn();

vi.mock("@/lib/api", () => {
  class MockApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }

  return {
    ApiError: MockApiError,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    fetchOnboarding: (...args: unknown[]) => fetchOnboardingMock(...args),
    upsertOnboarding: (...args: unknown[]) => upsertOnboardingMock(...args),
    completeOnboarding: (...args: unknown[]) => completeOnboardingMock(...args),
    runOnboardingAgent: (...args: unknown[]) => runOnboardingAgentMock(...args),
    exportBrandReport: (...args: unknown[]) => exportBrandReportMock(...args),
  };
});

function makeBrand(overrides: Partial<Brand> = {}): Brand {
  return {
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
    ...overrides,
  };
}

function makeOnboarding(overrides: Partial<OnboardingResponseData> = {}): OnboardingResponseData {
  return {
    id: "onboarding-1",
    brand_id: "brand-1",
    voice: "Friendly and confident",
    audience: "Small business owners",
    product_catalog: { products: [{ name: "Widget Pro" }] },
    competitors: ["Widget Inc"],
    goals: ["Grow LinkedIn following"],
    is_complete: true,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <OnboardingPage />
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("OnboardingPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchOnboardingMock.mockReset();
    upsertOnboardingMock.mockReset();
    completeOnboardingMock.mockReset();
    runOnboardingAgentMock.mockReset();
    exportBrandReportMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    vi.spyOn(window, "open").mockImplementation(() => null);
  });

  it("submits the not-started form and saves onboarding answers", async () => {
    fetchBrandsMock.mockResolvedValue([makeBrand()]);
    fetchOnboardingMock.mockResolvedValue(null);
    upsertOnboardingMock.mockResolvedValue(makeOnboarding({ is_complete: false }));
    const user = userEvent.setup();

    renderPage();

    expect(await screen.findByText("Start onboarding")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Brand voice"), "Friendly and confident");
    await user.type(screen.getByLabelText("Audience"), "Small business owners");
    // userEvent.type interprets "{"/"}" as special-key syntax, so set the
    // raw JSON text directly instead.
    fireEvent.change(screen.getByLabelText("Product catalog"), {
      target: { value: '{"products": [{"name": "Widget Pro"}]}' },
    });
    await user.type(screen.getByLabelText("Competitors"), "Widget Inc, Acme Rival");
    await user.type(screen.getByLabelText("Goals"), "Grow LinkedIn following");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Save answers" }));
    });

    await waitFor(() => {
      expect(upsertOnboardingMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        expect.objectContaining({
          voice: "Friendly and confident",
          audience: "Small business owners",
          product_catalog: { products: [{ name: "Widget Pro" }] },
          competitors: ["Widget Inc", "Acme Rival"],
          goals: ["Grow LinkedIn following"],
        })
      );
    });

    expect(await screen.findByText("Onboarding answers saved.")).toBeInTheDocument();
  });

  it("shows a pending state while generating the report, then renders it", async () => {
    fetchOnboardingMock.mockResolvedValue(makeOnboarding({ is_complete: true }));

    const reportedBrand = makeBrand({
      brand_report: {
        voice_and_tone: "Warm and direct.",
        audience: "Owners of small retail shops.",
        product_catalog_summary: "A line of productivity widgets.",
        competitive_positioning: "Positioned as the premium, easy-to-use option.",
      },
    });
    fetchBrandsMock.mockResolvedValueOnce([makeBrand()]).mockResolvedValueOnce([reportedBrand]);

    let resolveAgent: (() => void) | undefined;
    runOnboardingAgentMock.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveAgent = () => resolve();
        })
    );

    const user = userEvent.setup();
    renderPage();

    const generateButton = await screen.findByRole("button", { name: "Generate brand report" });
    await user.click(generateButton);

    await waitFor(() => expect(runOnboardingAgentMock).toHaveBeenCalledWith("test-token", "brand-1"));
    expect(completeOnboardingMock).not.toHaveBeenCalled();

    expect(await screen.findByRole("status")).toHaveTextContent(/running research and synthesis/i);
    expect(screen.getByRole("button", { name: "Generating…" })).toBeDisabled();

    await act(async () => {
      resolveAgent?.();
      await Promise.resolve();
    });

    expect(await screen.findByText("Warm and direct.")).toBeInTheDocument();
    expect(screen.getByText("Positioned as the premium, easy-to-use option.")).toBeInTheDocument();
    expect(await screen.findByText("Brand report generated.")).toBeInTheDocument();
  });

  it("exports and links the PDF report", async () => {
    const brandWithReport = makeBrand({
      brand_report: { voice_and_tone: "Warm and direct." },
    });
    fetchBrandsMock.mockResolvedValue([brandWithReport]);
    fetchOnboardingMock.mockResolvedValue(makeOnboarding({ is_complete: true }));
    exportBrandReportMock.mockResolvedValue({
      url: "https://cdn.example.com/reports/brand-1.pdf",
      generated_at: "2026-08-25T12:00:00Z",
    });

    const user = userEvent.setup();
    renderPage();

    const exportButton = await screen.findByRole("button", { name: "Download PDF report" });
    await act(async () => {
      await user.click(exportButton);
    });

    await waitFor(() => {
      expect(exportBrandReportMock).toHaveBeenCalledWith("test-token", "brand-1");
    });

    const link = await screen.findByRole("link", { name: "Open PDF report" });
    expect(link).toHaveAttribute("href", "https://cdn.example.com/reports/brand-1.pdf");
    expect(window.open).toHaveBeenCalledWith(
      "https://cdn.example.com/reports/brand-1.pdf",
      "_blank",
      "noopener,noreferrer"
    );
  });
});

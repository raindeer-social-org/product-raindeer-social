import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import OnboardingInterviewPage from "@/app/onboarding/interview/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";
import type { ResearchStreamEvent } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const fetchBrandsMock = vi.fn();
const fetchOnboardingMock = vi.fn();
const streamOnboardingResearchMock = vi.fn();
const updateBrandMock = vi.fn();
const upsertOnboardingMock = vi.fn();
const completeOnboardingMock = vi.fn();
const uploadBrandLogoMock = vi.fn();
const fetchSocialAccountsMock = vi.fn();
const connectLinkedInMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    fetchOnboarding: (...args: unknown[]) => fetchOnboardingMock(...args),
    streamOnboardingResearch: (...args: unknown[]) => streamOnboardingResearchMock(...args),
    updateBrand: (...args: unknown[]) => updateBrandMock(...args),
    upsertOnboarding: (...args: unknown[]) => upsertOnboardingMock(...args),
    completeOnboarding: (...args: unknown[]) => completeOnboardingMock(...args),
    uploadBrandLogo: (...args: unknown[]) => uploadBrandLogoMock(...args),
    fetchSocialAccounts: (...args: unknown[]) => fetchSocialAccountsMock(...args),
    connectLinkedIn: (...args: unknown[]) => connectLinkedInMock(...args),
  };
});

const BRAND = {
  id: "brand-1",
  organization_id: "org-1",
  name: "LexStart",
  industry: "Legal tech",
  logo_url: null,
  target_audience: null,
  colors: null,
  tone_descriptors: null,
  product_catalog: { sector: "B2B SaaS", website: "https://lexstart.in" },
  brand_report: null,
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

function renderPage() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <OnboardingInterviewPage />
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("OnboardingInterviewPage", () => {
  beforeEach(() => {
    push.mockClear();
    fetchBrandsMock.mockReset();
    fetchOnboardingMock.mockReset();
    streamOnboardingResearchMock.mockReset();
    updateBrandMock.mockReset();
    upsertOnboardingMock.mockReset();
    completeOnboardingMock.mockReset();
    uploadBrandLogoMock.mockReset();
    fetchSocialAccountsMock.mockReset();
    connectLinkedInMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue([BRAND]);
    fetchOnboardingMock.mockResolvedValue(null);
    fetchSocialAccountsMock.mockResolvedValue([]);
    updateBrandMock.mockResolvedValue(BRAND);
    upsertOnboardingMock.mockResolvedValue({});
    completeOnboardingMock.mockResolvedValue({});

    streamOnboardingResearchMock.mockImplementation(
      async (
        _token: string,
        _brandId: string,
        onEvent: (event: ResearchStreamEvent) => void
      ) => {
        onEvent({ event: "log", data: { text: "Searching the public web…" } });
        onEvent({ event: "signal", data: { title: "LexStart raises seed round", url: "https://x.test" } });
        onEvent({ event: "done", data: { count: 1 } });
      }
    );
  });

  it("auto-starts the research stream on the first question and renders real log lines", async () => {
    renderPage();

    expect(await screen.findByText("Let's confirm your website")).toBeInTheDocument();
    await waitFor(() => expect(streamOnboardingResearchMock).toHaveBeenCalledWith("test-token", "brand-1", expect.any(Function), expect.anything()));
    expect(await screen.findByText(/Searching the public web/)).toBeInTheDocument();
    expect(await screen.findByText(/Found: LexStart raises seed round/)).toBeInTheDocument();
  });

  it("saves brand colors via updateBrand when advancing past the colors question", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Let's confirm your website");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("What are your brand colors?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Toggle color #1B4DFF" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(updateBrandMock).toHaveBeenCalledWith("test-token", "brand-1", { colors: ["#1B4DFF"] });
    });
    expect(await screen.findByText("How would you describe your brand's voice?")).toBeInTheDocument();
  });

  it("saves selected voice-tone chips via upsertOnboarding", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Let's confirm your website");
    await user.click(screen.getByRole("button", { name: "Continue" })); // -> colors
    await screen.findByText("What are your brand colors?");
    await user.click(screen.getByRole("button", { name: "Continue" })); // -> voice chips

    await screen.findByText("How would you describe your brand's voice?");
    await user.click(screen.getByRole("button", { name: "Bold" }));
    await user.click(screen.getByRole("button", { name: "Playful" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(upsertOnboardingMock).toHaveBeenCalledWith("test-token", "brand-1", { voice: "Bold, Playful" });
    });
  });

  it("jumps straight to the connect step via 'Skip to social connections'", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Let's confirm your website");
    await user.click(screen.getByRole("button", { name: "Skip to social connections" }));

    expect(await screen.findByText("Connect where you publish")).toBeInTheDocument();
    await waitFor(() => expect(completeOnboardingMock).toHaveBeenCalledWith("test-token", "brand-1"));
  });

  it("reaches the connect step after the last question and 'Enter Raindeer' goes to /", async () => {
    const user = userEvent.setup();
    renderPage();

    const titles = [
      "Let's confirm your website",
      "What are your brand colors?",
      "How would you describe your brand's voice?",
      "What are your goals for the next quarter?",
      "Tell us about your audience, in your own words",
      "What do you sell, and who's it for?",
      "Who are your top competitors?",
      "Drop in anything that shows your brand at its best",
    ];

    for (const title of titles) {
      await screen.findByText(title);
      await user.click(screen.getByText("Skip"));
    }

    expect(await screen.findByText("Connect where you publish")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enter Raindeer" }));
    expect(push).toHaveBeenCalledWith("/");
  });
});

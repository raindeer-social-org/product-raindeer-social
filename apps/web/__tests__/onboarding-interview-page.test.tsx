import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
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
const fetchOnboardingAssetsMock = vi.fn();
const uploadOnboardingAssetMock = vi.fn();
const transcribeOnboardingVoiceAnswerMock = vi.fn();

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
    fetchOnboardingAssets: (...args: unknown[]) => fetchOnboardingAssetsMock(...args),
    uploadOnboardingAsset: (...args: unknown[]) => uploadOnboardingAssetMock(...args),
    transcribeOnboardingVoiceAnswer: (...args: unknown[]) => transcribeOnboardingVoiceAnswerMock(...args),
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
    fetchOnboardingAssetsMock.mockReset();
    uploadOnboardingAssetMock.mockReset();
    transcribeOnboardingVoiceAnswerMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue([BRAND]);
    fetchOnboardingMock.mockResolvedValue(null);
    fetchSocialAccountsMock.mockResolvedValue([]);
    updateBrandMock.mockResolvedValue(BRAND);
    upsertOnboardingMock.mockResolvedValue({});
    completeOnboardingMock.mockResolvedValue({});
    fetchOnboardingAssetsMock.mockResolvedValue([]);

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
      "What's your brand's mission, in one line?",
      "Anything your content should never say or show?",
      "How often do you want to post?",
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

  async function skipTo(user: ReturnType<typeof userEvent.setup>, title: string) {
    for (;;) {
      const current = await screen.findByRole("heading", { level: 2 });
      if (current.textContent === title) return;
      await user.click(screen.getByText("Skip"));
    }
  }

  it("saves mission via upsertOnboarding", async () => {
    const user = userEvent.setup();
    renderPage();

    await skipTo(user, "What's your brand's mission, in one line?");
    await user.type(screen.getByPlaceholderText(/Make professional-grade tools/), "Make widgets everyone loves.");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(upsertOnboardingMock).toHaveBeenCalledWith("test-token", "brand-1", {
        mission: "Make widgets everyone loves.",
      });
    });
  });

  it("saves content dos/don'ts as a split list via upsertOnboarding", async () => {
    const user = userEvent.setup();
    renderPage();

    await skipTo(user, "Anything your content should never say or show?");
    await user.type(screen.getByPlaceholderText(/Never joke about pricing/), "No pricing jokes, no memes");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(upsertOnboardingMock).toHaveBeenCalledWith("test-token", "brand-1", {
        content_dos_donts: ["No pricing jokes", "no memes"],
      });
    });
  });

  it("saves a single selected posting cadence via upsertOnboarding", async () => {
    const user = userEvent.setup();
    renderPage();

    await skipTo(user, "How often do you want to post?");
    await user.click(screen.getByRole("button", { name: "Weekly" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(upsertOnboardingMock).toHaveBeenCalledWith("test-token", "brand-1", { posting_cadence: "Weekly" });
    });
  });

  it("falls back to the text answer when the mic can't be used (no MediaRecorder in this environment)", async () => {
    const user = userEvent.setup();
    renderPage();

    await skipTo(user, "Tell us about your audience, in your own words");
    await user.click(screen.getByRole("button", { name: "Start recording" }));

    // jsdom has no MediaRecorder — startRecording must degrade to the
    // typed fallback rather than leaving the question unanswerable.
    const textarea = await screen.findByPlaceholderText("Type your answer — Aarav reads tone, not just words.");
    await user.type(textarea, "Small business owners who hate spreadsheets.");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(upsertOnboardingMock).toHaveBeenCalledWith("test-token", "brand-1", {
        audience: "Small business owners who hate spreadsheets.",
      });
    });
  });

  it("uploads a real asset file and shows it as filled instead of a blank slot", async () => {
    const user = userEvent.setup();
    uploadOnboardingAssetMock.mockResolvedValue({
      id: "asset-1",
      brand_id: "brand-1",
      slot: "style_guide",
      url: "https://storage.test/style-guide.pdf",
      filename: "style-guide.pdf",
      content_type: "application/pdf",
      created_at: "2026-01-01",
    });
    renderPage();

    await skipTo(user, "Drop in anything that shows your brand at its best");
    const file = new File(["guide"], "style-guide.pdf", { type: "application/pdf" });
    await act(async () => {
      await user.upload(screen.getByLabelText("Upload Style guide"), file);
    });

    await waitFor(() => expect(uploadOnboardingAssetMock).toHaveBeenCalledWith("test-token", "brand-1", "style_guide", file));
    expect(await screen.findByText("style-guide.pdf")).toBeInTheDocument();
  });
});

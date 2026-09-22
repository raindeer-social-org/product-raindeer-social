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
const streamOnboardingResearchMock = vi.fn();
const updateBrandMock = vi.fn();
const completeOnboardingMock = vi.fn();
const uploadBrandLogoMock = vi.fn();
const fetchSocialAccountsMock = vi.fn();
const connectLinkedInMock = vi.fn();
const fetchOnboardingAssetsMock = vi.fn();
const uploadOnboardingAssetMock = vi.fn();
const transcribeOnboardingVoiceAnswerMock = vi.fn();
const fetchNextOnboardingQuestionsMock = vi.fn();
const runOnboardingAgentMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    streamOnboardingResearch: (...args: unknown[]) => streamOnboardingResearchMock(...args),
    updateBrand: (...args: unknown[]) => updateBrandMock(...args),
    completeOnboarding: (...args: unknown[]) => completeOnboardingMock(...args),
    uploadBrandLogo: (...args: unknown[]) => uploadBrandLogoMock(...args),
    fetchSocialAccounts: (...args: unknown[]) => fetchSocialAccountsMock(...args),
    connectLinkedIn: (...args: unknown[]) => connectLinkedInMock(...args),
    fetchOnboardingAssets: (...args: unknown[]) => fetchOnboardingAssetsMock(...args),
    uploadOnboardingAsset: (...args: unknown[]) => uploadOnboardingAssetMock(...args),
    transcribeOnboardingVoiceAnswer: (...args: unknown[]) => transcribeOnboardingVoiceAnswerMock(...args),
    fetchNextOnboardingQuestions: (...args: unknown[]) => fetchNextOnboardingQuestionsMock(...args),
    runOnboardingAgent: (...args: unknown[]) => runOnboardingAgentMock(...args),
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

const SCRAPE_TITLE = "Let's confirm your website & brand colors";
const ASSETS_TITLE = "Drop in anything that shows your brand at its best";

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

async function skipFixedPage(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByText(SCRAPE_TITLE);
  await user.click(screen.getByText("Skip"));
}

describe("OnboardingInterviewPage", () => {
  beforeEach(() => {
    push.mockClear();
    fetchBrandsMock.mockReset();
    streamOnboardingResearchMock.mockReset();
    updateBrandMock.mockReset();
    completeOnboardingMock.mockReset();
    uploadBrandLogoMock.mockReset();
    fetchSocialAccountsMock.mockReset();
    connectLinkedInMock.mockReset();
    fetchOnboardingAssetsMock.mockReset();
    uploadOnboardingAssetMock.mockReset();
    transcribeOnboardingVoiceAnswerMock.mockReset();
    fetchNextOnboardingQuestionsMock.mockReset();
    runOnboardingAgentMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue([BRAND]);
    fetchSocialAccountsMock.mockResolvedValue([]);
    updateBrandMock.mockResolvedValue(BRAND);
    completeOnboardingMock.mockResolvedValue({});
    fetchOnboardingAssetsMock.mockResolvedValue([]);
    // Default: Aarav has nothing more to ask — most tests only care about
    // the one fixed page, so the dynamic phase should fall straight
    // through to the (optional) asset stage unless a test overrides this.
    fetchNextOnboardingQuestionsMock.mockResolvedValue({ done: true, page_index: 0, questions: [] });
    // Default: run-agent produces no usable brand_report, so
    // finishInterview() skips the capstone screen and falls straight
    // through to "connect" — same behavior as before Issue #158 existed.
    // Tests exercising the capstone screen itself override this.
    runOnboardingAgentMock.mockResolvedValue({ ...BRAND, brand_report: null });

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

  // --- One fixed page before Aarav takes over (issue #164) ---

  it("auto-starts the research stream on the fixed website+colors question and renders real log lines", async () => {
    renderPage();

    expect(await screen.findByText(SCRAPE_TITLE)).toBeInTheDocument();
    await waitFor(() => expect(streamOnboardingResearchMock).toHaveBeenCalledWith("test-token", "brand-1", expect.any(Function), expect.anything()));
    expect(await screen.findByText(/Searching the public web/)).toBeInTheDocument();
    expect(await screen.findByText(/Found: LexStart raises seed round/)).toBeInTheDocument();
  });

  it("surfaces social links found on the scraped site as clickable links", async () => {
    streamOnboardingResearchMock.mockImplementation(
      async (
        _token: string,
        _brandId: string,
        onEvent: (event: ResearchStreamEvent) => void
      ) => {
        onEvent({
          event: "extracted",
          data: {
            logo_url: "https://storage.test/logo.png",
            colors: ["#1B4DFF"],
            summary: "LexStart sells legal workflow software.",
            social_links: { instagram: "https://instagram.com/lexstart", linkedin: "https://linkedin.com/company/lexstart" },
          },
        });
        onEvent({ event: "done", data: { count: 0 } });
      }
    );
    renderPage();

    await screen.findByText(SCRAPE_TITLE);
    const instagramLink = await screen.findByRole("link", { name: "Instagram" });
    expect(instagramLink).toHaveAttribute("href", "https://instagram.com/lexstart");
    expect(screen.getByRole("link", { name: "Linkedin" })).toHaveAttribute(
      "href",
      "https://linkedin.com/company/lexstart"
    );
  });

  it("saves manually-picked brand colors via updateBrand when advancing past the fixed page", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText(SCRAPE_TITLE);
    await user.click(screen.getByRole("button", { name: "Toggle color #1B4DFF" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(updateBrandMock).toHaveBeenCalledWith("test-token", "brand-1", { colors: ["#1B4DFF"] });
    });
    expect(await screen.findByText(ASSETS_TITLE)).toBeInTheDocument();
  });

  it("jumps straight to the connect step via 'Skip to social connections'", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText(SCRAPE_TITLE);
    await user.click(screen.getByRole("button", { name: "Skip to social connections" }));

    expect(await screen.findByText("Connect where you publish")).toBeInTheDocument();
    await waitFor(() => expect(completeOnboardingMock).toHaveBeenCalledWith("test-token", "brand-1"));
  });

  it("reaches the optional asset stage after the fixed page, then connect after that", async () => {
    const user = userEvent.setup();
    renderPage();

    await skipFixedPage(user);

    // Dynamic phase (mocked done:true) falls straight through to the
    // optional asset stage — not another question, so it isn't gated
    // behind Aarav "asking" anything.
    expect(await screen.findByText(ASSETS_TITLE)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Skip" }));

    expect(await screen.findByText("Connect where you publish")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enter Raindeer" }));
    expect(push).toHaveBeenCalledWith("/");
  });

  // --- Adaptive, LLM-generated follow-up questions (Issue #153) ---

  it("renders an Aarav-generated question after the fixed page and submits the typed answer", async () => {
    const user = userEvent.setup();
    fetchNextOnboardingQuestionsMock.mockResolvedValueOnce({
      done: false,
      page_index: 1,
      questions: [
        {
          id: "integrations",
          type: "text",
          title: "What tools does LexStart integrate with?",
          sub: "Helps Ved research the right competitors.",
          options: null,
        },
      ],
    });
    fetchNextOnboardingQuestionsMock.mockResolvedValueOnce({ done: true, page_index: 0, questions: [] });

    renderPage();
    await skipFixedPage(user);

    expect(await screen.findByText("What tools does LexStart integrate with?")).toBeInTheDocument();
    expect(screen.getByText("STEP 2 OF 4 · ASKING SOMETHING NEW")).toBeInTheDocument();

    // Every free-text dynamic question is voice-first now (issue #164) —
    // typing means tapping "Prefer typing?" first, same as a "voice"-typed
    // question.
    await user.click(screen.getByRole("button", { name: "Prefer typing?" }));
    await user.type(screen.getByPlaceholderText("Type your answer."), "QuickBooks and Stripe");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(fetchNextOnboardingQuestionsMock).toHaveBeenLastCalledWith("test-token", "brand-1", 1, [
        {
          question: {
            id: "integrations",
            type: "text",
            title: "What tools does LexStart integrate with?",
            sub: "Helps Ved research the right competitors.",
            options: null,
          },
          answer: "QuickBooks and Stripe",
        },
      ]);
    });
    expect(await screen.findByText(ASSETS_TITLE)).toBeInTheDocument();
  });

  it("falls back to typing on a dynamic text question when the mic can't be used (no MediaRecorder in this environment)", async () => {
    const user = userEvent.setup();
    fetchNextOnboardingQuestionsMock.mockResolvedValueOnce({
      done: false,
      page_index: 1,
      questions: [
        {
          id: "audience",
          type: "text",
          title: "Who are you actually trying to reach?",
          sub: null,
          options: null,
        },
      ],
    });
    fetchNextOnboardingQuestionsMock.mockResolvedValueOnce({ done: true, page_index: 0, questions: [] });

    renderPage();
    await skipFixedPage(user);

    await screen.findByText("Who are you actually trying to reach?");
    await user.click(screen.getByRole("button", { name: "Start recording" }));

    // jsdom has no MediaRecorder — startRecording must degrade to the
    // typed fallback rather than leaving the question unanswerable.
    const textarea = await screen.findByPlaceholderText("Type your answer.");
    await user.type(textarea, "Small business owners who hate spreadsheets.");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(fetchNextOnboardingQuestionsMock).toHaveBeenLastCalledWith(
        "test-token",
        "brand-1",
        1,
        expect.arrayContaining([
          expect.objectContaining({ answer: "Small business owners who hate spreadsheets." }),
        ])
      );
    });
  });

  it("goes straight to the asset stage when Aarav has nothing more to ask", async () => {
    const user = userEvent.setup();
    renderPage();
    await skipFixedPage(user);

    await waitFor(() => expect(fetchNextOnboardingQuestionsMock).toHaveBeenCalledWith("test-token", "brand-1", 0, []));
    expect(await screen.findByText(ASSETS_TITLE)).toBeInTheDocument();
  });

  // --- Optional asset library, its own post-Aarav stage (issue #162) ---

  it("uploads a real asset file on the asset stage and shows it as filled instead of a blank slot", async () => {
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
    await skipFixedPage(user);

    expect(await screen.findByText(ASSETS_TITLE)).toBeInTheDocument();
    const file = new File(["guide"], "style-guide.pdf", { type: "application/pdf" });
    await act(async () => {
      await user.upload(screen.getByLabelText("Upload Style guide"), file);
    });

    await waitFor(() => expect(uploadOnboardingAssetMock).toHaveBeenCalledWith("test-token", "brand-1", "style_guide", file));
    expect(await screen.findByText("style-guide.pdf")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Connect where you publish")).toBeInTheDocument();
  });

  // --- Editable brand-identity capstone (Issue #158) ---

  async function reachAssetStageAndContinue(user: ReturnType<typeof userEvent.setup>) {
    await skipFixedPage(user);
    await screen.findByText(ASSETS_TITLE);
    await user.click(screen.getByRole("button", { name: "Continue" }));
  }

  it("shows the editable capstone screen when run-agent produces a brand_report, and continuing saves edits", async () => {
    const user = userEvent.setup();
    runOnboardingAgentMock.mockResolvedValue({
      ...BRAND,
      brand_report: {
        voice_and_tone: "Confident and precise.",
        audience: "In-house counsel at mid-market SaaS companies.",
      },
    });
    renderPage();
    await reachAssetStageAndContinue(user);

    expect(await screen.findByText("Here's what Aarav learned")).toBeInTheDocument();
    await waitFor(() => expect(runOnboardingAgentMock).toHaveBeenCalledWith("test-token", "brand-1"));

    const voiceField = await screen.findByDisplayValue("Confident and precise.");
    await user.clear(voiceField);
    await user.type(voiceField, "Warm but exacting.");

    await user.click(screen.getByRole("button", { name: "Looks good — continue" }));

    await waitFor(() => {
      expect(updateBrandMock).toHaveBeenCalledWith("test-token", "brand-1", {
        brand_report: {
          voice_and_tone: "Warm but exacting.",
          audience: "In-house counsel at mid-market SaaS companies.",
        },
      });
    });
    expect(await screen.findByText("Connect where you publish")).toBeInTheDocument();
  });

  it("skips the capstone screen and goes straight to connect when run-agent fails", async () => {
    const user = userEvent.setup();
    runOnboardingAgentMock.mockRejectedValue(new Error("LLM provider unavailable"));
    renderPage();
    await reachAssetStageAndContinue(user);

    expect(await screen.findByText("Connect where you publish")).toBeInTheDocument();
  });
});

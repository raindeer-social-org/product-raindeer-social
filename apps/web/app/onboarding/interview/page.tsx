"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  completeOnboarding,
  fetchOnboarding,
  fetchOnboardingAssets,
  streamOnboardingResearch,
  transcribeOnboardingVoiceAnswer,
  updateBrand,
  uploadBrandLogo,
  uploadOnboardingAsset,
  upsertOnboarding,
  type OnboardingAsset,
  type ResearchStreamEvent,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { SocialConnectionsPanel } from "@/app/social-accounts/social-connections-panel";

type QuestionType = "scrape" | "colors" | "chips" | "chipsSingle" | "text" | "voice" | "upload";

interface Question {
  id: string;
  type: QuestionType;
  title: string;
  sub: string;
}

const VOICE_CHIP_OPTIONS = [
  "Professional",
  "Playful",
  "Bold",
  "Minimal",
  "Warm",
  "Technical",
  "Luxury",
  "Approachable",
];

const GOAL_CHIP_OPTIONS = [
  "Brand awareness",
  "Lead generation",
  "Community building",
  "Thought leadership",
  "Product launches",
  "Hiring",
];

const CADENCE_OPTIONS = ["Daily", "A few times a week", "Weekly", "A few times a month"];

const PRESET_COLORS = ["#1B4DFF", "#0A1633", "#0E7A4E", "#B46A00", "#6B32C9", "#C9295A"];

const QUESTIONS: Question[] = [
  {
    id: "scrape",
    type: "scrape",
    title: "Let's confirm your website",
    sub: "Aarav reads your public site for real, live signals — this doesn't ask you anything, just watch it work.",
  },
  {
    id: "colors",
    type: "colors",
    title: "What are your brand colors?",
    sub: "Pick the palette Kavi should design with, and drop your logo if you have one handy.",
  },
  {
    id: "voiceChips",
    type: "chips",
    title: "How would you describe your brand's voice?",
    sub: "Pick as many as fit — Keshav writes copy to match.",
  },
  {
    id: "goals",
    type: "chips",
    title: "What are your goals for the next quarter?",
    sub: "This shapes what Ved researches and what Neer optimizes for.",
  },
  {
    id: "audience",
    type: "voice",
    title: "Tell us about your audience, in your own words",
    sub: "Who are you actually trying to reach?",
  },
  {
    id: "product",
    type: "text",
    title: "What do you sell, and who's it for?",
    sub: "The short version — Aarav will ask about the details later.",
  },
  {
    id: "competitors",
    type: "text",
    title: "Who are your top competitors?",
    sub: "Comma-separated is fine — Ved researches how you compare.",
  },
  {
    id: "mission",
    type: "text",
    title: "What's your brand's mission, in one line?",
    sub: "The thing you'd want on a billboard. Optional, but it sharpens everything Keshav and Kavi write.",
  },
  {
    id: "contentDosDonts",
    type: "text",
    title: "Anything your content should never say or show?",
    sub: "Comma-separated is fine — Neer holds every draft to this list.",
  },
  {
    id: "postingCadence",
    type: "chipsSingle",
    title: "How often do you want to post?",
    sub: "Keshav and Kavi plan around this — you can change it any time.",
  },
  {
    id: "assets",
    type: "upload",
    title: "Drop in anything that shows your brand at its best",
    sub: "Product photos, past posts, a style guide — totally optional.",
  },
];

const UPLOAD_SLOTS: { slot: string; label: string }[] = [
  { slot: "product_photos", label: "Product photos" },
  { slot: "team_photos", label: "Team photos" },
  { slot: "past_social_posts", label: "Past social posts" },
  { slot: "style_guide", label: "Style guide" },
];

function splitCommaList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function ChipButton({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={
        "rounded-[11px] border px-[15px] py-[11px] text-[13.5px] font-semibold transition-colors " +
        (selected
          ? "border-brand-600 bg-brand-50 text-brand-700"
          : "border-line bg-white text-ink-700 hover:bg-canvas")
      }
    >
      {label}
    </button>
  );
}

export default function OnboardingInterviewPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId, refresh: refreshBrands } = useBrand();
  const { push: pushToast } = useToast();
  const router = useRouter();

  const [stage, setStage] = useState<"questions" | "connect">("questions");
  const [stepIndex, setStepIndex] = useState(0);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const [voiceTone, setVoiceTone] = useState<string[]>([]);
  const [goals, setGoals] = useState<string[]>([]);
  const [audience, setAudience] = useState("");
  const [useTextFallback, setUseTextFallback] = useState(false);
  const [productDescription, setProductDescription] = useState("");
  const [competitorsText, setCompetitorsText] = useState("");
  const [mission, setMission] = useState("");
  const [contentDosDontsText, setContentDosDontsText] = useState("");
  const [postingCadence, setPostingCadence] = useState("");
  const [colors, setColors] = useState<string[]>([]);
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);

  const [scrapeLog, setScrapeLog] = useState<{ text: string; tone: "log" | "signal" | "done" }[]>([]);
  const [isScraping, setIsScraping] = useState(false);
  const [scrapeDone, setScrapeDone] = useState(false);
  const scrapeAbortRef = useRef<AbortController | null>(null);

  // Real mic recording (Issue #144) — MediaRecorder captures audio
  // client-side; the recorded blob is uploaded to the backend, which
  // transcribes it via the free, open-source, self-hosted Whisper
  // provider (packages/integrations/speech) and returns the transcript.
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const mediaStreamRef = useRef<MediaStream | null>(null);

  // Real asset uploads (Issue #144) — replaces the old decorative "+"
  // slots with actual file pickers backed by OnboardingAsset rows.
  const [assets, setAssets] = useState<OnboardingAsset[]>([]);
  const [uploadingSlot, setUploadingSlot] = useState<string | null>(null);

  // Resume in-progress onboarding — prefill whatever's already been saved
  // rather than starting the questionnaire over from scratch. Deliberately
  // does NOT set isLoaded when token/selectedBrandId are still missing:
  // both AuthProvider and BrandProvider resolve those asynchronously (a
  // localStorage read and a fetch, respectively), so on first mount this
  // effect can run once with both still null before either is ready. If
  // that early, empty pass flipped isLoaded to true, the scrape-autostart
  // effect below (gated on isLoaded) would fire immediately with no
  // token/brand, bail out inside runScrape, and then never get a second
  // chance — its own dependencies wouldn't change again once isLoaded was
  // already true. Waiting for real values here is what lets that effect's
  // dependency array pick up the transition from "not ready" to "ready".
  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!token || !selectedBrandId) return;
      try {
        const [onboarding, existingAssets] = await Promise.all([
          fetchOnboarding(token, selectedBrandId),
          fetchOnboardingAssets(token, selectedBrandId).catch(() => []),
        ]);
        if (cancelled) return;
        if (onboarding) {
          if (onboarding.voice) setVoiceTone(splitCommaList(onboarding.voice));
          if (onboarding.audience) setAudience(onboarding.audience);
          if (onboarding.product_catalog && typeof onboarding.product_catalog.description === "string") {
            setProductDescription(onboarding.product_catalog.description);
          }
          if (onboarding.competitors) setCompetitorsText(onboarding.competitors.join(", "));
          if (onboarding.goals) setGoals(onboarding.goals);
          if (onboarding.mission) setMission(onboarding.mission);
          if (onboarding.content_dos_donts) setContentDosDontsText(onboarding.content_dos_donts.join(", "));
          if (onboarding.posting_cadence) setPostingCadence(onboarding.posting_cadence);
        }
        setAssets(existingAssets);
        if (selectedBrand?.colors) setColors(selectedBrand.colors);
      } finally {
        if (!cancelled) setIsLoaded(true);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
    // Only re-run when the brand actually changes, not on every selectedBrand object refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, selectedBrandId]);

  useEffect(() => () => scrapeAbortRef.current?.abort(), []);

  useEffect(
    () => () => {
      mediaRecorderRef.current?.stop();
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    },
    []
  );

  const runScrape = useCallback(() => {
    if (!token || !selectedBrandId) return;
    scrapeAbortRef.current?.abort();
    const controller = new AbortController();
    scrapeAbortRef.current = controller;

    setScrapeLog([]);
    setScrapeDone(false);
    setIsScraping(true);

    function handleEvent(event: ResearchStreamEvent) {
      if (event.event === "log" && typeof event.data.text === "string") {
        setScrapeLog((current) => [...current, { text: event.data.text as string, tone: "log" }]);
      } else if (event.event === "signal" && typeof event.data.title === "string") {
        setScrapeLog((current) => [
          ...current,
          { text: `Found: ${event.data.title as string}`, tone: "signal" },
        ]);
      } else if (event.event === "done") {
        setScrapeLog((current) => [
          ...current,
          { text: `Done — ${event.data.count ?? 0} signal(s) captured.`, tone: "done" },
        ]);
        setScrapeDone(true);
      }
    }

    streamOnboardingResearch(token, selectedBrandId, handleEvent, controller.signal)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setScrapeLog((current) => [
          ...current,
          {
            text: err instanceof ApiError ? err.message : "Research preview failed.",
            tone: "done",
          },
        ]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsScraping(false);
      });
  }, [token, selectedBrandId]);

  // Kick off the scrape automatically the first time that question shows.
  useEffect(() => {
    if (isLoaded && token && selectedBrandId && stage === "questions" && stepIndex === 0 && scrapeLog.length === 0) {
      runScrape();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, token, selectedBrandId, stage, stepIndex]);

  const requiredAnswered = useMemo(
    () => ({
      scrape: scrapeDone,
      colors: colors.length > 0,
      voice: voiceTone.length > 0,
      goals: goals.length > 0,
      audience: audience.trim().length > 0,
      product: productDescription.trim().length > 0,
      competitors: competitorsText.trim().length > 0,
    }),
    [scrapeDone, colors, voiceTone, goals, audience, productDescription, competitorsText]
  );

  const memoryItems = [
    { label: "Website research", done: requiredAnswered.scrape },
    { label: "Brand colors & logo", done: requiredAnswered.colors },
    { label: "Brand voice", done: requiredAnswered.voice },
    { label: "Goals", done: requiredAnswered.goals },
    { label: "Audience", done: requiredAnswered.audience },
    { label: "What you offer", done: requiredAnswered.product },
    { label: "Competitors", done: requiredAnswered.competitors },
    { label: "Mission (optional)", done: mission.trim().length > 0, optional: true },
    { label: "Content dos/don'ts (optional)", done: contentDosDontsText.trim().length > 0, optional: true },
    { label: "Posting cadence (optional)", done: postingCadence.length > 0, optional: true },
    { label: "Brand assets (optional)", done: assets.length > 0, optional: true },
  ];
  const trackedCount = memoryItems.filter((item) => !item.optional).length;
  const doneCount = memoryItems.filter((item) => !item.optional && item.done).length;
  const memPct = trackedCount > 0 ? Math.round((doneCount / trackedCount) * 100) : 0;

  function toggleChip(list: string[], setList: (v: string[]) => void, value: string) {
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  async function handleLogoChange(file: File | null) {
    if (!file || !token || !selectedBrandId) return;
    setIsUploadingLogo(true);
    try {
      const brand = await uploadBrandLogo(token, selectedBrandId, file);
      await refreshBrands();
      if (brand.colors) setColors(brand.colors);
      pushToast("Logo uploaded.", "success");
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : "Failed to upload logo", "error");
    } finally {
      setIsUploadingLogo(false);
    }
  }

  function toggleColor(hex: string) {
    setColors((current) => (current.includes(hex) ? current.filter((c) => c !== hex) : [...current, hex]));
  }

  const currentQuestion = QUESTIONS[stepIndex];

  // Real mic recording + transcription (Issue #144). MediaRecorder
  // captures audio client-side (no external service needed just to
  // record); the recorded blob is sent to the backend, which transcribes
  // it via the free, open-source, self-hosted Whisper provider and
  // returns the transcript, which becomes this question's answer text —
  // reviewable/editable before continuing, same as the typed fallback.
  async function startRecording() {
    setRecordingError(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setUseTextFallback(true);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : undefined;
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
    } catch {
      // Mic permission denied/unavailable — fall back to typing rather
      // than leaving the question stuck.
      setUseTextFallback(true);
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;

    const finished = new Promise<Blob>((resolve) => {
      recorder.addEventListener(
        "stop",
        () => resolve(new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" })),
        { once: true }
      );
    });
    recorder.stop();
    setIsRecording(false);

    if (!token || !selectedBrandId) return;
    setIsTranscribing(true);
    finished
      .then((blob) => transcribeOnboardingVoiceAnswer(token, selectedBrandId, currentQuestion.id, blob))
      .then((answer) => {
        setAudience(answer.transcript);
      })
      .catch((err) => {
        setRecordingError(
          err instanceof ApiError ? err.message : "Couldn't transcribe that — try again, or type your answer."
        );
      })
      .finally(() => setIsTranscribing(false));
  }

  async function handleAssetUpload(slot: string, file: File | null) {
    if (!file || !token || !selectedBrandId) return;
    setUploadingSlot(slot);
    try {
      const asset = await uploadOnboardingAsset(token, selectedBrandId, slot, file);
      setAssets((current) => [...current.filter((a) => a.slot !== slot), asset]);
      pushToast("Uploaded.", "success");
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : "Failed to upload file", "error");
    } finally {
      setUploadingSlot(null);
    }
  }


  async function saveCurrentAnswer(): Promise<void> {
    if (!token || !selectedBrandId) return;
    setIsSaving(true);
    try {
      switch (currentQuestion.id) {
        case "colors":
          if (colors.length > 0) await updateBrand(token, selectedBrandId, { colors });
          break;
        case "voiceChips":
          if (voiceTone.length > 0) await upsertOnboarding(token, selectedBrandId, { voice: voiceTone.join(", ") });
          break;
        case "goals":
          if (goals.length > 0) await upsertOnboarding(token, selectedBrandId, { goals });
          break;
        case "audience":
          if (audience.trim()) await upsertOnboarding(token, selectedBrandId, { audience: audience.trim() });
          break;
        case "product":
          if (productDescription.trim())
            await upsertOnboarding(token, selectedBrandId, {
              product_catalog: { description: productDescription.trim() },
            });
          break;
        case "competitors":
          if (competitorsText.trim())
            await upsertOnboarding(token, selectedBrandId, { competitors: splitCommaList(competitorsText) });
          break;
        case "mission":
          if (mission.trim()) await upsertOnboarding(token, selectedBrandId, { mission: mission.trim() });
          break;
        case "contentDosDonts":
          if (contentDosDontsText.trim())
            await upsertOnboarding(token, selectedBrandId, {
              content_dos_donts: splitCommaList(contentDosDontsText),
            });
          break;
        case "postingCadence":
          if (postingCadence) await upsertOnboarding(token, selectedBrandId, { posting_cadence: postingCadence });
          break;
        default:
          break;
      }
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : "Failed to save your answer", "error");
    } finally {
      setIsSaving(false);
    }
  }

  async function goToConnect() {
    if (token && selectedBrandId) {
      try {
        await completeOnboarding(token, selectedBrandId);
      } catch {
        // Best-effort — onboarding can still be completed later from
        // /onboarding if required fields were skipped here. Not a blocker
        // for reaching the finishing step.
      }
    }
    setStage("connect");
  }

  async function handleNext() {
    await saveCurrentAnswer();
    if (stepIndex === QUESTIONS.length - 1) {
      await goToConnect();
    } else {
      setStepIndex((i) => i + 1);
    }
  }

  function handleSkip() {
    if (stepIndex === QUESTIONS.length - 1) {
      goToConnect();
    } else {
      setStepIndex((i) => i + 1);
    }
  }

  function handleBack() {
    setStepIndex((i) => Math.max(0, i - 1));
  }

  if (!selectedBrand) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas p-8">
        <EmptyState
          title="No brand yet"
          description="Finish creating your brand first."
          action={<Button onClick={() => router.push("/signup/brand")}>Go to brand setup</Button>}
        />
      </div>
    );
  }

  if (stage === "connect") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-canvas from-40% to-[#EEF1FF] px-6 py-11">
        <div className="w-full max-w-[720px]">
          <div className="mb-2.5 flex items-center gap-2 text-[11.5px] font-bold tracking-[.12em] text-brand-600">
            STEP 3 OF 3 · DISTRIBUTION
          </div>
          <h1 className="mb-1.5 text-[32px] font-bold leading-[1.12] tracking-tight text-ink-950">
            Connect where you publish
          </h1>
          <p className="mb-6 text-sm text-ink-400">
            Connect one to finish. You can add, remove or re-authorize any of these later in Settings.
          </p>

          <SocialConnectionsPanel />

          <div className="mt-5 flex items-center gap-3 rounded-2xl border border-line-soft bg-white p-4">
            <div className="h-[34px] w-[34px] shrink-0 rounded-full bg-gradient-to-br from-brand-600 to-brand-200" />
            <p className="flex-1 text-[13px] leading-relaxed text-ink-700">
              Aarav has what he needs to start building your brand memory. You can keep answering
              questions any time from Onboarding in Settings.
            </p>
            <Button onClick={() => router.push("/")}>Enter Raindeer</Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid min-h-screen grid-cols-1 bg-canvas md:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="flex flex-col gap-5 border-r border-line-soft bg-white p-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-[30px] w-[30px] items-center justify-center rounded-[9px] bg-gradient-to-br from-brand-600 to-brand-300 text-sm font-extrabold text-white">
            R
          </div>
          <span className="text-[15px] font-bold tracking-tight text-ink-950">
            raindeer<span className="text-brand-600">.</span>
          </span>
        </div>

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-xs font-bold text-ink-600">Brand memory</span>
            <span className="text-xs font-bold text-brand-600">{memPct}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-ink-50">
            <div
              className="h-full rounded-full bg-gradient-to-r from-brand-600 to-brand-300 transition-all"
              style={{ width: `${memPct}%` }}
            />
          </div>
        </div>

        <div className="flex flex-col gap-0.5">
          {memoryItems.map((item) => (
            <div
              key={item.label}
              className={
                "flex items-center gap-2.5 rounded-[9px] px-2.5 py-2 " +
                (item.done ? "bg-brand-50" : "")
              }
            >
              <div
                className={
                  "flex h-[17px] w-[17px] shrink-0 items-center justify-center rounded-full text-[10px] font-extrabold text-white " +
                  (item.done ? "bg-brand-600" : "bg-ink-100")
                }
              >
                {item.done ? "✓" : ""}
              </div>
              <span className={"text-[12.5px] font-medium " + (item.done ? "text-ink-950" : "text-ink-400")}>
                {item.label}
              </span>
            </div>
          ))}
        </div>

        <div className="mt-auto rounded-xl border border-brand-100 bg-brand-50 p-3">
          <p className="text-[11.5px] leading-relaxed text-ink-600">
            Every answer is written to your brand database. No agent will ask you this twice.
          </p>
        </div>
      </aside>

      <main className="flex min-w-0 flex-col">
        <div className="flex h-16 items-center justify-between border-b border-line-soft bg-white px-7">
          <div className="flex items-center gap-1.5">
            {QUESTIONS.map((question, index) => (
              <div
                key={question.id}
                className={
                  "h-[5px] rounded-full transition-colors " +
                  (index === stepIndex ? "w-6 bg-brand-600" : index < stepIndex ? "w-3.5 bg-brand-300" : "w-3.5 bg-ink-50")
                }
              />
            ))}
            <span className="ml-2.5 text-xs font-semibold text-ink-300">
              Question {stepIndex + 1} of {QUESTIONS.length}
            </span>
          </div>
          <Button variant="outline" size="sm" onClick={goToConnect}>
            Skip to social connections
          </Button>
        </div>

        <div className="flex flex-1 justify-center overflow-auto px-7 py-9">
          <div className="w-full max-w-[680px]">
            <div className="mb-5 flex items-start gap-3.5">
              <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-600 via-[#9BD2FF] to-[#C6B4FF] animate-rd-pulse">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-sm font-extrabold text-brand-600">
                  A
                </div>
              </div>
              <div className="min-w-0 pt-0.5">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-sm font-bold text-ink-950">Aarav</span>
                  <span className="rounded-[5px] bg-brand-50 px-1.5 py-0.5 text-[10px] font-bold tracking-widest text-brand-600">
                    AI ONBOARDING AGENT
                  </span>
                </div>
                <p className="text-xs text-ink-300">
                  Asked because you said{" "}
                  <b className="text-ink-600">
                    {selectedBrand.industry ?? "your brand"}
                    {selectedBrand.product_catalog?.sector
                      ? ` · ${selectedBrand.product_catalog.sector as unknown as string}`
                      : ""}
                  </b>
                </p>
              </div>
            </div>

            <div className="rounded-[18px] border border-line-soft bg-white p-6 shadow-modal">
              <h2 className="mb-2 text-2xl font-bold leading-tight tracking-tight text-ink-950">
                {currentQuestion.title}
              </h2>
              <p className="mb-5 text-sm leading-relaxed text-ink-400">{currentQuestion.sub}</p>

              {currentQuestion.type === "scrape" ? (
                <div>
                  <div className="mb-4 flex gap-2.5">
                    <div className="flex h-[46px] flex-1 items-center rounded-[11px] border border-line bg-white px-3.5 text-sm text-ink-600">
                      {(selectedBrand.product_catalog?.website as string | undefined) ??
                        "No website on file"}
                    </div>
                    <Button variant="secondary" onClick={runScrape} isLoading={isScraping}>
                      Re-scan
                    </Button>
                  </div>
                  <div
                    role="log"
                    aria-live="polite"
                    className="max-h-[186px] overflow-auto rounded-[13px] border border-line-soft bg-ink-950 p-4 font-mono text-[11.5px] leading-loose text-[#9FB4E8]"
                  >
                    {scrapeLog.length === 0 ? (
                      <div className="text-ink-300">Waiting to start…</div>
                    ) : (
                      scrapeLog.map((line, index) => (
                        <div key={index}>
                          <span
                            className={
                              line.tone === "signal"
                                ? "text-[#6BE3B0]"
                                : line.tone === "done"
                                  ? "text-white"
                                  : "text-[#7AA2FF]"
                            }
                          >
                            {line.tone === "done" ? "[done]" : line.tone === "signal" ? "[found]" : "[log]"}
                          </span>{" "}
                          {line.text}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ) : null}

              {currentQuestion.type === "colors" ? (
                <div>
                  <div className="mb-4 flex flex-wrap gap-3">
                    {PRESET_COLORS.map((hex) => (
                      <button
                        key={hex}
                        type="button"
                        aria-pressed={colors.includes(hex)}
                        aria-label={`Toggle color ${hex}`}
                        onClick={() => toggleColor(hex)}
                        className={
                          "flex flex-col items-center gap-1.5 rounded-2xl border-2 p-1 " +
                          (colors.includes(hex) ? "border-brand-600" : "border-transparent")
                        }
                      >
                        <span
                          className="block h-[62px] w-[62px] rounded-[10px] border border-black/5"
                          style={{ backgroundColor: hex }}
                        />
                        <span className="font-mono text-[11px] text-ink-500">{hex}</span>
                      </button>
                    ))}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-[13px] border-[1.5px] border-dashed border-ink-100 bg-canvas p-4 text-center">
                      <span className="text-sm font-bold text-ink-950">
                        {isUploadingLogo ? "Uploading…" : "Drop your logo"}
                      </span>
                      <span className="text-[11.5px] text-ink-300">SVG or PNG</span>
                      <input
                        type="file"
                        accept="image/*"
                        aria-label="Upload logo"
                        className="hidden"
                        disabled={isUploadingLogo}
                        onChange={(e) => handleLogoChange(e.target.files?.[0] ?? null)}
                      />
                    </label>
                    <div className="rounded-[13px] border border-line-soft p-3.5">
                      <div className="mb-2 text-[11.5px] font-bold text-ink-600">
                        {selectedBrand.logo_url ? "Your logo" : "No logo uploaded yet"}
                      </div>
                      {selectedBrand.logo_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={selectedBrand.logo_url}
                          alt={`${selectedBrand.name} logo`}
                          className="h-9 w-9 rounded-lg object-cover"
                        />
                      ) : (
                        <div className="flex gap-1.5">
                          {colors.map((c) => (
                            <i key={c} className="block h-[22px] w-[22px] rounded-md" style={{ background: c }} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : null}

              {currentQuestion.id === "voiceChips" ? (
                <div className="flex flex-wrap gap-2.5">
                  {VOICE_CHIP_OPTIONS.map((option) => (
                    <ChipButton
                      key={option}
                      label={option}
                      selected={voiceTone.includes(option)}
                      onClick={() => toggleChip(voiceTone, setVoiceTone, option)}
                    />
                  ))}
                </div>
              ) : null}

              {currentQuestion.id === "goals" ? (
                <div className="flex flex-wrap gap-2.5">
                  {GOAL_CHIP_OPTIONS.map((option) => (
                    <ChipButton
                      key={option}
                      label={option}
                      selected={goals.includes(option)}
                      onClick={() => toggleChip(goals, setGoals, option)}
                    />
                  ))}
                </div>
              ) : null}

              {currentQuestion.type === "voice" ? (
                <div>
                  {!useTextFallback ? (
                    <>
                      <div className="flex items-center gap-[18px] rounded-[14px] border border-brand-100 bg-brand-50 p-5">
                        <button
                          type="button"
                          onClick={isRecording ? stopRecording : startRecording}
                          disabled={isTranscribing}
                          aria-pressed={isRecording}
                          aria-label={isRecording ? "Stop recording" : "Start recording"}
                          className={
                            "flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-xl text-white transition-colors " +
                            (isRecording ? "bg-danger animate-rd-pulse" : "bg-brand-600 hover:bg-brand-700")
                          }
                        >
                          {isRecording ? "■" : "●"}
                        </button>
                        <div className="flex h-11 flex-1 items-center gap-[3px]">
                          {Array.from({ length: 32 }).map((_, index) => (
                            <i
                              key={index}
                              className={
                                "flex-1 rounded-sm bg-brand-600 " +
                                (isRecording ? "animate-rd-wave opacity-55" : "opacity-15")
                              }
                              style={{
                                height: `${20 + ((index * 37) % 60)}%`,
                                animationDelay: `${(index % 8) * 0.1}s`,
                              }}
                            />
                          ))}
                        </div>
                      </div>
                      <p className="mt-3 text-xs text-ink-300">
                        {isTranscribing
                          ? "Transcribing your answer…"
                          : isRecording
                            ? "Recording — tap the square to stop."
                            : "Tap the mic to record your answer. Transcribed on our own server via an open-source model — nothing leaves our infrastructure."}{" "}
                        <button
                          type="button"
                          className="font-semibold text-brand-600"
                          onClick={() => setUseTextFallback(true)}
                        >
                          Prefer typing? Answer in text instead
                        </button>
                      </p>
                      {recordingError && (
                        <p role="alert" className="mt-2 text-xs font-medium text-danger">
                          {recordingError}
                        </p>
                      )}
                      {audience.trim() && (
                        <div className="mt-3 rounded-[13px] border border-line-soft bg-white p-3.5 text-sm leading-relaxed text-ink-800">
                          {audience}
                        </div>
                      )}
                    </>
                  ) : (
                    <textarea
                      value={audience}
                      onChange={(e) => setAudience(e.target.value)}
                      placeholder="Type your answer — Aarav reads tone, not just words."
                      className="h-[132px] w-full resize-none rounded-[13px] border border-line bg-white p-3.5 text-sm leading-relaxed outline-none focus:border-brand-500"
                    />
                  )}
                </div>
              ) : null}

              {currentQuestion.type === "text" ? (
                <textarea
                  value={
                    currentQuestion.id === "product"
                      ? productDescription
                      : currentQuestion.id === "competitors"
                        ? competitorsText
                        : currentQuestion.id === "mission"
                          ? mission
                          : contentDosDontsText
                  }
                  onChange={(e) => {
                    const value = e.target.value;
                    if (currentQuestion.id === "product") setProductDescription(value);
                    else if (currentQuestion.id === "competitors") setCompetitorsText(value);
                    else if (currentQuestion.id === "mission") setMission(value);
                    else setContentDosDontsText(value);
                  }}
                  placeholder={
                    currentQuestion.id === "competitors"
                      ? "e.g. Acme Corp, Widgetron"
                      : currentQuestion.id === "contentDosDonts"
                        ? "e.g. Never joke about pricing, don't show competitor logos"
                        : currentQuestion.id === "mission"
                          ? "e.g. Make professional-grade tools every small team can afford."
                          : "Type your answer — Aarav reads tone, not just words."
                  }
                  className="h-[132px] w-full resize-none rounded-[13px] border border-line bg-white p-3.5 text-sm leading-relaxed outline-none focus:border-brand-500"
                />
              ) : null}

              {currentQuestion.type === "chipsSingle" ? (
                <div className="flex flex-wrap gap-2.5">
                  {CADENCE_OPTIONS.map((option) => (
                    <ChipButton
                      key={option}
                      label={option}
                      selected={postingCadence === option}
                      onClick={() => setPostingCadence(option)}
                    />
                  ))}
                </div>
              ) : null}

              {currentQuestion.type === "upload" ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {UPLOAD_SLOTS.map(({ slot, label }) => {
                    const uploaded = assets.find((a) => a.slot === slot);
                    const isUploading = uploadingSlot === slot;
                    const isImage = uploaded?.content_type.startsWith("image/");
                    return (
                      <label
                        key={slot}
                        className={
                          "flex aspect-square cursor-pointer flex-col items-center justify-center gap-1.5 overflow-hidden rounded-[13px] border-[1.5px] p-2.5 text-center " +
                          (uploaded ? "border-solid border-brand-200 bg-brand-50" : "border-dashed border-ink-100 bg-canvas")
                        }
                      >
                        {isUploading ? (
                          <span className="text-[11.5px] font-semibold text-ink-500">Uploading…</span>
                        ) : uploaded ? (
                          isImage ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={uploaded.url} alt={uploaded.filename} className="h-full w-full object-cover" />
                          ) : (
                            <>
                              <span className="text-lg">✓</span>
                              <span className="line-clamp-2 text-[11px] font-semibold leading-tight text-ink-600">
                                {uploaded.filename}
                              </span>
                            </>
                          )
                        ) : (
                          <>
                            <span className="text-lg text-ink-100">＋</span>
                            <span className="text-[11.5px] font-semibold leading-tight text-ink-500">{label}</span>
                          </>
                        )}
                        <input
                          type="file"
                          className="hidden"
                          disabled={isUploading}
                          aria-label={`Upload ${label}`}
                          onChange={(e) => handleAssetUpload(slot, e.target.files?.[0] ?? null)}
                        />
                      </label>
                    );
                  })}
                </div>
              ) : null}

              <div className="mt-6 flex items-center justify-between border-t border-line-faint pt-[18px]">
                <Button variant="outline" onClick={handleBack} disabled={stepIndex === 0}>
                  Back
                </Button>
                <div className="flex items-center gap-3">
                  <button type="button" onClick={handleSkip} className="text-[13.5px] font-semibold text-ink-300">
                    Skip
                  </button>
                  <Button onClick={handleNext} isLoading={isSaving}>
                    {stepIndex === QUESTIONS.length - 1 ? "Finish interview" : "Continue"}
                  </Button>
                </div>
              </div>
            </div>

            <p className="mt-[18px] text-center text-[11.5px] text-ink-200">
              Answers are stored in your brand database and reused by Ved, Keshav, Kavi and Neer.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  completeOnboarding,
  exportBrandReport,
  fetchOnboarding,
  runOnboardingAgent,
  upsertOnboarding,
  type BrandReportExportResult,
  type OnboardingResponseData,
  type OnboardingUpsertInput,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { BrandReportView } from "./brand-report-view";
import { OnboardingForm } from "./onboarding-form";

export default function OnboardingPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId, refresh: refreshBrands } = useBrand();
  const { push: pushToast } = useToast();

  const [onboarding, setOnboarding] = useState<OnboardingResponseData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [lastExport, setLastExport] = useState<BrandReportExportResult | null>(null);

  const loadOnboarding = useCallback(async () => {
    if (!token || !selectedBrandId) {
      setOnboarding(null);
      return;
    }
    setIsLoading(true);
    setLoadError(null);
    try {
      const result = await fetchOnboarding(token, selectedBrandId);
      setOnboarding(result);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Failed to load onboarding");
    } finally {
      setIsLoading(false);
    }
  }, [token, selectedBrandId]);

  useEffect(() => {
    setOnboarding(null);
    setLastExport(null);
    loadOnboarding();
  }, [loadOnboarding]);

  async function handleSaveAnswers(payload: OnboardingUpsertInput) {
    if (!token || !selectedBrandId) return;
    setIsSaving(true);
    try {
      const result = await upsertOnboarding(token, selectedBrandId, payload);
      setOnboarding(result);
      pushToast("Onboarding answers saved.", "success");
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : "Failed to save onboarding answers", "error");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleGenerateReport() {
    if (!token || !selectedBrandId || !onboarding) return;
    setIsGenerating(true);
    try {
      // The agent (apps/api/routers/onboarding.py::run_agent) requires
      // onboarding to already be marked complete — get that out of the way
      // first so "Generate brand report" reads as one action to the user.
      let current = onboarding;
      if (!current.is_complete) {
        current = await completeOnboarding(token, selectedBrandId);
        setOnboarding(current);
      }
      await runOnboardingAgent(token, selectedBrandId);
      // The agent writes brand_report onto the Brand row, not onto anything
      // BrandProvider already holds — refetch so selectedBrand picks it up.
      await refreshBrands();
      pushToast("Brand report generated.", "success");
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : "Failed to generate brand report", "error");
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleExportPdf() {
    if (!token || !selectedBrandId) return;
    setIsExporting(true);
    try {
      const result = await exportBrandReport(token, selectedBrandId);
      setLastExport(result);
      if (typeof window !== "undefined") {
        window.open(result.url, "_blank", "noopener,noreferrer");
      }
      pushToast("Brand report PDF ready.", "success");
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : "Failed to export PDF report", "error");
    } finally {
      setIsExporting(false);
    }
  }

  if (!selectedBrand) {
    return (
      <div>
        <PageHeader title="Onboarding" description="Teach the AI your brand's voice, audience, and goals." />
        <EmptyState
          title="No brand selected"
          description="Select a brand from the switcher to start or continue its onboarding."
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Onboarding"
        description={`Meet Aarav, your onboarding agent — teach it ${selectedBrand.name}'s voice, audience, and goals.`}
      />

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : loadError ? (
        <EmptyState title="Couldn't load onboarding" description={loadError} />
      ) : (
        <div className="space-y-6" key={`${selectedBrandId}-${onboarding?.id ?? "new"}`}>
          <Card>
            <CardHeader
              title={onboarding ? "Onboarding answers" : "Start onboarding"}
              description={
                onboarding
                  ? "Update your brand's questionnaire answers at any time."
                  : "Answer these questions so the AI can learn your brand."
              }
            />
            <CardBody>
              <OnboardingForm initialValues={onboarding} isSubmitting={isSaving} onSubmit={handleSaveAnswers} />
            </CardBody>
          </Card>

          {onboarding ? (
            <Card>
              <CardHeader
                title="Brand report"
                description={
                  selectedBrand.brand_report
                    ? "Regenerate the report any time your answers change."
                    : "Run the onboarding agent to generate your brand report."
                }
                action={
                  <Button onClick={handleGenerateReport} isLoading={isGenerating} disabled={isGenerating}>
                    {isGenerating
                      ? "Generating…"
                      : selectedBrand.brand_report
                        ? "Regenerate brand report"
                        : "Generate brand report"}
                  </Button>
                }
              />
              <CardBody>
                {isGenerating ? (
                  <p role="status" className="text-sm text-slate-500">
                    Aarav is running research and synthesis — this can take a minute or two. Feel
                    free to leave this open; the report will appear here as soon as it&rsquo;s ready.
                  </p>
                ) : selectedBrand.brand_report ? (
                  <div className="space-y-6">
                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 p-4">
                      <p className="text-sm text-slate-600">
                        {lastExport
                          ? `Last exported ${new Date(lastExport.generated_at).toLocaleString()}`
                          : "Export the report as a PDF to share with stakeholders."}
                      </p>
                      <div className="flex items-center gap-3">
                        {lastExport ? (
                          <a
                            href={lastExport.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-medium text-brand-600 hover:underline"
                          >
                            Open PDF report
                          </a>
                        ) : null}
                        <Button
                          variant="outline"
                          onClick={handleExportPdf}
                          isLoading={isExporting}
                          disabled={isExporting}
                        >
                          {isExporting ? "Preparing PDF…" : "Download PDF report"}
                        </Button>
                      </div>
                    </div>
                    <BrandReportView report={selectedBrand.brand_report} />
                  </div>
                ) : (
                  <EmptyState
                    title="No report yet"
                    description="Generate a brand report once you're happy with your onboarding answers."
                  />
                )}
              </CardBody>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  );
}

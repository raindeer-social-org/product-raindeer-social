"use client";

import { useState } from "react";
import { generateContentAIImages, type ContentAIVariant } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cn } from "@/components/ui/cn";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field, Textarea } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

const ASPECT_RATIOS = [
  { value: "1:1", label: "Square 1:1" },
  { value: "4:5", label: "Portrait 4:5" },
  { value: "9:16", label: "Story 9:16" },
  { value: "16:9", label: "Landscape 16:9" },
];

const STYLES = [
  { value: "editorial", label: "Editorial" },
  { value: "minimal", label: "Minimal" },
  { value: "bold", label: "Bold" },
  { value: "photographic", label: "Photographic" },
  { value: "illustrated", label: "Illustrated" },
];

const DEFAULT_PROMPT =
  "Editorial typographic card, deep navy, one bold statistic, thin grid lines, no stock photography.";
const VARIANT_COUNT = 4;

function ChipButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-[9px] border px-2.5 py-1.5 text-[12.5px] font-semibold transition-colors",
        active
          ? "border-brand-600 bg-brand-50 text-brand-700"
          : "border-line bg-white text-ink-600 hover:bg-canvas",
      )}
    >
      {children}
    </button>
  );
}

export default function ContentAIPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();
  const { push } = useToast();

  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [aspectRatio, setAspectRatio] = useState(ASPECT_RATIOS[0].value);
  const [style, setStyle] = useState(STYLES[0].value);
  const [lockBrandColors, setLockBrandColors] = useState(true);
  const [variants, setVariants] = useState<ContentAIVariant[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    if (!token || !selectedBrandId) return;
    if (!prompt.trim()) {
      setError("Describe the image first.");
      return;
    }

    setIsGenerating(true);
    setError(null);
    try {
      const result = await generateContentAIImages(token, selectedBrandId, {
        prompt,
        aspect_ratio: aspectRatio,
        style,
        lock_brand_colors: lockBrandColors,
        count: VARIANT_COUNT,
      });
      setVariants(result);
      const failed = result.filter((v) => v.status === "failed").length;
      if (failed > 0) {
        push(`${failed} of ${result.length} variants failed to generate`, "error");
      } else {
        push("Generated 4 variants", "success");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to generate images";
      setError(message);
      push(message, "error");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Content AI"
        description="Straight to the visual. Pick a style, describe the image, get variants built around it."
      />

      {!selectedBrand ? (
        <EmptyState title="No brand selected" description="Select a brand to generate images for it." />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <Card className="flex h-fit flex-col gap-4 p-4">
            <div>
              <div className="mb-2 text-xs font-bold text-ink-600">Aspect ratio</div>
              <div className="flex flex-wrap gap-1.5">
                {ASPECT_RATIOS.map((option) => (
                  <ChipButton
                    key={option.value}
                    active={aspectRatio === option.value}
                    onClick={() => setAspectRatio(option.value)}
                  >
                    {option.label}
                  </ChipButton>
                ))}
              </div>
            </div>

            <Field label="Describe the image" htmlFor="content-ai-prompt">
              <Textarea
                id="content-ai-prompt"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                rows={4}
              />
            </Field>

            <div>
              <div className="mb-2 text-xs font-bold text-ink-600">Style</div>
              <div className="flex flex-wrap gap-1.5">
                {STYLES.map((option) => (
                  <ChipButton
                    key={option.value}
                    active={style === option.value}
                    onClick={() => setStyle(option.value)}
                  >
                    {option.label}
                  </ChipButton>
                ))}
              </div>
            </div>

            <label className="flex items-center gap-2.5 rounded-[11px] border border-brand-100 bg-brand-50 px-3 py-2.5 text-[12.5px] text-ink-700">
              <input
                type="checkbox"
                checked={lockBrandColors}
                onChange={(event) => setLockBrandColors(event.target.checked)}
                className="h-[15px] w-[15px] accent-brand-600"
              />
              Lock to brand colours and logo
            </label>

            {error && (
              <p role="alert" className="text-sm font-medium text-danger">
                {error}
              </p>
            )}

            <Button onClick={handleGenerate} isLoading={isGenerating} className="h-11 w-full">
              Generate {VARIANT_COUNT} variants
            </Button>
          </Card>

          <div>
            {isGenerating ? (
              <div role="status" aria-live="polite" className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
                <span className="sr-only">Generating images…</span>
                {Array.from({ length: VARIANT_COUNT }).map((_, i) => (
                  <Skeleton key={i} className="aspect-square w-full rounded-2xl" />
                ))}
              </div>
            ) : variants.length === 0 ? (
              <EmptyState
                title="No variants yet"
                description="Generate 4 variants to see real images produced by the image-generation pipeline."
              />
            ) : (
              <ul className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
                {variants.map((variant, index) => (
                  <li key={index}>
                    <Card className="overflow-hidden">
                      {variant.status === "generated" && variant.url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={variant.url}
                          alt={`Generated variant ${index + 1}`}
                          className="aspect-square w-full object-cover"
                        />
                      ) : (
                        <div className="flex aspect-square w-full items-center justify-center bg-canvas text-sm font-medium text-ink-300">
                          Generation failed
                        </div>
                      )}
                      <div className="flex items-center gap-2 p-3">
                        <span className="text-[11.5px] text-ink-300">Variant {index + 1}</span>
                        {variant.status === "generated" && variant.url ? (
                          <a
                            href={variant.url}
                            target="_blank"
                            rel="noreferrer"
                            className="ml-auto text-[11.5px] font-bold text-brand-600 hover:underline"
                          >
                            Use this
                          </a>
                        ) : null}
                      </div>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

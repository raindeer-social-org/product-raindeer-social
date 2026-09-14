"use client";

import { useState } from "react";
import { generateCreativeAngles, type CreativeAngle } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field, Textarea } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

const DEFAULT_BRIEF =
  "Post about our new contract-review turnaround — 11 days to 40 minutes. Founder voice, not corporate.";

export default function CreativePage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();
  const { push } = useToast();

  const [brief, setBrief] = useState(DEFAULT_BRIEF);
  const [angles, setAngles] = useState<CreativeAngle[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    if (!token || !selectedBrandId) return;
    if (!brief.trim()) {
      setError("Describe what this post should be about first.");
      return;
    }

    setIsGenerating(true);
    setError(null);
    try {
      const result = await generateCreativeAngles(token, selectedBrandId, brief);
      setAngles(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to generate angles";
      setError(message);
      push(message, "error");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <div>
      <PageHeader
        title={
          <span className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-gradient-to-br from-agent-keshav-from to-agent-keshav-to text-xs font-extrabold text-white">
              K
            </span>
            Creative · Keshav
          </span>
        }
        description="Turns a brief into angles that sound like you. Pick one, or generate all six."
        action={
          <Button onClick={handleGenerate} isLoading={isGenerating} disabled={!selectedBrand}>
            Generate all 6 →
          </Button>
        }
      />

      {!selectedBrand ? (
        <EmptyState title="No brand selected" description="Select a brand to generate angles for it." />
      ) : (
        <>
          <Card className="mb-5 p-5">
            <Field label="Creative brief" htmlFor="creative-brief">
              <Textarea
                id="creative-brief"
                value={brief}
                onChange={(event) => setBrief(event.target.value)}
                rows={4}
              />
            </Field>
            {error && (
              <p role="alert" className="mt-2 text-sm font-medium text-danger">
                {error}
              </p>
            )}
          </Card>

          {isGenerating ? (
            <div role="status" aria-live="polite" className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
              <span className="sr-only">Generating angles…</span>
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <Card key={i} className="space-y-3 p-4">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-3 w-full" />
                </Card>
              ))}
            </div>
          ) : angles.length === 0 ? (
            <EmptyState
              title="No angles yet"
              description="Generate all 6 to see distinct angle/format cards for this brief."
            />
          ) : (
            <ul className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
              {angles.map((angle, index) => (
                <li key={`${angle.format}-${index}`}>
                  <Card className="flex h-full flex-col overflow-hidden">
                    <div className="flex items-center gap-2 border-b border-line-faint px-4 py-3">
                      <span className="rounded-[5px] bg-agent-keshav-solid px-1.5 py-0.5 text-[9.5px] font-extrabold text-white">
                        K
                      </span>
                      <span className="text-[11.5px] font-semibold text-ink-500">{angle.format}</span>
                      <span className="ml-auto text-[11.5px] font-extrabold text-agent-keshav-solid">
                        {angle.score}
                      </span>
                    </div>
                    <div className="flex flex-1 flex-col gap-2.5 p-4">
                      <p className="font-serif text-[19px] italic leading-tight text-ink-950">
                        {angle.hook}
                      </p>
                      <p className="text-[12.5px] leading-relaxed text-ink-500">{angle.why}</p>
                      <div className="mt-auto flex items-center gap-1.5 pt-2">
                        <span className="rounded-[6px] bg-violet-bg px-1.5 py-0.5 text-[11px] font-bold text-violet">
                          {angle.cta}
                        </span>
                        <span className="ml-auto text-[11px] font-medium text-ink-300">{angle.angle}</span>
                      </div>
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

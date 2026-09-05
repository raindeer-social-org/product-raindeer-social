"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchLatestResearch, runResearch, type ResearchRun } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

interface TrendItem {
  platform: string | null;
  title: string;
  content: string;
  url: string;
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function trendItemsFrom(run: ResearchRun): TrendItem[] {
  const items: TrendItem[] = [];
  for (const [platform, results] of Object.entries(run.brief.platform_trends ?? {})) {
    for (const result of results) {
      items.push({ platform, ...result });
    }
  }
  for (const result of run.brief.industry_trends ?? []) {
    items.push({ platform: null, ...result });
  }
  return items;
}

export default function ResearchPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();
  const { push } = useToast();

  const [run, setRun] = useState<ResearchRun | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token || !selectedBrandId) {
      setRun(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchLatestResearch(token, selectedBrandId);
      setRun(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load research");
    } finally {
      setIsLoading(false);
    }
  }, [token, selectedBrandId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRun() {
    if (!token || !selectedBrandId) return;
    setIsRunning(true);
    try {
      const result = await runResearch(token, selectedBrandId);
      setRun(result);
      push("Research complete", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "Failed to run research", "error");
    } finally {
      setIsRunning(false);
    }
  }

  const trendItems = run ? trendItemsFrom(run) : [];

  return (
    <div>
      <PageHeader
        title={
          <span className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-gradient-to-br from-agent-ved-from to-agent-ved-to text-xs font-extrabold text-white">
              V
            </span>
            Research · Ved
          </span>
        }
        description={
          <>
            Reads the whole internet on your category, then tells you only what changes a
            post. Showing data for:{" "}
            <strong className="font-medium text-slate-700">
              {selectedBrand ? selectedBrand.name : "no brand selected"}
            </strong>
          </>
        }
        action={
          <Button onClick={handleRun} isLoading={isRunning} disabled={!selectedBrand}>
            Run new research →
          </Button>
        }
      />

      {error && (
        <p role="alert" className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </p>
      )}

      {!selectedBrand ? (
        <EmptyState title="No brand selected" description="Select a brand to run research for it." />
      ) : isLoading ? (
        <div role="status" aria-live="polite" className="space-y-3">
          <span className="sr-only">Loading research…</span>
          {[0, 1, 2].map((i) => (
            <Card key={i} className="space-y-2 p-5">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-3 w-48" />
              <Skeleton className="h-16 w-full" />
            </Card>
          ))}
        </div>
      ) : !run || trendItems.length === 0 ? (
        <EmptyState
          title="No research yet"
          description="Run research to see trend cards drawn from live search results for this brand's category."
          action={
            <Button onClick={handleRun} isLoading={isRunning}>
              Run new research →
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <ul className="flex flex-col gap-3">
            {trendItems.map((item, index) => (
              <li key={`${item.url}-${index}`}>
                <Card className="p-4">
                  <div className="mb-1.5 flex items-center gap-2">
                    {item.platform ? (
                      <Badge tone="blue">{item.platform}</Badge>
                    ) : (
                      <Badge tone="slate">industry</Badge>
                    )}
                    <span className="text-xs text-ink-300">{domainOf(item.url)}</span>
                  </div>
                  <h3 className="mb-1.5 text-base font-bold tracking-tight text-ink-950">
                    {item.title}
                  </h3>
                  <p className="mb-3 text-sm leading-relaxed text-ink-500">{item.content}</p>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-semibold text-brand-600 hover:underline"
                  >
                    View source
                  </a>
                </Card>
              </li>
            ))}
          </ul>

          <div className="flex flex-col gap-3">
            <Card className="bg-ink-950 text-white">
              <CardBody>
                <div className="mb-2 text-[10.5px] font-extrabold tracking-[0.12em] text-agent-ved-to">
                  TRENDING TOPICS
                </div>
                {run.brief.timing_signal.trending_topics.length > 0 ? (
                  <ul className="flex flex-col gap-1.5">
                    {run.brief.timing_signal.trending_topics.map((topic) => (
                      <li key={topic} className="text-sm leading-relaxed text-white/90">
                        {topic}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-white/70">No standout trending topics this run.</p>
                )}
              </CardBody>
            </Card>
            <Card>
              <CardBody>
                <div className="mb-2.5 text-[11.5px] font-extrabold tracking-[0.1em] text-ink-300">
                  RESEARCHED
                </div>
                <p className="text-sm text-ink-600">
                  {new Date(run.brief.timing_signal.researched_at).toLocaleString()}
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {run.brief.timing_signal.platforms.map((platform) => (
                    <Badge key={platform} tone="blue">
                      {platform}
                    </Badge>
                  ))}
                </div>
              </CardBody>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

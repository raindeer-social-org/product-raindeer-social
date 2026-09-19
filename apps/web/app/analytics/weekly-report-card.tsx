import Link from "next/link";
import type { Report } from "@/lib/api";

// The mockup's dark "AI weekly report" card (Raindeer Social.dc.html,
// isAnalytics block) citing Ved by name. Renders a summary excerpt of the
// REAL latest weekly Report row for the selected brand — same data
// apps/web/app/reports/page.tsx already fetches in full via fetchReports
// (this component takes the already-fetched list/report as a prop rather
// than fetching itself, so the page owns one fetch instead of two) —
// linking there for the complete report rather than duplicating its
// rendering.
function excerpt(text: string, maxLength = 220): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxLength) return trimmed;
  return `${trimmed.slice(0, maxLength).trimEnd()}…`;
}

function formatPeriod(report: Pick<Report, "period_start" | "period_end">): string {
  const fmt = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `${fmt(report.period_start)} – ${fmt(report.period_end)}`;
}

export function WeeklyReportCard({
  report,
  isLoading,
  error,
}: {
  report: Report | null;
  isLoading: boolean;
  error: string | null;
}) {
  return (
    <div className="flex h-full flex-col rounded-2xl bg-gradient-to-br from-ink-950 to-brand-900 p-[18px] text-white">
      <div className="mb-2 text-[10.5px] font-extrabold tracking-[.12em] text-brand-200">
        WEEKLY REPORT · AI
      </div>

      {error ? (
        <p className="text-[13.5px] leading-relaxed text-brand-100">{error}</p>
      ) : isLoading ? (
        <div className="space-y-2">
          <div className="h-3 w-full animate-pulse rounded bg-white/10" />
          <div className="h-3 w-5/6 animate-pulse rounded bg-white/10" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-white/10" />
        </div>
      ) : report ? (
        <>
          <p className="mb-1 text-[11px] font-semibold text-brand-200">{formatPeriod(report)}</p>
          <p className="mb-3 flex-1 text-[13.5px] leading-relaxed text-brand-50">
            {excerpt(report.summary)}
          </p>
          <p className="mb-3 text-[13.5px] leading-relaxed text-brand-50">
            Ved is already folding this into next fortnight&apos;s research and timing signal.
          </p>
          <Link
            href="/reports"
            className="mt-auto inline-flex w-fit items-center gap-1 text-[12.5px] font-semibold text-white underline decoration-brand-300 underline-offset-2 hover:decoration-white"
          >
            Read the full report →
          </Link>
        </>
      ) : (
        <>
          <p className="mb-3 flex-1 text-[13.5px] leading-relaxed text-brand-50">
            No weekly report yet — reports are generated automatically once a week and this card will
            summarize the latest one for this brand as soon as it&apos;s ready.
          </p>
          <Link
            href="/reports"
            className="mt-auto inline-flex w-fit items-center gap-1 text-[12.5px] font-semibold text-white underline decoration-brand-300 underline-offset-2 hover:decoration-white"
          >
            View reports →
          </Link>
        </>
      )}
    </div>
  );
}

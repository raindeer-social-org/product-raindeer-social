import type { ReactNode } from "react";

// Known keys from packages/agents/onboarding/prompts.py::REQUIRED_REPORT_KEYS
// get a friendlier label; anything else (the LLM's exact JSON shape per key
// can vary, and it may add keys beyond these) falls back to a humanized
// version of its key name so the section still renders sensibly.
const SECTION_LABELS: Record<string, string> = {
  voice_and_tone: "Voice & tone",
  audience: "Audience",
  product_catalog_summary: "Product catalog summary",
  competitive_positioning: "Competitive positioning",
};

function humanizeKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function renderScalar(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function renderValue(value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") {
    return <p className="text-sm text-slate-400">Not available.</p>;
  }

  if (typeof value === "string") {
    return <p className="whitespace-pre-wrap text-sm text-slate-700">{value}</p>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <p className="text-sm text-slate-400">Not available.</p>;
    return (
      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
        {value.map((item, index) => (
          <li key={index}>{renderScalar(item)}</li>
        ))}
      </ul>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <p className="text-sm text-slate-400">Not available.</p>;
    return (
      <dl className="space-y-2">
        {entries.map(([key, entryValue]) => (
          <div key={key}>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              {humanizeKey(key)}
            </dt>
            <dd className="mt-0.5 text-sm text-slate-700">{renderScalar(entryValue)}</dd>
          </div>
        ))}
      </dl>
    );
  }

  return <p className="text-sm text-slate-700">{String(value)}</p>;
}

export function BrandReportView({ report }: { report: Record<string, unknown> }) {
  const entries = Object.entries(report);

  if (entries.length === 0) {
    return <p className="text-sm text-slate-500">The brand report is empty.</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="rounded-lg border border-slate-200 p-4">
          <h4 className="text-sm font-semibold text-slate-900">{SECTION_LABELS[key] ?? humanizeKey(key)}</h4>
          <div className="mt-2">{renderValue(value)}</div>
        </div>
      ))}
    </div>
  );
}

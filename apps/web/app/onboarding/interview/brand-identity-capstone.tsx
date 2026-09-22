"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";

// Section labels mirror packages/agents/onboarding/prompts.py::REQUIRED_REPORT_KEYS
// — a friendlier heading for the four keys Aarav's synthesis always
// produces; any extra key the LLM adds beyond those falls back to a
// humanized version of its own name so the section still renders sensibly.
const SECTION_LABELS: Record<string, string> = {
  voice_and_tone: "Voice & tone",
  audience: "Audience",
  product_catalog_summary: "Product catalog summary",
  competitive_positioning: "Competitive positioning",
};

function humanizeKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

interface BrandIdentityCapstoneProps {
  report: Record<string, unknown>;
  isSaving: boolean;
  onContinue: (edited: Record<string, unknown>) => void;
}

// The one editable capstone screen the interview reaches after Aarav's
// research + synthesis chain (apps/api/routers/onboarding.py::run_agent)
// produces a brand_report — previously this was written straight onto
// Brand.brand_report and never shown to the user before the "connect
// socials" step. String sections (every REQUIRED_REPORT_KEYS section, plus
// any string-valued section the LLM added beyond those) are editable
// inline; anything non-string (the LLM occasionally adds a nested object/
// array beyond the required keys) renders read-only rather than building a
// generic JSON editor for a case that's rare and not the point of this
// screen.
export function BrandIdentityCapstone({ report, isSaving, onContinue }: BrandIdentityCapstoneProps) {
  const [draft, setDraft] = useState<Record<string, unknown>>(report);

  const entries = Object.entries(draft);

  return (
    <div className="space-y-4 rounded-[18px] border border-line-soft bg-white p-6 shadow-modal">
      {entries.length === 0 ? (
        <p className="text-sm text-ink-400">
          Aarav couldn&apos;t put together a brand report yet — you can still continue and fill this in later
          from Brand Data.
        </p>
      ) : (
        entries.map(([key, value]) => (
          <div key={key}>
            <label htmlFor={`capstone-${key}`} className="text-xs font-semibold uppercase tracking-wide text-ink-400">
              {SECTION_LABELS[key] ?? humanizeKey(key)}
            </label>
            {typeof value === "string" ? (
              <textarea
                id={`capstone-${key}`}
                value={value}
                onChange={(e) => setDraft((current) => ({ ...current, [key]: e.target.value }))}
                rows={3}
                className="mt-1.5 w-full resize-none rounded-[13px] border border-line bg-white p-3.5 text-sm leading-relaxed outline-none focus:border-brand-500"
              />
            ) : (
              <p className="mt-1.5 whitespace-pre-wrap rounded-[13px] bg-canvas p-3.5 text-sm text-ink-700">
                {JSON.stringify(value)}
              </p>
            )}
          </div>
        ))
      )}

      <div className="flex justify-end border-t border-line-faint pt-[18px]">
        <Button onClick={() => onContinue(draft)} isLoading={isSaving}>
          Looks good — continue
        </Button>
      </div>
    </div>
  );
}

"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { AaravCompanion, type AaravMood } from "./aarav-companion";

// The interview's shell — one centered column on a soft gradient-mesh
// background, Aarav's live companion sitting front and center right above
// the step content, inside a glassmorphic card. Replaced an earlier
// two-pane split (robot pinned to a solid dark left rail) after direct
// feedback that the split read as dated ("look like 90's") — a single
// centered composition with translucency/blur/glow is the more modern
// pattern (Linear/Raycast/Vercel-style onboarding), and keeping the mascot
// directly above the question it's "asking" reads as more integrated than
// off in its own pane.
export function InterviewShell({
  mood,
  caption,
  stepLabel,
  children,
}: {
  mood: AaravMood;
  caption?: string | null;
  stepLabel: string;
  children: ReactNode;
}) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[#F4F6FE] px-6 py-12">
      {/* gradient-mesh ambient background */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-[10%] -top-[15%] h-[520px] w-[520px] rounded-full opacity-60 blur-[110px]"
        style={{ background: "radial-gradient(circle, rgba(107,50,201,.35), transparent 65%)" }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-[12%] top-[10%] h-[560px] w-[560px] rounded-full opacity-50 blur-[120px]"
        style={{ background: "radial-gradient(circle, rgba(27,77,255,.4), transparent 65%)" }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute bottom-[-18%] left-1/2 h-[520px] w-[720px] -translate-x-1/2 rounded-full opacity-40 blur-[130px]"
        style={{ background: "radial-gradient(circle, rgba(143,196,255,.45), transparent 65%)" }}
      />

      <div className="relative mx-auto flex max-w-[600px] flex-col items-center">
        <div className="mb-1 flex items-center gap-2.5">
          <div className="flex h-[30px] w-[30px] items-center justify-center rounded-[9px] bg-gradient-to-br from-brand-600 to-brand-300 text-sm font-extrabold text-white shadow-glow">
            R
          </div>
          <span className="text-[15px] font-bold tracking-tight text-ink-950">
            raindeer<span className="text-brand-600">.</span>
          </span>
        </div>

        <span className="mt-7 rounded-full border border-white/70 bg-white/60 px-3.5 py-1.5 text-[10.5px] font-bold uppercase tracking-[.14em] text-brand-700 shadow-sm backdrop-blur-md">
          {stepLabel}
        </span>

        <div className="mt-2">
          <AaravCompanion mood={mood} caption={caption} size="md" dark={false} />
        </div>

        <motion.div
          key={stepLabel}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="mt-2 w-full rounded-[28px] border border-white/60 bg-white/75 p-7 shadow-[0_30px_80px_-32px_rgba(27,77,255,.35)] backdrop-blur-2xl sm:p-8"
        >
          {children}
        </motion.div>
      </div>
    </div>
  );
}

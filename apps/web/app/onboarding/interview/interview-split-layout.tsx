"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { AaravCompanion, type AaravMood } from "./aarav-companion";

// The interview's two-pane shell — Aarav's live, reactive companion on the
// left (see aarav-companion.tsx), the actual step content on the right.
// Replaces the old full-bleed centered-card layout: the interview used to
// be the one step in the signup->brand->interview funnel that didn't get
// the split treatment (see signup/auth-split-layout.tsx's docstring) — this
// gives it one, built around a mascot that reacts to what Aarav is actually
// doing (scraping, thinking, listening) instead of a static agent roster.
export function InterviewSplitLayout({
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
    <div className="grid min-h-screen grid-cols-1 bg-canvas lg:grid-cols-[440px_minmax(0,1fr)]">
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-[#0A1633] via-[#12224F] to-[#1B2E6B] lg:flex lg:flex-col">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-24 -top-24 h-[420px] w-[420px] rounded-full opacity-40 blur-[80px]"
          style={{ background: "radial-gradient(circle, rgba(107,50,201,.6), transparent 65%)" }}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-32 -right-16 h-[420px] w-[420px] rounded-full opacity-40 blur-[90px]"
          style={{ background: "radial-gradient(circle, rgba(27,77,255,.55), transparent 65%)" }}
        />

        <div className="relative flex items-center gap-2.5 px-9 pt-8">
          <div className="flex h-[30px] w-[30px] items-center justify-center rounded-[9px] bg-gradient-to-br from-brand-600 to-brand-300 text-sm font-extrabold text-white">
            R
          </div>
          <span className="text-[15px] font-bold tracking-tight text-white">
            raindeer<span className="text-brand-300">.</span>
          </span>
        </div>

        <div className="relative flex flex-1 flex-col items-center justify-center px-9">
          <AaravCompanion mood={mood} caption={caption} size="lg" />
        </div>

        <p className="relative px-9 pb-8 text-[11.5px] font-semibold uppercase tracking-[.14em] text-white/40">
          {stepLabel}
        </p>
      </div>

      <div className="flex min-w-0 flex-col overflow-auto px-6 py-9 sm:px-11">
        <motion.div
          key={stepLabel}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className="mx-auto flex w-full max-w-[640px] flex-1 flex-col justify-center py-4"
        >
          {children}
        </motion.div>
      </div>
    </div>
  );
}

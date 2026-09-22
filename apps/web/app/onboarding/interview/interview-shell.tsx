"use client";

import type { ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AaravCompanion, type AaravMood } from "./aarav-companion";

// A real fact Aarav has collected, not a decorative placeholder — every tag
// rendered here traces back to something the brand actually answered (see
// page.tsx's addMemoryTag). Shows only the last few so it never turns into
// a wall of text; it's meant to read as "Aarav is building a profile as we
// talk", not as an audit log.
const MAX_VISIBLE_MEMORY_TAGS = 6;

function BrandMemoryTags({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null;
  const visible = tags.slice(-MAX_VISIBLE_MEMORY_TAGS);
  const hiddenCount = tags.length - visible.length;

  return (
    <div className="mt-5 flex w-full max-w-[280px] flex-col items-center gap-2 lg:mt-7">
      <span className="text-[10px] font-bold uppercase tracking-[.14em] text-ink-300">Aarav is learning</span>
      <div className="flex flex-wrap items-center justify-center gap-1.5">
        {hiddenCount > 0 ? (
          <span className="rounded-full border border-line-soft bg-white/70 px-2.5 py-1 text-[11px] font-semibold text-ink-300">
            +{hiddenCount} more
          </span>
        ) : null}
        <AnimatePresence initial={false}>
          {visible.map((tag) => (
            <motion.span
              key={tag}
              layout
              initial={{ opacity: 0, y: 8, scale: 0.85 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.85 }}
              transition={{ type: "spring", stiffness: 420, damping: 28 }}
              className="rounded-full border border-white/80 bg-white/80 px-2.5 py-1 text-[11px] font-semibold text-ink-600 shadow-sm backdrop-blur-sm"
            >
              {tag}
            </motion.span>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

// The interview's shell — a true half/half split on large screens (direct
// feedback: a fixed 400px side strip read as "tiny" on a real monitor —
// Aarav's half must carry equal visual weight to the question half, not
// play second fiddle to it), question content scrolling independently on
// one side, Aarav's companion centered and fixed on the other so it's
// always in view. Below the `lg` breakpoint this used to just `hidden` the
// entire companion panel — a real bug, not a deliberate mobile design: on
// any narrower window (a non-maximized laptop browser, a real phone) the
// whole mascot/gradient/Brand-Memory experience silently vanished and what
// was left was indistinguishable from the plain form this redesign
// replaced. Recomposed instead of hidden: a compact companion bar sits
// above the content and the whole page scrolls normally, matching how a
// real mobile onboarding flow should behave.
export function InterviewShell({
  mood,
  caption,
  stepLabel,
  memoryTags = [],
  children,
}: {
  mood: AaravMood;
  caption?: string | null;
  stepLabel: string;
  /** Real collected facts, rendered as small floating tags beside Aarav —
   * see BrandMemoryTags above. Optional: stages with nothing collected yet
   * simply render none. */
  memoryTags?: string[];
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-[#F4F6FE] lg:grid lg:h-screen lg:grid-cols-2 lg:overflow-hidden">
      {/* companion panel — a compact bar above the content below `lg`,
      a fixed no-scroll side column at `lg` and up */}
      <div className="relative order-first flex shrink-0 flex-col items-center justify-center overflow-hidden bg-gradient-to-br from-[#EEF2FF] via-[#F3EEFF] to-[#E9F3FF] px-6 py-7 lg:order-last lg:h-full lg:py-0">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-24 -top-24 h-[380px] w-[380px] rounded-full opacity-60 blur-[90px]"
          style={{ background: "radial-gradient(circle, rgba(107,50,201,.3), transparent 65%)" }}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 -left-16 h-[380px] w-[380px] rounded-full opacity-50 blur-[90px]"
          style={{ background: "radial-gradient(circle, rgba(27,77,255,.32), transparent 65%)" }}
        />
        <div className="relative flex flex-col items-center">
          <div className="scale-[0.82] lg:scale-100">
            <AaravCompanion mood={mood} caption={caption} size="lg" dark={false} />
          </div>
          <BrandMemoryTags tags={memoryTags} />
        </div>
      </div>

      {/* content — scrolls with the page below `lg`, scrolls independently
      in its own panel at `lg` and up */}
      <div className="flex min-w-0 flex-1 flex-col px-6 py-9 sm:px-11 lg:overflow-y-auto">
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex h-[30px] w-[30px] items-center justify-center rounded-[9px] bg-gradient-to-br from-brand-600 to-brand-300 text-sm font-extrabold text-white shadow-glow">
            R
          </div>
          <span className="text-[15px] font-bold tracking-tight text-ink-950">
            raindeer<span className="text-brand-600">.</span>
          </span>
        </div>

        <motion.div
          key={stepLabel}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className="mx-auto flex w-full max-w-[600px] flex-1 flex-col justify-center py-4"
        >
          <span className="mb-4 inline-flex w-fit rounded-full border border-line-soft bg-white px-3.5 py-1.5 text-[10.5px] font-bold uppercase tracking-[.14em] text-brand-700 shadow-sm">
            {stepLabel}
          </span>
          {children}
        </motion.div>
      </div>
    </div>
  );
}

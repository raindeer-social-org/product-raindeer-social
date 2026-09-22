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
    <div className="mt-7 flex w-full max-w-[280px] flex-col items-center gap-2">
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

// The interview's shell — follows the user's own wireframe
// (Images/aarav UI.png) exactly: the outer page itself never scrolls
// ("No Scroll" on the whole screen); the question content on the left
// scrolls independently in its own panel ("scrollable"); Aarav's live
// companion sits fixed in a panel on the right ("no-scroll" on the robot
// side) so it's always in view and never moves off-screen while a long
// page of questions scrolls past.
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
    <div className="grid h-screen grid-cols-1 overflow-hidden bg-[#F4F6FE] lg:grid-cols-[minmax(0,1fr)_400px]">
      {/* left: scrollable question content */}
      <div className="flex min-w-0 flex-col overflow-y-auto px-6 py-9 sm:px-11">
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

      {/* right: fixed, no-scroll companion panel — always in view */}
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-[#EEF2FF] via-[#F3EEFF] to-[#E9F3FF] lg:flex lg:flex-col lg:items-center lg:justify-center">
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
          <AaravCompanion mood={mood} caption={caption} size="lg" dark={false} />
          <BrandMemoryTags tags={memoryTags} />
        </div>
      </div>
    </div>
  );
}

"use client";

// A small, cute, always-alive stand-in for Aarav himself — the visual
// centerpiece of the interview's left rail (see interview-split-layout.tsx).
// Built entirely from CSS/SVG + Framer Motion (no 3D engine/model — this repo
// has no Three.js dependency and one isn't worth adding for a single
// mascot); depth comes from layered gradients, a soft ground shadow that
// breathes with the float animation, and a blurred ambient glow behind it,
// which reads as "alive and dimensional" without the weight of a real 3D
// renderer. `mood` is driven by whatever Aarav is actually doing on screen
// right now (scraping, waiting on the LLM, listening to a voice answer,
// done) — see page.tsx's companionMood — not just decorative idle motion.

import { motion, AnimatePresence, useReducedMotion } from "framer-motion";

export type AaravMood = "idle" | "reading" | "thinking" | "listening" | "happy";

const DEFAULT_CAPTION: Record<AaravMood, string> = {
  idle: "Ready when you are.",
  reading: "Reading your site…",
  thinking: "Thinking of what to ask next…",
  listening: "Listening…",
  happy: "Nice — got it.",
};

function Eye({ mood }: { mood: AaravMood }) {
  const prefersReducedMotion = useReducedMotion();

  if (mood === "happy") {
    return (
      <svg width="15" height="11" viewBox="0 0 15 11" fill="none" aria-hidden="true">
        <path d="M1 9C3.2 2 11.8 2 14 9" stroke="#BFE0FF" strokeWidth="2.6" strokeLinecap="round" />
      </svg>
    );
  }

  if (prefersReducedMotion) {
    return <span className="block h-[13px] w-[13px] rounded-full bg-gradient-to-b from-[#D6E7FF] to-[#8FC4FF]" />;
  }

  const animate =
    mood === "reading"
      ? { x: [-3, 3, -3] }
      : mood === "thinking"
        ? { y: [0, -2, -2, 0], scaleY: [1, 1, 0.15, 1] }
        : mood === "listening"
          ? { scale: [1, 1.28, 1] }
          : { scaleY: [1, 1, 1, 0.12, 1] }; // idle: occasional blink

  const transition =
    mood === "reading"
      ? { duration: 1.7, repeat: Infinity, ease: "easeInOut" as const }
      : mood === "thinking"
        ? { duration: 2.2, repeat: Infinity, times: [0, 0.45, 0.55, 1] }
        : mood === "listening"
          ? { duration: 0.85, repeat: Infinity, ease: "easeInOut" as const }
          : { duration: 3.8, repeat: Infinity, times: [0, 0.9, 0.94, 0.97, 1] };

  return (
    <motion.span
      className="block h-[13px] w-[13px] rounded-full bg-gradient-to-b from-[#D6E7FF] to-[#8FC4FF]"
      animate={animate}
      transition={transition}
    />
  );
}

export function AaravCompanion({
  mood,
  caption,
  size = "lg",
}: {
  mood: AaravMood;
  /** Overrides the mood's default caption — e.g. the live scrape-log line. */
  caption?: string | null;
  size?: "md" | "lg";
}) {
  const prefersReducedMotion = useReducedMotion();
  const dim = size === "lg" ? 208 : 152;
  const shownCaption = caption ?? DEFAULT_CAPTION[mood];

  return (
    <div className="relative flex flex-col items-center justify-center">
      <div className="relative flex items-center justify-center" style={{ width: dim * 1.5, height: dim * 1.35 }}>
        {/* ambient glow */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 rounded-full opacity-80 blur-3xl"
          style={{ background: "radial-gradient(circle at 50% 42%, rgba(143,196,255,.5), transparent 65%)" }}
        />

        {/* thought particles, only while thinking */}
        {mood === "thinking" && !prefersReducedMotion ? (
          <div aria-hidden="true" className="pointer-events-none absolute inset-0">
            {[0, 1, 2].map((i) => {
              const angle = (i * 120 * Math.PI) / 180;
              const radius = dim * 0.56;
              return (
                <motion.span
                  key={i}
                  className="absolute left-1/2 top-1/2 h-[7px] w-[7px] rounded-full bg-gradient-to-br from-[#BFE0FF] to-brand-600"
                  animate={{
                    x: [0, Math.cos(angle) * radius, 0],
                    y: [0, Math.sin(angle) * radius, 0],
                    opacity: [0.15, 1, 0.15],
                  }}
                  transition={{ duration: 2.3, repeat: Infinity, delay: i * 0.3, ease: "easeInOut" }}
                />
              );
            })}
          </div>
        ) : null}

        {/* listening pulse ring */}
        {mood === "listening" && !prefersReducedMotion ? (
          <motion.div
            aria-hidden="true"
            className="pointer-events-none absolute rounded-full border-2 border-[#8FC4FF]"
            style={{ width: dim * 0.92, height: dim * 0.92 }}
            animate={{ scale: [1, 1.35, 1], opacity: [0.55, 0, 0.55] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
          />
        ) : null}

        {/* ground shadow */}
        <motion.div
          aria-hidden="true"
          className="absolute bottom-2 rounded-full bg-ink-950/15 blur-[6px]"
          style={{ width: dim * 0.5, height: dim * 0.09 }}
          animate={prefersReducedMotion ? {} : { scaleX: [1, 0.82, 1], opacity: [0.35, 0.2, 0.35] }}
          transition={{ duration: mood === "happy" ? 0.9 : 3.2, repeat: Infinity, ease: "easeInOut" }}
        />

        {/* body */}
        <motion.div
          className="relative"
          style={{ width: dim, height: dim }}
          animate={
            prefersReducedMotion
              ? {}
              : mood === "happy"
                ? { y: [0, -20, 0], rotate: [0, -4, 4, 0] }
                : mood === "listening"
                  ? { y: [0, -6, 0] }
                  : { y: [0, -10, 0], rotate: [-1.5, 1.5, -1.5] }
          }
          transition={{
            duration: mood === "happy" ? 0.85 : mood === "listening" ? 1.1 : 3.4,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        >
          {/* antenna */}
          <div className="absolute left-1/2 top-0 flex -translate-x-1/2 -translate-y-[78%] flex-col items-center">
            <motion.span
              aria-hidden="true"
              className="h-[11px] w-[11px] rounded-full bg-gradient-to-br from-[#BFE0FF] to-brand-600 shadow-[0_0_16px_4px_rgba(27,77,255,.55)]"
              animate={
                prefersReducedMotion
                  ? {}
                  : mood === "thinking"
                    ? { opacity: [0.55, 1, 0.55], scale: [1, 1.35, 1] }
                    : { opacity: [0.8, 1, 0.8], scale: [1, 1.08, 1] }
              }
              transition={{ duration: mood === "thinking" ? 0.75 : 2.4, repeat: Infinity, ease: "easeInOut" }}
            />
            <span aria-hidden="true" className="h-5 w-[3px] bg-gradient-to-b from-brand-300 to-transparent" />
          </div>

          {/* head/body */}
          <div className="h-full w-full rounded-[34%] border border-white/70 bg-gradient-to-br from-[#EAF1FF] via-white to-[#DCE7FF] shadow-[0_24px_46px_-20px_rgba(27,77,255,.5)]">
            <div className="absolute inset-[9%] rounded-[30%] bg-gradient-to-br from-brand-600 via-[#6B32C9] to-[#8FC4FF]" />
            <div className="absolute inset-[19%] flex items-center justify-center overflow-hidden rounded-[38%] bg-[#0A1633]">
              <div className="flex items-center gap-[22%]">
                <Eye mood={mood} />
                <Eye mood={mood} />
              </div>
              {mood === "reading" && !prefersReducedMotion ? (
                <motion.div
                  aria-hidden="true"
                  className="absolute inset-x-[8%] h-[2.5px] rounded-full bg-gradient-to-r from-transparent via-[#8FC4FF] to-transparent"
                  animate={{ top: ["18%", "78%", "18%"] }}
                  transition={{ duration: 1.9, repeat: Infinity, ease: "easeInOut" }}
                />
              ) : null}
            </div>
          </div>
        </motion.div>
      </div>

      <AnimatePresence mode="wait">
        <motion.p
          key={shownCaption}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="max-w-[240px] text-center text-[13px] font-medium leading-snug text-white/90"
        >
          {shownCaption}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}

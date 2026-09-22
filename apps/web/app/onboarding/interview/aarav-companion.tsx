"use client";

// A small, cute, always-alive stand-in for Aarav himself — the visual
// centerpiece of the interview shell (see interview-shell.tsx). Shape and
// behavior follow the user's own wireframe (Images/aarav UI.png): a rounded
// head/body with two antennas, three oval feet, and 4 explicit requirements
// — "moving", "thinking", "revolving head", "cute very cute". Built
// entirely from CSS/SVG + Framer Motion (no 3D engine/model — this repo has
// no Three.js dependency and one isn't worth adding for a single mascot);
// the "revolving head" is a real 3D CSS rotateY on the head only (kept to a
// swivel range that never crosses 90°, so the flat face never shows its
// mirrored backface), not just a decorative flourish. `mood` is driven by
// whatever Aarav is actually doing on screen right now (scraping, waiting
// on the LLM, listening to a voice answer, done) — see page.tsx.

import { motion, AnimatePresence, useReducedMotion } from "framer-motion";

// A real, small state machine — not a grab-bag of animation flags. Every
// value here maps to one distinct thing Aarav is actually doing (see
// page.tsx's mood computation for each stage): CURIOUS/reading while
// scraping a site, THINKING while an LLM call is in flight, LISTENING while
// a voice answer records, CONFUSED (error) when something just failed,
// SUCCESS (happy) when a step completes, GOODBYE on the very last "enter
// the app" moment. idle is the resting state between all of those.
export type AaravMood = "idle" | "reading" | "thinking" | "listening" | "happy" | "error" | "goodbye";

const DEFAULT_CAPTION: Record<AaravMood, string> = {
  idle: "Ready when you are.",
  reading: "Reading your site…",
  thinking: "Thinking of what to ask next…",
  listening: "Listening…",
  happy: "Nice — got it.",
  error: "Hmm, that didn't work — try again?",
  goodbye: "See you inside!",
};

function Eye({ mood }: { mood: AaravMood }) {
  const prefersReducedMotion = useReducedMotion();

  if (mood === "happy" || mood === "goodbye") {
    return (
      <svg width="16" height="12" viewBox="0 0 16 12" fill="none" aria-hidden="true">
        <path d="M1 10C3.4 2 12.6 2 15 10" stroke="#BFE0FF" strokeWidth="2.8" strokeLinecap="round" />
      </svg>
    );
  }

  if (mood === "error") {
    // A small worried tilt rather than a harsh "X" — apologetic, not alarming.
    return (
      <motion.svg
        width="16"
        height="10"
        viewBox="0 0 16 10"
        fill="none"
        aria-hidden="true"
        animate={prefersReducedMotion ? {} : { x: [-1.5, 1.5, -1.5] }}
        transition={{ duration: 0.5, repeat: Infinity, ease: "easeInOut" }}
      >
        <path d="M1 3C3.4 1 5.6 1 8 3" stroke="#BFE0FF" strokeWidth="2.4" strokeLinecap="round" />
        <path d="M8 3C10.4 1 12.6 1 15 3" stroke="#BFE0FF" strokeWidth="2.4" strokeLinecap="round" />
      </motion.svg>
    );
  }

  if (prefersReducedMotion) {
    return <span className="block h-4 w-4 rounded-full bg-gradient-to-b from-[#E4EFFF] to-[#8FC4FF]" />;
  }

  const animate =
    mood === "reading"
      ? { x: [-3, 3, -3] }
      : mood === "thinking"
        ? { y: [0, -2, -2, 0], scaleY: [1, 1, 0.15, 1] }
        : mood === "listening"
          ? { scale: [1, 1.3, 1] }
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
      className="block h-4 w-4 rounded-full bg-gradient-to-b from-[#E4EFFF] to-[#8FC4FF] shadow-[0_0_6px_rgba(143,196,255,.8)]"
      animate={animate}
      transition={transition}
    />
  );
}

function Antenna({ side, mood }: { side: "left" | "right"; mood: AaravMood }) {
  const prefersReducedMotion = useReducedMotion();
  return (
    <div
      aria-hidden="true"
      className={
        "absolute top-0 flex -translate-y-[72%] flex-col items-center " +
        (side === "left" ? "left-[22%] -rotate-[18deg]" : "right-[22%] rotate-[18deg]")
      }
    >
      <motion.span
        className="h-[9px] w-[9px] rounded-full bg-gradient-to-br from-[#BFE0FF] to-brand-600 shadow-[0_0_14px_3px_rgba(27,77,255,.55)]"
        animate={
          prefersReducedMotion
            ? {}
            : mood === "thinking"
              ? { opacity: [0.55, 1, 0.55], scale: [1, 1.3, 1] }
              : { opacity: [0.8, 1, 0.8], scale: [1, 1.06, 1] }
        }
        transition={{ duration: mood === "thinking" ? 0.75 : 2.4, repeat: Infinity, ease: "easeInOut" }}
      />
      <span className="h-4 w-[2.5px] bg-gradient-to-b from-brand-300 to-transparent" />
    </div>
  );
}

export function AaravCompanion({
  mood,
  caption,
  size = "lg",
  dark = true,
}: {
  mood: AaravMood;
  /** Overrides the mood's default caption — e.g. the live scrape-log line. */
  caption?: string | null;
  size?: "md" | "lg";
  /** Whether this sits on a dark panel (white caption text) or a light
   * glass card (ink-toned caption text). */
  dark?: boolean;
}) {
  const prefersReducedMotion = useReducedMotion();
  const dim = size === "lg" ? 200 : 160;
  const shownCaption = caption ?? DEFAULT_CAPTION[mood];

  // "Revolving Head" (from the wireframe) — a real rotateY swivel, kept
  // inside ±34deg so the flat face never turns edge-on/reveals its mirrored
  // backface. Idle gets the widest, slowest "looking around" swivel since
  // nothing else is competing for attention; thinking/listening/reading
  // keep a smaller swivel so their own signal (particles/pulse/scan) reads
  // clearly.
  const headSwivel =
    mood === "idle"
      ? { rotateY: [0, 30, 0, -30, 0] }
      : mood === "happy" || mood === "goodbye"
        ? { rotateY: [0, 16, -16, 0] }
        : mood === "error"
          ? { rotateY: [0, -10, 10, -10, 0] } // a small "no, that's not right" shake
          : { rotateY: [0, 14, 0, -14, 0] };
  const headSwivelDuration =
    mood === "idle" ? 6.5 : mood === "happy" || mood === "goodbye" ? 0.9 : mood === "error" ? 0.5 : mood === "thinking" ? 3.2 : 4.5;

  return (
    <div className="relative flex flex-col items-center justify-center">
      <div className="relative flex items-center justify-center" style={{ width: dim * 1.5, height: dim * 1.3 }}>
        {/* ambient glow — warms to amber on error, a gentle "oops" rather
        than an alarming red */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 rounded-full opacity-80 blur-3xl"
          style={{
            background:
              mood === "error"
                ? "radial-gradient(circle at 50% 42%, rgba(255,196,107,.45), transparent 65%)"
                : "radial-gradient(circle at 50% 42%, rgba(143,196,255,.5), transparent 65%)",
          }}
        />

        {/* slow-rotating conic halo ring — a "sci-fi tech" flourish that
        reads as modern rather than a flat static icon */}
        {!prefersReducedMotion ? (
          <motion.div
            aria-hidden="true"
            className="pointer-events-none absolute rounded-full opacity-[0.35]"
            style={{
              width: dim * 1.22,
              height: dim * 1.22,
              background:
                "conic-gradient(from 0deg, transparent 0%, #8FC4FF 15%, transparent 30%, transparent 60%, #6B32C9 75%, transparent 92%)",
              maskImage: "radial-gradient(closest-side, transparent 74%, black 76%, black 85%, transparent 87%)",
              WebkitMaskImage:
                "radial-gradient(closest-side, transparent 74%, black 76%, black 85%, transparent 87%)",
            }}
            animate={{ rotate: 360 }}
            transition={{ duration: mood === "thinking" ? 5 : 14, repeat: Infinity, ease: "linear" }}
          />
        ) : null}

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
          className="absolute bottom-4 rounded-full bg-ink-950/15 blur-[6px]"
          style={{ width: dim * 0.46, height: dim * 0.08 }}
          animate={prefersReducedMotion ? {} : { scaleX: [1, 0.82, 1], opacity: [0.35, 0.2, 0.35] }}
          transition={{
            duration: mood === "happy" || mood === "goodbye" ? 0.9 : mood === "error" ? 0.5 : 3.2,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />

        {/* whole body — float/bob ("moving") */}
        <motion.div
          className="relative"
          style={{ width: dim, height: dim * 0.92 }}
          animate={
            prefersReducedMotion
              ? {}
              : mood === "happy"
                ? { y: [0, -18, 0], rotate: [0, -3, 3, 0] }
                : mood === "goodbye"
                  ? { y: [0, -14, 0], rotate: [0, 8, -4, 0] } // a little wave/bow
                  : mood === "error"
                    ? { y: [0, 3, 0], rotate: [0, -2, 2, 0] } // a small apologetic droop
                    : mood === "listening"
                      ? { y: [0, -6, 0] }
                      : { y: [0, -9, 0] }
          }
          transition={{
            duration:
              mood === "happy" || mood === "goodbye" ? 0.85 : mood === "error" ? 0.5 : mood === "listening" ? 1.1 : 3.2,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        >
          {/* three oval feet — planted, don't turn with the head */}
          <div className="absolute bottom-0 left-1/2 flex -translate-x-1/2 items-end gap-[8%]">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="rounded-[50%] bg-gradient-to-b from-brand-300 to-brand-600 opacity-90"
                style={{ width: dim * 0.15, height: dim * (i === 1 ? 0.22 : 0.18) }}
                animate={prefersReducedMotion ? {} : { scaleY: [1, 0.94, 1] }}
                transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut", delay: i * 0.15 }}
              />
            ))}
          </div>

          {/* head — "Revolving Head": real rotateY swivel, preserve-3d */}
          <motion.div
            className="absolute inset-x-0 top-0"
            style={{ height: dim * 0.72, perspective: 700 }}
          >
            <motion.div
              className="relative h-full w-full"
              style={{ transformStyle: "preserve-3d" }}
              animate={prefersReducedMotion ? {} : headSwivel}
              transition={{ duration: headSwivelDuration, repeat: Infinity, ease: "easeInOut" }}
            >
              <Antenna side="left" mood={mood} />
              <Antenna side="right" mood={mood} />

              <div className="h-full w-full rounded-[38%] border border-white/70 bg-gradient-to-br from-[#EAF1FF] via-white to-[#DCE7FF] shadow-[0_22px_44px_-18px_rgba(27,77,255,.5)]">
                <div className="absolute inset-[8%] overflow-hidden rounded-[32%] bg-gradient-to-br from-brand-600 via-[#6B32C9] to-[#8FC4FF]">
                  {/* glossy highlight — the "premium glass" touch */}
                  <div
                    aria-hidden="true"
                    className="absolute -left-[10%] -top-[18%] h-[65%] w-[65%] rounded-full bg-white opacity-30 blur-2xl"
                  />
                </div>
                <div className="absolute inset-[20%] flex items-center justify-center overflow-hidden rounded-[40%] bg-[#0A1633]">
                  <div className="flex items-center gap-[26%]">
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
          </motion.div>
        </motion.div>
      </div>

      <AnimatePresence mode="wait">
        <motion.p
          key={shownCaption}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className={
            "max-w-[240px] text-center text-[13px] font-medium leading-snug " +
            (dark ? "text-white/90" : "text-ink-500")
          }
        >
          {shownCaption}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}

"use client";

// Shared by page.tsx's fixed questionnaire and dynamic-question-card.tsx's
// AI-generated follow-ups — kept in its own file so neither has to import
// from the other (page.tsx renders DynamicQuestionCard for the AI phase;
// a page.tsx <-> dynamic-question-card.tsx circular import is avoidable
// entirely by factoring this out).

import { motion } from "framer-motion";

export function ChipButton({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      whileHover={{ y: -2, scale: selected ? 1.03 : 1.015 }}
      whileTap={{ scale: 0.94, y: 0 }}
      animate={{ scale: selected ? 1.03 : 1, y: 0 }}
      transition={{ type: "spring", stiffness: 500, damping: 25 }}
      className={
        "inline-flex items-center gap-1.5 rounded-[12px] border-[1.5px] px-4 py-3 text-sm font-semibold transition-colors " +
        (selected
          ? "border-brand-600 bg-brand-600 text-white shadow-[0_2px_10px_-2px_rgba(27,77,255,0.5)]"
          : "border-line bg-white text-ink-700 hover:border-brand-200 hover:bg-brand-50/60 hover:shadow-[0_6px_16px_-8px_rgba(27,77,255,0.35)]")
      }
    >
      {selected && (
        <motion.span
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 600, damping: 20 }}
          className="text-xs"
          aria-hidden="true"
        >
          ✓
        </motion.span>
      )}
      {label}
    </motion.button>
  );
}

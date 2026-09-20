"use client";

// Shared by page.tsx's fixed questionnaire and dynamic-question-card.tsx's
// AI-generated follow-ups — kept in its own file so neither has to import
// from the other (page.tsx renders DynamicQuestionCard for the AI phase;
// a page.tsx <-> dynamic-question-card.tsx circular import is avoidable
// entirely by factoring this out).

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
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={
        "rounded-[11px] border px-[15px] py-[11px] text-[13.5px] font-semibold transition-colors " +
        (selected
          ? "border-brand-600 bg-brand-50 text-brand-700"
          : "border-line bg-white text-ink-700 hover:bg-canvas")
      }
    >
      {label}
    </button>
  );
}

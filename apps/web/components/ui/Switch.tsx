"use client";

import { cn } from "./cn";

// Pill toggle matching the mockup's agent-behaviour switches (Raindeer
// Social.dc.html's `toggles` block: a 40x23 pill with a sliding 17px knob).
// A plain <button role="switch"> rather than <input type="checkbox"> so the
// mockup's exact visual (no native checkbox chrome) is achievable while
// staying keyboard/screen-reader accessible.
export function Switch({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-[23px] w-10 shrink-0 rounded-full transition-colors duration-150",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500",
        checked ? "bg-brand-600" : "bg-ink-100",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <span
        className={cn(
          "absolute top-[3px] h-[17px] w-[17px] rounded-full bg-white shadow-card transition-all duration-150",
          checked ? "left-[20px]" : "left-[3px]",
        )}
      />
    </button>
  );
}

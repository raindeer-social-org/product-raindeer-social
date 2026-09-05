import type { ReactNode } from "react";
import { cn } from "./cn";

export type BadgeTone = "slate" | "brand" | "green" | "amber" | "red" | "blue";

const TONE_CLASSES: Record<BadgeTone, string> = {
  slate: "bg-canvas text-ink-600 ring-line-soft",
  brand: "bg-brand-50 text-brand-700 ring-brand-100",
  green: "bg-success-bg text-success ring-success/20",
  amber: "bg-warning-bg text-warning ring-warning/20",
  red: "bg-danger-bg text-danger ring-danger/20",
  blue: "bg-brand-50 text-brand-700 ring-brand-100",
};

export function Badge({
  tone = "slate",
  dot,
  children,
  className,
}: {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {dot ? <span className={cn("h-1.5 w-1.5 rounded-full", `bg-current`)} /> : null}
      {children}
    </span>
  );
}
